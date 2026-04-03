"""Tests for services/schema.py using gateway introspect dispatch.

These tests patch db_mcp.gateway.dispatcher.get_connector, which is
where the connector is resolved after the schema service routes through
the gateway layer.
"""

from unittest.mock import MagicMock, patch


def _sql_connector(
    *,
    catalogs=None,
    schemas=None,
    tables=None,
    columns=None,
    sample_rows=None,
):
    from db_mcp_data.connectors.sql import SQLConnector

    c = MagicMock(spec=SQLConnector)
    c.get_catalogs.return_value = catalogs if catalogs is not None else [None, "analytics"]
    c.get_schemas.return_value = schemas if schemas is not None else ["public"]
    c.get_tables.return_value = tables if tables is not None else [
        {"name": "orders", "schema": "public", "full_name": "public.orders"}
    ]
    c.get_columns.return_value = columns if columns is not None else [
        {"name": "id", "type": "INTEGER"},
    ]
    c.get_table_sample.return_value = sample_rows if sample_rows is not None else [
        {"id": 1}
    ]
    return c


def _patch(connector):
    return patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector)


# ---------------------------------------------------------------------------
# list_catalogs
# ---------------------------------------------------------------------------

def test_list_catalogs_via_gateway(tmp_path):
    from db_mcp.services.schema import list_catalogs

    connector = _sql_connector(catalogs=[None, "analytics", "warehouse"])
    with _patch(connector):
        result = list_catalogs(connection_path=tmp_path)

    assert result["success"] is True
    assert result["catalogs"] == ["analytics", "warehouse"]
    assert result["count"] == 2
    assert result["has_catalogs"] is True
    assert result["error"] is None


def test_list_catalogs_empty(tmp_path):
    from db_mcp.services.schema import list_catalogs

    connector = _sql_connector(catalogs=[None])
    with _patch(connector):
        result = list_catalogs(connection_path=tmp_path)

    assert result["success"] is True
    assert result["catalogs"] == []
    assert result["has_catalogs"] is False


# ---------------------------------------------------------------------------
# list_schemas
# ---------------------------------------------------------------------------

def test_list_schemas_via_gateway(tmp_path):
    from db_mcp.services.schema import list_schemas

    connector = _sql_connector(schemas=[None, "public", "sales"])
    with _patch(connector):
        result = list_schemas(connection_path=tmp_path, catalog="warehouse")

    assert result["schemas"] == ["public", "sales"]
    assert result["count"] == 2
    assert result["catalog"] == "warehouse"
    connector.get_schemas.assert_called_once_with(catalog="warehouse")


# ---------------------------------------------------------------------------
# list_tables
# ---------------------------------------------------------------------------

def test_list_tables_via_gateway(tmp_path):
    from db_mcp.services.schema import list_tables

    tables = [{"name": "orders", "schema": "public", "full_name": "public.orders"}]
    connector = _sql_connector(tables=tables)
    with _patch(connector):
        result = list_tables(connection_path=tmp_path, schema="public", catalog="warehouse")

    assert result["tables"] == tables
    assert result["count"] == 1
    assert result["schema"] == "public"
    assert result["catalog"] == "warehouse"
    connector.get_tables.assert_called_once_with(schema="public", catalog="warehouse")


# ---------------------------------------------------------------------------
# describe_table
# ---------------------------------------------------------------------------

def test_describe_table_via_gateway(tmp_path):
    from db_mcp.services.schema import describe_table

    columns = [{"name": "id", "type": "INTEGER"}, {"name": "total", "type": "NUMERIC"}]
    connector = _sql_connector(columns=columns)
    with _patch(connector):
        result = describe_table(
            table_name="orders",
            connection_path=tmp_path,
            schema="public",
            catalog="warehouse",
        )

    assert result["table_name"] == "orders"
    assert result["full_name"] == "warehouse.public.orders"
    assert result["columns"] == columns
    assert result["column_count"] == 2
    assert result["error"] is None
    connector.get_columns.assert_called_once_with("orders", schema="public", catalog="warehouse")


# ---------------------------------------------------------------------------
# sample_table — stays on direct connector path (not gateway scope)
# ---------------------------------------------------------------------------

def test_sample_table_still_uses_connector_directly(tmp_path):
    """sample_table is data retrieval, not schema introspection — direct path unchanged."""
    from db_mcp.services.schema import sample_table

    rows = [{"id": 1, "total": 100}]
    connector = _sql_connector(sample_rows=rows)

    # patch at services.schema level — sample_table still calls get_connector directly
    with patch("db_mcp.services.schema.get_connector", return_value=connector):
        result = sample_table(
            table_name="orders",
            connection_path=tmp_path,
            schema="public",
            catalog="warehouse",
            limit=10,
        )

    assert result["rows"] == rows
    assert result["row_count"] == 1
    assert result["limit"] == 10
