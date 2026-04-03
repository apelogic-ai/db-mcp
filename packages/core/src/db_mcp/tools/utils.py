"""Backward-compatible wrappers for connection utilities."""

from db_mcp_data.connectors import get_connector, get_connector_capabilities

from db_mcp.config import get_settings
from db_mcp.registry import ConnectionRegistry
from db_mcp.services import connection as connection_service


def _sync_service_dependencies() -> None:
    """Keep legacy patch points on this module working during the migration."""
    connection_service.get_settings = get_settings
    connection_service.get_connector = get_connector
    connection_service.get_connector_capabilities = get_connector_capabilities
    connection_service.ConnectionRegistry = ConnectionRegistry


def require_connection(connection: str | None, tool_name: str | None = None) -> str:
    return connection_service.require_connection(connection, tool_name=tool_name)


def _resolve_connection_path(connection: str) -> str:
    _sync_service_dependencies()
    return connection_service._resolve_connection_path(connection)


def resolve_connection(
    connection: str | None,
    *,
    require_type: str | None = None,
    require_capability: str | None = None,
) -> tuple:
    _sync_service_dependencies()
    return connection_service.resolve_connection(
        connection,
        require_type=require_type,
        require_capability=require_capability,
    )


def get_resolved_provider_id(connection: str | None) -> str:
    _sync_service_dependencies()
    return connection_service.get_resolved_provider_id(connection)


__all__ = [
    "_resolve_connection_path",
    "get_resolved_provider_id",
    "require_connection",
    "resolve_connection",
]
