"""Connection CRUD services."""

import os
from pathlib import Path
from typing import Any

import yaml
from db_mcp_data.connectors.templates import get_connector_template
from db_mcp_data.db.connection import detect_dialect_from_url
from db_mcp_knowledge.onboarding.state import create_initial_state, load_state, save_state
from db_mcp_knowledge.vault.paths import connector_path as _connector_path
from db_mcp_models import OnboardingPhase
from dotenv import dotenv_values


def _read_connection_env_values(conn_path: Path) -> dict[str, str]:
    env_file = conn_path / ".env"
    if not env_file.exists():
        return {}

    env_vars = dotenv_values(env_file)
    return {
        str(key): str(value)
        for key, value in env_vars.items()
        if key and value is not None
    }


def _normalize_api_env_entries(raw_entries: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not isinstance(raw_entries, list):
        return entries

    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue

        name = str(raw_entry.get("name", "") or "").strip()
        slot = str(raw_entry.get("slot", "") or "").strip()
        if not name and not slot:
            continue

        resolved_name = name or slot
        entries.append(
            {
                "slot": slot or resolved_name,
                "name": resolved_name,
                "value": str(raw_entry.get("value", "") or "").strip(),
                "prompt": str(raw_entry.get("prompt", "") or "").strip(),
                "secret": bool(raw_entry.get("secret", True)),
                "removed": bool(raw_entry.get("removed", False)),
            }
        )

    return entries


def _build_api_auth_overrides(params: dict[str, Any]) -> dict[str, Any]:
    auth_params = params.get("auth") if isinstance(params.get("auth"), dict) else {}

    def _value(primary_key: str, nested_key: str | None = None) -> str:
        nested = nested_key or primary_key
        raw = params.get(primary_key, "")
        if raw in (None, ""):
            raw = auth_params.get(nested, "")
        return str(raw or "").strip()

    overrides: dict[str, Any] = {}
    auth_type = _value("authType", "type")
    if auth_type:
        overrides["type"] = auth_type

    header_name = _value("headerName")
    if header_name:
        overrides["header_name"] = header_name

    param_name = _value("paramName")
    if param_name:
        overrides["param_name"] = param_name

    token_env = _value("tokenEnv")
    if token_env:
        overrides["token_env"] = token_env

    username_env = _value("usernameEnv")
    if username_env:
        overrides["username_env"] = username_env

    password_env = _value("passwordEnv")
    if password_env:
        overrides["password_env"] = password_env

    return overrides


def _resolve_api_env_values(
    conn_path: Path | None,
    env_entries: list[dict[str, Any]],
) -> dict[str, str]:
    existing_env = _read_connection_env_values(conn_path) if conn_path else {}
    merged_env = dict(existing_env)

    for entry in env_entries:
        name = entry["name"]
        slot = entry["slot"]
        value = entry["value"]
        removed = bool(entry.get("removed", False))

        if removed:
            merged_env.pop(name, None)
            if slot:
                merged_env.pop(slot, None)
            continue

        if slot and slot != name:
            merged_env.pop(slot, None)

        resolved_value = value or existing_env.get(name) or existing_env.get(slot)
        if resolved_value:
            merged_env[name] = resolved_value

    return merged_env


def _write_api_env_file(conn_path: Path, env_entries: list[dict[str, Any]]) -> None:
    merged_env = _resolve_api_env_values(conn_path, env_entries)
    env_file = conn_path / ".env"
    ordered_names: list[str] = []
    for entry in env_entries:
        if entry.get("removed", False):
            continue
        if entry["name"] not in ordered_names:
            ordered_names.append(entry["name"])

    remaining_names = sorted(name for name in merged_env if name not in ordered_names)
    ordered_names.extend(remaining_names)

    with open(env_file, "w") as f:
        f.write("# API connection credentials\n")
        f.write("# This file is gitignored - do not commit\n\n")
        for name in ordered_names:
            value = merged_env.get(name, "")
            if value:
                f.write(f"{name}={value}\n")


def _build_template_env_name_overrides(env_entries: list[dict[str, Any]]) -> dict[str, str]:
    return {
        entry["slot"]: entry["name"]
        for entry in env_entries
        if entry["slot"] and entry["name"]
    }


def update_api_connection(
    name: str,
    params: dict[str, Any],
    *,
    conn_path: Path,
    materialize_connector_template,
) -> dict[str, Any]:
    """Update a persisted API connection."""
    connector_yaml = _connector_path(conn_path)
    with open(connector_yaml) as f:
        cdata = yaml.safe_load(f) or {}

    template_id = str(params.get("templateId", "") or "").strip()
    env_entries = _normalize_api_env_entries(params.get("envVars"))

    if template_id:
        cdata = materialize_connector_template(
            template_id,
            base_url=str(params.get("baseUrl", "") or "").strip() or None,
            env_name_overrides=_build_template_env_name_overrides(env_entries),
            auth_overrides=_build_api_auth_overrides(params),
        )
        if cdata is None:
            return {
                "success": False,
                "error": f"Unknown connector template: {template_id}",
            }
    else:
        cdata.pop("template_id", None)
        if "baseUrl" in params:
            cdata["base_url"] = params["baseUrl"]
        if "auth" in params:
            auth = params["auth"]
            auth_type = auth.get("type", "bearer")
            auth_data: dict[str, Any] = {"type": auth_type}
            if auth_type == "basic":
                auth_data["username_env"] = auth.get("usernameEnv", "")
                auth_data["password_env"] = auth.get("passwordEnv", "")
            elif auth_type != "none":
                auth_data["token_env"] = auth.get("tokenEnv", "")
                auth_data["header_name"] = auth.get("headerName", "Authorization")
                auth_data["param_name"] = auth.get("paramName", "api_key")
            cdata["auth"] = auth_data

    if "endpoints" in params:
        cdata["endpoints"] = [
            {
                "name": ep.get("name", ""),
                "path": ep.get("path", ""),
                "method": ep.get("method", "GET"),
            }
            for ep in params["endpoints"]
        ]
    if "pagination" in params:
        pag = params["pagination"]
        cdata["pagination"] = {
            "type": pag.get("type", "none"),
            "cursor_param": pag.get("cursorParam", ""),
            "cursor_field": pag.get("cursorField", ""),
            "page_size_param": pag.get("pageSizeParam", "limit"),
            "page_size": pag.get("pageSize", 100),
            "data_field": pag.get("dataField", "data"),
        }
    if "rateLimitRps" in params:
        cdata["rate_limit"] = {"requests_per_second": params["rateLimitRps"]}

    if env_entries:
        _write_api_env_file(conn_path, env_entries)
    else:
        api_key = str(params.get("apiKey", "") or "").strip()
        if api_key:
            token_env = str(cdata.get("auth", {}).get("token_env", "")).strip()
            if token_env:
                env_file = conn_path / ".env"
                with open(env_file, "w") as f:
                    f.write(f"{token_env}={api_key}\n")

    with open(connector_yaml, "w") as f:
        yaml.dump(cdata, f, default_flow_style=False)

    return {"success": True, "name": name}


def create_api_connection(
    name: str,
    params: dict[str, Any],
    *,
    conn_path: Path,
    config_file: Path | None = None,
    set_active: bool,
    set_active_connection=None,  # deprecated: ignored, module-level function is used
    materialize_connector_template,
    connector_spec_version: str,
) -> dict[str, Any]:
    """Create and persist an API connection."""
    base_url = str(params.get("baseUrl", "") or "").strip()
    if not base_url:
        return {"success": False, "error": "Base URL is required"}

    auth_type = str(params.get("authType", "bearer") or "bearer")
    token_env = str(params.get("tokenEnv", "") or "").strip()
    api_key = str(params.get("apiKey", "") or "").strip()
    header_name = str(params.get("headerName", "") or "").strip()
    param_name = str(params.get("paramName", "") or "").strip()
    template_id = str(params.get("templateId", "") or "").strip()
    env_entries = _normalize_api_env_entries(params.get("envVars"))

    if template_id:
        connector_data = materialize_connector_template(
            template_id,
            base_url=base_url,
            env_name_overrides=_build_template_env_name_overrides(env_entries),
            auth_overrides=_build_api_auth_overrides(params),
        )
        if connector_data is None:
            return {"success": False, "error": f"Unknown connector template: {template_id}"}

        conn_path.mkdir(parents=True, exist_ok=True)

        connector_yaml = _connector_path(conn_path)
        with open(connector_yaml, "w") as f:
            yaml.dump(connector_data, f, default_flow_style=False, sort_keys=False)

        _write_api_env_file(conn_path, env_entries)
    else:
        if not env_entries and auth_type != "none":
            env_var_name = token_env or "API_KEY"
            env_entries = [
                {
                    "slot": env_var_name,
                    "name": env_var_name,
                    "value": api_key,
                    "prompt": "",
                    "secret": True,
                }
            ]

        auth_data: dict[str, Any] = {"type": auth_type}
        if auth_type != "none":
            auth_data["token_env"] = token_env or "API_KEY"
        if auth_type == "header" and header_name:
            auth_data["header_name"] = header_name
        if auth_type == "query_param" and param_name:
            auth_data["param_name"] = param_name

        connector_data = {
            "spec_version": connector_spec_version,
            "type": "api",
            "profile": "api_openapi",
            "base_url": base_url,
            "auth": auth_data,
            "endpoints": [],
            "pagination": {"type": "none"},
            "rate_limit": {"requests_per_second": 10.0},
        }

        conn_path.mkdir(parents=True, exist_ok=True)
        connector_yaml = _connector_path(conn_path)
        with open(connector_yaml, "w") as f:
            yaml.dump(connector_data, f, default_flow_style=False)

        _write_api_env_file(conn_path, env_entries)

    data_dir = conn_path / "data"
    data_dir.mkdir(exist_ok=True)

    gitignore_file = conn_path / ".gitignore"
    with open(gitignore_file, "w") as f:
        f.write("# Ignore credentials\n")
        f.write(".env\n")
        f.write("# Ignore local state\n")
        f.write("state.yaml\n")
        f.write("# Ignore synced data\n")
        f.write("data/\n")

    if set_active and config_file is not None:
        from db_mcp.services.connection import set_active_connection

        set_active_connection(name, config_file)

    return {
        "success": True,
        "name": name,
        "dialect": "duckdb",
        "isActive": set_active,
    }


def update_sql_connection(name: str, database_url: str, *, conn_path: Path) -> dict[str, Any]:
    """Update the DATABASE_URL for a SQL connection."""
    env_file = conn_path / ".env"
    with open(env_file, "w") as f:
        f.write(f"DATABASE_URL={database_url}\n")

    return {"success": True, "name": name}


def update_file_connection(name: str, directory: str, *, conn_path: Path) -> dict[str, Any]:
    """Update the configured directory for a file connection."""
    connector_yaml = _connector_path(conn_path)
    with open(connector_yaml) as f:
        cdata = yaml.safe_load(f) or {}

    cdata["directory"] = directory
    with open(connector_yaml, "w") as f:
        yaml.dump(cdata, f, default_flow_style=False)

    return {"success": True, "name": name}


def discover_api_connection(
    name: str,
    *,
    connections_dir: Path,
    load_connector_config,
    get_runtime_connector=None,
    api_config_type,
) -> dict[str, Any]:
    """Run API discovery for a saved connection and persist onboarding state."""
    conn_path = connections_dir / name
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    connector_yaml = _connector_path(conn_path)
    if not connector_yaml.exists():
        return {"success": False, "error": "No connector.yaml found"}

    config = load_connector_config(connector_yaml)
    if not isinstance(config, api_config_type):
        return {"success": False, "error": "Connection is not an API connector"}

    if get_runtime_connector is None:
        def get_runtime_connector(path: Path) -> Any:
            from db_mcp_data.connectors import get_connector as load_runtime_connector

            return load_runtime_connector(connection_path=str(path))
    connector = get_runtime_connector(conn_path)
    result = connector.discover()

    if result.get("endpoints_found", 0) > 0:
        connector.save_connector_yaml(connector_yaml)

        state = load_state(connection_path=conn_path) or create_initial_state(name)
        state.provider_id = name
        state.phase = OnboardingPhase.DOMAIN
        state.database_url_configured = True
        state.connection_verified = True
        state.dialect_detected = config.api_title or state.dialect_detected or "api"

        discovered_endpoints = sorted(
            {
                str(endpoint.get("path") or endpoint.get("name") or "").strip()
                for endpoint in result.get("endpoints", [])
                if str(endpoint.get("path") or endpoint.get("name") or "").strip()
            }
        )
        state.tables_discovered = discovered_endpoints
        state.tables_total = len(discovered_endpoints)
        if discovered_endpoints:
            state.current_table = discovered_endpoints[0]

        state_result = save_state(state, connection_path=conn_path)
        if not state_result.get("saved"):
            return {
                "success": False,
                "error": state_result.get("error") or "Failed to save onboarding state",
            }

    return {
        "success": True,
        **result,
    }


def create_sql_connection(
    name: str,
    database_url: str,
    *,
    connections_dir: Path,
    config_file: Path,
    set_active: bool = True,
) -> dict[str, Any]:
    """Create a SQL database connection.

    1. Validates *name* uniqueness.
    2. Calls :func:`test_database_url` — rejects if the connection fails.
    3. Creates ``<connections_dir>/<name>/`` with ``.env`` and ``.gitignore``.
    4. Optionally sets the connection as active.

    Returns ``{"success": bool, "name": str, "dialect": str|None, ...}``.
    """
    from db_mcp.services.connection_test import test_database_url

    conn_path = connections_dir / name
    if conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' already exists"}

    if not database_url:
        return {"success": False, "error": "Database URL is required"}

    test_result = test_database_url(database_url)
    if not test_result["success"]:
        return {
            "success": False,
            "error": f"Connection test failed: {test_result.get('error', 'Unknown error')}",
        }

    dialect = detect_dialect_from_url(database_url)
    conn_path.mkdir(parents=True, exist_ok=True)

    env_file = conn_path / ".env"
    env_file.write_text(
        "# db-mcp connection credentials\n"
        "# This file is gitignored - do not commit\n\n"
        f'DATABASE_URL="{database_url}"\n'
    )

    (conn_path / ".gitignore").write_text(
        "# Ignore credentials\n.env\n# Ignore local state\nstate.yaml\n"
    )

    if set_active:
        from db_mcp.services.connection import set_active_connection

        set_active_connection(name, config_file)

    return {"success": True, "name": name, "dialect": dialect, "isActive": set_active}


def create_file_connection(
    name: str,
    params: dict[str, Any],
    *,
    conn_path: Path,
    config_file: Path,
    set_active: bool = True,
) -> dict[str, Any]:
    """Create a file-type database connection.

    Validates the directory via :func:`test_file_directory`, writes
    ``connector.yaml`` and ``.gitignore``, and optionally sets active.
    """
    from db_mcp_data.contracts.connector_contracts import CONNECTOR_SPEC_VERSION

    from db_mcp.services.connection_test import test_file_directory

    directory = params.get("directory", "").strip()
    if not directory:
        return {"success": False, "error": "Directory path is required"}

    test_result = test_file_directory(directory)
    if not test_result["success"]:
        return {
            "success": False,
            "error": f"Connection test failed: {test_result.get('error', 'Unknown error')}",
        }

    conn_path.mkdir(parents=True, exist_ok=True)

    connector_yaml = _connector_path(conn_path)
    with open(connector_yaml, "w") as f:
        yaml.dump(
            {
                "spec_version": CONNECTOR_SPEC_VERSION,
                "type": "file",
                "profile": "file_local",
                "directory": directory,
            },
            f,
            default_flow_style=False,
        )

    (conn_path / ".gitignore").write_text("# Ignore local state\nstate.yaml\n")

    if set_active:
        from db_mcp.services.connection import set_active_connection

        set_active_connection(name, config_file)

    return {"success": True, "name": name, "dialect": "duckdb", "isActive": set_active}


def delete_connection(
    name: str,
    *,
    connections_dir: Path,
    config_file: Path,
) -> dict[str, Any]:
    """Delete a database connection by name.

    If the connection being deleted is currently active, automatically switches
    to the first remaining connection (or clears the active key).
    Returns ``{"success": bool, "name": str}``.
    """
    import shutil

    conn_path = connections_dir / name
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    active_connection: str | None = None
    config: dict[str, Any] = {}
    if config_file.exists():
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}
        active_connection = config.get("active_connection")

    if name == active_connection:
        others = [
            d.name for d in connections_dir.iterdir() if d.is_dir() and d.name != name
        ]
        if others:
            config["active_connection"] = others[0]
        else:
            config.pop("active_connection", None)
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    shutil.rmtree(conn_path)
    return {"success": True, "name": name}


