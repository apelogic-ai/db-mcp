"""Tests for TUI event model."""

from __future__ import annotations

from datetime import datetime, timezone


def test_feed_event_is_importable():
    from db_mcp_cli.tui.events import FeedEvent

    assert FeedEvent is not None


def test_feed_event_construction():
    from db_mcp_cli.tui.events import FeedEvent

    evt = FeedEvent(
        id="exec-001",
        type="query",
        headline="SELECT COUNT(*) FROM users",
        timestamp=datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert evt.id == "exec-001"
    assert evt.type == "query"
    assert evt.done is False
    assert evt.sub_lines == []
    assert evt.pending_action is None


def test_feed_event_render_pending():
    from db_mcp_cli.tui.events import FeedEvent

    evt = FeedEvent(
        id="exec-002",
        type="query",
        headline="monthly revenue by region",
        timestamp=datetime.now(timezone.utc),
    )
    markup = evt.render()
    assert "monthly revenue" in markup
    assert "\u25cf" in markup  # ● bullet


def test_feed_event_render_done():
    from db_mcp_cli.tui.events import FeedEvent

    evt = FeedEvent(
        id="exec-003",
        type="query",
        headline="monthly revenue by region",
        sub_lines=["38ms  |  1,240 rows"],
        done=True,
        timestamp=datetime.now(timezone.utc),
    )
    markup = evt.render()
    assert "\u23bf" in markup or "\u2514" in markup or "\u239c" in markup or "38ms" in markup


def test_feed_event_from_execution():
    """FeedEvent.from_execution builds from an execution dict."""
    from db_mcp_cli.tui.events import FeedEvent

    execution = {
        "execution_id": "abc-123",
        "state": "succeeded",
        "sql": "SELECT 1",
        "duration_ms": 42.0,
        "rows_returned": 5,
        "created_at": 1743681600.0,
    }
    evt = FeedEvent.from_execution(execution)
    assert evt.id == "abc-123"
    assert evt.type == "query"
    assert evt.done is True
    assert "SELECT 1" in evt.headline
