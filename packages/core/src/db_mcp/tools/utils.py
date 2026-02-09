"""Shared utilities for MCP tools."""

from pathlib import Path


def _resolve_connection_path(connection: str | None) -> str | None:
    """Resolve a connection name to its filesystem path.

    Args:
        connection: Connection name (e.g., 'prod', 'staging').
            If None, returns None (use default connection).

    Returns:
        Absolute path to the connection directory, or None.
    """
    if connection is None:
        return None
    from db_mcp.config import get_settings

    settings = get_settings()
    base = settings.connections_dir or str(Path.home() / ".db-mcp" / "connections")
    return str(Path(base) / connection)
