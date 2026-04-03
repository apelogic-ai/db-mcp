"""Schema introspection services."""

from pathlib import Path

from db_mcp_data.connectors import get_connector
from db_mcp_data.gateway import introspect as gateway_introspect


def _make_full_name(table_name: str, schema: str | None, catalog: str | None) -> str:
    """Build a fully qualified table name."""
    if catalog and schema:
        return f"{catalog}.{schema}.{table_name}"
    if schema:
        return f"{schema}.{table_name}"
    return table_name


def list_catalogs(connection_path: Path | str) -> dict:
    """List catalogs for a resolved connection path."""
    connection_path = Path(connection_path)
    try:
        raw = gateway_introspect(
            connection_path.name, "catalogs", connection_path=connection_path
        )
        if raw.get("status") == "error":
            return {
                "success": False, "catalogs": [], "count": 0,
                "has_catalogs": False, "error": raw["error"],
            }
        catalogs_list = [c for c in raw.get("catalogs", []) if c is not None]
        return {
            "success": True,
            "catalogs": catalogs_list,
            "count": len(catalogs_list),
            "has_catalogs": len(catalogs_list) > 0,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False, "catalogs": [], "count": 0,
            "has_catalogs": False, "error": str(e),
        }


def list_schemas(connection_path: Path | str, catalog: str | None = None) -> dict:
    """List schemas for a resolved connection path."""
    connection_path = Path(connection_path)
    raw = gateway_introspect(
        connection_path.name, "schemas", connection_path=connection_path, catalog=catalog
    )
    if raw.get("status") == "error":
        return {"schemas": [], "count": 0, "catalog": catalog, "error": raw["error"]}
    schemas_list = [s for s in raw.get("schemas", []) if s is not None]
    return {
        "schemas": schemas_list,
        "count": len(schemas_list),
        "catalog": catalog,
        "error": None,
    }


def list_schemas_with_counts(
    connection_path: Path | str, catalog: str | None = None
) -> dict:
    """List schemas with table counts via sequential gateway.introspect() calls.

    Routes through gateway for all connector access: catalogs → schemas per catalog
    → table count per schema.
    """
    connection_path = Path(connection_path)
    connection_name = connection_path.name
    schemas_list = []

    try:
        if catalog:
            active_catalogs = [catalog]
        else:
            raw = gateway_introspect(connection_name, "catalogs", connection_path=connection_path)
            if raw.get("status") == "error":
                return {
                    "success": False, "schemas": [], "count": 0,
                    "catalog": catalog, "error": raw.get("error"),
                }
            active_catalogs = [c for c in raw.get("catalogs", []) if c is not None]
            if not active_catalogs:
                active_catalogs = [None]  # single-catalog databases return [None]

        for current_catalog in active_catalogs:
            raw_schemas = gateway_introspect(
                connection_name, "schemas",
                connection_path=connection_path, catalog=current_catalog,
            )
            for schema in raw_schemas.get("schemas", []):
                if schema is None:
                    continue
                table_count = None
                try:
                    raw_tables = gateway_introspect(
                        connection_name, "tables",
                        connection_path=connection_path,
                        schema=schema, catalog=current_catalog,
                    )
                    table_count = len(raw_tables.get("tables", []))
                except Exception:
                    pass
                schemas_list.append(
                    {"name": schema, "catalog": current_catalog, "tableCount": table_count}
                )

        return {
            "success": True,
            "schemas": schemas_list,
            "count": len(schemas_list),
            "catalog": catalog,
            "error": None,
        }
    except Exception as e:
        return {"success": False, "schemas": [], "count": 0, "catalog": catalog, "error": str(e)}


