"""Unified execution engine backed by persistent execution store."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from db_mcp_data.execution.models import (
    ExecutionError,
    ExecutionErrorCode,
    ExecutionHandle,
    ExecutionRequest,
    ExecutionResult,
)
from db_mcp_data.execution.store import ExecutionStore

_STORE_FILENAME = "executions.sqlite"
_EXECUTION_STORE_CACHE: dict[Path, ExecutionStore] = {}


def _payload_hash(payload: dict | None) -> str | None:
    if not payload:
        return None
    # Sort keys for deterministic hashing; normalize whitespace in SQL strings
    normalized = json.dumps(
        {k: " ".join(v.split()) if isinstance(v, str) else v for k, v in sorted(payload.items())}
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# Backward-compat alias
def _sql_hash(sql: str | None) -> str | None:
    if not sql:
        return None
    return _payload_hash({"sql": sql})


def get_execution_store(connection_path: Path) -> ExecutionStore:
    """Return per-connection cached execution store."""
    conn_path = Path(connection_path).resolve()
    if conn_path not in _EXECUTION_STORE_CACHE:
        db_path = conn_path / "state" / _STORE_FILENAME
        _EXECUTION_STORE_CACHE[conn_path] = ExecutionStore(db_path)
    return _EXECUTION_STORE_CACHE[conn_path]


def get_execution_engine(connection_path: Path) -> "ExecutionEngine":
    """Construct an execution engine for a connection path."""
    return ExecutionEngine(get_execution_store(connection_path))


class ExecutionEngine:
    """State-machine execution coordinator."""

    def __init__(self, store: ExecutionStore):
        self._store = store

    def submit_sync(
        self,
        request: ExecutionRequest,
        runner: Any,
    ) -> tuple[ExecutionHandle, ExecutionResult]:
        """Execute a request synchronously and persist lifecycle transitions."""
        ph = _payload_hash(request.payload)
        handle = self._store.create_submission(request, payload_hash=ph)
        existing_result = self._store.get_result(handle.execution_id)

        if existing_result is not None and existing_result.state in {
            existing_result.state.SUCCEEDED,
            existing_result.state.FAILED,
            existing_result.state.CANCELLED,
            existing_result.state.TIMED_OUT,
        }:
            return handle, existing_result

        self._store.mark_running(handle.execution_id)
        started = time.time()

        try:
            runner_result = runner(request.payload)
            duration_ms = (time.time() - started) * 1000

            data = runner_result.get("data", [])
            columns = runner_result.get("columns", [])
            rows_returned = runner_result.get("rows_returned", len(data))
            rows_affected = runner_result.get("rows_affected")
            metadata = runner_result.get("metadata", {})

            self._store.mark_succeeded(
                handle.execution_id,
                data=data,
                columns=columns,
                rows_returned=rows_returned,
                rows_affected=rows_affected,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        except Exception as exc:
            duration_ms = (time.time() - started) * 1000
            error = ExecutionError(
                code=ExecutionErrorCode.ENGINE,
                message=str(exc),
                retryable=False,
            )
            self._store.mark_failed(
                handle.execution_id,
                error=error,
                duration_ms=duration_ms,
            )

        result = self._store.get_result(handle.execution_id)
        if result is None:
            # Should never happen, but keep deterministic failure semantics.
            fallback_error = ExecutionError(
                code=ExecutionErrorCode.TOOLING,
                message="Execution result missing after submission",
            )
            self._store.mark_failed(
                handle.execution_id,
                error=fallback_error,
                duration_ms=None,
            )
            result = self._store.get_result(handle.execution_id)

        # result is guaranteed non-None by the fallback path above
        return handle, result  # type: ignore[return-value]

    def get_result(self, execution_id: str) -> ExecutionResult | None:
        """Fetch execution result by ID."""
        return self._store.get_result(execution_id)

    def submit_async(self, request: ExecutionRequest) -> ExecutionHandle:
        """Create an async execution submission without running it."""
        return self._store.create_submission(request, payload_hash=_payload_hash(request.payload))

    def mark_running(self, execution_id: str) -> None:
        """Mark an existing execution as running."""
        self._store.mark_running(execution_id)

    def update_metadata(
        self,
        execution_id: str,
        metadata: dict[str, Any],
        *,
        merge: bool = True,
    ) -> None:
        """Update metadata for an execution."""
        self._store.update_metadata(execution_id, metadata, merge=merge)

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
        """Mark an execution as succeeded."""
        self._store.mark_succeeded(
            execution_id,
            data=data,
            columns=columns,
            rows_returned=rows_returned,
            rows_affected=rows_affected,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def mark_failed(
        self,
        execution_id: str,
        *,
        message: str,
        code: ExecutionErrorCode = ExecutionErrorCode.ENGINE,
        retryable: bool = False,
        duration_ms: float | None = None,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mark an execution as failed."""
        self._store.mark_failed(
            execution_id,
            error=ExecutionError(
                code=code,
                message=message,
                retryable=retryable,
                details=details or {},
            ),
            duration_ms=duration_ms,
            metadata=metadata,
        )
