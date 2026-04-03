"""Tests for services/query.py using gateway adapter dispatch.

These tests verify the gateway path — run_sql without the execute_query /
direct_execute injection kwargs.  The connector is mocked at the dispatcher
level so no real database is touched.
"""

from unittest.mock import AsyncMock, MagicMock

import db_mcp_data.gateway as gw
import pytest
from db_mcp_data.execution.query_store import Query, QueryStatus
from db_mcp_models.gateway import ColumnMeta, DataResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sql_connector(rows=None):
    from db_mcp_data.connectors.sql import SQLConnector

    c = MagicMock(spec=SQLConnector)
    c.execute_sql.return_value = rows if rows is not None else [{"answer": 1}]
    return c


def _patch_connector(connector, monkeypatch):
    monkeypatch.setattr(
        "db_mcp_data.gateway.dispatcher.get_connector",
        lambda *, connection_path: connector,
    )
    # Patch the capabilities lookup used by gateway.capabilities() so that
    # MagicMock connectors (which don't expose .config) still resolve correctly.
    monkeypatch.setattr(
        "db_mcp_data.connectors.get_connector_capabilities",
        lambda c: {"supports_sql": True},
    )


# ---------------------------------------------------------------------------
# Direct SQL path via gateway (no execute_query kwarg)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_sql_direct_gateway_returns_success(monkeypatch, tmp_path):
    from db_mcp.services.query import run_sql

    connector = _make_sql_connector(rows=[{"n": 42}])
    _patch_connector(connector, monkeypatch)

    monkeypatch.setattr(
        "db_mcp.services.query.check_protocol_ack_gate",
        lambda *, connection, connection_path: None,
    )
    monkeypatch.setattr(
        "db_mcp.services.query.evaluate_sql_execution_policy",
        lambda *, sql, capabilities, confirmed, require_validate_first: (None, "SELECT", False),
    )

    result = await run_sql(
        connection="prod",
        sql="SELECT 42 AS n",
        connection_path=tmp_path,
        # no execute_query or direct_execute — gateway path
    )

    assert result["status"] == "success"
    assert result["data"] == [{"n": 42}]
    assert result["rows_returned"] == 1
    assert result["columns"] == ["n"]


@pytest.mark.asyncio
async def test_run_sql_direct_gateway_empty_result(monkeypatch, tmp_path):
    from db_mcp.services.query import run_sql

    connector = _make_sql_connector(rows=[])
    _patch_connector(connector, monkeypatch)

    monkeypatch.setattr(
        "db_mcp.services.query.check_protocol_ack_gate",
        lambda *, connection, connection_path: None,
    )
    monkeypatch.setattr(
        "db_mcp.services.query.evaluate_sql_execution_policy",
        lambda *, sql, capabilities, confirmed, require_validate_first: (None, "SELECT", False),
    )

    result = await run_sql(
        connection="prod",
        sql="SELECT 1 WHERE false",
        connection_path=tmp_path,
    )

    assert result["status"] == "success"
    assert result["data"] == []
    assert result["columns"] == []
    assert result["rows_returned"] == 0


@pytest.mark.asyncio
async def test_run_sql_direct_gateway_connector_error(monkeypatch, tmp_path):
    from db_mcp.services.query import run_sql

    connector = _make_sql_connector()
    connector.execute_sql.side_effect = Exception("table not found")
    _patch_connector(connector, monkeypatch)

    monkeypatch.setattr(
        "db_mcp.services.query.check_protocol_ack_gate",
        lambda *, connection, connection_path: None,
    )
    monkeypatch.setattr(
        "db_mcp.services.query.evaluate_sql_execution_policy",
        lambda *, sql, capabilities, confirmed, require_validate_first: (None, "SELECT", False),
    )

    result = await run_sql(
        connection="prod",
        sql="SELECT * FROM missing_table",
        connection_path=tmp_path,
    )

    assert result["status"] == "error"
    assert "table not found" in result["error"]


# ---------------------------------------------------------------------------
# Validated query path via gateway (no execute_query kwarg)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_sql_validated_query_via_gateway(monkeypatch, tmp_path):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="q-gw",
        sql="SELECT 99 AS val",
        status=QueryStatus.VALIDATED,
        connection="prod",
        cost_tier="low",
    )

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))
    monkeypatch.setattr(
        gw,
        "execute",
        AsyncMock(
            return_value=DataResponse(
                status="success",
                data=[{"val": 99}],
                columns=[ColumnMeta(name="val")],
                rows_returned=1,
            )
        ),
    )
    monkeypatch.setattr(gw, "mark_running", AsyncMock())
    monkeypatch.setattr(gw, "mark_complete", AsyncMock())
    monkeypatch.setattr(gw, "mark_error", AsyncMock())
    monkeypatch.setattr(
        "db_mcp.services.query.check_protocol_ack_gate",
        lambda *, connection, connection_path: None,
    )
    monkeypatch.setattr(
        "db_mcp.services.query.evaluate_sql_execution_policy",
        lambda *, sql, capabilities, confirmed, require_validate_first, query_id=None: (
            None, "SELECT", False
        ),
    )

    result = await run_sql(
        connection="prod",
        query_id="q-gw",
        connection_path=tmp_path,
        # no execute_query — gateway.execute() is now the dispatch path
    )

    assert result["status"] == "success"
    assert result["data"] == [{"val": 99}]
    assert result["query_id"] == "q-gw"
    gw.execute.assert_awaited_once_with("q-gw", connection_path=tmp_path, options=None)


@pytest.mark.asyncio
async def test_run_sql_validated_query_gateway_execution_error(monkeypatch, tmp_path):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="q-gw-fail",
        sql="SELECT boom()",
        status=QueryStatus.VALIDATED,
        connection="prod",
        cost_tier="low",
    )

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))
    monkeypatch.setattr(
        gw,
        "execute",
        AsyncMock(
            return_value=DataResponse(
                status="error",
                data=[],
                columns=[],
                rows_returned=0,
                error="boom() not defined",
            )
        ),
    )
    monkeypatch.setattr(gw, "mark_running", AsyncMock())
    monkeypatch.setattr(gw, "mark_complete", AsyncMock())
    monkeypatch.setattr(gw, "mark_error", AsyncMock())
    monkeypatch.setattr(
        "db_mcp.services.query.check_protocol_ack_gate",
        lambda *, connection, connection_path: None,
    )
    monkeypatch.setattr(
        "db_mcp.services.query.evaluate_sql_execution_policy",
        lambda *, sql, capabilities, confirmed, require_validate_first, query_id=None: (
            None, "SELECT", False
        ),
    )

    result = await run_sql(
        connection="prod",
        query_id="q-gw-fail",
        connection_path=tmp_path,
    )

    assert result["status"] == "error"
    assert "boom() not defined" in result["error"]
