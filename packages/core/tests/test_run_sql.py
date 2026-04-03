"""Tests for run_sql behavior with sql-like API connectors."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import db_mcp_data.gateway as gw
import pytest
from db_mcp_data.connectors.api import APIAuthConfig, APIConnector, APIConnectorConfig
from db_mcp_data.execution import engine as execution_engine
from db_mcp_data.execution.query_store import Query, QueryStatus

from db_mcp.config import reset_settings
from db_mcp.registry import ConnectionRegistry
from db_mcp.tools.generation import _get_result, _run_sql, _validate_sql

CONNECTION = "test_connection"
WRITE_CONNECTION = "write_connection"
ASYNC_CONNECTION = "analytics_connection"


@pytest.fixture(autouse=True)
def isolate_connection_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prevent tests from writing execution artifacts into ~/.db-mcp."""
    connections_dir = tmp_path / "connections"
    connections_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CONNECTIONS_DIR", str(connections_dir))
    reset_settings()
    ConnectionRegistry.reset()
    execution_engine._EXECUTION_STORE_CACHE.clear()
    yield
    reset_settings()
    ConnectionRegistry.reset()
    execution_engine._EXECUTION_STORE_CACHE.clear()


class _FakeSQLConnector:
    def execute_sql(self, sql: str):
        return [{"id": 1, "name": "Alice"}]


class _FakeAsyncSQLConnector:
    def __init__(self):
        self.status_calls = 0

    def submit_sql(self, sql: str):
        return {"mode": "async", "execution_id": "remote-exec-1"}

    def get_execution_status(self, execution_id: str):
        self.status_calls += 1
        if self.status_calls == 1:
            return {"state": "RUNNING"}
        return {"state": "QUERY_STATE_COMPLETED", "is_execution_finished": True}

    def get_execution_results(self, execution_id: str):
        return [{"token": "SOL", "volume": 123.0}]


class _FakeApiSyncAsyncConnector:
    def __init__(self):
        self.status_calls = 0

    def submit_sql(self, sql: str):
        return {"mode": "async", "execution_id": "remote-sync-mode-exec"}

    def get_execution_status(self, execution_id: str):
        self.status_calls += 1
        if self.status_calls == 1:
            return {"state": "RUNNING"}
        return {"state": "QUERY_STATE_COMPLETED", "is_execution_finished": True}

    def get_execution_results(self, execution_id: str):
        return [{"metric": "validators", "value": 827}]


class _FakeApiSyncSyncConnector:
    def submit_sql(self, sql: str):
        return {"mode": "sync", "rows": [{"ok": 1}]}


class _FakeQueryStore:
    def __init__(self, query: Query | None = None):
        self.query = query
        self.updated: list[tuple[str, QueryStatus]] = []

    async def get(self, query_id: str) -> Query | None:
        return self.query

    async def update_status(self, query_id: str, status: QueryStatus, **kwargs):
        self.updated.append((query_id, status))


@pytest.mark.asyncio
async def test_run_sql_requires_validate_when_supported():
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"supports_sql": True, "supports_validate_sql": True},
        ),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "error"
    assert "validate" in payload["error"].lower()


@pytest.mark.asyncio
async def test_run_sql_allows_direct_sql_for_api_sync():
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "api_sync",
            },
        ),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"
    assert payload["rows_returned"] == 1
    assert payload["data"][0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_run_sql_allows_direct_sql_for_standard_connector():
    """Standard SQL connectors (no sql_mode) should support direct SQL when validate disabled."""
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                # No sql_mode specified - this is the key difference from api_sync test
            },
        ),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"
    assert payload["rows_returned"] == 1
    assert payload["data"][0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_run_sql_allows_direct_sql_for_engine_mode():
    """Engine mode SQL connectors should support direct SQL when validate disabled."""
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "engine",  # This is what playground connector has
            },
        ),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"
    assert payload["rows_returned"] == 1
    assert payload["data"][0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_run_sql_direct_engine_mode_delegates_to_query_service():
    captured = {}

    async def _fake_run_sql(**kwargs):
        captured.update(kwargs)
        return {
            "status": "success",
            "mode": "sync",
            "query_id": "q-direct",
            "execution_id": "exec-direct",
            "state": "succeeded",
            "sql": "SELECT 1",
            "data": [{"ok": 1}],
            "columns": ["ok"],
            "rows_returned": 1,
            "duration_ms": 1.0,
            "provider_id": "test_connection",
            "cost_tier": "unknown",
            "statement_type": "SELECT",
            "is_write": False,
            "rows_affected": None,
        }

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "engine",
            },
        ),
        patch("db_mcp.tools.generation.query_service.run_sql", side_effect=_fake_run_sql),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"
    assert payload["query_id"] == "q-direct"
    assert captured["connection"] == CONNECTION
    assert captured["sql"] == "SELECT 1"
    assert callable(captured["execute_query"])
    assert callable(captured["generate_query_id"])
    assert captured["connection_path"].name == CONNECTION


