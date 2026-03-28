"""Connector abstraction layer.

Defines the Connector protocol and provides factory functions
for creating connectors from configuration.
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml
from pydantic import ValidationError

from db_mcp.capabilities import normalize_capabilities, resolve_connector_profile
from db_mcp.config import get_settings
from db_mcp.connector_plugins import get_connector_plugin
from db_mcp.connectors.api import (
    APIAuthConfig,
    APIConnector,
    APIConnectorConfig,
    APIEndpointConfig,
    APIPaginationConfig,
    APIQueryParamConfig,
    build_api_connector_config,
)
from db_mcp.connectors.file import FileConnector, FileConnectorConfig, FileSourceConfig
from db_mcp.connectors.sql import SQLConnector, SQLConnectorConfig
from db_mcp.contracts.connector_contracts import (
    format_validation_error,
    validate_connector_contract,
)


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

        data = _load_connector_payload(path)

        if "spec_version" in data:
            try:
                validate_connector_contract(data)
            except ValidationError as exc:
                details = "; ".join(format_validation_error(exc))
                raise ValueError(f"Invalid connector contract: {details}") from exc

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

    Reads connector.yaml from the connection directory. For SQL connectors,
    falls back to connection-local `.env` DATABASE_URL, then settings DATABASE_URL.

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

    raw_data = _load_connector_payload(yaml_path) if yaml_path.exists() else {}
    plugin_id = str(raw_data.get("template_id", "") or "").strip()
    plugin = get_connector_plugin(plugin_id) if plugin_id else None
    if plugin is not None and plugin.runtime_factory is not None:
        return plugin.runtime_factory(raw_data, conn_path, settings)

    config = ConnectorConfig.from_yaml(yaml_path)

    factory = _CONNECTOR_FACTORIES.get(type(config))
    if factory is None:
        raise ValueError(f"Cannot create connector for config type: {config.type}")
    return factory(config, conn_path, settings)


def _load_database_url_from_env(conn_path: Path) -> str:
    """Load DATABASE_URL from a connection-local .env file."""
    env_path = conn_path / ".env"
    if not env_path.exists():
        return ""

    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "DATABASE_URL":
                    return value.strip().strip("\"'")
    except Exception:
        return ""

    return ""


def _load_connector_payload(path: Path) -> dict[str, Any]:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("connector.yaml must contain a top-level mapping")
    return data


def _load_sql_config(data: dict[str, Any]) -> SQLConnectorConfig:
    from dataclasses import fields

    # Get valid field names from the dataclass (excluding init=False fields)
    valid_fields = {f.name for f in fields(SQLConnectorConfig) if f.init}

    # Filter to only known fields, plus capabilities which is handled separately
    filtered_data = {k: v for k, v in data.items() if k in valid_fields}
    filtered_data["capabilities"] = data.get("capabilities", {}) or {}

    return SQLConnectorConfig(**filtered_data)


def _load_file_config(data: dict[str, Any]) -> FileConnectorConfig:
    sources_data = data.get("sources", [])
    sources = [FileSourceConfig(**s) for s in sources_data]
    directory = data.get("directory", "")
    return FileConnectorConfig(
        profile=data.get("profile", ""),
        sources=sources,
        directory=directory,
        description=data.get("description", ""),
        capabilities=data.get("capabilities", {}) or {},
    )


def _load_api_config(data: dict[str, Any]) -> APIConnectorConfig:
    return build_api_connector_config(data)


def _build_sql_connector(
    config: SQLConnectorConfig, conn_path: Path, settings: Any
) -> SQLConnector:
    env_database_url = _load_database_url_from_env(conn_path)
    if env_database_url:
        # Connection-local .env is the highest precedence source for secrets.
        config.database_url = env_database_url
    elif not config.database_url:
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
    return APIConnector(config, data_dir, env_path=str(conn_path / ".env"))


_CONFIG_LOADERS: dict[str, Any] = {
    "sql": _load_sql_config,
    "file": _load_file_config,
    "api": _load_api_config,
}

_CONNECTOR_FACTORIES: dict[type, Any] = {
    SQLConnectorConfig: _build_sql_connector,
    FileConnectorConfig: _build_file_connector,
    APIConnectorConfig: _build_api_connector,
}


def _resolve_connector_descriptor(connector: Connector) -> tuple[str, dict[str, Any], str]:
    """Resolve (type, capability_overrides, profile) for a connector instance."""
    if isinstance(connector, APIConnector):
        connector_type = "api"
        config_caps = connector.api_config.capabilities
        configured_profile = connector.api_config.profile
    elif isinstance(connector, SQLConnector):
        connector_type = "sql"
        config_caps = connector.config.capabilities
        configured_profile = connector.config.profile
    elif isinstance(connector, FileConnector):
        connector_type = "file"
        config_caps = connector.config.capabilities
        configured_profile = connector.config.profile
    else:
        connector_type = "unknown"
        config_caps = {}
        configured_profile = ""

    if not isinstance(config_caps, dict):
        config_caps = {}

    profile = resolve_connector_profile(connector_type, configured_profile)
    return connector_type, config_caps, profile


def get_connector_capabilities(connector: Connector) -> dict[str, Any]:
    """Return normalized capability flags for a connector."""
    connector_type, config_caps, profile = _resolve_connector_descriptor(connector)
    return normalize_capabilities(connector_type, config_caps, profile=profile)


def get_connector_profile(connector: Connector) -> str:
    """Return effective connector profile for a connector."""
    _, _, profile = _resolve_connector_descriptor(connector)
    return profile


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
    "get_connector_profile",
    "normalize_capabilities",
    "SQLConnector",
    "SQLConnectorConfig",
    "get_connector",
]
