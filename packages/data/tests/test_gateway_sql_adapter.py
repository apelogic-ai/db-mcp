"""Tests for SQLAdapter — execute and introspect against a mock SQLConnector."""

from unittest.mock import MagicMock

from db_mcp_models.gateway import DataRequest, EndpointQuery, SQLQuery

from db_mcp_data.gateway.adapter import ConnectorAdapter
from db_mcp_data.gateway.sql_adapter import SQLAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sql_connector(
    *,
    catalogs=None,
    schemas=None,
    tables=None,
    columns=None,
    rows=None,
):
    """Return a mock that looks like a SQLConnector."""
    from db_mcp_data.connectors.sql import SQLConnector

    connector = MagicMock(spec=SQLConnector)
    connector.get_catalogs.return_value = catalogs or ["main"]
    connector.get_schemas.return_value = schemas or ["public"]
    connector.get_tables.return_value = tables or [
        {"name": "orders", "schema": "public", "full_name": "public.orders"}
    ]
    connector.get_columns.return_value = columns or [
        {"name": "id", "type": "INTEGER"},
        {"name": "amount", "type": "NUMERIC"},
    ]
    connector.execute_sql.return_value = rows if rows is not None else [
        {"id": 1, "amount": 99.0},
        {"id": 2, "amount": 42.5},
    ]
    return connector


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_sql_adapter_satisfies_protocol():
    assert isinstance(SQLAdapter(), ConnectorAdapter)


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

def test_can_handle_sql_connector():
    from db_mcp_data.connectors.sql import SQLConnector
    connector = MagicMock(spec=SQLConnector)
    assert SQLAdapter().can_handle(connector) is True


def test_cannot_handle_api_connector():
    from db_mcp_data.connectors.api import APIConnector
    connector = MagicMock(spec=APIConnector)
    assert SQLAdapter().can_handle(connector) is False


def test_cannot_handle_file_connector():
    from db_mcp_data.connectors.file import FileConnector
    connector = MagicMock(spec=FileConnector)
    assert SQLAdapter().can_handle(connector) is False


def test_cannot_handle_arbitrary_object():
    assert SQLAdapter().can_handle(object()) is False


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def test_execute_returns_success_status(tmp_path):
    connector = _make_sql_connector()
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT id, amount FROM orders"))
    result = SQLAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.is_success


def test_execute_returns_rows(tmp_path):
    rows = [{"id": 1, "amount": 99.0}, {"id": 2, "amount": 42.5}]
    connector = _make_sql_connector(rows=rows)
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT id, amount FROM orders"))
    result = SQLAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.data == rows
    assert result.rows_returned == 2


def test_execute_infers_columns_from_rows(tmp_path):
    connector = _make_sql_connector(rows=[{"id": 1, "amount": 99.0}])
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1"))
    result = SQLAdapter().execute(connector, request, connection_path=tmp_path)
    assert [c.name for c in result.columns] == ["id", "amount"]


def test_execute_empty_result_has_empty_columns(tmp_path):
    connector = _make_sql_connector(rows=[])
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1 WHERE false"))
    result = SQLAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.data == []
    assert result.columns == []
    assert result.rows_returned == 0


def test_execute_passes_params_to_connector(tmp_path):
    connector = _make_sql_connector(rows=[])
    request = DataRequest(
        connection="prod",
        query=SQLQuery(sql="SELECT * FROM t WHERE id = :id", params={"id": 5}),
    )
    SQLAdapter().execute(connector, request, connection_path=tmp_path)
    connector.execute_sql.assert_called_once_with("SELECT * FROM t WHERE id = :id", {"id": 5})


def test_execute_rejects_endpoint_query(tmp_path):
    connector = _make_sql_connector()
    request = DataRequest(connection="prod", query=EndpointQuery(endpoint="dashboards"))
    result = SQLAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.status == "error"
    assert "SQLQuery" in result.error


def test_execute_wraps_connector_exception(tmp_path):
    from db_mcp_data.connectors.sql import SQLConnector
    connector = MagicMock(spec=SQLConnector)
    connector.execute_sql.side_effect = Exception("connection refused")
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1"))
    result = SQLAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.status == "error"
    assert "connection refused" in result.error


# ---------------------------------------------------------------------------
# introspect
# ---------------------------------------------------------------------------

def test_introspect_catalogs(tmp_path):
    connector = _make_sql_connector(catalogs=["db1", "db2"])
    result = SQLAdapter().introspect(connector, "catalogs", connection_path=tmp_path)
    assert result["catalogs"] == ["db1", "db2"]


def test_introspect_schemas(tmp_path):
    connector = _make_sql_connector(schemas=["public", "analytics"])
    result = SQLAdapter().introspect(connector, "schemas", catalog="db1", connection_path=tmp_path)
    assert result["schemas"] == ["public", "analytics"]
    connector.get_schemas.assert_called_once_with(catalog="db1")


def test_introspect_tables(tmp_path):
    tables = [{"name": "orders", "schema": "public", "full_name": "public.orders"}]
    connector = _make_sql_connector(tables=tables)
    result = SQLAdapter().introspect(
        connector, "tables", catalog=None, schema="public", connection_path=tmp_path
    )
    assert result["tables"] == tables
    connector.get_tables.assert_called_once_with(schema="public", catalog=None)


def test_introspect_columns(tmp_path):
    cols = [{"name": "id", "type": "INTEGER"}]
    connector = _make_sql_connector(columns=cols)
    result = SQLAdapter().introspect(
        connector, "columns", schema="public", table="orders", connection_path=tmp_path
    )
    assert result["columns"] == cols
    connector.get_columns.assert_called_once_with("orders", schema="public", catalog=None)


def test_introspect_invalid_scope_returns_error(tmp_path):
    connector = _make_sql_connector()
    result = SQLAdapter().introspect(connector, "indexes", connection_path=tmp_path)
    assert result["status"] == "error"
    assert "indexes" in result["error"]


def test_introspect_columns_requires_table(tmp_path):
    connector = _make_sql_connector()
    result = SQLAdapter().introspect(connector, "columns", connection_path=tmp_path)
    assert result["status"] == "error"
    assert "table" in result["error"].lower()
