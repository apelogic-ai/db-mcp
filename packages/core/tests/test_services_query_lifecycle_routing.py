"""RED tests — services/query.py lifecycle routing through the gateway.

Phase 2 plan, item 1: services/query.py must route capability resolution
through gateway.capabilities() and query persistence through gateway.create()
rather than calling get_connector() / store.register_validated() directly.

Each test patches the *direct* import in services.query to raise, and patches
the gateway surface to return suitable stubs.  The tests fail RED because the
current implementation still uses the old direct paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import db_mcp_data.gateway as gw
import pytest
from db_mcp_data.execution.query_store import Query, QueryStatus
from db_mcp_models.gateway import DataRequest, SQLQuery, ValidatedQuery

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _validated_query(query_id: str, sql: str, connection: str = "prod") -> ValidatedQuery:
    return ValidatedQuery(
        query_id=query_id,
        connection=connection,
        query_type="sql",
        request=DataRequest(connection=connection, query=SQLQuery(sql=sql)),
        cost_tier="unknown",
        validated_at=datetime.now(UTC),
    )


def _raise_get_connector(*, connection_path):
    raise AssertionError(
        "services/query.py must not call get_connector() directly; "
        "use gateway.capabilities() instead"
    )


def _raise_get_query_store():
    raise AssertionError(
        "services/query.py must not call get_query_store() directly for persistence; "
        "use gateway.create() instead"
    )


# ---------------------------------------------------------------------------
# 1. validate_sql — capability resolution goes through gateway.capabilities()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_sql_capability_check_uses_gateway_not_get_connector(
    monkeypatch, tmp_path
):
    """validate_sql must call gateway.capabilities() instead of get_connector()
    when no connector/capabilities override is supplied."""
    from db_mcp.services.query import validate_sql

    # Patch the direct import in services/query.py to raise.
    monkeypatch.setattr("db_mcp.services.query.get_connector", _raise_get_connector)

    # Provide capabilities via the gateway surface.
    monkeypatch.setattr(
        gw,
        "capabilities",
        lambda connection_path: {"supports_validate_sql": False},
    )

    result = await validate_sql(
        sql="SELECT 1",
        connection="prod",
        connection_path=tmp_path,
    )

    # supports_validate_sql=False → validation not supported response
    assert result["valid"] is False
    assert "not supported" in result["error"]


# ---------------------------------------------------------------------------
# 2a. validate_sql — write path persists via gateway.create(), not register_validated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_sql_write_path_persists_via_gateway_create(monkeypatch, tmp_path):
    """validate_sql (write statement) must call gateway.create() instead of
    query_store_factory() → store.register_validated()."""
    from db_mcp.services.query import validate_sql

    expected_qid = "gw-write-001"
    gateway_created: list[tuple] = []

    async def mock_gateway_create(request, *, connection_path=None, **kwargs):
        gateway_created.append((request, kwargs))
        return _validated_query(expected_qid, request.query.sql, request.connection)

    monkeypatch.setattr("db_mcp.services.query.get_connector", _raise_get_connector)
    monkeypatch.setattr(
        gw,
        "capabilities",
        lambda connection_path: {
            "supports_validate_sql": True,
            "allow_sql_writes": True,
            "allowed_write_statements": ["INSERT"],
            "require_write_confirmation": True,
        },
    )
    monkeypatch.setattr(gw, "create", mock_gateway_create)

    result = await validate_sql(
        sql="INSERT INTO orders(id) VALUES (1)",
        connection="prod",
        connection_path=tmp_path,
    )

    assert result["valid"] is True
    assert result["query_id"] == expected_qid
    assert result["is_write"] is True
    assert len(gateway_created) == 1, "gateway.create() must be called exactly once"


# ---------------------------------------------------------------------------
# 2b. validate_sql — read/EXPLAIN path persists via gateway.create()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_sql_read_path_persists_via_gateway_create(monkeypatch, tmp_path):
    """validate_sql (SELECT + EXPLAIN) must call gateway.create() instead of
    query_store_factory() → store.register_validated()."""
    from db_mcp_data.validation.explain import CostTier, ExplainResult

    from db_mcp.services.query import validate_sql

    expected_qid = "gw-read-002"
    gateway_created: list[tuple] = []

    async def mock_gateway_create(request, *, connection_path=None, **kwargs):
        gateway_created.append((request, kwargs))
        return _validated_query(expected_qid, request.query.sql, request.connection)

    def mock_explain(sql, *, connection_path):
        return ExplainResult(
            valid=True,
            explanation=[{"plan": "Seq Scan on orders"}],
            estimated_rows=500,
            estimated_cost=12.5,
            estimated_size_gb=None,
            cost_tier=CostTier.AUTO,
            tier_reason="Low cost",
        )

    monkeypatch.setattr("db_mcp.services.query.get_connector", _raise_get_connector)
    monkeypatch.setattr(
        gw,
        "capabilities",
        lambda connection_path: {"supports_validate_sql": True},
    )
    monkeypatch.setattr(gw, "create", mock_gateway_create)
    monkeypatch.setattr("db_mcp.services.query.explain_sql", mock_explain)

    result = await validate_sql(
        sql="SELECT * FROM orders",
        connection="prod",
        connection_path=tmp_path,
    )

    assert result["valid"] is True
    assert result["query_id"] == expected_qid
    assert result["is_write"] is False
    assert result["estimated_rows"] == 500
    assert len(gateway_created) == 1, "gateway.create() must be called exactly once"


# ---------------------------------------------------------------------------
# 3. run_sql (query-id path) — capability check goes through gateway.capabilities()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_sql_query_id_path_capability_check_uses_gateway(monkeypatch, tmp_path):
    """run_sql(query_id=...) must resolve connector capabilities through
    gateway.capabilities() instead of calling get_connector() directly."""
    from db_mcp.services.query import run_sql

    validated_q = Query(
        query_id="q-gw-cap",
        sql="SELECT 1 AS n",
        status=QueryStatus.VALIDATED,
        connection="prod",
        cost_tier="auto",
    )

    # Patch the direct import to raise.
    monkeypatch.setattr("db_mcp.services.query.get_connector", _raise_get_connector)

    # Gateway provides capabilities and query lifecycle.
    monkeypatch.setattr(
        gw,
        "capabilities",
        lambda connection_path: {"supports_sql": True},
    )
    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=validated_q))
    from db_mcp_models.gateway import ColumnMeta, DataResponse
    monkeypatch.setattr(
        gw,
        "execute",
        AsyncMock(
            return_value=DataResponse(
                status="success",
                data=[{"n": 1}],
                columns=[ColumnMeta(name="n")],
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
        query_id="q-gw-cap",
        connection_path=tmp_path,
        # no connector or capabilities override — must go through gateway
    )

    assert result["status"] == "success"
    assert result["data"] == [{"n": 1}]
