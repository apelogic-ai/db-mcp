"""Tests for TUI application using Textual pilot."""

from __future__ import annotations

import pytest


def test_tui_app_is_importable():
    from db_mcp_cli.tui.app import DBMcpTUI

    assert DBMcpTUI is not None


@pytest.mark.asyncio
async def test_tui_app_has_feed_and_status_bar():
    """App must compose an EventFeed and StatusBar."""
    from db_mcp_cli.tui.app import DBMcpTUI

    async with DBMcpTUI().run_test() as pilot:
        from db_mcp_cli.tui.widgets.feed import EventFeed
        from db_mcp_cli.tui.widgets.status import StatusBar

        feed = pilot.app.query_one(EventFeed)
        status = pilot.app.query_one(StatusBar)
        assert feed is not None
        assert status is not None


@pytest.mark.asyncio
async def test_tui_app_feed_can_add_event():
    """EventFeed must accept FeedEvent objects."""
    from datetime import datetime, timezone

    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.events import FeedEvent
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        feed = pilot.app.query_one(EventFeed)
        evt = FeedEvent(
            id="test-001",
            type="query",
            headline="SELECT 1",
            timestamp=datetime.now(timezone.utc),
            done=True,
        )
        feed.add_event(evt)
        await pilot.pause()
        assert feed.event_count == 1


@pytest.mark.asyncio
async def test_tui_app_feed_deduplicates():
    """Adding the same event ID twice should not duplicate it."""
    from datetime import datetime, timezone

    from db_mcp_cli.tui.app import DBMcpTUI
    from db_mcp_cli.tui.events import FeedEvent
    from db_mcp_cli.tui.widgets.feed import EventFeed

    async with DBMcpTUI().run_test() as pilot:
        feed = pilot.app.query_one(EventFeed)
        evt = FeedEvent(
            id="test-dup",
            type="query",
            headline="SELECT 1",
            timestamp=datetime.now(timezone.utc),
            done=True,
        )
        feed.add_event(evt)
        feed.add_event(evt)
        await pilot.pause()
        assert feed.event_count == 1
