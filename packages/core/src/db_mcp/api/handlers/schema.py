"""Schema introspection and sample handlers."""

from __future__ import annotations

import logging
from typing import Any

import db_mcp.services.schema as schema_service
from db_mcp.api.helpers import _connections_dir, resolve_connection_context

logger = logging.getLogger(__name__)


async def handle_schema_catalogs(params: dict[str, Any]) -> dict[str, Any]:
    _, conn_path = resolve_connection_context()
    return schema_service.list_catalogs(conn_path)


async def handle_schema_schemas(params: dict[str, Any]) -> dict[str, Any]:
    catalog = params.get("catalog")
    _, conn_path = resolve_connection_context()
    return schema_service.list_schemas_with_counts(conn_path, catalog=catalog)


async def handle_schema_tables(params: dict[str, Any]) -> dict[str, Any]:
    schema = params.get("schema")
    catalog = params.get("catalog")
    if not schema:
        return {"success": False, "tables": [], "error": "schema is required"}

    provider_id, conn_path = resolve_connection_context()
    return schema_service.list_tables_with_descriptions(
        connection_path=conn_path,
        provider_id=provider_id,
        schema=schema,
        catalog=catalog,
    )


async def handle_schema_columns(params: dict[str, Any]) -> dict[str, Any]:
    table = params.get("table")
    schema = params.get("schema")
    catalog = params.get("catalog")
    if not table:
        return {"success": False, "columns": [], "error": "table is required"}

    provider_id, conn_path = resolve_connection_context()
    return schema_service.describe_table_with_descriptions(
        table_name=table,
        connection_path=conn_path,
        provider_id=provider_id,
        schema=schema,
        catalog=catalog,
    )


async def handle_schema_validate_link(params: dict[str, Any]) -> dict[str, Any]:
    link = params.get("link", "")
    _, conn_path = resolve_connection_context()
    return schema_service.validate_link(link, connection_path=conn_path)


async def handle_sample_table(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    table_name = params.get("table_name")
    schema = params.get("schema")
    catalog = params.get("catalog")
    limit = params.get("limit", 5)

    if not connection:
        return {"error": "connection is required", "rows": [], "row_count": 0, "limit": 0}
    if not table_name:
        return {"error": "table_name is required", "rows": [], "row_count": 0, "limit": 0}

    try:
        limit_value = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit_value = 5

    full_name = ".".join(part for part in [catalog, schema, table_name] if part)

    try:
        return schema_service.sample_table(
            table_name=str(table_name),
            connection_path=_connections_dir() / str(connection),
            schema=str(schema) if schema else None,
            catalog=str(catalog) if catalog else None,
            limit=limit_value,
        )
    except Exception as e:
        logger.exception("Failed to sample table %s: %s", table_name, e)
        return {
            "table_name": table_name,
            "schema": schema,
            "catalog": catalog,
            "full_name": full_name or str(table_name),
            "rows": [],
            "row_count": 0,
            "limit": limit_value,
            "error": str(e),
        }
