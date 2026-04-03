"""TDD tests for B2d — generalize ExecutionRequest payload model."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from db_mcp_data.execution import ExecutionRequest, ExecutionState
from db_mcp_data.execution.engine import ExecutionEngine
from db_mcp_data.execution.store import ExecutionStore

# ---------------------------------------------------------------------------
# 1. ExecutionRequest: new payload-based API
# ---------------------------------------------------------------------------


def test_execution_request_sql_payload():
    """ExecutionRequest with query_type='sql' and payload dict."""
    req = ExecutionRequest(
        connection="prod",
        query_type="sql",
        payload={"sql": "SELECT 1"},
    )
    assert req.query_type == "sql"
    assert req.payload == {"sql": "SELECT 1"}
    assert req.sql == "SELECT 1"


def test_execution_request_endpoint_payload():
    """ExecutionRequest with query_type='endpoint' and endpoint payload."""
    req = ExecutionRequest(
        connection="myapi",
        query_type="endpoint",
        payload={"endpoint": "users", "params": {"page": 1}},
    )
    assert req.query_type == "endpoint"
    assert req.payload["endpoint"] == "users"
    assert req.sql is None


# ---------------------------------------------------------------------------
# 2. Backward compat: sql= kwarg still works
# ---------------------------------------------------------------------------


def test_execution_request_sql_kwarg_compat():
    """Passing sql= as a kwarg should set payload={'sql': ...} and query_type='sql'."""
    req = ExecutionRequest(connection="prod", sql="SELECT 42")
    assert req.query_type == "sql"
    assert req.payload == {"sql": "SELECT 42"}
    assert req.sql == "SELECT 42"


def test_execution_request_sql_kwarg_with_explicit_query_type():
    """sql= kwarg respects an explicitly provided query_type."""
    req = ExecutionRequest(connection="prod", sql="SELECT 1", query_type="sql_api")
    assert req.query_type == "sql_api"
    assert req.sql == "SELECT 1"


# ---------------------------------------------------------------------------
# 3. ExecutionStore persists query_type + payload_json + payload_hash
# ---------------------------------------------------------------------------


def test_store_persists_query_type_and_payload(tmp_path: Path):
    """create_submission must store query_type, payload_json, and payload_hash."""
    store = ExecutionStore(tmp_path / "executions.sqlite")
    req = ExecutionRequest(
        connection="prod",
        query_type="endpoint",
        payload={"endpoint": "orders", "params": {}},
    )
    handle = store.create_submission(req, payload_hash="hash-ep-1")

    # Read raw row to verify columns
    with sqlite3.connect(tmp_path / "executions.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT query_type, payload_json, payload_hash FROM executions WHERE execution_id = ?",
            (handle.execution_id,),
        ).fetchone()

    assert row is not None
    assert row["query_type"] == "endpoint"
    assert json.loads(row["payload_json"]) == {"endpoint": "orders", "params": {}}
    assert row["payload_hash"] == "hash-ep-1"


def test_store_persists_sql_payload(tmp_path: Path):
    """SQL ExecutionRequest: payload_json stores the sql dict."""
    store = ExecutionStore(tmp_path / "executions.sqlite")
    req = ExecutionRequest(connection="prod", sql="SELECT 1")
    handle = store.create_submission(req, payload_hash="hash-sql-1")

    with sqlite3.connect(tmp_path / "executions.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT query_type, payload_json, sql FROM executions WHERE execution_id = ?",
            (handle.execution_id,),
        ).fetchone()

    assert row["query_type"] == "sql"
    assert json.loads(row["payload_json"]) == {"sql": "SELECT 1"}
    # Deprecated sql column should still be populated for backward compat
    assert row["sql"] == "SELECT 1"


# ---------------------------------------------------------------------------
# 4. Schema migration: existing DB without new columns gets them added
# ---------------------------------------------------------------------------


def test_store_migrates_existing_db_adds_payload_columns(tmp_path: Path):
    """Opening a DB without query_type/payload_json/payload_hash adds the columns."""
    db_path = tmp_path / "executions.sqlite"

    # Create old-style schema without the new columns
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE executions (
                execution_id TEXT PRIMARY KEY,
                connection TEXT NOT NULL,
                query_id TEXT,
                sql TEXT,
                sql_hash TEXT,
                idempotency_key TEXT,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL,
                rows_returned INTEGER NOT NULL DEFAULT 0,
                rows_affected INTEGER,
                duration_ms REAL,
                error_code TEXT,
                error_message TEXT,
                error_retryable INTEGER,
                error_details TEXT,
                data_json TEXT,
                columns_json TEXT,
                metadata_json TEXT
            )
            """
        )

    # Opening the store should not raise, and should add the new columns
    store = ExecutionStore(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        columns = [row[1] for row in conn.execute("PRAGMA table_info(executions)").fetchall()]

    assert "query_type" in columns
    assert "payload_json" in columns
    assert "payload_hash" in columns

    # And the store should be usable
    req = ExecutionRequest(connection="prod", sql="SELECT 1")
    handle = store.create_submission(req)
    assert handle.execution_id is not None


# ---------------------------------------------------------------------------
# 5. ExecutionEngine calls runner(payload: dict), not runner(sql: str)
# ---------------------------------------------------------------------------


def test_engine_submit_sync_passes_payload_to_runner(tmp_path: Path):
    """submit_sync must call runner(payload_dict), not runner(sql_str)."""
    store = ExecutionStore(tmp_path / "executions.sqlite")
    engine = ExecutionEngine(store)

    req = ExecutionRequest(connection="prod", query_type="sql", payload={"sql": "SELECT 99"})
    received: list = []

    def runner(payload: dict):
        received.append(payload)
        return {
            "data": [{"v": 99}],
            "columns": ["v"],
            "rows_returned": 1,
            "rows_affected": None,
        }

    handle, result = engine.submit_sync(req, runner)

    assert received == [{"sql": "SELECT 99"}], (
        "runner must receive the payload dict, not a SQL string"
    )
    assert result.state == ExecutionState.SUCCEEDED
    assert result.data == [{"v": 99}]


def test_engine_submit_sync_endpoint_payload(tmp_path: Path):
    """Endpoint queries route through the engine with their endpoint payload."""
    store = ExecutionStore(tmp_path / "executions.sqlite")
    engine = ExecutionEngine(store)

    req = ExecutionRequest(
        connection="myapi",
        query_type="endpoint",
        payload={"endpoint": "users", "params": {"active": True}},
    )

    def runner(payload: dict):
        # Endpoint runner uses endpoint name from payload
        assert payload["endpoint"] == "users"
        return {
            "data": [{"id": 1}],
            "columns": ["id"],
            "rows_returned": 1,
            "rows_affected": None,
        }

    handle, result = engine.submit_sync(req, runner)

    assert result.state == ExecutionState.SUCCEEDED
    assert result.data == [{"id": 1}]


# ---------------------------------------------------------------------------
# 6. payload_hash used for idempotency (replaces sql_hash)
# ---------------------------------------------------------------------------


def test_engine_idempotency_uses_payload_hash(tmp_path: Path):
    """Repeated submit_sync with same payload_hash returns existing execution."""
    store = ExecutionStore(tmp_path / "executions.sqlite")
    engine = ExecutionEngine(store)

    call_count = 0

    def runner(payload: dict):
        nonlocal call_count
        call_count += 1
        return {"data": [{"n": 1}], "columns": ["n"], "rows_returned": 1, "rows_affected": None}

    req = ExecutionRequest(
        connection="prod",
        sql="SELECT 1",
        idempotency_key="idem-payload-key",
    )

    handle_1, _ = engine.submit_sync(req, runner)
    handle_2, _ = engine.submit_sync(req, runner)

    assert handle_2.execution_id == handle_1.execution_id
    assert call_count == 1, "runner should only be called once for idempotent requests"
