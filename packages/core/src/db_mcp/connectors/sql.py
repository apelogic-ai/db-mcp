"""SQL database connector — wraps existing db/ module."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, text

from db_mcp.db.connection import (
    DatabaseError,
    detect_dialect_from_url,
    get_engine,
)
from db_mcp.db.connection import (
    test_connection as db_test_connection,
)
from db_mcp.db.introspection import (
    get_catalogs as db_get_catalogs,
)
from db_mcp.db.introspection import (
    get_columns as db_get_columns,
)
from db_mcp.db.introspection import (
    get_schemas as db_get_schemas,
)
from db_mcp.db.introspection import (
    get_table_sample as db_get_table_sample,
)
from db_mcp.db.introspection import (
    get_tables as db_get_tables,
)


@dataclass
class SQLConnectorConfig:
    """Configuration for a SQL database connector."""

    type: str = field(default="sql", init=False)
    database_url: str = ""
    description: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)


class SQLConnector:
    """Connector for SQL databases via SQLAlchemy.

    Delegates to existing db.connection and db.introspection functions,
    passing the database_url from config.
    """

    def __init__(self, config: SQLConnectorConfig) -> None:
        self.config = config

    def get_engine(self) -> Engine:
        """Get the SQLAlchemy engine for this connection.

        This is SQL-specific and not part of the Connector protocol.
        Used by validation/explain and generation for direct engine access.
        """
        connect_args = self.config.capabilities.get("connect_args")
        if not isinstance(connect_args, dict):
            connect_args = None
        return get_engine(self.config.database_url, connect_args=connect_args)

    def test_connection(self) -> dict[str, Any]:
        """Test database connectivity."""
        return db_test_connection(self.config.database_url)

    def get_dialect(self) -> str:
        """Return the SQL dialect name."""
        return detect_dialect_from_url(self.config.database_url)

    def get_catalogs(self) -> list[str | None]:
        """List database catalogs."""
        return db_get_catalogs(self.config.database_url)

    def get_schemas(self, catalog: str | None = None) -> list[str | None]:
        """List schemas, optionally within a catalog."""
        return db_get_schemas(self.config.database_url, catalog=catalog)

    def get_tables(
        self, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        """List tables in a schema."""
        return db_get_tables(schema=schema, catalog=catalog, database_url=self.config.database_url)

    def get_columns(
        self, table_name: str, schema: str | None = None, catalog: str | None = None
    ) -> list[dict[str, Any]]:
        """Get column metadata for a table."""
        return db_get_columns(
            table_name, schema=schema, catalog=catalog, database_url=self.config.database_url
        )

    def get_table_sample(
        self,
        table_name: str,
        schema: str | None = None,
        catalog: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get sample rows from a table."""
        return db_get_table_sample(
            table_name,
            schema=schema,
            catalog=catalog,
            limit=limit,
            database_url=self.config.database_url,
        )

    def execute_sql(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        """Execute SQL and return rows as dicts."""
        try:
            connect_args = self.config.capabilities.get("connect_args")
            if not isinstance(connect_args, dict):
                connect_args = None
            engine = get_engine(self.config.database_url, connect_args=connect_args)
            with engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            raise DatabaseError(f"Failed to execute SQL: {e}") from e
