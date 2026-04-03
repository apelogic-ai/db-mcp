"""Typed execution contract for deterministic query execution."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ExecutionState(str, Enum):
    """Lifecycle states for query execution."""

    PRECHECK = "precheck"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ExecutionErrorCode(str, Enum):
    """Normalized error classes across connectors."""

    AUTH = "AUTH"
    TRANSPORT = "TRANSPORT"
    VALIDATION = "VALIDATION"
    ENGINE = "ENGINE"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    POLICY = "POLICY"
    TOOLING = "TOOLING"
    UNKNOWN = "UNKNOWN"


class ExecutionError(BaseModel):
    """Structured execution error payload."""

    code: ExecutionErrorCode = Field(default=ExecutionErrorCode.UNKNOWN)
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionRequest(BaseModel):
    """Canonical request envelope for a query execution."""

    connection: str
    query_type: str = "sql"  # "sql", "endpoint", "sql_api"
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str | None = None
    query_id: str | None = None
    idempotency_key: str | None = None
    confirmed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _compat_sql_kwarg(cls, data: Any) -> Any:
        """Accept legacy sql= kwarg and fold it into payload."""
        if not isinstance(data, dict):
            return data
        if "sql" in data and "payload" not in data:
            data = dict(data)
            sql_val = data.pop("sql")
            data["payload"] = {"sql": sql_val}
            data.setdefault("query_type", "sql")
        return data

    @property
    def sql(self) -> str | None:
        """Backward-compat: return SQL string from payload, or None."""
        return self.payload.get("sql")


class ExecutionHandle(BaseModel):
    """Reference returned when an execution is accepted."""

    execution_id: str
    connection: str
    state: ExecutionState
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sql_hash: str | None = None
    query_id: str | None = None


class ExecutionResult(BaseModel):
    """Normalized execution result shape."""

    execution_id: str
    state: ExecutionState
    data: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows_returned: int = 0
    rows_affected: int | None = None
    duration_ms: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: ExecutionError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
