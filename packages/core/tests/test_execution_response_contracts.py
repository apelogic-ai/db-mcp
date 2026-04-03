"""Strict response-contract tests for run_sql/get_result envelopes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from db_mcp_data.contracts.response_contracts import (
    GetResultCompleteContract,
    GetResultErrorContract,
    GetResultRunningContract,
    RunSqlAsyncErrorContract,
    RunSqlAsyncSubmittedContract,
    RunSqlSyncSuccessContract,
)

from db_mcp.tools.generation import _get_result, _run_sql

CONNECTION = "contract-conn"


class _FakeSyncConnector:
    def execute_sql(self, sql: str):
        return [{"token": "SOL", "volume": 10}]


class _FakeAsyncConnector:
    def __init__(self):
        self._status_calls = 0

    def submit_sql(self, sql: str):
        return {"mode": "async", "execution_id": "remote-1"}

    def get_execution_status(self, execution_id: str):
        self._status_calls += 1
        if self._status_calls == 1:
            return {"state": "RUNNING"}
        return {"state": "QUERY_STATE_COMPLETED", "is_execution_finished": True}

    def get_execution_results(self, execution_id: str):
        return [{"token": "JUP", "volume": 20}]


class _FakeAsyncFailConnector:
    def submit_sql(self, sql: str):
        raise RuntimeError("submit exploded")


@pytest.mark.asyncio
async def test_run_sql_sync_success_contract(tmp_path: Path):
    connection_path = tmp_path / "conn"
    connection_path.mkdir(parents=True)

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSyncConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "engine",
            },
        ),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value=str(connection_path),
        ),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    RunSqlSyncSuccessContract.model_validate(result.structuredContent)


@pytest.mark.asyncio
async def test_run_sql_async_submit_and_poll_contracts(tmp_path: Path):
    connection_path = tmp_path / "conn"
    connection_path.mkdir(parents=True)
    connector = _FakeAsyncConnector()

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=connector),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "supports_async_jobs": True,
                "sql_mode": "api_async",
            },
        ),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value=str(connection_path),
        ),
    ):
        submitted = await _run_sql(sql="SELECT 1", connection=CONNECTION)
        submitted_payload = submitted.structuredContent
        RunSqlAsyncSubmittedContract.model_validate(submitted_payload)

        execution_id = submitted_payload["execution_id"]
        running = await _get_result(query_id=execution_id, connection=CONNECTION)
        RunSqlAsyncSubmittedContract.model_validate(submitted_payload)
        GetResultRunningContract.model_validate(running.structuredContent)

        complete = await _get_result(query_id=execution_id, connection=CONNECTION)
        GetResultCompleteContract.model_validate(complete.structuredContent)


@pytest.mark.asyncio
async def test_run_sql_async_error_contract(tmp_path: Path):
    connection_path = tmp_path / "conn"
    connection_path.mkdir(parents=True)

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeAsyncFailConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "supports_async_jobs": True,
                "sql_mode": "api_async",
            },
        ),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value=str(connection_path),
        ),
    ):
        run_result = await _run_sql(sql="SELECT 1", connection=CONNECTION)
        payload = run_result.structuredContent
        RunSqlAsyncErrorContract.model_validate(payload)

        polled = await _get_result(query_id=payload["execution_id"], connection=CONNECTION)
        GetResultErrorContract.model_validate(polled.structuredContent)