def list_tables(
    connection_path: Path | str,
    schema: str | None = None,
    catalog: str | None = None,
) -> dict:
    """List tables for a resolved connection path."""
    connection_path = Path(connection_path)
    raw = gateway_introspect(
        connection_path.name, "tables",
        connection_path=connection_path, schema=schema, catalog=catalog
    )
    if raw.get("status") == "error":
        return {
            "tables": [], "count": 0, "schema": schema,
            "catalog": catalog, "error": raw["error"],
        }
    tables = raw.get("tables", [])
    return {
        "tables": tables,
        "count": len(tables),
        "schema": schema,
        "catalog": catalog,
        "error": None,
    }


def describe_table(
    table_name: str,
    connection_path: Path | str,
    schema: str | None = None,
    catalog: str | None = None,
) -> dict:
    """Describe a table for a resolved connection path."""
    connection_path = Path(connection_path)
    raw = gateway_introspect(
        connection_path.name, "columns",
        connection_path=connection_path, table=table_name, schema=schema, catalog=catalog
    )
    if raw.get("status") == "error":
        return {
            "table_name": table_name, "schema": schema, "catalog": catalog,
            "full_name": _make_full_name(table_name, schema, catalog),
            "columns": [], "column_count": 0, "error": raw["error"],
        }
    columns = raw.get("columns", [])
    return {
        "table_name": table_name,
        "schema": schema,
        "catalog": catalog,
        "full_name": _make_full_name(table_name, schema, catalog),
        "columns": columns,
        "column_count": len(columns),
        "error": None,
    }


def sample_table(
    table_name: str,
    connection_path: Path,
    schema: str | None = None,
    catalog: str | None = None,
    limit: int = 5,
) -> dict:
    """Get sample rows for a table from a resolved connection path.

    Intentionally stays on the direct connector path (does not use gateway.introspect).
    Reason: row sampling is data retrieval, not schema introspection. The gateway's
    introspect() scope covers catalogs/schemas/tables/columns only; get_table_sample()
    executes a live query and has no gateway scope equivalent.
    This is a permanent exception, not a deferred migration.
    """
    limit = max(1, min(limit, 100))
    connector = get_connector(connection_path=connection_path)
    rows = connector.get_table_sample(
        table_name,
        schema=schema,
        catalog=catalog,
        limit=limit,
    )
    return {
        "table_name": table_name,
        "schema": schema,
        "catalog": catalog,
        "full_name": _make_full_name(table_name, schema, catalog),
        "rows": rows,
        "row_count": len(rows),
        "limit": limit,
        "error": None,
    }


def validate_link(link: str, connection_path: Path) -> dict:
    """Validate a db://catalog/schema/table[/column] link via gateway.introspect()."""
    if not link.startswith("db://"):
        return {"success": True, "valid": False, "parsed": {}, "error": "Link must start with db://"}

    parts = link[5:].split("/")
    if len(parts) < 3:
        return {
            "success": True,
            "valid": False,
            "parsed": {},
            "error": "Link must have at least catalog/schema/table",
        }

    catalog = parts[0] if parts[0] else None
    schema = parts[1] if len(parts) > 1 else None
    table = parts[2] if len(parts) > 2 else None
    column = parts[3] if len(parts) > 3 else None

    parsed = {"catalog": catalog, "schema": schema, "table": table, "column": column}
    connection_name = Path(connection_path).name

    try:
        if table and schema:
            raw_tables = gateway_introspect(
                connection_name, "tables",
                connection_path=connection_path, schema=schema, catalog=catalog,
            )
            table_names = [
                t.get("name", t) if isinstance(t, dict) else t
                for t in raw_tables.get("tables", [])
            ]
            if table not in table_names:
                return {
                    "success": True,
                    "valid": False,
                    "parsed": parsed,
                    "error": f"Table '{table}' not found in {catalog}/{schema}",
                }

            if column:
                raw_cols = gateway_introspect(
                    connection_name, "columns",
                    connection_path=connection_path,
                    table=table, schema=schema, catalog=catalog,
                )
                column_names = [c["name"] for c in raw_cols.get("columns", [])]
                if column not in column_names:
                    return {
                        "success": True,
                        "valid": False,
                        "parsed": parsed,
                        "error": f"Column '{column}' not found in {table}",
                    }

        return {"success": True, "valid": True, "parsed": parsed, "error": None}
    except Exception as e:
        return {"success": True, "valid": False, "parsed": parsed, "error": str(e)}


