"""Tests for FileAdapter — execute and introspect against a mock FileConnector."""

from unittest.mock import MagicMock

from db_mcp_models.gateway import DataRequest, EndpointQuery, SQLQuery

from db_mcp_data.gateway.adapter import ConnectorAdapter
from db_mcp_data.gateway.file_adapter import FileAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file_connector(*, rows=None, tables=None, columns=None):
    from db_mcp_data.connectors.file import FileConnector

    connector = MagicMock(spec=FileConnector)
    connector.execute_sql.return_value = rows if rows is not None else [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]
    connector.get_catalogs.return_value = [None]
    connector.get_schemas.return_value = [None]
    connector.get_tables.return_value = tables or [
        {"name": "users", "schema": None, "full_name": "users"}
    ]
    connector.get_columns.return_value = columns or [
        {"name": "name", "type": "VARCHAR"},
        {"name": "age", "type": "INTEGER"},
    ]
    return connector


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_file_adapter_satisfies_protocol():
    assert isinstance(FileAdapter(), ConnectorAdapter)


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

def test_can_handle_file_connector():
    from db_mcp_data.connectors.file import FileConnector
    connector = MagicMock(spec=FileConnector)
    assert FileAdapter().can_handle(connector) is True


def test_cannot_handle_api_connector():
    """APIConnector extends FileConnector but must not be handled by FileAdapter."""
    from db_mcp_data.connectors.api import APIConnector
    connector = MagicMock(spec=APIConnector)
    assert FileAdapter().can_handle(connector) is False


def test_cannot_handle_sql_connector():
    from db_mcp_data.connectors.sql import SQLConnector
    connector = MagicMock(spec=SQLConnector)
    assert FileAdapter().can_handle(connector) is False


def test_cannot_handle_arbitrary_object():
    assert FileAdapter().can_handle(object()) is False


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def test_execute_returns_success(tmp_path):
    connector = _make_file_connector()
    request = DataRequest(connection="local", query=SQLQuery(sql="SELECT * FROM users"))
    result = FileAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.is_success


def test_execute_returns_rows(tmp_path):
    rows = [{"name": "Alice", "age": 30}]
    connector = _make_file_connector(rows=rows)
    request = DataRequest(connection="local", query=SQLQuery(sql="SELECT * FROM users LIMIT 1"))
    result = FileAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.data == rows
    assert result.rows_returned == 1


def test_execute_infers_columns(tmp_path):
    connector = _make_file_connector(rows=[{"name": "Alice", "age": 30}])
    request = DataRequest(connection="local", query=SQLQuery(sql="SELECT * FROM users"))
    result = FileAdapter().execute(connector, request, connection_path=tmp_path)
    assert [c.name for c in result.columns] == ["name", "age"]


def test_execute_empty_result(tmp_path):
    connector = _make_file_connector(rows=[])
    request = DataRequest(connection="local", query=SQLQuery(sql="SELECT 1 WHERE false"))
    result = FileAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.data == []
    assert result.columns == []
    assert result.rows_returned == 0


def test_execute_passes_sql_to_connector(tmp_path):
    connector = _make_file_connector(rows=[])
    sql = "SELECT name FROM users WHERE age > 20"
    request = DataRequest(connection="local", query=SQLQuery(sql=sql))
    FileAdapter().execute(connector, request, connection_path=tmp_path)
    connector.execute_sql.assert_called_once_with(sql, None)


def test_execute_rejects_endpoint_query(tmp_path):
    connector = _make_file_connector()
    request = DataRequest(connection="local", query=EndpointQuery(endpoint="items"))
    result = FileAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.status == "error"
    assert "EndpointQuery" in result.error


def test_execute_wraps_connector_exception(tmp_path):
    from db_mcp_data.connectors.file import FileConnector
    connector = MagicMock(spec=FileConnector)
    connector.execute_sql.side_effect = Exception("no such table: missing")
    request = DataRequest(connection="local", query=SQLQuery(sql="SELECT * FROM missing"))
    result = FileAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.status == "error"
    assert "missing" in result.error


# ---------------------------------------------------------------------------
# introspect
# ---------------------------------------------------------------------------

def test_introspect_catalogs_returns_none_sentinel(tmp_path):
    connector = _make_file_connector()
    result = FileAdapter().introspect(connector, "catalogs", connection_path=tmp_path)
    assert result["catalogs"] == [None]


def test_introspect_schemas_returns_none_sentinel(tmp_path):
    connector = _make_file_connector()
    result = FileAdapter().introspect(connector, "schemas", connection_path=tmp_path)
    assert result["schemas"] == [None]


def test_introspect_tables(tmp_path):
    tables = [{"name": "users", "schema": None, "full_name": "users"}]
    connector = _make_file_connector(tables=tables)
    result = FileAdapter().introspect(connector, "tables", connection_path=tmp_path)
    assert result["tables"] == tables


def test_introspect_columns(tmp_path):
    cols = [{"name": "name", "type": "VARCHAR"}]
    connector = _make_file_connector(columns=cols)
    result = FileAdapter().introspect(
        connector, "columns", table="users", connection_path=tmp_path
    )
    assert result["columns"] == cols
    connector.get_columns.assert_called_once_with("users", schema=None, catalog=None)


def test_introspect_columns_requires_table(tmp_path):
    connector = _make_file_connector()
    result = FileAdapter().introspect(connector, "columns", connection_path=tmp_path)
    assert result["status"] == "error"
    assert "table" in result["error"].lower()


def test_introspect_invalid_scope(tmp_path):
    connector = _make_file_connector()
    result = FileAdapter().introspect(connector, "partitions", connection_path=tmp_path)
    assert result["status"] == "error"
