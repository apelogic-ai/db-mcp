"""Tests for TUI gap commands and connection switcher."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from db_mcp_cli.tui.events import FeedEvent


@pytest.mark.asyncio
async def test_add_rule_with_pending_gap():
    """'/add-rule' with no text should use the pending gap's suggested rule."""
    from db_mcp_cli.tui.app import DBMcpTUI

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.pending_gap = FeedEvent(
            id="gap-1",
            type="gap",
            headline="unknown term: churn",
            timestamp=datetime.now(timezone.utc),
            pending_action="gap",
            sub_lines=["suggested: churn means monthly cancellation rate"],
        )
        pilot.app.client.add_rule = MagicMock(return_value=True)

        await pilot.app.dispatch_command("/add-rule")
        await pilot.pause()

        pilot.app.client.add_rule.assert_called_once_with(
            "churn means monthly cancellation rate"
        )
        assert pilot.app.pending_gap is None


@pytest.mark.asyncio
async def test_add_rule_with_explicit_text():
    """'/add-rule foo bar' should use the explicit text."""
    from db_mcp_cli.tui.app import DBMcpTUI

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.client.add_rule = MagicMock(return_value=True)

        await pilot.app.dispatch_command("/add-rule churn = cancellation rate")
        await pilot.pause()

        pilot.app.client.add_rule.assert_called_once_with("churn = cancellation rate")


@pytest.mark.asyncio
async def test_add_rule_with_no_gap_and_no_text():
    """'/add-rule' with no pending gap and no text should show error."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        await pilot.app.dispatch_command("/add-rule")
        await pilot.pause()

        feed = pilot.app.query_one(EventFeed)
        assert feed.event_count == 1  # error event


@pytest.mark.asyncio
async def test_dismiss_with_pending_gap():
    """'/dismiss' should dismiss the pending gap."""
    from db_mcp_cli.tui.app import DBMcpTUI

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.pending_gap = FeedEvent(
            id="gap-2",
            type="gap",
            headline="unknown term: ARR",
            timestamp=datetime.now(timezone.utc),
            pending_action="gap",
        )
        pilot.app.client.dismiss_gap = MagicMock(return_value=True)

        await pilot.app.dispatch_command("/dismiss")
        await pilot.pause()

        pilot.app.client.dismiss_gap.assert_called_once_with("gap-2")
        assert pilot.app.pending_gap is None


@pytest.mark.asyncio
async def test_dismiss_with_no_pending_gap():
    """'/dismiss' with no pending gap should show error."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        await pilot.app.dispatch_command("/dismiss")
        await pilot.pause()

        feed = pilot.app.query_one(EventFeed)
        assert feed.event_count == 1  # error event


@pytest.mark.asyncio
async def test_use_switches_connection():
    """'/use mydb' should call switch_connection."""
    from db_mcp_cli.tui.app import DBMcpTUI

    async with DBMcpTUI().run_test() as pilot:
        pilot.app.client.switch_connection = MagicMock(return_value=True)

        await pilot.app.dispatch_command("/use mydb")
        await pilot.pause()

        pilot.app.client.switch_connection.assert_called_once_with("mydb")


@pytest.mark.asyncio
async def test_use_with_no_name_shows_error():
    """'/use' with no connection name should show error."""
    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        await pilot.app.dispatch_command("/use")
        await pilot.pause()

        feed = pilot.app.query_one(EventFeed)
        assert feed.event_count == 1  # error event