@pytest.mark.asyncio
async def test_run_sql_direct_api_mode_delegates_to_query_service():
    captured = {}
    fake_connector = object()

    async def _fake_run_sql(**kwargs):
        captured.update(kwargs)
        return {
            "status": "submitted",
            "mode": "async",
            "query_id": "exec-api",
            "execution_id": "exec-api",
            "state": "running",
            "sql": "SELECT 1",
            "external_execution_id": "remote-exec-1",
            "message": "submitted",
            "poll_interval_seconds": 5,
        }

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=fake_connector),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "api_sync",
            },
        ),
        patch("db_mcp.tools.generation.query_service.run_sql", side_effect=_fake_run_sql),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "submitted"
    assert payload["query_id"] == "exec-api"
    assert captured["connection"] == CONNECTION
    assert captured["sql"] == "SELECT 1"
    assert captured["connector"] is fake_connector
    assert captured["capabilities"]["sql_mode"] == "api_sync"
    assert callable(captured["generate_query_id"])
    assert captured["direct_execute"] is None
    assert captured["connection_path"].name == CONNECTION


@pytest.mark.asyncio
async def test_run_sql_passes_validated_query_dependencies_without_mutating_query_service():
    from db_mcp.tools.generation import query_service

    captured = {}
    sentinel_ack_gate = object()
    fake_connector = object()

    async def _fake_run_sql(**kwargs):
        captured.update(kwargs)
        captured["current_ack_gate"] = query_service.check_protocol_ack_gate
        return {
            "status": "success",
            "query_id": "q-1",
            "execution_id": "exec-1",
            "state": "succeeded",
            "sql": "SELECT 1",
            "data": [],
            "columns": [],
            "rows_returned": 0,
            "duration_ms": 1.0,
            "provider_id": CONNECTION,
            "cost_tier": "auto",
            "statement_type": "SELECT",
            "is_write": False,
            "rows_affected": None,
        }

    with (
        patch("db_mcp.tools.generation.query_service.run_sql", side_effect=_fake_run_sql),
        patch("db_mcp.tools.generation.get_connector", return_value=fake_connector),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"supports_sql": True, "supports_validate_sql": True},
        ),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value="/tmp/test-connection",
        ),
        patch.object(query_service, "check_protocol_ack_gate", sentinel_ack_gate),
    ):
        result = await _run_sql(query_id="q-1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"
    assert captured["connection"] == CONNECTION
    assert captured["query_id"] == "q-1"
    assert captured["connector"] is fake_connector
    assert captured["capabilities"]["supports_validate_sql"] is True
    # query_store_factory is no longer injected — run_sql routes through gateway lifecycle
    assert "query_store_factory" not in captured
    assert callable(captured["protocol_ack_checker"])
    assert callable(captured["execution_policy_evaluator"])
    assert captured["connection_path"] == Path("/tmp/test-connection")
    assert captured["current_ack_gate"] is sentinel_ack_gate


@pytest.mark.asyncio
async def test_run_sql_uses_api_connector_capabilities_not_file_defaults(tmp_path: Path):
    """APIConnector inherits FileConnector; runtime caps must still resolve as API."""
    conn_path = tmp_path / "conn"
    data_dir = conn_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    connector = APIConnector(
        APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token="test-token"),
            capabilities={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "api_sync",
            },
        ),
        data_dir=str(data_dir),
    )

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=connector),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value=str(conn_path),
        ),
        patch.object(connector, "submit_sql", return_value={"mode": "sync", "rows": [{"ok": 1}]}),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"
    assert payload["rows_returned"] == 1
    assert payload["data"][0]["ok"] == 1


