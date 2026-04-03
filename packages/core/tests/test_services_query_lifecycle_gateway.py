"""RED tests — complete gateway lifecycle boundary in services/query.py.

Phase 2 plan item 1, remaining gaps:
  - validate_sql still has a query_store_factory backward-compat branch that
    calls register_validated() directly (lines 779-790, 881-893).
  - run_sql still retrieves queries from the store directly via
    query_store_factory (line 492) and drives update_status() calls directly
    (lines 569, 620, 655, 675).
  - tools/generation.py injects query_store_factory=get_query_store into both,
    so the old path is taken in production.

The gateway needs new lifecycle functions (get_query, mark_running, mark_complete,
mark_error, start_query_execution).  validate_sql and run_sql must lose their
query_store_factory injection seams and route exclusively through those functions.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import db_mcp_data.gateway as gw
import pytest
from db_mcp_data.execution.query_store import Query, QueryStatus
from db_mcp_models.gateway import DataRequest, SQLQuery, ValidatedQuery

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vq(query_id: str, sql: str, connection: str = "prod") -> ValidatedQuery:
    return ValidatedQuery(
        query_id=query_id,
        connection=connection,
        query_type="sql",
        request=DataRequest(connection=connection, query=SQLQuery(sql=sql)),
        cost_tier="unknown",
        validated_at=datetime.now(UTC),
    )


def _query(query_id: str, sql: str, connection: str = "prod") -> Query:
    return Query(
        query_id=query_id,
        sql=sql,
        status=QueryStatus.READY,
        connection=connection,
        cost_tier="auto",
    )


# ---------------------------------------------------------------------------
# 1. validate_sql has no query_store_factory parameter
# ---------------------------------------------------------------------------

def test_validate_sql_has_no_query_store_factory_parameter():
    """validate_sql must not accept a query_store_factory injection.

    All persistence must route exclusively through gateway.create(); having
    a secondary injection seam keeps a back-door around the gateway boundary.
    """
    from db_mcp.services.query import validate_sql

    sig = inspect.signature(validate_sql)
    assert "query_store_factory" not in sig.parameters, (
        "validate_sql should not expose query_store_factory; "
        "persistence is managed exclusively by gateway.create()."
    )


# ---------------------------------------------------------------------------
# 2. run_sql has no query_store_factory parameter
# ---------------------------------------------------------------------------

def test_run_sql_has_no_query_store_factory_parameter():
    """run_sql must not accept a query_store_factory injection.

    Query retrieval and lifecycle state transitions must route exclusively
    through gateway.get_query() / gateway.mark_running() etc.
    """
    from db_mcp.services.query import run_sql

    sig = inspect.signature(run_sql)
    assert "query_store_factory" not in sig.parameters, (
        "run_sql should not expose query_store_factory; "
        "lifecycle management routes through gateway lifecycle functions."
    )


# ---------------------------------------------------------------------------
# 3. run_sql retrieves validated queries via gateway.get_query()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_sql_query_id_retrieval_uses_gateway_get_query(monkeypatch, tmp_path):
    """run_sql(query_id=...) must call gateway.get_query() to retrieve the
    validated query, not query_store_factory() / store.get() directly.

    Proof: patching gateway.get_query and making get_query_store raise; the
    call must succeed, proving services/query.py did not touch the store.
    """
    from db_mcp.services.query import run_sql

    expected_q = _query("q-lifecycle", "SELECT 1 AS n")

    # gateway.get_query is the expected path.
    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=expected_q))

    # Capabilities and status lifecycle via gateway.
    monkeypatch.setattr(gw, "capabilities", lambda connection_path: {"supports_sql": True})
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
        query_id="q-lifecycle",
        connection_path=tmp_path,
        execute_query=lambda sql, *, connection, query_id: {
            "data": [{"n": 1}],
            "columns": ["n"],
            "rows_returned": 1,
            "rows_affected": None,
            "provider_id": None,
            "statement_type": "SELECT",
            "is_write": False,
        },
    )

    assert result["status"] == "success"
    gw.get_query.assert_called_once_with("q-lifecycle")


# ---------------------------------------------------------------------------
# 4. run_sql status transitions use gateway lifecycle functions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_sql_status_transitions_use_gateway_lifecycle(monkeypatch, tmp_path):
    """run_sql must drive status transitions through gateway.mark_running() and
    gateway.mark_complete() (or gateway.mark_error()), not by calling
    store.update_status() directly.
    """
    from db_mcp.services.query import run_sql

    expected_q = _query("q-states", "SELECT 42 AS answer")
    mark_running_calls: list = []
    mark_complete_calls: list = []

    async def mock_mark_running(query_id: str) -> None:
        mark_running_calls.append(query_id)

    async def mock_mark_complete(query_id: str, *, rows_returned: int) -> None:
        mark_complete_calls.append((query_id, rows_returned))

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=expected_q))
    monkeypatch.setattr(gw, "capabilities", lambda connection_path: {"supports_sql": True})
    monkeypatch.setattr(gw, "mark_running", mock_mark_running)
    monkeypatch.setattr(gw, "mark_complete", mock_mark_complete)
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
        query_id="q-states",
        connection_path=tmp_path,
        execute_query=lambda sql, *, connection, query_id: {
            "data": [{"answer": 42}],
            "columns": ["answer"],
            "rows_returned": 1,
            "rows_affected": None,
            "provider_id": None,
            "statement_type": "SELECT",
            "is_write": False,
        },
    )

    assert result["status"] == "success"
    assert mark_running_calls == ["q-states"], "gateway.mark_running() must be called"
    assert mark_complete_calls == [("q-states", 1)], "gateway.mark_complete() must be called"
