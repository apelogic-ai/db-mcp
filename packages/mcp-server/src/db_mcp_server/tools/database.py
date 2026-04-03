"""Thin MCP tool wrappers for database/schema introspection tools (step 3.06).

Each function calls db_mcp.services.schema directly and applies MCP protocol
formatting via db_mcp_server.protocol.inject_protocol.  No logic from
db_mcp.tools.database is imported here.
"""

from __future__ import annotations

from db_mcp.registry import ConnectionRegistry
from db_mcp.services.connection import _resolve_connection_path
from db_mcp.services.schema import (
    describe_table,
    list_catalogs,
    list_schemas,
    list_tables,
    sample_table,
)
from db_mcp_data.connectors import get_connector

from db_mcp_server.protocol import inject_protocol


async def _list_connections() -> dict:
    """List all available database connections."""
    registry = ConnectionRegistry.get_instance()
    connections = registry.list_connections()
    return {
        "connections": connections,
        "count": len(connections),
    }


async def _test_connection(connection: str, database_url: str | None = None) -> dict:
    """Test database connection."""
    if database_url:
        from db_mcp_data.db.connection import test_connection

        return test_connection(database_url)
    connector = get_connector(connection_path=_resolve_connection_path(connection))
    return connector.test_connection()


async def _list_catalogs(connection: str, database_url: str | None = None) -> object:
    """List all catalogs in the database (Trino 3-level hierarchy)."""
    try:
        result = list_catalogs(connection_path=_resolve_connection_path(connection))
        return inject_protocol(result)
    except Exception as e:
        return inject_protocol(
            {"catalogs": [], "count": 0, "has_catalogs": False, "error": str(e)}
        )


async def _list_schemas(
    connection: str,
    catalog: str | None = None,
    database_url: str | None = None,
) -> object:
    """List all schemas in the database (or in a specific catalog for Trino)."""
    try:
        result = list_schemas(
            connection_path=_resolve_connection_path(connection),
            catalog=catalog,
        )
        return inject_protocol(result)
    except Exception as e:
        return inject_protocol(
            {"schemas": [], "count": 0, "catalog": catalog, "error": str(e)}
        )


async def _list_tables(
    connection: str,
    schema: str | None = None,
    catalog: str | None = None,
    database_url: str | None = None,
) -> object:
    """List all tables in a schema (and catalog for Trino).

    IMPORTANT: This database uses 3-level hierarchy (catalog.schema.table).
    Always use list_catalogs() first, then list_schemas(catalog='...').
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
            {"tables": [], "count": 0, "schema": schema, "catalog": catalog, "error": str(e)}
        )


def _make_full_name(table_name: str, schema: str | None, catalog: str | None) -> str:
    if catalog and schema:
        return f"{catalog}.{schema}.{table_name}"
    if schema:
        return f"{schema}.{table_name}"
    return table_name


async def _describe_table(
    table_name: str,
    connection: str,
    schema: str | None = None,
    catalog: str | None = None,
    database_url: str | None = None,
) -> object:
    """Get detailed information about a table."""
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
) -> object:
    """Get sample rows from a table."""
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
