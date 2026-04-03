"""Connection resolution services."""

import os
from pathlib import Path
from typing import Any

import yaml
from db_mcp_data.connector_templates import get_connector_template
from db_mcp_data.connectors import get_connector, get_connector_capabilities
from db_mcp_data.db.connection import detect_dialect_from_url, get_engine
from db_mcp_knowledge.onboarding.state import create_initial_state, load_state, save_state
from db_mcp_knowledge.vault.paths import (
    DESCRIPTIONS_FILE,
    DOMAIN_MODEL_FILE,
)
from db_mcp_knowledge.vault.paths import (
    connector_path as _connector_path,
)
from db_mcp_knowledge.vault.paths import (
    state_path as _state_path,
)
from db_mcp_models import OnboardingPhase
from dotenv import dotenv_values

from db_mcp.config import get_settings
from db_mcp.registry import ConnectionRegistry


def require_connection(connection: str | None, tool_name: str | None = None) -> str:
    """Require an explicit connection name."""
    if connection is None:
        if tool_name:
            raise ValueError(
                f"{tool_name} requires connection=<name>. "
                "Use list_connections to see available connections."
            )
        raise ValueError(
            "connection is required for this tool. "
            "Use list_connections to see available connections."
        )
    return connection


def _resolve_connection_path(connection: str) -> str:
    """Resolve a connection name to its filesystem path."""
    connection = require_connection(connection)
    settings = get_settings()
    base = settings.connections_dir or str(Path.home() / ".db-mcp" / "connections")
    return str(Path(base) / connection)


def resolve_connection(
    connection: str | None,
    *,
    require_type: str | None = None,
    require_capability: str | None = None,
) -> tuple:
    """Resolve a connection parameter to (connector, name, path)."""
    registry = ConnectionRegistry.get_instance()
    connections = registry.discover()

    if connection is not None:
        if connection not in connections:
            available = list(connections.keys())
            if available:
                raise ValueError(
                    f"Connection '{connection}' not found. "
                    f"Available connections: {', '.join(available)}"
                )
            raise ValueError(
                f"Connection '{connection}' not found. No connections are configured."
            )

        info = connections[connection]

        if require_type is not None and info.type != require_type:
            raise ValueError(
                f"Connection '{connection}' is type '{info.type}', "
                f"but '{require_type}' is required."
            )

        connector = registry.get_connector(connection)

        if require_capability is not None:
            caps = get_connector_capabilities(connector)
            if not caps.get(require_capability, False):
                raise ValueError(
                    f"Connection '{connection}' does not support '{require_capability}'."
                )

        return connector, connection, info.path

    if not connections:
        settings = get_settings()
        conn_name = settings.get_effective_provider_id()
        conn_path = settings.get_effective_connection_path()
        connector = get_connector(connection_path=conn_path)

        if require_capability is not None:
            caps = get_connector_capabilities(connector)
            if not caps.get(require_capability, False):
                raise ValueError(f"The active connection does not support '{require_capability}'.")

        if require_type is not None:
            from db_mcp_data.connectors import APIConnector, FileConnector, SQLConnector

            type_map = {
                "sql": SQLConnector,
                "file": FileConnector,
                "api": APIConnector,
            }
            expected_cls = type_map.get(require_type)
            if expected_cls is not None and not isinstance(connector, expected_cls):
                raise ValueError(f"The active connection is not of type '{require_type}'.")

        return connector, conn_name, conn_path

    if require_type is not None:
        candidates = {
            name: info for name, info in connections.items() if info.type == require_type
        }
    else:
        candidates = dict(connections)

    if len(candidates) == 1:
        name = next(iter(candidates))
        info = candidates[name]
        connector = registry.get_connector(name)

        if require_capability is not None:
            caps = get_connector_capabilities(connector)
            if not caps.get(require_capability, False):
                available_names = list(connections.keys())
                raise ValueError(
                    f"Connection '{name}' does not support '{require_capability}'. "
                    f"Available connections: {', '.join(available_names)}"
                )

        return connector, name, info.path

    if len(candidates) == 0:
        available_names = list(connections.keys())
        if require_type:
            msg = f"No connections of type '{require_type}' found."
        else:
            msg = "No connections found."
        if available_names:
            msg += f" Available connections: {', '.join(available_names)}"
        raise ValueError(msg)

    available_names = list(candidates.keys())
    if require_type:
        msg = (
            f"Multiple {require_type} connections available: {', '.join(available_names)}. "
            f"Specify connection=<name> to select one."
        )
    else:
        msg = (
            f"Multiple connections available: {', '.join(available_names)}. "
            f"Specify connection=<name> to select one."
        )
    raise ValueError(msg)


