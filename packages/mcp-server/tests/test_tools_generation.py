"""Tests for db_mcp_server.tools.generation wrapper functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def _patch_inject():
    with patch(
        "db_mcp_server.tools.generation.inject_protocol", side_effect=lambda x: x
    ) as m:
        yield m


@pytest.mark.asyncio
async def test_validate_sql(_patch_inject):
    mock_result = {"valid": True, "query_id": "abc"}

    with (
        patch(
            "db_mcp_server.tools.generation._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.generation.svc_validate_sql",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_validate,
    ):
        from db_mcp_server.tools.generation import _validate_sql

        result = await _validate_sql(sql="SELECT 1", connection="mydb")

    assert result == {"valid": True, "query_id": "abc"}
    mock_validate.assert_called_once()
    call_kwargs = mock_validate.call_args.kwargs
    assert call_kwargs["sql"] == "SELECT 1"
    assert call_kwargs["connection"] == "mydb"
    assert call_kwargs["connection_path"] == "/tmp/conn"


@pytest.mark.asyncio
async def test_run_sql_with_query_id(_patch_inject):
    mock_result = {"rows": [{"x": 1}]}
    mock_connector = MagicMock()
    mock_caps = {"supports_validate_sql": True}

    with (
        patch(
            "db_mcp_server.tools.generation._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.generation.get_connector",
            return_value=mock_connector,
        ),
        patch(
            "db_mcp_server.tools.generation.get_connector_capabilities",
            return_value=mock_caps,
        ),
        patch(
            "db_mcp_server.tools.generation.svc_run_sql",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_run,
    ):
        from db_mcp_server.tools.generation import _run_sql

        result = await _run_sql(connection="mydb", query_id="q123")

    assert result == {"rows": [{"x": 1}]}
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["query_id"] == "q123"
    assert call_kwargs["connection"] == "mydb"


@pytest.mark.asyncio
async def test_run_sql_direct_sql_path(_patch_inject):
    mock_result = {"rows": [{"y": 2}]}
    mock_connector = MagicMock()
    mock_caps = {"supports_validate_sql": False}

    with (
        patch(
            "db_mcp_server.tools.generation._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.generation.get_connector",
            return_value=mock_connector,
        ),
        patch(
            "db_mcp_server.tools.generation.get_connector_capabilities",
            return_value=mock_caps,
        ),
        patch(
            "db_mcp_server.tools.generation.svc_run_sql",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_run,
    ):
        from db_mcp_server.tools.generation import _run_sql

        result = await _run_sql(connection="mydb", sql="SELECT 1")

    assert result == {"rows": [{"y": 2}]}
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["sql"] == "SELECT 1"
    assert call_kwargs["query_id"] is None


@pytest.mark.asyncio
async def test_export_results_csv():
    mock_connector = MagicMock()
    mock_engine = MagicMock()
    mock_conn_ctx = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"id": 1, "name": "alice"}
    mock_result_proxy = MagicMock()
    mock_result_proxy.keys.return_value = ["id", "name"]
    mock_result_proxy.__iter__ = lambda self: iter([mock_row])
    mock_conn_ctx.execute.return_value = mock_result_proxy
    mock_conn_ctx.__enter__ = lambda self: self
    mock_conn_ctx.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn_ctx
    mock_connector.get_engine.return_value = mock_engine

    with (
        patch(
            "db_mcp_server.tools.generation._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.generation.validate_read_only",
            return_value=(True, None),
        ),
        patch(
            "db_mcp_server.tools.generation.get_connector",
            return_value=mock_connector,
        ),
        patch(
            "db_mcp_server.tools.generation.isinstance",
            side_effect=lambda obj, cls: True,
            create=True,
        ) if False else patch(
            "db_mcp_server.tools.generation.SQLConnector",
            new=type(mock_connector),
        ),
    ):
        from db_mcp_server.tools.generation import _export_results

        result = await _export_results(
            sql="SELECT id, name FROM users",
            connection="mydb",
            format="csv",
        )

    assert result["status"] == "complete"
    assert result["format"] == "csv"
    assert "content" in result
    assert result["rows_exported"] == 1


@pytest.mark.asyncio
async def test_export_results_rejected():
    with patch(
        "db_mcp_server.tools.generation._resolve_connection_path",
        return_value="/tmp/conn",
    ), patch(
        "db_mcp_server.tools.generation.validate_read_only",
        return_value=(False, "Write statements not allowed"),
    ):
        from db_mcp_server.tools.generation import _export_results

        result = await _export_results(
            sql="DROP TABLE users", connection="mydb"
        )

    assert result["status"] == "rejected"
    assert "error" in result


@pytest.mark.asyncio
async def test_get_result_from_query_store(_patch_inject):
    mock_query = MagicMock()
    mock_query.status = "complete"
    mock_query.execution_id = "exec-1"
    mock_query.rows_returned = 1
    mock_query.error = None

    mock_exec_result = MagicMock()
    mock_exec_result.data = [{"a": 1}]
    mock_exec_result.columns = ["a"]
    mock_exec_result.rows_returned = 1

    mock_engine = MagicMock()
    mock_engine.get_result.return_value = mock_exec_result

    mock_store = MagicMock()
    mock_store.get = AsyncMock(return_value=mock_query)

    with (
        patch(
            "db_mcp_server.tools.generation.get_query_store",
            return_value=mock_store,
        ),
        patch(
            "db_mcp_server.tools.generation.get_execution_engine",
            return_value=mock_engine,
        ),
        patch(
            "db_mcp_data.execution.query_store.QueryStatus",
        ) as MockQS,
    ):
        MockQS.COMPLETE = "complete"
        MockQS.ERROR = "error"

        from db_mcp_server.tools.generation import _get_result

        result = await _get_result(query_id="q1", connection="mydb")

    assert result["status"] == "complete"
    assert result["query_id"] == "q1"
    assert result["data"] == [{"a": 1}]


@pytest.mark.asyncio
async def test_get_result_from_execution_engine(_patch_inject):
    mock_store = MagicMock()
    mock_store.get = AsyncMock(return_value=None)

    from db_mcp_data.execution import ExecutionState

    mock_exec_result = MagicMock()
    mock_exec_result.state = ExecutionState.SUCCEEDED
    mock_exec_result.data = [{"b": 2}]
    mock_exec_result.columns = ["b"]
    mock_exec_result.rows_returned = 1
    mock_exec_result.duration_ms = 42

    mock_engine = MagicMock()
    mock_engine.get_result.return_value = mock_exec_result

    with (
        patch(
            "db_mcp_server.tools.generation.get_query_store",
            return_value=mock_store,
        ),
        patch(
            "db_mcp_server.tools.generation._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.generation.get_execution_engine",
            return_value=mock_engine,
        ),
    ):
        from db_mcp_server.tools.generation import _get_result

        result = await _get_result(query_id="q2", connection="mydb")

    assert result["status"] == "complete"
    assert result["data"] == [{"b": 2}]
    assert result["rows_returned"] == 1
    mock_engine.get_result.assert_called_once_with("q2")
