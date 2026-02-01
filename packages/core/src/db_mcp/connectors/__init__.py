"""Connector abstraction layer.

Defines the Connector protocol and provides factory functions
for creating connectors from configuration.
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from db_mcp.config import get_settings
from db_mcp.connectors.file import FileConnector, FileConnectorConfig, FileSourceConfig
from db_mcp.connectors.sql import SQLConnector, SQLConnectorConfig


class ConnectorConfig:
    """Base connector configuration with factory method."""

    type: str = "sql"

    @staticmethod
    def from_yaml(path: Path) -> "ConnectorConfig":
        """Load connector config from a YAML file.

        Args:
            path: Path to connector.yaml

        Returns:
            Appropriate ConnectorConfig subclass

        Raises:
            ValueError: If connector type is unknown
        """
        if not path.exists():
            return SQLConnectorConfig()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        connector_type = data.get("type", "sql")

        if connector_type == "sql":
            return SQLConnectorConfig(**{k: v for k, v in data.items() if k != "type"})
        elif connector_type == "file":
            sources_data = data.get("sources", [])
            sources = [FileSourceConfig(**s) for s in sources_data]
            directory = data.get("directory", "")
            return FileConnectorConfig(sources=sources, directory=directory)
        else:
            raise ValueError(f"Unknown connector type: {connector_type}")


@runtime_checkable
class Connector(Protocol):
    """Protocol defining the interface all connectors must implement."""

    def test_connection(self) -> dict[str, Any]:
        """Test connectivity and return status info."""
        ...

    def get_dialect(self) -> str:
        """Return the dialect/source type identifier."""
        ...

    def get_catalogs(self) -> list[str | None]:
        """List available catalogs."""
        ...

    def get_schemas(self, catalog: str | None = None) -> list[str | None]:
        """List schemas, optionally within a catalog."""
        ...

    def get_tables(
        self, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        """List tables/endpoints/files."""
        ...

    def get_columns(
        self, table_name: str, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        """Get column metadata for a table."""
        ...

    def get_table_sample(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get sample rows from a table."""
        ...

    def execute_sql(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return rows as dicts."""
        ...


def get_connector(connection_path: str | None = None) -> Connector:
    """Factory: create a Connector from the current connection config.

    Reads connector.yaml from the connection directory. Falls back to
    SQLConnector with DATABASE_URL from settings.

    Args:
        connection_path: Optional path to connection directory.
            If not provided, uses settings.

    Returns:
        A Connector instance
    """
    settings = get_settings()

    if connection_path is None:
        connection_path = settings.get_effective_connection_path()

    conn_path = Path(connection_path)
    yaml_path = conn_path / "connector.yaml"

    config = ConnectorConfig.from_yaml(yaml_path)

    if isinstance(config, SQLConnectorConfig):
        if not config.database_url:
            config.database_url = settings.database_url
        return SQLConnector(config)

    if isinstance(config, FileConnectorConfig):
        return FileConnector(config)

    raise ValueError(f"Cannot create connector for config type: {config.type}")


__all__ = [
    "Connector",
    "ConnectorConfig",
    "FileConnector",
    "FileConnectorConfig",
    "FileSourceConfig",
    "SQLConnector",
    "SQLConnectorConfig",
    "get_connector",
]
