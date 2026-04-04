"""EventFeed widget — scrolling event log."""

from __future__ import annotations

from textual.widgets import RichLog

from db_mcp_cli.tui.events import FeedEvent


class EventFeed(RichLog):
    """Scrolling feed of db-mcp events."""

    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=True, markup=True, **kwargs)
        self._seen_ids: set[str] = set()

    @property
    def event_count(self) -> int:
        return len(self._seen_ids)

    def add_event(self, event: FeedEvent) -> None:
        """Add an event to the feed, deduplicating by ID."""
        if event.id in self._seen_ids:
            return
        self._seen_ids.add(event.id)
        self.write(event.render())