def sync_api_connection(
    name: str,
    *,
    connections_dir: Path,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Sync data from API endpoints for a named connection.

    Returns ``{"success": bool, "synced": [...], "rows_fetched": {...}, "errors": [...]}``.
    """
    conn_path = connections_dir / name
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    connector_yaml = _connector_path(conn_path)
    if not connector_yaml.exists():
        return {"success": False, "error": "No connector.yaml found"}

    try:
        from db_mcp_data.connectors import ConnectorConfig
        from db_mcp_data.connectors.api import APIConnector, APIConnectorConfig

        config = ConnectorConfig.from_yaml(connector_yaml)
        if not isinstance(config, APIConnectorConfig):
            return {"success": False, "error": "Connection is not an API connector"}

        data_dir = str(conn_path / "data")
        connector = APIConnector(config, data_dir)

        env_file = conn_path / ".env"
        if env_file.exists():
            env_vars = dotenv_values(env_file)
            for k, v in env_vars.items():
                if v is not None:
                    os.environ[k] = v

        result = connector.sync(endpoint_name=endpoint)
        return {"success": True, **result}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def build_api_template_descriptor(template_id: str) -> dict[str, Any] | None:
    """Return a UI-ready descriptor dict for *template_id*, or None if unknown."""
    template = get_connector_template(template_id)
    if template is None:
        return None

    auth = template.connector.get("auth", {}) or {}
    return {
        "id": template.id,
        "title": template.title,
        "description": template.description,
        "baseUrlPrompt": template.base_url_prompt,
        "baseUrl": template.connector.get("base_url", ""),
        "connectorType": template.connector.get("type", "api"),
        "auth": {
            "type": auth.get("type", "bearer"),
            "tokenEnv": auth.get("token_env", ""),
            "headerName": auth.get("header_name", "Authorization"),
            "paramName": auth.get("param_name", "api_key"),
            "usernameEnv": auth.get("username_env", ""),
            "passwordEnv": auth.get("password_env", ""),
        },
        "env": [
            {
                "slot": env_var.name,
                "name": env_var.name,
                "prompt": env_var.prompt,
                "secret": env_var.secret,
                "hasSavedValue": False,
            }
            for env_var in template.env
        ],
    }