def get_resolved_provider_id(connection: str | None) -> str:
    """Resolve connection param to a provider_id string for store operations."""
    if connection is not None:
        return connection

    settings = get_settings()
    return settings.get_effective_provider_id()


def test_named_connection(name: str, *, connections_dir: Path) -> dict:
    """Test a saved named connection from the connections directory."""
    conn_path = connections_dir / name
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    connector = get_connector(str(conn_path))
    result = connector.test_connection()
    connected = bool(result.get("connected"))
    response = {
        "success": connected,
        "dialect": result.get("dialect"),
    }
    if connected:
        response["message"] = "Connection successful"
    else:
        response["error"] = result.get("error", "Connection failed")
    if result.get("hint"):
        response["hint"] = result["hint"]
    return response


def get_connection_dialect(*, connection_path: Path) -> str:
    """Get the runtime dialect for a resolved connection path."""
    connector = get_connector(connection_path=connection_path)
    return connector.get_dialect()


def list_connections_summary(
    *,
    connections_dir: Path,
    config_file: Path,
    env_connection_name: str | None,
    detect_dialect_from_url,
) -> dict:
    """List configured connections with summary metadata for UI/BICP."""
    active_connection = None
    if config_file.exists():
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}
            active_connection = config.get("active_connection")

    if not active_connection:
        active_connection = env_connection_name or os.environ.get("CONNECTION_NAME") or None

    connections = []
    if connections_dir.exists():
        for conn_path in sorted(connections_dir.iterdir()):
            if not conn_path.is_dir():
                continue

            name = conn_path.name
            has_schema = (conn_path / DESCRIPTIONS_FILE).exists()
            has_domain = (conn_path / DOMAIN_MODEL_FILE).exists()
            has_credentials = (conn_path / ".env").exists()
            has_state = _state_path(conn_path).exists()
            has_discovery = has_schema

            connector_type = "sql"
            api_title = None
            base_url = None
            connector_yaml = _connector_path(conn_path)
            if connector_yaml.exists():
                try:
                    with open(connector_yaml) as f:
                        cdata = yaml.safe_load(f) or {}
                        connector_type = cdata.get("type", "sql")
                        if connector_type == "api":
                            api_title = cdata.get("api_title")
                            base_url = cdata.get("base_url", "")
                            has_discovery = bool(cdata.get("endpoints"))
                except Exception:
                    pass

            dialect = None
            if connector_type == "api":
                if api_title:
                    dialect = api_title
                elif base_url:
                    try:
                        from urllib.parse import urlparse

                        parsed = urlparse(base_url)
                        domain = parsed.netloc or parsed.path
                        parts = domain.replace("www.", "").split(".")
                        if len(parts) >= 2:
                            main_part = (
                                parts[-2]
                                if parts[-1] in ("com", "io", "ai", "co", "org", "net")
                                else parts[0]
                            )
                        else:
                            main_part = parts[0]
                        dialect = f"{main_part.capitalize()} API"
                    except Exception:
                        dialect = f"{name} API"
                else:
                    dialect = f"{name} API"
            elif connector_type == "file":
                dialect = "duckdb"
            elif has_credentials:
                env_file = conn_path / ".env"
                try:
                    with open(env_file) as f:
                        for line in f:
                            if line.startswith("DATABASE_URL="):
                                url = line.split("=", 1)[1].strip().strip("\"'")
                                dialect = detect_dialect_from_url(url)
                                break
                except Exception:
                    pass

            onboarding_phase = None
            if has_state:
                try:
                    with open(_state_path(conn_path)) as f:
                        state = yaml.safe_load(f) or {}
                        onboarding_phase = state.get("phase")
                except Exception:
                    pass

            connections.append(
                {
                    "name": name,
                    "isActive": name == active_connection,
                    "hasSchema": has_schema,
                    "hasDiscovery": has_discovery,
                    "hasDomain": has_domain,
                    "hasCredentials": has_credentials,
                    "connectorType": connector_type,
                    "dialect": dialect,
                    "onboardingPhase": onboarding_phase,
                }
            )

    return {
        "connections": connections,
        "activeConnection": active_connection,
    }


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


