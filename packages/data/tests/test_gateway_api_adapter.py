"""Tests for APIAdapter — execute (endpoint + sql paths) and introspect."""

from unittest.mock import MagicMock

from db_mcp_models.gateway import DataRequest, EndpointQuery, SQLQuery

from db_mcp_data.gateway.adapter import ConnectorAdapter
from db_mcp_data.gateway.api_adapter import APIAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_connector(
    *,
    endpoint_rows=None,
    endpoint_error=None,
    sql_rows=None,
    catalogs=None,
    schemas=None,
    tables=None,
    columns=None,
):
    from db_mcp_data.connectors.api import APIConnector

    connector = MagicMock(spec=APIConnector)

    if endpoint_error:
        connector.query_endpoint.return_value = {"error": endpoint_error}
    else:
        rows = endpoint_rows if endpoint_rows is not None else [{"id": 1, "name": "alpha"}]
        connector.query_endpoint.return_value = {"data": rows, "rows_returned": len(rows)}

    connector.execute_sql.return_value = sql_rows if sql_rows is not None else [
        {"count": 42}
    ]

    connector.get_catalogs.return_value = catalogs or [None]
    connector.get_schemas.return_value = schemas or ["public"]
    connector.get_tables.return_value = tables or [
        {"name": "dashboards", "schema": "public", "full_name": "public.dashboards"}
    ]
    connector.get_columns.return_value = columns or [{"name": "id", "type": "INTEGER"}]
    return connector


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_api_adapter_satisfies_protocol():
    assert isinstance(APIAdapter(), ConnectorAdapter)


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

def test_can_handle_api_connector():
    from db_mcp_data.connectors.api import APIConnector
    connector = MagicMock(spec=APIConnector)
    assert APIAdapter().can_handle(connector) is True


def test_cannot_handle_sql_connector():
    from db_mcp_data.connectors.sql import SQLConnector
    connector = MagicMock(spec=SQLConnector)
    assert APIAdapter().can_handle(connector) is False


def test_cannot_handle_plain_file_connector():
    """FileConnector alone (not APIConnector) should not be handled by APIAdapter."""
    from db_mcp_data.connectors.api import APIConnector
    from db_mcp_data.connectors.file import FileConnector
    connector = MagicMock(spec=FileConnector)
    # Ensure it's not also an APIConnector
    assert not isinstance(connector, APIConnector)
    assert APIAdapter().can_handle(connector) is False


# ---------------------------------------------------------------------------
# execute — EndpointQuery path
# ---------------------------------------------------------------------------

def test_execute_endpoint_returns_success(tmp_path):
    connector = _make_api_connector()
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(endpoint="dashboards"),
    )
    result = APIAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.is_success


def test_execute_endpoint_returns_rows_and_count(tmp_path):
    rows = [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]
    connector = _make_api_connector(endpoint_rows=rows)
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(endpoint="dashboards"),
    )
    result = APIAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.data == rows
    assert result.rows_returned == 2


def test_execute_endpoint_infers_columns(tmp_path):
    rows = [{"id": 1, "name": "alpha"}]
    connector = _make_api_connector(endpoint_rows=rows)
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(endpoint="dashboards"),
    )
    result = APIAdapter().execute(connector, request, connection_path=tmp_path)
    assert [c.name for c in result.columns] == ["id", "name"]


def test_execute_endpoint_passes_params_and_method(tmp_path):
    connector = _make_api_connector()
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(
            endpoint="reports",
            params={"status": "active"},
            method="POST",
            max_pages=2,
        ),
    )
    APIAdapter().execute(connector, request, connection_path=tmp_path)
    connector.query_endpoint.assert_called_once_with(
        "reports",
        params={"status": "active"},
        max_pages=2,
        method_override="POST",
    )


def test_execute_endpoint_propagates_api_error(tmp_path):
    connector = _make_api_connector(endpoint_error="Not found")
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(endpoint="missing"),
    )
    result = APIAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.status == "error"
    assert "Not found" in result.error


def test_execute_endpoint_wraps_exception(tmp_path):
    from db_mcp_data.connectors.api import APIConnector
    connector = MagicMock(spec=APIConnector)
    connector.query_endpoint.side_effect = RuntimeError("network timeout")
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(endpoint="dashboards"),
    )
    result = APIAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.status == "error"
    assert "network timeout" in result.error


# ---------------------------------------------------------------------------
# execute — SQLQuery path (API SQL, e.g. Dune)
# ---------------------------------------------------------------------------

def test_execute_sql_query_returns_success(tmp_path):
    connector = _make_api_connector(sql_rows=[{"result": 1}])
    request = DataRequest(
        connection="dune",
        query=SQLQuery(sql="SELECT count(*) AS result FROM transfers"),
    )
    result = APIAdapter().execute(connector, request, connection_path=tmp_path)
    assert result.is_success
    assert result.data == [{"result": 1}]


def test_execute_sql_query_infers_columns(tmp_path):
    connector = _make_api_connector(sql_rows=[{"count": 42}])
    request = DataRequest(connection="dune", query=SQLQuery(sql="SELECT count(*)"))
    result = APIAdapter().execute(connector, request, connection_path=tmp_path)
    assert [c.name for c in result.columns] == ["count"]


# ---------------------------------------------------------------------------
# introspect
# ---------------------------------------------------------------------------

def test_introspect_catalogs(tmp_path):
    connector = _make_api_connector(catalogs=["default"])
    result = APIAdapter().introspect(connector, "catalogs", connection_path=tmp_path)
    assert result["catalogs"] == ["default"]


def test_introspect_schemas(tmp_path):
    connector = _make_api_connector(schemas=["public", "metrics"])
    result = APIAdapter().introspect(connector, "schemas", connection_path=tmp_path)
    assert result["schemas"] == ["public", "metrics"]


def test_introspect_tables(tmp_path):
    tables = [{"name": "dashboards", "schema": "public", "full_name": "public.dashboards"}]
    connector = _make_api_connector(tables=tables)
    result = APIAdapter().introspect(
        connector, "tables", schema="public", connection_path=tmp_path
    )
    assert result["tables"] == tables


def test_introspect_columns(tmp_path):
    cols = [{"name": "id", "type": "INTEGER"}]
    connector = _make_api_connector(columns=cols)
    result = APIAdapter().introspect(
        connector, "columns", table="dashboards", connection_path=tmp_path
    )
    assert result["columns"] == cols


def test_introspect_invalid_scope(tmp_path):
    connector = _make_api_connector()
    result = APIAdapter().introspect(connector, "indexes", connection_path=tmp_path)
    assert result["status"] == "error"
