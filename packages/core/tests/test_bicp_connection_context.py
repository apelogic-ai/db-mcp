"""Regression tests for BICP active-connection routing."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from db_mcp.bicp.agent import DBMCPAgent


def _make_agent() -> DBMCPAgent:
    agent = DBMCPAgent.__new__(DBMCPAgent)
    agent._settings = MagicMock()
    agent._settings.provider_id = "default"
    agent._settings.get_effective_provider_id.return_value = "default"
    agent._settings.get_effective_connection_path.return_value = Path("/tmp/connections/default")
    return agent


@pytest.mark.asyncio
async def test_generate_candidates_uses_active_connection_for_schema_and_examples():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    schema = MagicMock()
    schema.tables = []
    examples = SimpleNamespace(examples=[])

    query = SimpleNamespace(natural_language="show me events")

    with (
        patch.object(agent, "_get_active_connection_path", return_value=active_path),
        patch(
            "db_mcp.bicp.agent.load_schema_descriptions", return_value=schema
        ) as mock_load_schema,
        patch("db_mcp.bicp.agent.load_examples", return_value=examples) as mock_load_examples,
    ):
        await agent.generate_candidates(MagicMock(), query)

    assert mock_load_schema.call_args.kwargs["connection_path"] == active_path
    assert mock_load_schema.call_args.args[0] == "wifimetrics-trino"
    assert mock_load_examples.call_args.args[0] == "wifimetrics-trino"


@pytest.mark.asyncio
async def test_execute_query_uses_active_connection_for_connector():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    query = SimpleNamespace(final_sql="SELECT 1")
    connector = MagicMock()
    connector.execute_sql.return_value = [{"x": 1}]

    with (
        patch.object(agent, "_get_active_connection_path", return_value=active_path),
        patch("db_mcp.bicp.agent.get_connector", return_value=connector) as mock_get_connector,
        patch("db_mcp.bicp.agent.get_connector_capabilities", return_value={}),
        patch(
            "db_mcp.bicp.agent.validate_sql_permissions",
            return_value=(True, None, "SELECT", False),
        ),
    ):
        await agent.execute_query(MagicMock(), query)

    assert mock_get_connector.call_args.kwargs["connection_path"] == active_path


@pytest.mark.asyncio
async def test_schema_tables_handler_uses_active_connection_context():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    connector = MagicMock()
    connector.get_tables.return_value = [{"name": "events", "full_name": "chinook.public.events"}]
    schema = SimpleNamespace(tables=[])

    with (
        patch.object(agent, "_get_active_connection_path", return_value=active_path),
        patch("db_mcp.bicp.agent.get_connector", return_value=connector) as mock_get_connector,
        patch(
            "db_mcp.bicp.agent.load_schema_descriptions", return_value=schema
        ) as mock_load_schema,
    ):
        result = await agent._handle_schema_tables({"schema": "public", "catalog": "chinook"})

    assert result["success"] is True
    assert mock_get_connector.call_args.kwargs["connection_path"] == active_path
    assert mock_load_schema.call_args.kwargs["connection_path"] == active_path
    assert mock_load_schema.call_args.args[0] == "wifimetrics-trino"


@pytest.mark.asyncio
async def test_execute_query_allows_write_when_connection_policy_enables_it():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    query = SimpleNamespace(final_sql="INSERT INTO events(id) VALUES (1)")
    connector = MagicMock()
    connector.execute_sql.return_value = []

    with (
        patch.object(agent, "_get_active_connection_path", return_value=active_path),
        patch("db_mcp.bicp.agent.get_connector", return_value=connector),
        patch(
            "db_mcp.bicp.agent.get_connector_capabilities",
            return_value={
                "allow_sql_writes": True,
                "allowed_write_statements": ["INSERT"],
                "require_write_confirmation": False,
            },
        ),
    ):
        columns, rows = await agent.execute_query(MagicMock(), query)

    assert columns == []
    assert rows == []