# ---------------------------------------------------------------------------
# Knowledge-enriched schema functions (bridge: data + knowledge layers)
# ---------------------------------------------------------------------------


def _load_schema_knowledge(provider_id: str, connection_path: Path):
    """Load schema knowledge descriptions for enrichment.  Lazy import keeps
    schema.py free of a hard dependency on context_service at module level."""
    from db_mcp.services.context import load_schema_knowledge

    return load_schema_knowledge(provider_id, connection_path=connection_path)


def list_tables_with_descriptions(
    connection_path: Path,
    provider_id: str,
    schema: str,
    catalog: str | None = None,
) -> dict:
    """List tables for a schema, enriched with knowledge layer descriptions.

    Calls ``list_tables()`` (data layer) then overlays human-authored
    descriptions from the vault (knowledge layer).  Returns a BICP-shaped
    ``{"success": bool, "tables": [...], "error": str | None}`` response.

    This function is an intentional bridge between the data and knowledge
    layers.  Keeping it here (rather than in the BICP handler) means the
    BICP handler stays a thin delegate.
    """
    try:
        tables_result = list_tables(connection_path, schema=schema, catalog=catalog)
        if tables_result.get("error"):
            return {"success": False, "tables": [], "error": tables_result["error"]}

        schema_desc = _load_schema_knowledge(provider_id, connection_path)
        desc_by_name: dict[str, str | None] = {}
        if schema_desc:
            for t in schema_desc.tables:
                if t.full_name:
                    desc_by_name[t.full_name] = t.description
                desc_by_name[t.name] = t.description

        tables_list = []
        for table in tables_result["tables"]:
            name = table.get("name", table) if isinstance(table, dict) else table
            full_name = table.get("full_name", name) if isinstance(table, dict) else name
            description = desc_by_name.get(full_name) or desc_by_name.get(name)
            tables_list.append({"name": name, "description": description})

        return {"success": True, "tables": tables_list}
    except Exception as e:
        return {"success": False, "tables": [], "error": str(e)}


def describe_table_with_descriptions(
    table_name: str,
    connection_path: Path,
    provider_id: str,
    schema: str | None = None,
    catalog: str | None = None,
) -> dict:
    """Describe a table's columns, enriched with knowledge layer descriptions.

    Calls ``describe_table()`` (data layer) then overlays human-authored
    column descriptions from the vault (knowledge layer).  Returns a
    BICP-shaped ``{"success": bool, "columns": [...], "error": str | None}``
    response.

    Each column dict has keys: ``name``, ``type``, ``nullable``,
    ``isPrimaryKey``, ``description``.

    This function is an intentional bridge between the data and knowledge
    layers.
    """
    try:
        describe_result = describe_table(
            table_name=table_name,
            connection_path=connection_path,
            schema=schema,
            catalog=catalog,
        )
        if describe_result.get("error"):
            return {"success": False, "columns": [], "error": describe_result["error"]}

        full_name = describe_result["full_name"]

        schema_desc = _load_schema_knowledge(provider_id, connection_path)
        col_descs: dict[str, str | None] = {}
        if schema_desc:
            for t in schema_desc.tables:
                if t.name == table_name or t.full_name == table_name or t.full_name == full_name:
                    for col in t.columns or []:
                        col_descs[col.name] = col.description
                    break

        columns_list = [
            {
                "name": col["name"],
                "type": col.get("type", "VARCHAR"),
                "nullable": col.get("nullable", True),
                "description": col_descs.get(col["name"]),
                "isPrimaryKey": col.get("primary_key", False),
            }
            for col in describe_result["columns"]
        ]

        return {"success": True, "columns": columns_list}
    except Exception as e:
        return {"success": False, "columns": [], "error": str(e)}
