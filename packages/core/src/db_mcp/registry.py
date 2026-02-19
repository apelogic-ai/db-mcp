"""Connection registry for multi-connection support.

Discovers, caches, and provides access to multiple database connections.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml

from db_mcp.config import Settings, get_settings
from db_mcp.connectors import Connector, get_connector


class ConnectionInfo:
    """Metadata about a discovered connection."""

    __slots__ = ("name", "path", "type", "dialect", "description", "is_default")

    def __init__(
        self,
        name: str,
        path: Path,
        type: str = "sql",
        dialect: str = "",
        description: str = "",
        is_default: bool = False,
    ):
        self.name = name
        self.path = path
        self.type = type
        self.dialect = dialect
        self.description = description
        self.is_default = is_default

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "dialect": self.dialect,
            "description": self.description,
            "is_default": self.is_default,
        }


class ConnectionRegistry:
    """Registry that discovers and caches database connections.

    Thread-safe singleton per settings configuration.
    """

    _instance: ConnectionRegistry | None = None
    _lock = threading.Lock()

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._connections: dict[str, ConnectionInfo] = {}
        self._connectors: dict[str, Connector] = {}
        self._discovered = False

    @classmethod
    def get_instance(cls, settings: Settings | None = None) -> ConnectionRegistry:
        """Get or create the singleton registry instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(settings)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def _get_connections_dir(self) -> Path:
        """Resolve the connections directory."""
        if self._settings.connections_dir:
            return Path(self._settings.connections_dir)
        return Path.home() / ".db-mcp" / "connections"

    def discover(self) -> dict[str, ConnectionInfo]:
        """Scan connections directory and discover all connections.

        Returns:
            Dict mapping connection name to ConnectionInfo.
        """
        connections_dir = self._get_connections_dir()
        self._connections.clear()

        if not connections_dir.is_dir():
            self._discovered = True
            return self._connections

        default_name = self._settings.connection_name or "default"

        for entry in sorted(connections_dir.iterdir()):
            if not entry.is_dir():
                continue
            yaml_path = entry / "connector.yaml"
            if not yaml_path.exists():
                continue

            name = entry.name
            try:
                with open(yaml_path) as f:
                    data = yaml.safe_load(f) or {}
            except Exception:
                data = {}

            self._connections[name] = ConnectionInfo(
                name=name,
                path=entry,
                type=data.get("type", "sql"),
                dialect=data.get("dialect", ""),
                description=data.get("description", ""),
                is_default=(name == default_name),
            )

        self._discovered = True
        return self._connections

    def list_connections(self) -> list[dict[str, Any]]:
        """List all discovered connections with metadata.

        Auto-discovers if not yet done.
        """
        if not self._discovered:
            self.discover()
        return [info.to_dict() for info in self._connections.values()]

    def get_connection_path(self, name: str | None = None) -> Path:
        """Resolve a connection name to its directory path.

        Args:
            name: Connection name. If None, uses the default.
        """
        if name is None:
            return self._settings.get_effective_connection_path()

        if not self._discovered:
            self.discover()

        info = self._connections.get(name)
        if info is not None:
            return info.path

        # Fall back to constructing the path
        return self._get_connections_dir() / name

    def get_connector(self, name: str | None = None) -> Connector:
        """Get a connector by connection name, with lazy loading and caching.

        Args:
            name: Connection name. If None, uses the default.
        """
        cache_key = name or self._settings.connection_name or "default"

        cached = self._connectors.get(cache_key)
        if cached is not None:
            return cached

        path = self.get_connection_path(name)
        connector = get_connector(str(path))
        self._connectors[cache_key] = connector
        return connector

    # =========================================================================
    # New multi-connection helpers
    # =========================================================================

    def get_capabilities(self, name: str | None = None) -> dict[str, Any]:
        """Get normalized capabilities for a connection (via connector).

        Args:
            name: Connection name. If None, uses the default.
        """
        from db_mcp.connectors import get_connector_capabilities

        connector = self.get_connector(name)
        return get_connector_capabilities(connector)

    def get_connections_by_type(self, conn_type: str) -> list[ConnectionInfo]:
        """Return all connections of a given type (sql, api, file, metabase).

        Args:
            conn_type: Connector type string.
        """
        if not self._discovered:
            self.discover()
        return [info for info in self._connections.values() if info.type == conn_type]

    def has_capability(self, name: str, capability: str) -> bool:
        """Check if a connection has a specific capability.

        Args:
            name: Connection name.
            capability: Capability key (e.g. 'supports_sql').
        """
        try:
            caps = self.get_capabilities(name)
            return bool(caps.get(capability, False))
        except Exception:
            return False

    def get_default_name(self) -> str:
        """Return the configured default connection name."""
        return self._settings.connection_name or self._settings.provider_id or "default"