def get_named_connection_details(
    name: str,
    *,
    connections_dir: Path,
    match_connector_template=None,
    get_connector_template=None,
) -> dict:
    """Read persisted details for a named connection."""
    conn_path = connections_dir / name
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    connector_data: dict[str, object] = {}
    connector_yaml = _connector_path(conn_path)
    if connector_yaml.exists():
        with open(connector_yaml) as f:
            connector_data = yaml.safe_load(f) or {}

    connector_type = connector_data.get("type", "sql")
    if connector_type == "file":
        return {
            "success": True,
            "name": name,
            "connectorType": "file",
            "directory": connector_data.get("directory", ""),
        }

    if connector_type == "api":
        auth = connector_data.get("auth", {})
        endpoints = connector_data.get("endpoints", [])
        pagination = connector_data.get("pagination", {})
        rate_limit = connector_data.get("rate_limit", {})
        preset_id = match_connector_template(connector_data)
        env_values = _read_connection_env_values(conn_path)
        env_vars: list[dict[str, object]] = []

        if preset_id and get_connector_template is not None:
            template = get_connector_template(preset_id)
            template_auth = template.connector.get("auth", {}) if template is not None else {}
            template_env_vars = template.env if template is not None else []
            for env_var in template_env_vars:
                resolved_name = env_var.name
                for auth_key in ("token_env", "username_env", "password_env"):
                    if template_auth.get(auth_key) == env_var.name:
                        resolved_name = auth.get(auth_key, resolved_name)
                        break
                env_vars.append(
                    {
                        "slot": env_var.name,
                        "name": resolved_name,
                        "prompt": env_var.prompt,
                        "secret": env_var.secret,
                        "hasSavedValue": bool(env_values.get(resolved_name)),
                    }
                )
        elif isinstance(auth, dict) and auth.get("type") == "basic":
            username_env = auth.get("username_env", "API_USERNAME")
            password_env = auth.get("password_env", "API_PASSWORD")
            env_vars.extend(
                [
                    {
                        "slot": username_env,
                        "name": username_env,
                        "prompt": "Username/email",
                        "secret": False,
                        "hasSavedValue": bool(env_values.get(username_env)),
                    },
                    {
                        "slot": password_env,
                        "name": password_env,
                        "prompt": "Password/token",
                        "secret": True,
                        "hasSavedValue": bool(env_values.get(password_env)),
                    },
                ]
            )
        elif isinstance(auth, dict) and auth.get("type") != "none":
            token_env = auth.get("token_env", "API_KEY")
            env_vars.append(
                {
                    "slot": token_env,
                    "name": token_env,
                    "prompt": "API token",
                    "secret": True,
                    "hasSavedValue": bool(env_values.get(token_env)),
                }
            )

        auth_dict = auth if isinstance(auth, dict) else {}
        endpoints_list = endpoints if isinstance(endpoints, list) else []
        pagination_dict = pagination if isinstance(pagination, dict) else {}
        rate_limit_dict = rate_limit if isinstance(rate_limit, dict) else {}

        return {
            "success": True,
            "name": name,
            "connectorType": "api",
            "baseUrl": connector_data.get("base_url", ""),
            "presetId": preset_id,
            "auth": {
                "type": auth_dict.get("type", "bearer"),
                "tokenEnv": auth_dict.get("token_env", ""),
                "headerName": auth_dict.get("header_name", "Authorization"),
                "paramName": auth_dict.get("param_name", "api_key"),
                "usernameEnv": auth_dict.get("username_env", ""),
                "passwordEnv": auth_dict.get("password_env", ""),
            },
            "envVars": env_vars,
            "endpoints": [
                {
                    "name": ep.get("name", ""),
                    "path": ep.get("path", ""),
                    "method": ep.get("method", "GET"),
                }
                for ep in endpoints_list
                if isinstance(ep, dict)
            ],
            "pagination": {
                "type": pagination_dict.get("type", "none"),
                "cursorParam": pagination_dict.get("cursor_param", ""),
                "cursorField": pagination_dict.get("cursor_field", ""),
                "pageSizeParam": pagination_dict.get("page_size_param", "limit"),
                "pageSize": pagination_dict.get("page_size", 100),
                "dataField": pagination_dict.get("data_field", "data"),
            },
            "rateLimitRps": rate_limit_dict.get("requests_per_second", 10.0),
        }

    env_values = _read_connection_env_values(conn_path)
    database_url = env_values.get("DATABASE_URL", "")
    connector_database_url = connector_data.get("database_url")
    if isinstance(connector_database_url, str) and connector_database_url.strip():
        database_url = connector_database_url.strip()

    return {
        "success": True,
        "name": name,
        "connectorType": "sql",
        "databaseUrl": database_url,
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


# ---------------------------------------------------------------------------
# Active-connection helpers
# ---------------------------------------------------------------------------


def set_active_connection(name: str, config_file: Path) -> None:
    """Write *name* as the active connection into *config_file*.

    Creates the config file and any missing parent directories.
    Preserves all other keys already present in the file.
    """
    config: dict[str, Any] = {}
    if config_file.exists():
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}
    config["active_connection"] = name
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def get_active_connection_path(
    *,
    config_file: Path | None = None,
    connections_dir: Path | None = None,
) -> Path | None:
    """Return the filesystem path for the active connection, or None.

    Resolution order:
    1. ``active_connection`` key in *config_file*.
    2. ``CONNECTION_NAME`` environment variable.
    Returns None when neither source provides a value.
    """
    if config_file is None:
        config_file = Path.home() / ".db-mcp" / "config.yaml"
    if connections_dir is None:
        connections_dir = Path.home() / ".db-mcp" / "connections"

    active: str | None = None
    if config_file.exists():
        with open(config_file) as f:
            cfg = yaml.safe_load(f) or {}
        active = cfg.get("active_connection")

    if not active:
        active = os.environ.get("CONNECTION_NAME")
    if not active:
        return None

    return connections_dir / active