@pytest.mark.asyncio
async def test_run_sql_api_async_submits_and_get_result_polls(tmp_path: Path):
    """api_async connectors should submit and then resolve through get_result polling."""
    connection_path = tmp_path / "conn"
    connection_path.mkdir(parents=True, exist_ok=True)
    connector = _FakeAsyncSQLConnector()

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
        submit_result = await _run_sql(sql="SELECT 1", connection=CONNECTION)
        submit_payload = submit_result.structuredContent
        assert submit_payload["status"] == "submitted"
        execution_id = submit_payload["execution_id"]

        running = await _get_result(query_id=execution_id, connection=CONNECTION)
        running_payload = running.structuredContent
        assert running_payload["status"] == "running"

        complete = await _get_result(query_id=execution_id, connection=CONNECTION)
        complete_payload = complete.structuredContent
        assert complete_payload["status"] == "complete"
        assert complete_payload["rows_returned"] == 1
        assert complete_payload["data"][0]["token"] == "SOL"


@pytest.mark.asyncio
async def test_run_sql_api_sync_submits_async_and_get_result_polls(tmp_path: Path):
    """api_sync connectors may still return execution_id and should use unified polling."""
    connection_path = tmp_path / "conn"
    connection_path.mkdir(parents=True, exist_ok=True)
    connector = _FakeApiSyncAsyncConnector()

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=connector),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "supports_async_jobs": False,
                "sql_mode": "api_sync",
            },
        ),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value=str(connection_path),
        ),
    ):
        submit_result = await _run_sql(sql="SELECT 1", connection=CONNECTION)
        submit_payload = submit_result.structuredContent
        assert submit_payload["status"] == "submitted"
        execution_id = submit_payload["execution_id"]
        assert submit_payload["external_execution_id"] == "remote-sync-mode-exec"

        running = await _get_result(query_id=execution_id, connection=CONNECTION)
        running_payload = running.structuredContent
        assert running_payload["status"] == "running"

        complete = await _get_result(query_id=execution_id, connection=CONNECTION)
        complete_payload = complete.structuredContent
        assert complete_payload["status"] == "complete"
        assert complete_payload["rows_returned"] == 1
        assert complete_payload["data"][0]["metric"] == "validators"


@pytest.mark.asyncio
async def test_run_sql_api_sync_submit_sql_sync_returns_success(tmp_path: Path):
    """api_sync connectors returning sync rows via submit_sql should complete immediately."""
    connection_path = tmp_path / "conn"
    connection_path.mkdir(parents=True, exist_ok=True)
    connector = _FakeApiSyncSyncConnector()

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=connector),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "supports_async_jobs": False,
                "sql_mode": "api_sync",
            },
        ),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value=str(connection_path),
        ),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"
    assert payload["rows_returned"] == 1
    assert payload["data"][0]["ok"] == 1


@pytest.mark.asyncio
async def test_run_sql_direct_sql_blocked_when_protocol_ack_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    connection_path = tmp_path / "conn"
    connection_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DB_MCP_REQUIRE_PROTOCOL_ACK", "1")

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
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

    payload = result.structuredContent
    assert payload["status"] == "error"
    assert payload["error_code"] == "POLICY"


@pytest.mark.asyncio
async def test_run_sql_direct_sql_response_no_validate_mention():
    """Success response must not tell user to call validate_sql."""
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "api_sync",
            },
        ),
    ):
        result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"
    # Check the text content doesn't mention validate_sql
    text_parts = [c.text for c in result.content if hasattr(c, "text")]
    full_text = " ".join(text_parts).lower()
    assert (
        "validate_sql" not in full_text
        or "not supported" in full_text
        or "not needed" in full_text
    )


