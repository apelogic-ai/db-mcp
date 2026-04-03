"""Versioned JSON-schema contracts for SQL execution tool responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

RESPONSE_CONTRACT_SCHEMA_VERSION = "v1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunSqlSyncSuccessContract(_StrictModel):
    status: Literal["success"]
    mode: Literal["sync"]
    execution_id: str
    state: Literal["succeeded"]
    query_id: str
    sql: str
    data: list[dict[str, Any]]
    columns: list[str]
    rows_returned: int
    duration_ms: float | None
    provider_id: str | None
    cost_tier: str
    statement_type: str
    is_write: bool
    rows_affected: int | None


class RunSqlAsyncSubmittedContract(_StrictModel):
    status: Literal["submitted"]
    mode: Literal["async"]
    query_id: str
    execution_id: str
    state: Literal["running"]
    sql: str
    external_execution_id: str
    message: str
    poll_interval_seconds: int


class RunSqlAsyncErrorContract(_StrictModel):
    status: Literal["error"]
    query_id: str
    execution_id: str
    state: Literal["failed"]
    error_code: Literal["ENGINE"]
    error: str
    sql: str


class GetResultRunningContract(_StrictModel):
    status: Literal["running"]
    query_id: str
    execution_id: str
    state: Literal["submitted", "running", "precheck"]
    external_execution_id: str | None
    message: str


class GetResultCompleteContract(_StrictModel):
    status: Literal["complete"]
    query_id: str
    execution_id: str
    state: Literal["succeeded"]
    sql: str | None
    data: list[dict[str, Any]]
    columns: list[str]
    rows_returned: int
    duration_ms: float | None


class GetResultErrorContract(_StrictModel):
    status: Literal["error"]
    query_id: str
    execution_id: str
    state: Literal["failed"]
    error: str
    error_code: str | None


def get_response_contract_models() -> dict[str, type[BaseModel]]:
    """Return named response-contract models for schema export."""
    return {
        "run_sql_sync_success": RunSqlSyncSuccessContract,
        "run_sql_async_submitted": RunSqlAsyncSubmittedContract,
        "run_sql_async_error": RunSqlAsyncErrorContract,
        "get_result_running": GetResultRunningContract,
        "get_result_complete": GetResultCompleteContract,
        "get_result_error": GetResultErrorContract,
    }


def build_response_contract_schemas() -> dict[str, dict[str, Any]]:
    """Build JSON schemas for all response-contract models."""
    schemas: dict[str, dict[str, Any]] = {}
    for name, model in get_response_contract_models().items():
        schemas[name] = model.model_json_schema()
    return schemas
