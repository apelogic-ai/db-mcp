"""Persistent execution store backed by SQLite."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from db_mcp_data.execution.models import (
    ExecutionError,
    ExecutionErrorCode,
    ExecutionHandle,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
)


def _to_utc(ts: float | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=UTC)


def _safe_json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


class ExecutionStore:
    """SQLite-backed execution lifecycle store."""

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
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
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_executions_connection_idempotency
                ON executions(connection, idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )

    def create_submission(
        self,
        request: ExecutionRequest,
        sql_hash: str | None = None,
    ) -> ExecutionHandle:
        """Create a submission record or return existing one for idempotency key."""
        now = time.time()
        execution_id = str(uuid.uuid4())

        if request.idempotency_key:
            existing = self.get_by_idempotency(request.connection, request.idempotency_key)
            if existing is not None:
                return existing

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO executions (
                    execution_id, connection, query_id, sql, sql_hash,
                    idempotency_key, state, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    request.connection,
                    request.query_id,
                    request.sql,
                    sql_hash,
                    request.idempotency_key,
                    ExecutionState.SUBMITTED.value,
                    now,
                    json.dumps(request.metadata or {}),
                ),
            )

        return ExecutionHandle(
            execution_id=execution_id,
            connection=request.connection,
            state=ExecutionState.SUBMITTED,
            submitted_at=_to_utc(now) or datetime.now(UTC),
            query_id=request.query_id,
            sql_hash=sql_hash,
        )

    def get_by_idempotency(self, connection: str, idempotency_key: str) -> ExecutionHandle | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT execution_id, connection, state, created_at, query_id, sql_hash
                FROM executions
                WHERE connection = ? AND idempotency_key = ?
                """,
                (connection, idempotency_key),
            ).fetchone()
        if row is None:
            return None

        return ExecutionHandle(
            execution_id=row["execution_id"],
            connection=row["connection"],
            state=ExecutionState(row["state"]),
            submitted_at=_to_utc(row["created_at"]) or datetime.now(UTC),
            query_id=row["query_id"],
            sql_hash=row["sql_hash"],
        )

    def mark_running(self, execution_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE executions
                SET state = ?, started_at = ?
                WHERE execution_id = ?
                """,
                (ExecutionState.RUNNING.value, time.time(), execution_id),
            )

    def update_metadata(
        self,
        execution_id: str,
        metadata: dict[str, Any],
        *,
        merge: bool = True,
    ) -> None:
        """Update metadata for an execution."""
        if not metadata:
            return

        if merge:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT metadata_json FROM executions WHERE execution_id = ?",
                    (execution_id,),
                ).fetchone()
                existing = _safe_json_load(
                    row["metadata_json"] if row is not None else None,
                    {},
                )
                if not isinstance(existing, dict):
                    existing = {}
                merged = dict(existing)
                merged.update(metadata)
                conn.execute(
                    "UPDATE executions SET metadata_json = ? WHERE execution_id = ?",
                    (json.dumps(merged), execution_id),
                )
            return

        with self._connect() as conn:
            conn.execute(
                "UPDATE executions SET metadata_json = ? WHERE execution_id = ?",
                (json.dumps(metadata), execution_id),
            )

    def mark_succeeded(
        self,
        execution_id: str,
        *,
        data: list[dict[str, Any]],
        columns: list[str],
        rows_returned: int,
        rows_affected: int | None,
        duration_ms: float | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE executions
                SET state = ?, completed_at = ?, rows_returned = ?,
                    rows_affected = ?, duration_ms = ?, data_json = ?,
                    columns_json = ?, metadata_json = COALESCE(?, metadata_json)
                WHERE execution_id = ?
                """,
                (
                    ExecutionState.SUCCEEDED.value,
                    time.time(),
                    rows_returned,
                    rows_affected,
                    duration_ms,
                    json.dumps(data),
                    json.dumps(columns),
                    json.dumps(metadata) if metadata is not None else None,
                    execution_id,
                ),
            )

    def mark_failed(
        self,
        execution_id: str,
        *,
        error: ExecutionError,
        duration_ms: float | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE executions
                SET state = ?, completed_at = ?, duration_ms = ?,
                    error_code = ?, error_message = ?, error_retryable = ?,
                    error_details = ?, metadata_json = COALESCE(?, metadata_json)
                WHERE execution_id = ?
                """,
                (
                    ExecutionState.FAILED.value,
                    time.time(),
                    duration_ms,
                    error.code.value,
                    error.message,
                    1 if error.retryable else 0,
                    json.dumps(error.details),
                    json.dumps(metadata) if metadata is not None else None,
                    execution_id,
                ),
            )

    def get_result(self, execution_id: str) -> ExecutionResult | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            return None

        error = None
        if row["error_message"]:
            error_code = row["error_code"] or ExecutionErrorCode.UNKNOWN.value
            try:
                code = ExecutionErrorCode(error_code)
            except ValueError:
                code = ExecutionErrorCode.UNKNOWN
            error = ExecutionError(
                code=code,
                message=row["error_message"],
                retryable=bool(row["error_retryable"]),
                details=_safe_json_load(row["error_details"], {}),
            )

        return ExecutionResult(
            execution_id=row["execution_id"],
            state=ExecutionState(row["state"]),
            data=_safe_json_load(row["data_json"], []),
            columns=_safe_json_load(row["columns_json"], []),
            rows_returned=row["rows_returned"] or 0,
            rows_affected=row["rows_affected"],
            duration_ms=row["duration_ms"],
            started_at=_to_utc(row["started_at"]),
            completed_at=_to_utc(row["completed_at"]),
            error=error,
            metadata=_safe_json_load(row["metadata_json"], {}),
        )
