"""TDD tests for B2c — _api_query routes through ExecutionEngine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from db_mcp_data.execution.models import ExecutionHandle, ExecutionResult, ExecutionState


def _make_handle() -> ExecutionHandle:
    return ExecutionHandle(
        execution_id="exec-api-1",
        connection="myapi",
        state=ExecutionState.SUCCEEDED,
    )


def _make_result(state=ExecutionState.SUCCEEDED, data=None, error=None) -> ExecutionResult:
    from db_mcp_data.execution.models import ExecutionError, ExecutionErrorCode

    return ExecutionResult(
        execution_id="exec-api-1",
        state=state,
        data=data or [{"id": 1, "name": "alice"}],
        columns=["id", "name"],
        rows_returned=len(data or [{"id": 1, "name": "alice"}]),
        error=ExecutionError(code=ExecutionErrorCode.ENGINE, message=error) if error else None,
    )


# ---------------------------------------------------------------------------
# 1. _api_query returns execution_id in its response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_query_returns_execution_id():
    """_api_query must include execution_id in the returned dict."""
    mock_connector = MagicMock()
    mock_connector.query_endpoint.return_value = {
        "data": [{"id": 1}],
        "rows_returned": 1,
    }
    handle = _make_handle()
    result = _make_result()

    with (
        patch(
            "db_mcp.tools.api.require_connection",
            return_value="myapi",
        ),
        patch(
            "db_mcp.tools.api.resolve_connection",
            return_value=(mock_connector, "myapi", Path("/fake/conn")),
        ),
        patch(
            "db_mcp.tools.api.isinstance",
            side_effect=lambda obj, cls: True,
            create=True,
        ) if False else patch(
            "db_mcp.tools.api.APIConnector",
            new=type(mock_connector),
        ),
        patch(
            "db_mcp.tools.api.get_execution_engine"
        ) as mock_get_engine,
    ):
        mock_engine = MagicMock()
        mock_engine.submit_sync.return_value = (handle, result)
        mock_get_engine.return_value = mock_engine

        from db_mcp.tools.api import _api_query

        response = await _api_query(endpoint="users", connection="myapi")

    assert "execution_id" in response, "_api_query must return execution_id"
    assert response["execution_id"] == "exec-api-1"
    assert response["rows_returned"] == 1


# ---------------------------------------------------------------------------
# 2. _api_query calls ExecutionEngine.submit_sync (not connector directly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_query_uses_execution_engine():
    """_api_query must call engine.submit_sync, not connector.query_endpoint directly."""
    mock_connector = MagicMock()
    handle = _make_handle()
    result = _make_result()

    with (
        patch("db_mcp.tools.api.require_connection", return_value="myapi"),
        patch(
            "db_mcp.tools.api.resolve_connection",
            return_value=(mock_connector, "myapi", Path("/fake/conn")),
        ),
        patch("db_mcp.tools.api.APIConnector", new=type(mock_connector)),
        patch("db_mcp.tools.api.get_execution_engine") as mock_get_engine,
    ):
        mock_engine = MagicMock()
        mock_engine.submit_sync.return_value = (handle, result)
        mock_get_engine.return_value = mock_engine

        from db_mcp.tools.api import _api_query

        await _api_query(endpoint="users", connection="myapi", params={"page": 1})

    mock_engine.submit_sync.assert_called_once()
    # connector.query_endpoint is NOT called at the tool level — only inside the runner
    # which submit_sync invokes. The engine call proves the wiring.


# ---------------------------------------------------------------------------
# 3. _api_query with engine FAILED state returns error dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_query_engine_failure_returns_error():
    """When ExecutionEngine marks execution FAILED, _api_query returns an error dict."""
    mock_connector = MagicMock()
    handle = _make_handle()
    failed_result = _make_result(state=ExecutionState.FAILED, data=[], error="network timeout")

    with (
        patch("db_mcp.tools.api.require_connection", return_value="myapi"),
        patch(
            "db_mcp.tools.api.resolve_connection",
            return_value=(mock_connector, "myapi", Path("/fake/conn")),
        ),
        patch("db_mcp.tools.api.APIConnector", new=type(mock_connector)),
        patch("db_mcp.tools.api.get_execution_engine") as mock_get_engine,
    ):
        mock_engine = MagicMock()
        mock_engine.submit_sync.return_value = (handle, failed_result)
        mock_get_engine.return_value = mock_engine

        from db_mcp.tools.api import _api_query

        response = await _api_query(endpoint="users", connection="myapi")

    assert "error" in response
    assert "execution_id" not in response


# ---------------------------------------------------------------------------
# 4. Runner passed to submit_sync calls connector.query_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_query_runner_calls_connector_endpoint():
    """The runner passed to submit_sync must call connector.query_endpoint with correct args."""
    mock_connector = MagicMock()
    mock_connector.query_endpoint.return_value = {
        "data": [{"x": 1}],
        "rows_returned": 1,
    }

    captured_runner = None

    def capture_submit(request, runner):
        nonlocal captured_runner
        captured_runner = runner
        # Call the runner to verify it hits the connector
        runner_result = runner("")
        from db_mcp_data.execution.models import ExecutionHandle, ExecutionResult, ExecutionState

        h = ExecutionHandle(
            execution_id="exec-2",
            connection="myapi",
            state=ExecutionState.SUCCEEDED,
        )
        r = ExecutionResult(
            execution_id="exec-2",
            state=ExecutionState.SUCCEEDED,
            data=runner_result.get("data", []),
            columns=list(runner_result.get("data", [{}])[0].keys()),
            rows_returned=runner_result.get("rows_returned", 0),
        )
        return h, r

    with (
        patch("db_mcp.tools.api.require_connection", return_value="myapi"),
        patch(
            "db_mcp.tools.api.resolve_connection",
            return_value=(mock_connector, "myapi", Path("/fake/conn")),
        ),
        patch("db_mcp.tools.api.APIConnector", new=type(mock_connector)),
        patch("db_mcp.tools.api.get_execution_engine") as mock_get_engine,
    ):
        mock_engine = MagicMock()
        mock_engine.submit_sync.side_effect = capture_submit
        mock_get_engine.return_value = mock_engine

        from db_mcp.tools.api import _api_query

        await _api_query(
            endpoint="events", connection="myapi", params={"type": "click"}, max_pages=2
        )

    mock_connector.query_endpoint.assert_called_once_with(
        "events", {"type": "click"}, 2, id=None
    )


# ---------------------------------------------------------------------------
# 5. ExecutionRequest metadata carries endpoint info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_query_execution_request_metadata():
    """ExecutionRequest submitted to engine must carry endpoint name in metadata."""
    mock_connector = MagicMock()
    handle = _make_handle()
    result = _make_result()

    captured_request = None

    def capture_submit(request, runner):
        nonlocal captured_request
        captured_request = request
        return handle, result

    with (
        patch("db_mcp.tools.api.require_connection", return_value="myapi"),
        patch(
            "db_mcp.tools.api.resolve_connection",
            return_value=(mock_connector, "myapi", Path("/fake/conn")),
        ),
        patch("db_mcp.tools.api.APIConnector", new=type(mock_connector)),
        patch("db_mcp.tools.api.get_execution_engine") as mock_get_engine,
    ):
        mock_engine = MagicMock()
        mock_engine.submit_sync.side_effect = capture_submit
        mock_get_engine.return_value = mock_engine

        from db_mcp.tools.api import _api_query

        await _api_query(endpoint="orders", connection="myapi", params={"status": "open"})

    assert captured_request is not None
    assert captured_request.metadata.get("endpoint") == "orders"
    assert captured_request.connection == "myapi"
