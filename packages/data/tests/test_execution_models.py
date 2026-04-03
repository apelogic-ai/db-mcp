"""Tests for unified execution model types."""

from db_mcp_data.execution import (
    ExecutionError,
    ExecutionErrorCode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
)


def test_execution_request_requires_connection():
    req = ExecutionRequest(connection="analytics_connection", sql="SELECT 1")
    assert req.connection == "analytics_connection"
    assert req.sql == "SELECT 1"


def test_execution_error_code_is_typed():
    err = ExecutionError(code=ExecutionErrorCode.TIMEOUT, message="timed out", retryable=True)
    assert err.code == ExecutionErrorCode.TIMEOUT
    assert err.retryable is True


def test_execution_result_error_payload():
    err = ExecutionError(code=ExecutionErrorCode.ENGINE, message="query failed")
    result = ExecutionResult(execution_id="exec-1", state=ExecutionState.FAILED, error=err)
    assert result.state == ExecutionState.FAILED
    assert result.error is not None
    assert result.error.code == ExecutionErrorCode.ENGINE
