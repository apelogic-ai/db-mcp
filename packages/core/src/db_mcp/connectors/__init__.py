"""Connector abstraction layer.

Defines the Connector protocol and provides factory functions
for creating connectors from configuration.
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from db_mcp.config import get_settings
from db_mcp.connectors.api import (
    APIAuthConfig,
    APIConnector,
    APIConnectorConfig,
    APIEndpointConfig,
    APIPaginationConfig,
    APIQueryParamConfig,
)
from db_mcp.connectors.file import FileConnector, FileConnectorConfig, FileSourceConfig
from db_mcp.connectors.metabase import (
    MetabaseAuthConfig,
    MetabaseConnector,
    MetabaseConnectorConfig,
)
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
        loader = _CONFIG_LOADERS.get(connector_type)
        if loader is None:
            raise ValueError(f"Unknown connector type: {connector_type}")
        return loader(data)


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

    factory = _CONNECTOR_FACTORIES.get(type(config))
    if factory is None:
        raise ValueError(f"Cannot create connector for config type: {config.type}")
    return factory(config, conn_path, settings)


def _load_sql_config(data: dict[str, Any]) -> SQLConnectorConfig:
    return SQLConnectorConfig(
        **{k: v for k, v in data.items() if k not in {"type", "capabilities"}},
        capabilities=data.get("capabilities", {}) or {},
    )


def _load_file_config(data: dict[str, Any]) -> FileConnectorConfig:
    sources_data = data.get("sources", [])
    sources = [FileSourceConfig(**s) for s in sources_data]
    directory = data.get("directory", "")
    return FileConnectorConfig(
        sources=sources,
        directory=directory,
        capabilities=data.get("capabilities", {}) or {},
    )


def _load_api_config(data: dict[str, Any]) -> APIConnectorConfig:
    auth_data = data.get("auth", {})
    auth = APIAuthConfig(**auth_data) if auth_data else APIAuthConfig()

    endpoints_data = data.get("endpoints", [])
    endpoints = []
    for e in endpoints_data:
        qp_data = e.pop("query_params", [])
        query_params = [APIQueryParamConfig(**qp) for qp in qp_data]
        endpoints.append(APIEndpointConfig(**e, query_params=query_params))

    pagination_data = data.get("pagination", {})
    pagination = (
        APIPaginationConfig(**pagination_data) if pagination_data else APIPaginationConfig()
    )

    rate_limit = data.get("rate_limit", {})
    rate_limit_rps = rate_limit.get("requests_per_second", 10.0) if rate_limit else 10.0

    return APIConnectorConfig(
        base_url=data.get("base_url", ""),
        auth=auth,
        endpoints=endpoints,
        pagination=pagination,
        rate_limit_rps=rate_limit_rps,
        capabilities=data.get("capabilities", {}) or {},
        api_title=data.get("api_title", ""),
        api_description=data.get("api_description", ""),
    )


def _load_metabase_config(data: dict[str, Any]) -> MetabaseConnectorConfig:
    auth_data = data.get("auth", {})
    auth = MetabaseAuthConfig(**auth_data) if auth_data else MetabaseAuthConfig()
    return MetabaseConnectorConfig(
        base_url=data.get("base_url", ""),
        database_id=data.get("database_id"),
        database_name=data.get("database_name"),
        auth=auth,
        capabilities=data.get("capabilities", {}) or {},
    )


def _build_sql_connector(
    config: SQLConnectorConfig, conn_path: Path, settings: Any
) -> SQLConnector:
    if not config.database_url:
        config.database_url = settings.database_url
    return SQLConnector(config)


def _build_file_connector(
    config: FileConnectorConfig, conn_path: Path, settings: Any
) -> FileConnector:
    return FileConnector(config)


def _build_api_connector(
    config: APIConnectorConfig, conn_path: Path, settings: Any
) -> APIConnector:
    data_dir = str(conn_path / "data")
    return APIConnector(config, data_dir)


def _build_metabase_connector(
    config: MetabaseConnectorConfig, conn_path: Path, settings: Any
) -> MetabaseConnector:
    return MetabaseConnector(config, env_path=str(conn_path / ".env"))


_CONFIG_LOADERS: dict[str, Any] = {
    "sql": _load_sql_config,
    "file": _load_file_config,
    "api": _load_api_config,
    "metabase": _load_metabase_config,
}

_CONNECTOR_FACTORIES: dict[type, Any] = {
    SQLConnectorConfig: _build_sql_connector,
    FileConnectorConfig: _build_file_connector,
    APIConnectorConfig: _build_api_connector,
    MetabaseConnectorConfig: _build_metabase_connector,
}


def get_connector_capabilities(connector: Connector) -> dict[str, Any]:
    """Return normalized capability flags for a connector."""
    defaults: dict[str, Any] = {
        "supports_sql": False,
        "supports_validate_sql": False,
        "supports_async_jobs": False,
        "sql_mode": None,
    }

    if isinstance(connector, SQLConnector):
        defaults.update(
            {
                "supports_sql": True,
                "supports_validate_sql": True,
                "supports_async_jobs": True,
                "sql_mode": "engine",
            }
        )
        config_caps = connector.config.capabilities
    elif isinstance(connector, FileConnector):
        defaults.update(
            {
                "supports_sql": True,
                "supports_validate_sql": True,
                "supports_async_jobs": True,
                "sql_mode": "engine",
            }
        )
        config_caps = connector.config.capabilities
    elif isinstance(connector, MetabaseConnector):
        defaults.update(
            {
                "supports_sql": True,
                "supports_validate_sql": False,
                "supports_async_jobs": False,
                "sql_mode": "api_sync",
            }
        )
        config_caps = connector.config.capabilities
    elif isinstance(connector, APIConnector):
        config_caps = connector.api_config.capabilities
    else:
        config_caps = {}

    if not isinstance(config_caps, dict):
        config_caps = {}

    merged = dict(defaults)
    merged.update(config_caps)
    return merged


__all__ = [
    "APIAuthConfig",
    "APIConnector",
    "APIConnectorConfig",
    "APIEndpointConfig",
    "APIPaginationConfig",
    "APIQueryParamConfig",
    "Connector",
    "ConnectorConfig",
    "FileConnector",
    "FileConnectorConfig",
    "FileSourceConfig",
    "get_connector_capabilities",
    "MetabaseAuthConfig",
    "MetabaseConnector",
    "MetabaseConnectorConfig",
    "SQLConnector",
    "SQLConnectorConfig",
    "get_connector",
]
