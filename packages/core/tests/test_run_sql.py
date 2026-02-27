"""Tests for run_sql behavior with sql-like API connectors."""

from pathlib import Path
from unittest.mock import patch

import pytest

from db_mcp.tasks.store import Query, QueryStatus
from db_mcp.tools.generation import _run_sql, _validate_sql

CONNECTION = "test-conn"


class _FakeSQLConnector:
    def execute_sql(self, sql: str):
        return [{"id": 1, "name": "Alice"}]


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
async def test_validate_sql_reports_unsupported_for_api_connector():
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"supports_validate_sql": False},
        ),
    ):
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
async def test_validate_sql_allows_write_when_enabled_for_connection():
    query = Query(
        query_id="q-1",
        sql="INSERT INTO users(id) VALUES (1)",
        status=QueryStatus.VALIDATED,
        connection="prod",
    )

    class _Store:
        async def register_validated(self, **kwargs):
            return query

    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_validate_sql": True,
                "allow_sql_writes": True,
                "allowed_write_statements": ["INSERT"],
                "require_write_confirmation": True,
            },
        ),
        patch("db_mcp.tasks.store.get_query_store", return_value=_Store()),
    ):
        result = await _validate_sql("INSERT INTO users(id) VALUES (1)", connection="prod")

    payload = result.structuredContent
    assert payload["valid"] is True
    assert payload["query_id"] == "q-1"
    assert payload["is_write"] is True
    assert payload["statement_type"] == "INSERT"


@pytest.mark.asyncio
async def test_validate_sql_rejects_disallowed_write_statement():
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={
                "supports_validate_sql": True,
                "allow_sql_writes": True,
                "allowed_write_statements": ["INSERT"],
            },
        ),
    ):
        result = await _validate_sql("DELETE FROM users WHERE id = 1", connection=CONNECTION)

    payload = result.structuredContent
    assert payload["valid"] is False
    assert "not enabled" in payload["error"].lower()


@pytest.mark.asyncio
async def test_run_sql_write_requires_confirmation_by_default():
    query = Query(
        query_id="q-1",
        sql="INSERT INTO users(id) VALUES (1)",
        status=QueryStatus.VALIDATED,
        connection="prod",
    )
    store = _FakeQueryStore(query=query)

    with (
        patch("db_mcp.tasks.store.get_query_store", return_value=store),
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.utils.resolve_connection",
            return_value=(_FakeSQLConnector(), "prod", Path("/tmp/prod")),
        ),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"allow_sql_writes": True, "require_write_confirmation": True},
        ),
        patch("db_mcp.tools.generation._execute_query") as mock_execute,
    ):
        result = await _run_sql(query_id="q-1", connection="prod")

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
        connection="prod",
    )
    store = _FakeQueryStore(query=query)

    with (
        patch("db_mcp.tasks.store.get_query_store", return_value=store),
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.tools.utils.resolve_connection",
            return_value=(_FakeSQLConnector(), "prod", Path("/tmp/prod")),
        ),
        patch(
            "db_mcp.tools.generation.get_connector_capabilities",
            return_value={"allow_sql_writes": True, "require_write_confirmation": True},
        ),
        patch(
            "db_mcp.tools.generation._execute_query",
            return_value={
                "data": [],
                "columns": [],
                "rows_returned": 0,
                "duration_ms": 2.0,
                "provider_id": "prod",
                "statement_type": "INSERT",
                "is_write": True,
                "rows_affected": 1,
            },
        ),
    ):
        result = await _run_sql(query_id="q-1", confirmed=True, connection="prod")

    payload = result.structuredContent
    assert payload["status"] == "success"
    assert payload["is_write"] is True
    assert payload["rows_affected"] == 1
