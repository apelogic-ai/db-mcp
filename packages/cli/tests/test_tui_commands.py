"""Tests for TUI command input and dispatcher."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def test_command_dispatcher_is_importable():
    from db_mcp_cli.tui.commands import CommandDispatcher

    assert CommandDispatcher is not None


def test_dispatcher_recognizes_slash_commands():
    from db_mcp_cli.tui.commands import CommandDispatcher

    d = CommandDispatcher()
    assert d.is_command("/confirm")
    assert d.is_command("/cancel")
    assert d.is_command("/clear")
    assert d.is_command("/help")
    assert d.is_command("/quit")
    assert d.is_command("q")
    assert not d.is_command("SELECT 1")
    assert not d.is_command("hello world")


@pytest.mark.asyncio
async def test_app_has_command_input():
    """App must compose a CommandInput widget."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.input import CommandInput

    async with DBMcpTUI().run_test() as pilot:
        inp = pilot.app.query_one(CommandInput)
        assert inp is not None


@pytest.mark.asyncio
async def test_clear_command_resets_feed():
    """The /clear command should clear the event feed."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.events import FeedEvent
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        feed = pilot.app.query_one(EventFeed)
        feed.add_event(FeedEvent(
            id="x", type="query", headline="test",
            timestamp=datetime.now(timezone.utc), done=True,
        ))
        assert feed.event_count == 1

        await pilot.app.dispatch_command("/clear")
        await pilot.pause()
        assert feed.event_count == 0


@pytest.mark.asyncio
async def test_confirm_with_no_pending_shows_error():
    """Calling /confirm with no pending confirm should add an error."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        await pilot.app.dispatch_command("/confirm")
        await pilot.pause()
        feed = pilot.app.query_one(EventFeed)
        # Should have added an error event
        assert feed.event_count == 1


@pytest.mark.asyncio
async def test_confirm_with_pending_calls_client():
    """Calling /confirm with a pending confirm should invoke the client."""
    from db_mcp_cli.tui.app import DBMcpTUI

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.pending_confirm_id = "exec-999"
        pilot.app.client.confirm_execution = MagicMock(return_value=True)

        await pilot.app.dispatch_command("/confirm")
        await pilot.pause()

        pilot.app.client.confirm_execution.assert_called_once_with("exec-999", "confirm")
        assert pilot.app.pending_confirm_id is None


@pytest.mark.asyncio
async def test_cancel_with_pending_calls_client():
    """Calling /cancel with a pending confirm should cancel it."""
    from db_mcp_cli.tui.app import DBMcpTUI

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.pending_confirm_id = "exec-999"
        pilot.app.client.confirm_execution = MagicMock(return_value=True)

        await pilot.app.dispatch_command("/cancel")
        await pilot.pause()

        pilot.app.client.confirm_execution.assert_called_once_with("exec-999", "cancel")
        assert pilot.app.pending_confirm_id is None
