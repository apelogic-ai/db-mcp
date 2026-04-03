"""Adapters must return DataResponse from execute(), not raw dicts."""

from unittest.mock import MagicMock

import pytest
from db_mcp_models.gateway import ColumnMeta, DataResponse


def _sql_connector(rows=None):
    from db_mcp_data.connectors.sql import SQLConnector
    c = MagicMock(spec=SQLConnector)
    c.execute_sql.return_value = rows if rows is not None else [{"id": 1, "val": "a"}]
    return c


def _api_connector(endpoint_rows=None, sql_rows=None):
    from db_mcp_data.connectors.api import APIConnector
    c = MagicMock(spec=APIConnector)
    rows = endpoint_rows if endpoint_rows is not None else [{"id": 1}]
    c.query_endpoint.return_value = {"data": rows, "rows_returned": len(rows)}
    c.execute_sql.return_value = sql_rows if sql_rows is not None else [{"n": 42}]
    return c


def _file_connector(rows=None):
    from db_mcp_data.connectors.file import FileConnector
    c = MagicMock(spec=FileConnector)
    c.execute_sql.return_value = rows if rows is not None else [{"name": "Alice"}]
    return c


# ---------------------------------------------------------------------------
# SQLAdapter
# ---------------------------------------------------------------------------

def test_sql_adapter_execute_returns_data_response(tmp_path):
    from db_mcp_models.gateway import DataRequest, SQLQuery

    from db_mcp_data.gateway.sql_adapter import SQLAdapter

    resp = SQLAdapter().execute(
        _sql_connector(rows=[{"id": 1}]),
        DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1 AS id")),
        connection_path=tmp_path,
    )
    assert isinstance(resp, DataResponse)


def test_sql_adapter_execute_success_fields(tmp_path):
    from db_mcp_models.gateway import DataRequest, SQLQuery

    from db_mcp_data.gateway.sql_adapter import SQLAdapter

    resp = SQLAdapter().execute(
        _sql_connector(rows=[{"id": 1, "val": "a"}]),
        DataRequest(connection="prod", query=SQLQuery(sql="SELECT id, val FROM t")),
        connection_path=tmp_path,
    )
    assert resp.is_success
    assert resp.data == [{"id": 1, "val": "a"}]
    assert resp.rows_returned == 1
    assert resp.columns == [ColumnMeta(name="id"), ColumnMeta(name="val")]
    assert resp.error is None


def test_sql_adapter_execute_error_returns_data_response(tmp_path):
    from db_mcp_models.gateway import DataRequest, SQLQuery

    from db_mcp_data.gateway.sql_adapter import SQLAdapter

    connector = _sql_connector()
    connector.execute_sql.side_effect = Exception("no such table")
    resp = SQLAdapter().execute(
        connector,
        DataRequest(connection="prod", query=SQLQuery(sql="SELECT * FROM missing")),
        connection_path=tmp_path,
    )
    assert isinstance(resp, DataResponse)
    assert resp.status == "error"
    assert "no such table" in resp.error


# ---------------------------------------------------------------------------
# APIAdapter
# ---------------------------------------------------------------------------

def test_api_adapter_execute_endpoint_returns_data_response(tmp_path):
    from db_mcp_models.gateway import DataRequest, EndpointQuery

    from db_mcp_data.gateway.api_adapter import APIAdapter

    resp = APIAdapter().execute(
        _api_connector(endpoint_rows=[{"id": 1}]),
        DataRequest(connection="mb", query=EndpointQuery(endpoint="dashboards")),
        connection_path=tmp_path,
    )
    assert isinstance(resp, DataResponse)
    assert resp.is_success
    assert resp.rows_returned == 1


def test_api_adapter_execute_sql_returns_data_response(tmp_path):
    from db_mcp_models.gateway import DataRequest, SQLQuery

    from db_mcp_data.gateway.api_adapter import APIAdapter

    resp = APIAdapter().execute(
        _api_connector(sql_rows=[{"n": 42}]),
        DataRequest(connection="dune", query=SQLQuery(sql="SELECT 42 AS n")),
        connection_path=tmp_path,
    )
    assert isinstance(resp, DataResponse)
    assert resp.data == [{"n": 42}]


# ---------------------------------------------------------------------------
# FileAdapter
# ---------------------------------------------------------------------------

def test_file_adapter_execute_returns_data_response(tmp_path):
    from db_mcp_models.gateway import DataRequest, SQLQuery

    from db_mcp_data.gateway.file_adapter import FileAdapter

    resp = FileAdapter().execute(
        _file_connector(rows=[{"name": "Alice"}]),
        DataRequest(connection="local", query=SQLQuery(sql="SELECT name FROM users")),
        connection_path=tmp_path,
    )
    assert isinstance(resp, DataResponse)
    assert resp.is_success
    assert resp.columns == [ColumnMeta(name="name")]


# ---------------------------------------------------------------------------
# gateway.run() returns DataResponse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gateway_run_returns_data_response(tmp_path):
    from unittest.mock import patch

    from db_mcp_models.gateway import DataRequest, SQLQuery

    import db_mcp_data.gateway as gateway

    connector = _sql_connector(rows=[{"x": 1}])
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = await gateway.run(
            DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1 AS x")),
            connection_path=tmp_path,
        )
    assert isinstance(result, DataResponse)
    assert result.is_success
    assert result.data == [{"x": 1}]