def switch_active_connection(
    name: str,
    *,
    connections_dir: Path,
    config_file: Path,
) -> dict[str, Any]:
    """Set *name* as the active connection after verifying it exists.

    Returns ``{"success": True, "activeConnection": name}`` on success or
    ``{"success": False, "error": "..."}`` otherwise.
    """
    if not name:
        return {"success": False, "error": "Connection name required"}
    if not (connections_dir / name).exists():
        return {"success": False, "error": f"Connection '{name}' not found"}

    set_active_connection(name, config_file)
    return {
        "success": True,
        "activeConnection": name,
        "message": "Restart the UI server to use the new connection",
    }


# ---------------------------------------------------------------------------
# Connection lifecycle: create / delete
# ---------------------------------------------------------------------------


def extract_connect_args_from_url(
    database_url: str,
) -> tuple[str, dict[str, Any] | None]:
    """Strip non-SQLAlchemy query params from *database_url* and return them.

    Recognised params: ``http_scheme``, ``httpScheme``, ``verify``.
    Returns ``(sanitized_url, connect_args_dict_or_None)``.
    """
    import urllib.parse

    try:
        parsed = urllib.parse.urlparse(database_url)
    except Exception:
        return database_url, None

    if not parsed.query:
        return database_url, None

    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    connect_args: dict[str, Any] = {}

    http_scheme = params.pop("http_scheme", None) or params.pop("httpScheme", None)
    if http_scheme:
        connect_args["http_scheme"] = http_scheme[-1]

    verify = params.pop("verify", None)
    if verify:
        raw = str(verify[-1]).strip().lower()
        connect_args["verify"] = raw not in ("false", "0", "no", "off")

    if not connect_args:
        return database_url, None

    new_query = urllib.parse.urlencode(params, doseq=True)
    sanitized = parsed._replace(query=new_query).geturl()
    return sanitized, connect_args


