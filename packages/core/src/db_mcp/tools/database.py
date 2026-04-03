"""Database MCP tools."""

from db_mcp_data.connectors import get_connector
from db_mcp_data.db.connection import detect_dialect_from_url

from db_mcp.registry import ConnectionRegistry
from db_mcp.services.schema import (
    describe_table,
    list_catalogs,
    list_schemas,
    list_tables,
    sample_table,
)
from db_mcp.tools.protocol import inject_protocol
from db_mcp.tools.utils import _resolve_connection_path


async def _list_connections() -> dict:
    """List all available database connections.

    Returns metadata for each configured connection including name, type,
    dialect, description, and whether it is the default connection.

    Returns:
        List of connection info dicts
    """
    registry = ConnectionRegistry.get_instance()
    connections = registry.list_connections()
    return {
        "connections": connections,
        "count": len(connections),
    }


async def _test_connection(connection: str, database_url: str | None = None) -> dict:
    """Test database connection.

    Args:
        connection: Connection name for multi-connection support.
        database_url: Optional database URL override for one-off testing.

    Returns:
        Connection status and info
    """
    if database_url:
        # Direct URL provided — use legacy path for one-off testing
        from db_mcp_data.db.connection import test_connection

        return test_connection(database_url)
    connector = get_connector(connection_path=_resolve_connection_path(connection))
    return connector.test_connection()


async def _detect_dialect(database_url: str) -> dict:
    """Detect SQL dialect from database URL.

    Args:
        database_url: Database connection URL

    Returns:
        Detected dialect info
    """
    dialect = detect_dialect_from_url(database_url)
    return {
        "dialect": dialect,
        "database_url_prefix": database_url.split("://")[0] if "://" in database_url else None,
    }


async def _list_catalogs(connection: str, database_url: str | None = None) -> dict:
    """List all catalogs in the database (Trino 3-level hierarchy).

    Args:
        connection: Connection name for multi-connection support.
        database_url: Optional database URL (unused when connection is provided).

    Returns:
        List of catalog names
    """
    try:
        result = list_catalogs(connection_path=_resolve_connection_path(connection))
        return inject_protocol(result)
    except Exception as e:
        return inject_protocol(
            {
                "catalogs": [],
                "count": 0,
                "has_catalogs": False,
                "error": str(e),
            }
        )


async def _list_schemas(
    connection: str,
    catalog: str | None = None,
    database_url: str | None = None,
) -> dict:
    """List all schemas in the database (or in a specific catalog for Trino).

    Args:
        connection: Connection name for multi-connection support.
        catalog: Optional catalog name (for Trino 3-level hierarchy).
        database_url: Optional database URL (unused when connection is provided).

    Returns:
        List of schema names
    """
    try:
        result = list_schemas(
            connection_path=_resolve_connection_path(connection),
            catalog=catalog,
        )
        return inject_protocol(result)
    except Exception as e:
        return inject_protocol(
            {
                "schemas": [],
                "count": 0,
                "catalog": catalog,
                "error": str(e),
            }
        )


async def _list_tables(
    connection: str,
    schema: str | None = None,
    catalog: str | None = None,
    database_url: str | None = None,
) -> dict:
    """List all tables in a schema (and catalog for Trino).

    IMPORTANT: This database uses 3-level hierarchy (catalog.schema.table).
    Always use list_catalogs() first, then list_schemas(catalog='...').

    Before generating SQL, check for existing examples:
        shell(command='grep -ri "keyword" examples/')

    Args:
        connection: Connection name for multi-connection support.
        schema: Schema name. If None, uses default schema.
        catalog: Catalog name - REQUIRED for Trino databases.
        database_url: Optional database URL (unused when connection is provided).

    Returns:
        List of table info with fully qualified names
    """
    try:
        result = list_tables(
            connection_path=_resolve_connection_path(connection),
            schema=schema,
            catalog=catalog,
        )
        return inject_protocol(result)
    except Exception as e:
        return inject_protocol(
            {
                "tables": [],
                "count": 0,
                "schema": schema,
                "catalog": catalog,
                "error": str(e),
            }
        )


def _make_full_name(table_name: str, schema: str | None, catalog: str | None) -> str:
    """Build fully qualified table name."""
    if catalog and schema:
        return f"{catalog}.{schema}.{table_name}"
    elif schema:
        return f"{schema}.{table_name}"
    return table_name


async def _describe_table(
    table_name: str,
    connection: str,
    schema: str | None = None,
    catalog: str | None = None,
    database_url: str | None = None,
) -> dict:
    """Get detailed information about a table.

    Before writing SQL, search for existing examples:
        shell(command='grep -ri "table_name" examples/')

    This database uses 3-level hierarchy: catalog.schema.table

    Args:
        table_name: Name of the table
        connection: Connection name for multi-connection support.
        schema: Schema name. If None, uses default schema.
        catalog: Catalog name - REQUIRED for Trino databases.
        database_url: Optional database URL (unused when connection is provided).

    Returns:
        Table info including columns
    """
    try:
        result = describe_table(
            table_name=table_name,
            connection_path=_resolve_connection_path(connection),
            schema=schema,
            catalog=catalog,
        )
        return inject_protocol(result)
    except Exception as e:
        full_name = _make_full_name(table_name, schema, catalog)
        return inject_protocol(
            {
                "table_name": table_name,
                "schema": schema,
                "catalog": catalog,
                "full_name": full_name,
                "columns": [],
                "column_count": 0,
                "error": str(e),
            }
        )


async def _sample_table(
    table_name: str,
    connection: str,
    schema: str | None = None,
    catalog: str | None = None,
    limit: int = 5,
    database_url: str | None = None,
) -> dict:
    """Get sample rows from a table.

    Args:
        table_name: Name of the table
        connection: Connection name for multi-connection support.
        schema: Schema name. If None, uses default schema.
        catalog: Optional catalog name (for Trino 3-level hierarchy).
        limit: Maximum rows to return (default 5, max 100)
        database_url: Optional database URL (unused when connection is provided).

    Returns:
        Sample rows from the table
    """
    # Enforce limit bounds
    limit = max(1, min(limit, 100))

    try:
        result = sample_table(
            table_name=table_name,
            connection_path=_resolve_connection_path(connection),
            schema=schema,
            catalog=catalog,
            limit=limit,
        )
        return inject_protocol(result)
    except Exception as e:
        full_name = _make_full_name(table_name, schema, catalog)
        return inject_protocol(
            {
                "table_name": table_name,
                "schema": schema,
                "catalog": catalog,
                "full_name": full_name,
                "rows": [],
                "row_count": 0,
                "limit": limit,
                "error": str(e),
            }
        )
