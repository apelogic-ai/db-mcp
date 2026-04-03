"""Tests for query services."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import db_mcp_data.gateway as gw
import pytest
from db_mcp_data.execution.models import ExecutionState
from db_mcp_data.execution.query_store import Query, QueryStatus
from db_mcp_models.gateway import DataRequest, SQLQuery, ValidatedQuery


def _vq(query_id: str, sql: str, cost_tier: str = "unknown") -> ValidatedQuery:
    """Minimal ValidatedQuery stub for tests."""
    return ValidatedQuery(
        query_id=query_id,
        connection="prod",
        query_type="sql",
        request=DataRequest(connection="prod", query=SQLQuery(sql=sql)),
        cost_tier=cost_tier,
        validated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_validate_sql_reports_unsupported_for_connector(monkeypatch):
    from db_mcp.services.query import validate_sql

    result = await validate_sql(
        sql="SELECT 1",
        connection="prod",
        connection_path=Path("/tmp/prod"),
        capabilities={"supports_validate_sql": False},
    )

    assert result == {
        "valid": False,
        "error": "Validation is not supported for this connector.",
        "sql": "SELECT 1",
        "query_id": None,
        "guidance": {
            "next_steps": [
                "Call run_sql(connection=..., sql=...) directly",
                "Or use api_query for connector-specific endpoints",
            ]
        },
    }


@pytest.mark.asyncio
async def test_validate_sql_rejects_write_when_write_mode_disabled(monkeypatch):
    from db_mcp.services.query import validate_sql

    result = await validate_sql(
        sql="INSERT INTO users(id) VALUES (1)",
        connection="prod",
        connection_path=Path("/tmp/prod"),
        capabilities={"supports_validate_sql": True},
    )

    assert result == {
        "valid": False,
        "error": "Statement type 'INSERT' is not allowed (write mode disabled).",
        "sql": "INSERT INTO users(id) VALUES (1)",
        "query_id": None,
        "statement_type": "INSERT",
        "is_write": True,
    }


@pytest.mark.asyncio
async def test_validate_sql_registers_allowed_write_query(monkeypatch):
    from db_mcp.services.query import validate_sql

    monkeypatch.setattr(
        gw,
        "create",
        AsyncMock(return_value=_vq("q-1", "INSERT INTO users(id) VALUES (1)", "confirm")),
    )

    result = await validate_sql(
        sql="INSERT INTO users(id) VALUES (1)",
        connection="prod",
        connection_path=Path("/tmp/prod"),
        capabilities={
            "supports_validate_sql": True,
            "allow_sql_writes": True,
            "allowed_write_statements": ["INSERT"],
            "require_write_confirmation": True,
        },
    )

    assert result["valid"] is True
    assert result["query_id"] == "q-1"
    assert result["statement_type"] == "INSERT"
    assert result["is_write"] is True
    assert result["write_confirmation_required"] is True


@pytest.mark.asyncio
async def test_validate_sql_returns_explain_error_for_invalid_read(monkeypatch):
    from db_mcp.services.query import validate_sql

    class _ExplainResult:
        valid = False
        error = "syntax error at or near FROM"

    monkeypatch.setattr(
        "db_mcp.services.query.explain_sql",
        lambda sql, connection_path: _ExplainResult(),
    )

    result = await validate_sql(
        sql="SELECT FROM users",
        connection="prod",
        connection_path=Path("/tmp/prod"),
        capabilities={"supports_validate_sql": True},
    )

    assert result == {
        "valid": False,
        "error": "syntax error at or near FROM",
        "sql": "SELECT FROM users",
        "query_id": None,
        "statement_type": "SELECT",
        "is_write": False,
    }


@pytest.mark.asyncio
async def test_validate_sql_registers_valid_read_query(monkeypatch):
    from db_mcp.services.query import validate_sql

    class _Tier:
        value = "auto"

    class _ExplainResult:
        valid = True
        explanation = ["Seq Scan on users", "Filter: active = true"]
        estimated_rows = 25
        estimated_cost = 1.5
        estimated_size_gb = 0.001
        cost_tier = _Tier()
        tier_reason = "Statement validated."

    monkeypatch.setattr(
        "db_mcp.services.query.explain_sql",
        lambda sql, connection_path: _ExplainResult(),
    )
    monkeypatch.setattr(
        gw, "create", AsyncMock(return_value=_vq("q-2", "SELECT * FROM users", "auto"))
    )

    result = await validate_sql(
        sql="SELECT * FROM users",
        connection="prod",
        connection_path=Path("/tmp/prod"),
        capabilities={"supports_validate_sql": True},
    )

    assert result["valid"] is True
    assert result["query_id"] == "q-2"
    assert result["cost_tier"] == "auto"
    assert result["estimated_rows"] == 25
    assert result["estimated_cost"] == 1.5
    assert result["estimated_size_gb"] == 0.001
    assert result["statement_type"] == "SELECT"
    assert result["is_write"] is False


@pytest.mark.asyncio
async def test_validate_sql_returns_execution_guidance_for_valid_read(monkeypatch):
    from db_mcp.services.query import validate_sql

    class _Tier:
        value = "auto"

    class _ExplainResult:
        valid = True
        explanation = ["Seq Scan on users"]
        estimated_rows = 25
        estimated_cost = 1.5
        estimated_size_gb = 0.001
        cost_tier = _Tier()
        tier_reason = "Statement validated."

    monkeypatch.setattr(
        "db_mcp.services.query.explain_sql",
        lambda sql, connection_path: _ExplainResult(),
    )
    monkeypatch.setattr(
        gw, "create", AsyncMock(return_value=_vq("q-3", "SELECT * FROM users", "auto"))
    )

    result = await validate_sql(
        sql="SELECT * FROM users",
        connection="prod",
        connection_path=Path("/tmp/prod"),
        capabilities={"supports_validate_sql": True},
    )

    assert result["message"] == (
        "Query validated successfully. "
        "Use run_sql(query_id='q-3', connection='prod') to execute. "
        "Query ID expires in 30 minutes."
    )
    assert result["guidance"]["next_steps"][0] == (
        "Execute with: run_sql(query_id='q-3', connection='prod')"
    )


@pytest.mark.asyncio
async def test_validate_sql_does_not_require_write_confirmation_for_read_queries(monkeypatch):
    from db_mcp.services.query import validate_sql

    class _Tier:
        value = "auto"

    class _ExplainResult:
        valid = True
        explanation = ["Seq Scan on users"]
        estimated_rows = 25
        estimated_cost = 1.5
        estimated_size_gb = 0.001
        cost_tier = _Tier()
        tier_reason = "Statement validated."

    monkeypatch.setattr(
        "db_mcp.services.query.explain_sql",
        lambda sql, connection_path: _ExplainResult(),
    )
    monkeypatch.setattr(
        gw, "create",
        AsyncMock(return_value=_vq("q-read", "SELECT * FROM users", "auto"))
    )

    result = await validate_sql(
        sql="SELECT * FROM users",
        connection="prod",
        connection_path=Path("/tmp/prod"),
        capabilities={
            "supports_validate_sql": True,
            "require_write_confirmation": True,
        },
    )

    assert result["is_write"] is False
    assert result["write_confirmation_required"] is False


@pytest.mark.asyncio
async def test_validate_sql_registers_non_explainable_read(monkeypatch):
    from db_mcp.services.query import validate_sql

    monkeypatch.setattr(
        gw, "create", AsyncMock(return_value=_vq("q-4", "SHOW TABLES", "auto"))
    )

    result = await validate_sql(
        sql="SHOW TABLES",
        connection="prod",
        connection_path=Path("/tmp/prod"),
        capabilities={"supports_validate_sql": True},
    )

    assert result["valid"] is True
    assert result["query_id"] == "q-4"
    assert result["statement_type"] == "SHOW"
    assert result["cost_tier"] == "auto"
    assert result["tier_reason"] == "SHOW statements are validated without EXPLAIN."


@pytest.mark.asyncio
async def test_run_sql_requires_query_id_or_sql():
    from db_mcp.services.query import run_sql

    result = await run_sql(connection="prod")

    assert result == {
        "status": "error",
        "error": "Provide query_id or sql.",
        "guidance": {
            "next_steps": [
                (
                    "For SQL databases: call validate_sql(sql=..., connection=...) then "
                    "run_sql(query_id=..., connection=...)"
                ),
                "For SQL-like APIs: call run_sql(connection=..., sql=...) directly",
            ]
        },
    }


@pytest.mark.asyncio
async def test_run_sql_requires_validate_when_supported(monkeypatch):
    from db_mcp.services.query import run_sql

    result = await run_sql(
        connection="prod",
        sql="SELECT 1",
        connection_path=Path("/tmp/prod"),
        capabilities={"supports_sql": True, "supports_validate_sql": True},
    )

    assert result == {
        "status": "error",
        "error": "Validation required. Use validate_sql first.",
        "guidance": {
            "next_steps": [
                "Call validate_sql(sql=...) to get a query_id",
                "Then call run_sql(query_id=..., connection=...)",
            ]
        },
    }


@pytest.mark.asyncio
async def test_run_sql_rejects_direct_sql_for_non_sql_connector(monkeypatch):
    from db_mcp.services.query import run_sql

    result = await run_sql(
        connection="prod",
        sql="SELECT 1",
        connection_path=Path("/tmp/prod"),
        capabilities={"supports_sql": False, "supports_validate_sql": False},
    )

    assert result == {
        "status": "error",
        "error": "Active connector does not support SQL execution.",
    }


@pytest.mark.asyncio
async def test_run_sql_returns_error_for_unknown_query_id(monkeypatch):
    from db_mcp.services.query import run_sql

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=None))

    result = await run_sql(connection="prod", query_id="missing")

    assert result == {
        "status": "error",
        "error": "Query not found. Use validate_sql first to get a query_id.",
        "query_id": "missing",
        "guidance": {
            "next_steps": [
                "1. Call validate_sql(sql='YOUR SQL HERE')",
                "2. Use the returned query_id with run_sql(query_id='...', connection='...')",
            ],
        },
    }


@pytest.mark.asyncio
async def test_run_sql_rejects_expired_query(monkeypatch):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="expired",
        sql="SELECT 1",
        status=QueryStatus.EXPIRED,
        connection="prod",
    )

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))

    result = await run_sql(connection="prod", query_id="expired")

    assert result == {
        "status": "error",
        "error": "Query validation has expired. Please re-validate.",
        "query_id": "expired",
        "guidance": {
            "next_steps": [
                "Call validate_sql again with your SQL",
                "Query IDs expire after 30 minutes",
            ],
        },
    }


@pytest.mark.asyncio
async def test_run_sql_rejects_connection_mismatch(monkeypatch):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="q-other",
        sql="SELECT 1",
        status=QueryStatus.VALIDATED,
        connection="warehouse",
    )

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))

    result = await run_sql(connection="prod", query_id="q-other")

    assert result == {
        "status": "error",
        "error": (
            "Query was validated for connection 'warehouse', "
            "but run_sql was called with connection 'prod'."
        ),
        "query_id": "q-other",
    }


@pytest.mark.asyncio
async def test_run_sql_rejects_non_executable_query_status(monkeypatch):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="q-running",
        sql="SELECT 1",
        status=QueryStatus.RUNNING,
        connection="prod",
    )

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))

    result = await run_sql(connection="prod", query_id="q-running")

    assert result == {
        "status": "error",
        "error": "Query cannot be executed. Status: running",
        "query_id": "q-running",
    }


@pytest.mark.asyncio
async def test_run_sql_rejects_write_query_without_confirmation(monkeypatch):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="q-write",
        sql="INSERT INTO users(id) VALUES (1)",
        status=QueryStatus.VALIDATED,
        connection="prod",
        cost_tier="confirm",
    )

    class _Store:
        async def get(self, query_id: str):
            assert query_id == "q-write"
            return query

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))

    result = await run_sql(
        connection="prod",
        query_id="q-write",
        connection_path=Path("/tmp/prod"),
        capabilities={"allow_sql_writes": True, "require_write_confirmation": True},
    )

    assert result == {
        "status": "confirm_required",
        "sql": "INSERT INTO users(id) VALUES (1)",
        "statement_type": "INSERT",
        "is_write": True,
        "message": "Write statement requires confirmation. Re-run with confirmed=true to execute.",
        "query_id": "q-write",
    }


@pytest.mark.asyncio
async def test_run_sql_executes_validated_query_synchronously(monkeypatch):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="q-sync",
        sql="SELECT 1 AS answer",
        status=QueryStatus.VALIDATED,
        connection="prod",
        cost_tier="auto",
    )

    class _Store:
        def __init__(self):
            self.updated: list[tuple[str, QueryStatus, dict | None, int]] = []

        async def get(self, query_id: str):
            assert query_id == "q-sync"
            return query

        async def update_status(
            self,
            query_id: str,
            status: QueryStatus,
            result: dict | None = None,
            error: str | None = None,
            rows_returned: int = 0,
        ):
            assert error is None
            self.updated.append((query_id, status, result, rows_returned))

    class _Handle:
        execution_id = "exec-1"

    class _Result:
        state = ExecutionState.SUCCEEDED
        data = [{"answer": 1}]
        columns = ["answer"]
        rows_returned = 1
        duration_ms = 2.5
        metadata = {
            "provider_id": "prod",
            "statement_type": "SELECT",
            "is_write": False,
        }
        rows_affected = None

    class _Engine:
        def submit_sync(self, request, runner):
            assert request.connection == "prod"
            assert request.sql == "SELECT 1 AS answer"
            assert request.query_id == "q-sync"
            assert request.idempotency_key == "q-sync"
            runner_result = runner("SELECT 1 AS answer")
            assert runner_result == {
                "data": [{"answer": 1}],
                "columns": ["answer"],
                "rows_returned": 1,
                "rows_affected": None,
                "metadata": {
                    "provider_id": "prod",
                    "statement_type": "SELECT",
                    "is_write": False,
                },
            }
            return _Handle(), _Result()

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))
    mark_running = AsyncMock()
    mark_complete = AsyncMock()
    monkeypatch.setattr(gw, "mark_running", mark_running)
    monkeypatch.setattr(gw, "mark_complete", mark_complete)

    result = await run_sql(
        connection="prod",
        query_id="q-sync",
        connection_path=Path("/tmp/prod"),
        execution_engine=_Engine(),
        capabilities={},
        execute_query=lambda sql, *, connection, query_id: {
            "data": [{"answer": 1}],
            "columns": ["answer"],
            "rows_returned": 1,
            "duration_ms": 2.5,
            "provider_id": "prod",
            "statement_type": "SELECT",
            "is_write": False,
            "rows_affected": None,
        },
    )

    assert result["status"] == "success"
    assert result["query_id"] == "q-sync"
    assert result["execution_id"] == "exec-1"
    assert result["rows_returned"] == 1
    assert result["data"] == [{"answer": 1}]
    assert result["statement_type"] == "SELECT"
    assert result["is_write"] is False
    mark_running.assert_awaited_once_with("q-sync")
    mark_complete.assert_awaited_once_with(
        "q-sync",
        result={
            "data": [{"answer": 1}],
            "columns": ["answer"],
            "rows_returned": 1,
            "duration_ms": 2.5,
            "provider_id": "prod",
            "statement_type": "SELECT",
            "is_write": False,
            "rows_affected": None,
        },
        rows_returned=1,
    )


@pytest.mark.asyncio
async def test_run_sql_returns_error_for_failed_sync_execution(monkeypatch):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="q-fail",
        sql="SELECT broken()",
        status=QueryStatus.VALIDATED,
        connection="prod",
        cost_tier="auto",
    )

    class _Store:
        def __init__(self):
            self.updated: list[tuple[str, QueryStatus, str | None]] = []

        async def get(self, query_id: str):
            assert query_id == "q-fail"
            return query

        async def update_status(
            self,
            query_id: str,
            status: QueryStatus,
            result: dict | None = None,
            error: str | None = None,
            rows_returned: int = 0,
        ):
            assert result is None
            assert rows_returned == 0
            self.updated.append((query_id, status, error))

    class _Handle:
        execution_id = "exec-fail"

    class _Error:
        message = "relation does not exist"

    class _Result:
        state = ExecutionState.FAILED
        error = _Error()

    class _Engine:
        def submit_sync(self, request, runner):
            assert request.connection == "prod"
            assert request.sql == "SELECT broken()"
            assert request.query_id == "q-fail"
            assert request.idempotency_key == "q-fail"
            return _Handle(), _Result()

    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))
    mark_running = AsyncMock()
    mark_error = AsyncMock()
    monkeypatch.setattr(gw, "mark_running", mark_running)
    monkeypatch.setattr(gw, "mark_error", mark_error)

    result = await run_sql(
        connection="prod",
        query_id="q-fail",
        connection_path=Path("/tmp/prod"),
        execution_engine=_Engine(),
        capabilities={},
        execute_query=lambda sql, *, connection, query_id: {},
    )

    assert result == {
        "status": "error",
        "error": "Execution failed: relation does not exist",
        "query_id": "q-fail",
        "execution_id": "exec-fail",
        "state": "failed",
        "sql": "SELECT broken()",
    }
    mark_running.assert_awaited_once_with("q-fail")
    mark_error.assert_awaited_once_with("q-fail", error="relation does not exist")


@pytest.mark.asyncio
async def test_run_sql_submits_large_validated_query_for_async_execution(monkeypatch):
    from db_mcp.services.query import run_sql

    query = Query(
        query_id="q-async",
        sql="SELECT * FROM events",
        status=QueryStatus.VALIDATED,
        connection="prod",
        cost_tier="auto",
        estimated_rows=75_000,
    )

    class _StartedQuery:
        pass

    class _Store:
        def __init__(self):
            self.started: list[str] = []

        async def get(self, query_id: str):
            assert query_id == "q-async"
            return query

        async def start_execution(self, query_id: str):
            self.started.append(query_id)
            return _StartedQuery()

    class _Handle:
        execution_id = "exec-async"
        state = ExecutionState.SUBMITTED

    class _Engine:
        def submit_async(self, request):
            assert request.connection == "prod"
            assert request.sql == "SELECT * FROM events"
            assert request.query_id == "q-async"
            assert request.idempotency_key == "q-async"
            return _Handle()

    spawned = {}

    def _spawn_background(*, query_id: str, sql: str, connection: str, execution_id: str):
        spawned["call"] = {
            "query_id": query_id,
            "sql": sql,
            "connection": connection,
            "execution_id": execution_id,
        }

    start_query_execution = AsyncMock(return_value=True)
    monkeypatch.setattr(gw, "get_query", AsyncMock(return_value=query))
    monkeypatch.setattr(gw, "start_query_execution", start_query_execution)

    result = await run_sql(
        connection="prod",
        query_id="q-async",
        connection_path=Path("/tmp/prod"),
        execution_engine=_Engine(),
        capabilities={},
        execute_query=lambda sql, *, connection, query_id: {},
        spawn_background_execution=_spawn_background,
    )

    assert result == {
        "status": "submitted",
        "mode": "async",
        "query_id": "q-async",
        "execution_id": "exec-async",
        "state": "submitted",
        "sql": "SELECT * FROM events",
        "estimated_rows": 75_000,
        "message": (
            "Query submitted for background execution. "
            "Estimated ~75,000 rows to scan. "
            "Use get_result('q-async', connection='prod') to check status."
        ),
        "poll_interval_seconds": 10,
        "guidance": {
            "next_steps": [
                "Poll status with: get_result('q-async', connection='prod')",
                "Check every 10-30 seconds until status is 'complete'",
            ],
        },
    }
    start_query_execution.assert_awaited_once_with("q-async")
    assert spawned["call"] == {
        "query_id": "q-async",
        "sql": "SELECT * FROM events",
        "connection": "prod",
        "execution_id": "exec-async",
    }


@pytest.mark.asyncio
async def test_run_sql_executes_direct_sql_synchronously_when_validate_is_disabled(monkeypatch):
    from db_mcp.services.query import run_sql

    class _Handle:
        execution_id = "exec-direct"

    class _Result:
        state = ExecutionState.SUCCEEDED
        data = [{"answer": 1}]
        columns = ["answer"]
        rows_returned = 1
        duration_ms = 1.25
        metadata = {
            "provider_id": "prod",
            "statement_type": "SELECT",
            "is_write": False,
        }
        rows_affected = None

    class _Engine:
        def submit_sync(self, request, runner):
            assert request.connection == "prod"
            assert request.sql == "SELECT 1 AS answer"
            assert request.query_id == "q-direct"
            assert request.idempotency_key == "q-direct"
            runner_result = runner("SELECT 1 AS answer")
            assert runner_result == {
                "data": [{"answer": 1}],
                "columns": ["answer"],
                "rows_returned": 1,
                "rows_affected": None,
                "metadata": {
                    "provider_id": "prod",
                    "statement_type": "SELECT",
                    "is_write": False,
                },
            }
            return _Handle(), _Result()

    result = await run_sql(
        connection="prod",
        sql="SELECT 1 AS answer",
        connection_path=Path("/tmp/prod"),
        execution_engine=_Engine(),
        capabilities={"supports_sql": True, "supports_validate_sql": False},
        execute_query=lambda sql, *, connection, query_id: {
            "data": [{"answer": 1}],
            "columns": ["answer"],
            "rows_returned": 1,
            "duration_ms": 1.25,
            "provider_id": "prod",
            "statement_type": "SELECT",
            "is_write": False,
            "rows_affected": None,
        },
        generate_query_id=lambda sql: "q-direct",
    )

    assert result == {
        "status": "success",
        "mode": "sync",
        "execution_id": "exec-direct",
        "state": "succeeded",
        "query_id": "q-direct",
        "sql": "SELECT 1 AS answer",
        "data": [{"answer": 1}],
        "columns": ["answer"],
        "rows_returned": 1,
        "duration_ms": 1.25,
        "provider_id": "prod",
        "cost_tier": "unknown",
        "statement_type": "SELECT",
        "is_write": False,
        "rows_affected": None,
    }


@pytest.mark.asyncio
async def test_run_sql_executes_sql_like_api_sync_submission(monkeypatch):
    from db_mcp.services.query import run_sql

    class _Connector:
        def submit_sql(self, sql: str):
            assert sql == "SELECT 1"
            return {"mode": "sync", "rows": [{"ok": 1}]}

    class _Handle:
        execution_id = "exec-api-sync"

    class _Engine:
        def __init__(self):
            self.marked = []

        def submit_async(self, request):
            assert request.connection == "prod"
            assert request.sql == "SELECT 1"
            assert request.query_id == "q-api-sync"
            assert request.idempotency_key == "q-api-sync"
            assert request.metadata == {"sql_mode": "api_sync"}
            return _Handle()

        def mark_succeeded(
            self,
            execution_id,
            *,
            data,
            columns,
            rows_returned,
            rows_affected,
            duration_ms,
            metadata,
        ):
            self.marked.append(
                (
                    execution_id,
                    data,
                    columns,
                    rows_returned,
                    rows_affected,
                    duration_ms,
                    metadata,
                )
            )

    connector = _Connector()
    engine = _Engine()

    # Keep get_connector patch: needed for lazy connector resolution in the SQL-API path.
    monkeypatch.setattr(
        "db_mcp.services.query.get_connector",
        lambda *, connection_path: connector,
    )

    result = await run_sql(
        connection="prod",
        sql="SELECT 1",
        connection_path=Path("/tmp/prod"),
        execution_engine=engine,
        capabilities={
            "supports_sql": True,
            "supports_validate_sql": False,
            "sql_mode": "api_sync",
        },
        generate_query_id=lambda sql: "q-api-sync",
    )

    assert result == {
        "status": "success",
        "mode": "sync",
        "query_id": "q-api-sync",
        "execution_id": "exec-api-sync",
        "state": "succeeded",
        "sql": "SELECT 1",
        "data": [{"ok": 1}],
        "columns": ["ok"],
        "rows_returned": 1,
        "duration_ms": None,
        "provider_id": None,
        "cost_tier": "unknown",
        "statement_type": None,
        "is_write": False,
        "rows_affected": None,
    }
    assert engine.marked == [
        (
            "exec-api-sync",
            [{"ok": 1}],
            ["ok"],
            1,
            None,
            None,
            {
                "sql_mode": "api_sync",
                "submission_mode": "sync",
            },
        )
    ]


@pytest.mark.asyncio
async def test_run_sql_submits_sql_like_api_async_execution(monkeypatch):
    from db_mcp.services.query import run_sql

    class _Connector:
        def submit_sql(self, sql: str):
            assert sql == "SELECT 1"
            return {"mode": "async", "execution_id": "remote-exec-1"}

    class _Handle:
        execution_id = "exec-api-async"

    class _Engine:
        def __init__(self):
            self.updated = []
            self.running = []

        def submit_async(self, request):
            assert request.connection == "prod"
            assert request.sql == "SELECT 1"
            assert request.query_id == "q-api-async"
            assert request.idempotency_key == "q-api-async"
            assert request.metadata == {"sql_mode": "api_sync"}
            return _Handle()

        def update_metadata(self, execution_id, metadata, merge=False):
            self.updated.append((execution_id, metadata, merge))

        def mark_running(self, execution_id):
            self.running.append(execution_id)

    connector = _Connector()
    engine = _Engine()

    # Keep get_connector patch: needed for lazy connector resolution in the SQL-API path.
    monkeypatch.setattr(
        "db_mcp.services.query.get_connector",
        lambda *, connection_path: connector,
    )

    result = await run_sql(
        connection="prod",
        sql="SELECT 1",
        connection_path=Path("/tmp/prod"),
        execution_engine=engine,
        capabilities={
            "supports_sql": True,
            "supports_validate_sql": False,
            "sql_mode": "api_sync",
        },
        generate_query_id=lambda sql: "q-api-async",
    )

    assert result == {
        "status": "submitted",
        "mode": "async",
        "query_id": "exec-api-async",
        "execution_id": "exec-api-async",
        "state": "running",
        "sql": "SELECT 1",
        "external_execution_id": "remote-exec-1",
        "message": (
            "Query submitted to SQL API. "
            "Use get_result('exec-api-async', connection='prod') to poll status."
        ),
        "poll_interval_seconds": 5,
    }
    assert engine.updated == [
        (
            "exec-api-async",
            {
                "sql_mode": "api_sync",
                "external_execution_id": "remote-exec-1",
                "submission_mode": "async",
            },
            True,
        )
    ]
    assert engine.running == ["exec-api-async"]
