"""Tests for the unified execution engine and persistent execution store."""

from pathlib import Path

from db_mcp_data.execution import (
    ExecutionRequest,
    ExecutionState,
)
from db_mcp_data.execution.engine import ExecutionEngine
from db_mcp_data.execution.store import ExecutionStore


def test_execution_store_persists_across_instances(tmp_path: Path):
    db_path = tmp_path / "executions.sqlite"

    store_a = ExecutionStore(db_path)
    request = ExecutionRequest(connection="playground", sql="SELECT 1", idempotency_key="abc")
    handle = store_a.create_submission(request, sql_hash="hash-1")
    store_a.mark_running(handle.execution_id)
    store_a.mark_succeeded(
        handle.execution_id,
        data=[{"x": 1}],
        columns=["x"],
        rows_returned=1,
        rows_affected=None,
        duration_ms=1.5,
    )

    # New store instance over same sqlite file should see persisted result.
    store_b = ExecutionStore(db_path)
    result = store_b.get_result(handle.execution_id)

    assert result is not None
    assert result.state == ExecutionState.SUCCEEDED
    assert result.rows_returned == 1
    assert result.data == [{"x": 1}]


def test_execution_engine_submit_sync_success(tmp_path: Path):
    store = ExecutionStore(tmp_path / "executions.sqlite")
    engine = ExecutionEngine(store)
    request = ExecutionRequest(connection="analytics_connection", sql="SELECT 1")

    def runner(payload: dict):
        assert payload.get("sql") == "SELECT 1"
        return {
            "data": [{"ok": True}],
            "columns": ["ok"],
            "rows_returned": 1,
            "rows_affected": None,
        }

    handle, result = engine.submit_sync(request, runner)

    assert handle.state == ExecutionState.SUBMITTED
    assert result.execution_id == handle.execution_id
    assert result.state == ExecutionState.SUCCEEDED
    assert result.data == [{"ok": True}]
    assert result.rows_returned == 1


def test_execution_engine_submit_sync_failure(tmp_path: Path):
    store = ExecutionStore(tmp_path / "executions.sqlite")
    engine = ExecutionEngine(store)
    request = ExecutionRequest(connection="analytics_connection", sql="SELECT broken")

    def runner(payload: dict):
        raise RuntimeError(f"boom on {payload.get('sql', '')}")

    handle, result = engine.submit_sync(request, runner)

    assert handle.state == ExecutionState.SUBMITTED
    assert result.execution_id == handle.execution_id
    assert result.state == ExecutionState.FAILED
    assert result.error is not None
    assert "boom on SELECT broken" in result.error.message


def test_execution_engine_idempotency_returns_existing_execution(tmp_path: Path):
    store = ExecutionStore(tmp_path / "executions.sqlite")
    engine = ExecutionEngine(store)
    request = ExecutionRequest(
        connection="analytics_connection",
        sql="SELECT 1",
        idempotency_key="same-key",
    )

    def runner(payload: dict):
        return {
            "data": [{"value": 1}],
            "columns": ["value"],
            "rows_returned": 1,
            "rows_affected": None,
        }

    handle_1, result_1 = engine.submit_sync(request, runner)
    handle_2, result_2 = engine.submit_sync(request, runner)

    assert handle_2.execution_id == handle_1.execution_id
    assert result_2.execution_id == result_1.execution_id
    assert result_2.data == [{"value": 1}]
