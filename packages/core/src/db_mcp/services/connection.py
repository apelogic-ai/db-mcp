"""Connection resolution services."""

import os
from pathlib import Path
from typing import Any

import yaml
from db_mcp_data.connectors import get_connector, get_connector_capabilities
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

from db_mcp.config import get_settings
from db_mcp.registry import ConnectionRegistry
from db_mcp.services.connection_crud import _read_connection_env_values


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


from db_mcp.services.connection_crud import (  # noqa: E402
    build_api_template_descriptor,
    create_api_connection,
    create_file_connection,
    create_sql_connection,
    delete_connection,
    discover_api_connection,
    sync_api_connection,
    update_api_connection,
    update_file_connection,
    update_sql_connection,
)
from db_mcp.services.connection_test import (  # noqa: E402
    extract_connect_args_from_url,
    test_api_connection,
    test_database_url,
    test_file_directory,
    test_named_connection,
)

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