@pytest.mark.asyncio
async def test_run_sql_no_params_guidance_adapts():
    """When called with no params, guidance should mention direct sql option."""
    result = await _run_sql(connection=CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "error"
    assert any(
        "run_sql(connection=..., sql=...)" in step for step in payload["guidance"]["next_steps"]
    )


@pytest.mark.asyncio
async def test_validate_sql_reports_unsupported_for_api_connector(monkeypatch):
    monkeypatch.setattr(
        gw, "capabilities", lambda connection_path: {"supports_validate_sql": False}
    )
    result = await _validate_sql("SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["valid"] is False
    assert "not supported" in payload["error"].lower()


@pytest.mark.asyncio
async def test_validate_sql_rejects_write_by_default():
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"supports_validate_sql": True},
        ),
    ):
        result = await _validate_sql("INSERT INTO users(id) VALUES (1)", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["valid"] is False
    assert "not allowed" in payload["error"].lower()


@pytest.mark.asyncio
async def test_validate_sql_allows_write_when_enabled_for_connection(monkeypatch):
    query = Query(
        query_id="q-1",
        sql="INSERT INTO users(id) VALUES (1)",
        status=QueryStatus.VALIDATED,
        connection=WRITE_CONNECTION,
    )

    class _Store:
        async def register_validated(self, **kwargs):
            return query

    monkeypatch.setattr(
        gw,
        "capabilities",
        lambda connection_path: {
            "supports_validate_sql": True,
            "allow_sql_writes": True,
            "allowed_write_statements": ["INSERT"],
            "require_write_confirmation": True,
        },
    )
    with patch("db_mcp_data.execution.query_store.get_query_store", return_value=_Store()):
        result = await _validate_sql(
            "INSERT INTO users(id) VALUES (1)", connection=WRITE_CONNECTION
        )

    payload = result.structuredContent
    assert payload["valid"] is True
    assert payload["query_id"] == "q-1"
    assert payload["is_write"] is True
    assert payload["statement_type"] == "INSERT"


@pytest.mark.asyncio
async def test_validate_sql_rejects_disallowed_write_statement(monkeypatch):
    monkeypatch.setattr(
        gw,
        "capabilities",
        lambda connection_path: {
            "supports_validate_sql": True,
            "allow_sql_writes": True,
            "allowed_write_statements": ["INSERT"],
        },
    )
    result = await _validate_sql("DELETE FROM users WHERE id = 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["valid"] is False
    assert "not enabled" in payload["error"].lower()


@pytest.mark.asyncio
async def test_validate_sql_passes_dependencies_without_mutating_query_service():
    """_validate_sql passes policy injection kwargs to validate_sql without
    mutating query_service module attributes.  query_store_factory is no longer
    injected; persistence routes through gateway.create() exclusively."""
    from db_mcp.tools.generation import query_service

    captured = {}
    sentinel_explain = object()

    async def _fake_validate_sql(**kwargs):
        captured.update(kwargs)
        captured["current_explain_sql"] = query_service.explain_sql
        return {"valid": True, "query_id": "q-1"}

    with (
        patch(
            "db_mcp.tools.generation.query_service.validate_sql",
            side_effect=_fake_validate_sql,
        ),
        patch.object(
            query_service,
            "explain_sql",
            sentinel_explain,
        ),
    ):
        result = await _validate_sql("SELECT 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["valid"] is True
    assert captured["connection"] == CONNECTION
    assert captured["sql"] == "SELECT 1"
    # query_store_factory is no longer injected — persistence goes through gateway.create()
    assert "query_store_factory" not in captured
    assert callable(captured["validate_permissions"])
    assert callable(captured["write_policy_getter"])
    assert callable(captured["should_explain"])
    assert callable(captured["explain"])
    assert captured["current_explain_sql"] is sentinel_explain


@pytest.mark.asyncio
async def test_run_sql_write_requires_confirmation_by_default():
    query = Query(
        query_id="q-1",
        sql="INSERT INTO users(id) VALUES (1)",
        status=QueryStatus.VALIDATED,
        connection=WRITE_CONNECTION,
    )
    store = _FakeQueryStore(query=query)

    with (
        patch("db_mcp_data.execution.query_store.get_query_store", return_value=store),
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.utils.resolve_connection",
            return_value=(_FakeSQLConnector(), WRITE_CONNECTION, Path("/tmp/write_connection")),
        ),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"allow_sql_writes": True, "require_write_confirmation": True},
        ),
        patch("db_mcp.tools.generation._execute_query") as mock_execute,
    ):
        result = await _run_sql(query_id="q-1", connection=WRITE_CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "confirm_required"
    assert payload["is_write"] is True
    mock_execute.assert_not_called()


@pytest.mark.asyncio
async def test_run_sql_write_executes_when_confirmed():
    query = Query(
        query_id="q-1",
        sql="INSERT INTO users(id) VALUES (1)",
        status=QueryStatus.VALIDATED,
        connection=WRITE_CONNECTION,
    )
    store = _FakeQueryStore(query=query)

    from db_mcp_models.gateway import DataResponse

    with (
        patch("db_mcp_data.execution.query_store.get_query_store", return_value=store),
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"allow_sql_writes": True, "require_write_confirmation": True},
        ),
        # gateway.execute() is now the execution dispatch boundary.
        patch.object(
            gw,
            "execute",
            new=AsyncMock(
                return_value=DataResponse(
                    status="success",
                    data=[],
                    columns=[],
                    rows_returned=0,
                )
            ),
        ),
        patch.object(gw, "mark_running", new=AsyncMock()),
        patch.object(gw, "mark_complete", new=AsyncMock()),
        patch.object(gw, "mark_error", new=AsyncMock()),
    ):
        result = await _run_sql(query_id="q-1", confirmed=True, connection=WRITE_CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "success"


@pytest.mark.asyncio
async def test_get_result_can_read_direct_sql_execution_result(tmp_path: Path):
    """Direct run_sql execution IDs should be retrievable through get_result fallback."""
    connection_path = tmp_path / "conn"
    connection_path.mkdir(parents=True)

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "api_sync",
            },
        ),
        patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value=str(connection_path),
        ),
    ):
        run_result = await _run_sql(sql="SELECT 1", connection=CONNECTION)

        run_payload = run_result.structuredContent
        assert run_payload["status"] == "success"
        execution_id = run_payload.get("execution_id")
        assert execution_id

        get_result = await _get_result(query_id=execution_id, connection=CONNECTION)
        get_payload = get_result.structuredContent
        assert get_payload["status"] == "complete"
        assert get_payload["execution_id"] == execution_id
        assert get_payload["rows_returned"] == 1