def test_database_url(
    database_url: str,
    *,
    connect_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attempt a live connect to *database_url* and return a status dict.

    Uses SQLAlchemy ``get_engine`` (sync).  Returns::

        {"success": True/False, "message": str, "dialect": str|None,
         "error": str|None, "hint": str|None}
    """
    from sqlalchemy import text

    dialect = detect_dialect_from_url(database_url)
    try:
        clean_url, inferred_args = extract_connect_args_from_url(database_url)
        if connect_args is None:
            connect_args = inferred_args
        engine = get_engine(clean_url, connect_args=connect_args)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return {"success": True, "message": "Connection successful", "dialect": dialect}
    except Exception as exc:
        error_msg = str(exc)
        if database_url in error_msg:
            error_msg = error_msg.replace(database_url, "[DATABASE_URL]")
        hint = None
        if dialect == "postgresql" and "sslmode" not in database_url:
            ssl_kw = ["ssl", "SSL", "certificate", "tls", "TLS", "HTTPS"]
            if any(kw in error_msg for kw in ssl_kw):
                hint = "Try adding ?sslmode=require to the database URL."
        return {"success": False, "error": error_msg, "hint": hint, "dialect": dialect}


def test_file_directory(directory: str) -> dict[str, Any]:
    """Test whether *directory* is a valid file-connector source.

    Instantiates a ``FileConnector`` and delegates to its ``test_connection``.
    Returns ``{"success": bool, "dialect": "duckdb", ...}``.
    """
    from db_mcp_data.connectors.file import FileConnector, FileConnectorConfig

    config = FileConnectorConfig(directory=directory)
    connector = FileConnector(config)
    result = connector.test_connection()
    if result["connected"]:
        source_count = len(result.get("sources", {}))
        return {
            "success": True,
            "message": f"Found {source_count} table{'s' if source_count != 1 else ''}",
            "dialect": "duckdb",
            "sources": result.get("sources", {}),
        }
    return {
        "success": False,
        "error": result.get("error", "No supported files found"),
        "dialect": "duckdb",
    }


def test_api_connection(
    params: dict[str, Any],
    *,
    connections_dir: Path | None = None,
) -> dict[str, Any]:
    """Test an API connection described by *params*.

    Builds a temporary ``APIConnector``, runs ``test_connection()``, and
    returns ``{"success": bool, "message": str, "dialect": str, "error": str|None}``.
    """
    import tempfile

    from db_mcp_data.connectors import _load_api_config
    from db_mcp_data.connectors.api import APIAuthConfig, APIConnector, APIConnectorConfig

    base_url = params.get("baseUrl", "").strip()
    name = params.get("name", "").strip()
    api_key = params.get("apiKey", "").strip()
    auth_type = params.get("authType", "bearer")
    header_name = params.get("headerName", "Authorization")
    param_name = params.get("paramName", "api_key")
    token_env = "" if auth_type == "none" else params.get("tokenEnv", "API_KEY")
    template_id = str(params.get("templateId", "") or "").strip()
    env_entries = _normalize_api_env_entries(params.get("envVars"))

    conn_path = (connections_dir / name) if (connections_dir and name) else None
    resolved_env_values = _resolve_api_env_values(conn_path, env_entries)

    if api_key and token_env:
        resolved_env_values[token_env] = api_key

    if template_id:
        from db_mcp_data.connector_templates import materialize_connector_template

        connector_data = materialize_connector_template(
            template_id,
            base_url=base_url,
            env_name_overrides=_build_template_env_name_overrides(env_entries),
            auth_overrides=_build_api_auth_overrides(params),
        )
        if connector_data is None:
            return {"success": False, "error": f"Unknown connector template: {template_id}"}
        config = _load_api_config(connector_data)
    else:
        if not resolved_env_values and token_env and conn_path is not None:
            existing_env = _read_connection_env_values(conn_path)
            if token_env in existing_env:
                resolved_env_values[token_env] = existing_env[token_env]
        auth = APIAuthConfig(
            type=auth_type,
            token_env=token_env,
            header_name=header_name,
            param_name=param_name,
        )
        config = APIConnectorConfig(base_url=base_url, auth=auth)

    with tempfile.TemporaryDirectory() as temp_dir:
        env_path = None
        if resolved_env_values:
            import os as _os

            env_path = _os.path.join(temp_dir, ".env")
            with open(env_path, "w") as f:
                for env_name, env_value in resolved_env_values.items():
                    if env_value:
                        f.write(f"{env_name}={env_value}\n")

        connector = APIConnector(config, temp_dir, env_path=env_path)
        result = connector.test_connection()

    if result["connected"]:
        endpoint_count = result.get("endpoints", 0)
        return {
            "success": True,
            "message": f"API reachable ({endpoint_count} endpoints configured)",
            "dialect": result.get("dialect", "duckdb"),
        }
    return {
        "success": False,
        "error": result.get("error", "Connection failed"),
        "dialect": result.get("dialect", "duckdb"),
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


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------


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


__all__ = [
    # existing
    "create_api_connection",
    "discover_api_connection",
    "_resolve_connection_path",
    "get_named_connection_details",
    "get_resolved_provider_id",
    "list_connections_summary",
    "require_connection",
    "resolve_connection",
    "test_named_connection",
    "update_api_connection",
    "update_file_connection",
    "update_sql_connection",
    # new in Phase 4
    "set_active_connection",
    "get_active_connection_path",
    "switch_active_connection",
    "extract_connect_args_from_url",
    "test_database_url",
    "test_file_directory",
    "test_api_connection",
    "create_sql_connection",
    "create_file_connection",
    "delete_connection",
    "sync_api_connection",
    "build_api_template_descriptor",
]
