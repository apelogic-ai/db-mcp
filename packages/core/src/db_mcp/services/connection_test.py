"""Connection testing/validation services."""

from pathlib import Path
from typing import Any

from db_mcp_data.connectors import get_connector
from db_mcp_data.db.connection import detect_dialect_from_url, get_engine

from db_mcp.services.connection_crud import (
    _build_api_auth_overrides,
    _build_template_env_name_overrides,
    _normalize_api_env_entries,
    _read_connection_env_values,
    _resolve_api_env_values,
)


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