@pytest.mark.asyncio
async def test_get_result_resolves_api_execution_ids_not_in_query_store(tmp_path: Path):
    from db_mcp_data.connectors.api import (
        APIAuthConfig,
        APIConnector,
        APIConnectorConfig,
        APIEndpointConfig,
    )

    connector = APIConnector(
        APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="header", token_env="TEST_API_KEY"),
            endpoints=[
                APIEndpointConfig(
                    name="get_execution_status",
                    path="/execution/{execution_id}/status",
                    method="GET",
                ),
                APIEndpointConfig(
                    name="get_execution_results",
                    path="/execution/{execution_id}/results",
                    method="GET",
                ),
            ],
        ),
        data_dir=str(tmp_path / "data"),
    )

    def _query_endpoint(name: str, params=None, **kwargs):
        if name == "get_execution_status":
            return {
                "data": [
                    {
                        "execution_id": "exec-123",
                        "state": "QUERY_STATE_COMPLETED",
                        "is_execution_finished": True,
                    }
                ],
                "rows_returned": 1,
            }
        if name == "get_execution_results":
            return {"data": [{"token": "SOL", "volume": 1000}], "rows_returned": 1}
        return {"error": f"Unknown endpoint: {name}"}

    connector.query_endpoint = _query_endpoint  # type: ignore[method-assign]
    connector.api_config.endpoints = [
        SimpleNamespace(name="get_execution_status"),
        SimpleNamespace(name="get_execution_results"),
    ]

    class _MissingStore:
        async def get(self, query_id: str):
            return None

    with (
        patch("db_mcp_data.execution.query_store.get_query_store", return_value=_MissingStore()),
        patch(
            "db_mcp.tools.utils.resolve_connection",
            return_value=(connector, ASYNC_CONNECTION, Path("/tmp/analytics_connection")),
        ),
    ):
        result = await _get_result("exec-123", connection=ASYNC_CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "complete"
    assert payload["query_id"] == "exec-123"
    assert payload["rows_returned"] == 1
    assert payload["data"][0]["token"] == "SOL"


@pytest.mark.asyncio
async def test_get_result_surfaces_api_execution_failures(tmp_path: Path):
    from db_mcp_data.connectors.api import (
        APIAuthConfig,
        APIConnector,
        APIConnectorConfig,
        APIEndpointConfig,
    )

    connector = APIConnector(
        APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="header", token_env="TEST_API_KEY"),
            endpoints=[
                APIEndpointConfig(
                    name="get_execution_status",
                    path="/execution/{execution_id}/status",
                    method="GET",
                )
            ],
        ),
        data_dir=str(tmp_path / "data"),
    )

    connector.query_endpoint = lambda name, params=None, **kwargs: {  # type: ignore[method-assign]
        "data": [
            {
                "execution_id": "exec-123",
                "state": "QUERY_STATE_FAILED",
                "error": {"message": "line 1:15: mismatched input 'FROMM'"},
            }
        ],
        "rows_returned": 1,
    }
    connector.api_config.endpoints = [SimpleNamespace(name="get_execution_status")]

    class _MissingStore:
        async def get(self, query_id: str):
            return None

    with (
        patch("db_mcp_data.execution.query_store.get_query_store", return_value=_MissingStore()),
        patch(
            "db_mcp.tools.utils.resolve_connection",
            return_value=(connector, ASYNC_CONNECTION, Path("/tmp/analytics_connection")),
        ),
    ):
        result = await _get_result("exec-123", connection=ASYNC_CONNECTION)

    payload = result.structuredContent
    assert payload["status"] == "error"
    assert "FROMM" in payload["error"]
