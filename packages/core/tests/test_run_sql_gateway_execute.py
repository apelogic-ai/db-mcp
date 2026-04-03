"""RED test — run_sql must route synchronous query_id dispatch through
gateway.execute(), not through ExecutionEngine.submit_sync + _validated_runner.

Plan step 2.09: Wire services/query.py to use gateway.execute().

The production path (tools/generation.py) must also stop injecting
execute_query=_execute_query for the query-id path; once gateway.execute()
is wired the injection seam is removed and the service always routes through
the gateway boundary.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import db_mcp_data.gateway as gw
import pytest
from db_mcp_data.execution.query_store import Query, QueryStatus
from db_mcp_models.gateway import ColumnMeta, DataResponse


def _query(query_id: str, sql: str, connection: str = "prod") -> Query:
    return Query(
        query_id=query_id,
        sql=sql,
        status=QueryStatus.READY,
        connection=connection,
        cost_tier="auto",
    )


# ---------------------------------------------------------------------------
# 1. run_sql — synchronous query_id path calls gateway.execute()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_sql_query_id_sync_path_calls_gateway_execute(monkeypatch, tmp_path):
    """run_sql(query_id=...) must call gateway.execute() for synchronous dispatch.

    When no execute_query callback is injected, execution routes through
    gateway.execute(), not ExecutionEngine.submit_sync + _validated_runner.

    Proof: monkeypatch gateway.execute to record the call; the test passes only
    when run_sql actually calls it.
    """
    from db_mcp.services.query import run_sql

    expected_q = _query("q-gw-exec", "SELECT 42 AS answer")
    execute_calls: list[str] = []

    async def mock_gateway_execute(query_id, *, connection_path=None, options=None):
        execute_calls.append(query_id)
        return DataResponse(
            status="success",
            data=[{"answer": 42}],
            columns=[ColumnMeta(name="answer")],
            rows_returned=1,
        )

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=expected_q))
    monkeypatch.setattr(gw, "capabilities", lambda connection_path: {"supports_sql": True})
    monkeypatch.setattr(gw, "execute", mock_gateway_execute)
    monkeypatch.setattr(gw, "mark_running", AsyncMock())
    monkeypatch.setattr(gw, "mark_complete", AsyncMock())
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
        query_id="q-gw-exec",
        connection_path=tmp_path,
        # No execute_query injection — must route through gateway.execute()
    )

    assert result["status"] == "success"
    assert result["data"] == [{"answer": 42}]
    assert result["rows_returned"] == 1
    assert execute_calls == ["q-gw-exec"], (
        "gateway.execute() must be called; run_sql still routes through "
        "ExecutionEngine.submit_sync + _validated_runner instead"
    )


# ---------------------------------------------------------------------------
# 2. tools/generation.py — query_id path does not inject execute_query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generation_run_sql_query_id_path_does_not_inject_execute_query():
    """tools/generation.py must not pass execute_query= for the query_id path.

    The injection bypasses gateway.execute() in the service layer.  Removing
    it lets run_sql route through the gateway unconditionally for query-id
    execution.

    Proof: capture kwargs forwarded to query_service.run_sql; execute_query
    must be absent.
    """
    from db_mcp.tools.generation import _run_sql

    captured: dict = {}

    async def _fake_run_sql(**kwargs):
        captured.update(kwargs)
        return {
            "status": "success",
            "query_id": "q-1",
            "execution_id": "q-1",
            "state": "succeeded",
            "sql": "SELECT 1",
            "data": [],
            "columns": [],
            "rows_returned": 0,
            "duration_ms": None,
            "provider_id": None,
            "cost_tier": "auto",
            "statement_type": None,
            "is_write": False,
            "rows_affected": None,
        }

    from unittest.mock import MagicMock

    fake_connector = MagicMock()
    fake_connector.config = MagicMock()
    fake_connector.config.capabilities = {}
    fake_connector.config.profile = ""

    with (
        patch("db_mcp.tools.generation.query_service.run_sql", side_effect=_fake_run_sql),
        patch("db_mcp.tools.generation.get_connector", return_value=fake_connector),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"supports_sql": True, "supports_validate_sql": True},
        ),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value="/tmp/test-connection",
        ),
    ):
        await _run_sql(query_id="q-1", connection="test_connection")

    assert "execute_query" not in captured, (
        "tools/generation.py must not pass execute_query= for the query_id path; "
        f"got captured keys: {list(captured)}"
    )
    assert "execution_engine" not in captured, (
        "tools/generation.py must not pass execution_engine= for the query_id path; "
        f"got captured keys: {list(captured)}"
    )
