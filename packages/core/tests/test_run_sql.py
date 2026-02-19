"""Tests for run_sql behavior with sql-like API connectors."""

from unittest.mock import patch

import pytest

from db_mcp.tools.generation import _run_sql, _validate_sql


class _FakeSQLConnector:
    def execute_sql(self, sql: str):
        return [{"id": 1, "name": "Alice"}]


@pytest.mark.asyncio
async def test_run_sql_requires_validate_when_supported():
    with (
        patch("db_mcp.connectors.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.connectors.get_connector_capabilities",
            return_value={"supports_sql": True, "supports_validate_sql": True},
        ),
    ):
        result = await _run_sql(sql="SELECT 1")

    payload = result.structuredContent
    assert payload["status"] == "error"
    assert "validate" in payload["error"].lower()


@pytest.mark.asyncio
async def test_run_sql_allows_direct_sql_for_api_sync():
    with (
        patch("db_mcp.tools.generation.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.connectors.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "api_sync",
            },
        ),
    ):
        result = await _run_sql(sql="SELECT 1")

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
            "db_mcp.connectors.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                # No sql_mode specified - this is the key difference from api_sync test
            },
        ),
    ):
        result = await _run_sql(sql="SELECT 1")

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
            "db_mcp.connectors.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "engine",  # This is what playground connector has
            },
        ),
    ):
        result = await _run_sql(sql="SELECT 1")

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
            "db_mcp.connectors.get_connector_capabilities",
            return_value={
                "supports_sql": True,
                "supports_validate_sql": False,
                "sql_mode": "api_sync",
            },
        ),
    ):
        result = await _run_sql(sql="SELECT 1")

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
    result = await _run_sql()

    payload = result.structuredContent
    assert payload["status"] == "error"
    assert any("run_sql(sql=...)" in step for step in payload["guidance"]["next_steps"])


@pytest.mark.asyncio
async def test_validate_sql_reports_unsupported_for_api_connector():
    with (
        patch("db_mcp.connectors.get_connector", return_value=_FakeSQLConnector()),
        patch(
            "db_mcp.connectors.get_connector_capabilities",
            return_value={"supports_validate_sql": False},
        ),
    ):
        result = await _validate_sql("SELECT 1")

    payload = result.structuredContent
    assert payload["valid"] is False
    assert "not supported" in payload["error"].lower()
