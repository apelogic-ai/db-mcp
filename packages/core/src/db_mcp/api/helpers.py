"""Shared helpers for API router and handler modules."""

from __future__ import annotations

from pathlib import Path

from db_mcp.services.connection import get_active_connection_path

_CONNECTIONS_DIR = Path.home() / ".db-mcp" / "connections"
_CONFIG_FILE = Path.home() / ".db-mcp" / "config.yaml"


def _connections_dir() -> Path:
    return _CONNECTIONS_DIR


def _config_file() -> Path:
    return _CONFIG_FILE


def resolve_connection_context() -> tuple[str, Path]:
    """Resolve the active connection (name, path).

    Priority:
    1. Active connection from ``~/.db-mcp/config.yaml``
    2. Process-level env vars (``CONNECTION_NAME``)
    3. Effective settings
    """
    active = get_active_connection_path(
        config_file=_config_file(),
        connections_dir=_connections_dir(),
    )
    if active is not None:
        return active.name, active

    from db_mcp.config import get_settings

    settings = get_settings()
    return settings.get_effective_provider_id(), settings.get_effective_connection_path()


def _is_git_enabled(conn_path: Path) -> bool:
    return (conn_path / ".git").exists()
