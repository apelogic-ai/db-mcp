"""Tests for TUI ACP insider agent client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_acp_client_is_importable():
    from db_mcp_cli.tui.acp_client import ACPClient

    assert ACPClient is not None


def test_acp_client_construction():
    from db_mcp_cli.tui.acp_client import ACPClient

    client = ACPClient(agent_command="claude", mcp_url="http://localhost:8080/mcp")
    assert client.agent_command == "claude"
    assert client.mcp_url == "http://localhost:8080/mcp"
    assert client.session_id is None


@pytest.mark.asyncio
async def test_acp_client_prompt_starts_agent_if_needed():
    """First prompt should spawn the agent process and create a session."""
    from db_mcp_cli.tui.acp_client import ACPClient

    client = ACPClient(agent_command="claude", mcp_url="http://localhost:8080/mcp")

    mock_conn = AsyncMock()
    mock_conn.initialize.return_value = MagicMock(protocol_version=1)
    mock_conn.new_session.return_value = MagicMock(session_id="sess-1")
    mock_conn.prompt.return_value = MagicMock()

    mock_process = MagicMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=(mock_conn, mock_process))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("db_mcp_cli.tui.acp_client.spawn_agent_process", return_value=mock_ctx):
        await client.prompt("what is the revenue?", on_update=lambda text: None)

    mock_conn.initialize.assert_called_once()
    mock_conn.new_session.assert_called_once()
    mock_conn.prompt.assert_called_once()
    assert client.session_id == "sess-1"


@pytest.mark.asyncio
async def test_app_routes_plain_text_to_acp():
    """Plain text input (no /) should be routed to ACP prompt."""
    from db_mcp_cli.tui.app import DBMcpTUI

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.acp = MagicMock()
        pilot.app.acp.prompt = AsyncMock()

        await pilot.app.dispatch_command("what tables do we have?")
        await pilot.pause()

        pilot.app.acp.prompt.assert_called_once()
        call_args = pilot.app.acp.prompt.call_args
        assert "what tables do we have?" in call_args[0][0]
