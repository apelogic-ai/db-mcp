"""db-mcp TUI application."""

from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding

from db_mcp_cli.tui.client import APIClient
from db_mcp_cli.tui.commands import CommandDispatcher
from db_mcp_cli.tui.widgets.feed import EventFeed
from db_mcp_cli.tui.widgets.input import CommandInput
from db_mcp_cli.tui.widgets.status import StatusBar


class DBMcpTUI(App):
    """Terminal UI for db-mcp — event feed with command input."""

    TITLE = "db-mcp"
    CSS = """
    EventFeed {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, base_url: str = "http://localhost:8080", **kwargs) -> None:
        super().__init__(**kwargs)
        self.client = APIClient(base_url=base_url)
        self.dispatcher = CommandDispatcher()
        self.pending_confirm_id: str | None = None

    def compose(self) -> ComposeResult:
        yield EventFeed()
        yield CommandInput()
        yield StatusBar()

    def on_mount(self) -> None:
        """Start polling on mount."""
        self.set_interval(1.5, self._poll)

    async def dispatch_command(self, raw: str) -> None:
        """Dispatch a command from the input widget."""
        await self.dispatcher.dispatch(raw, self)

    def _poll(self) -> None:
        """Poll for new events (runs in Textual worker)."""
        self._poll_worker()

    @work(thread=True)
    def _poll_worker(self) -> None:
        """Background thread: fetch events and post to main thread."""
        events = self.client.fetch_executions()
        status = self.client.fetch_status()
        self.call_from_thread(self._apply_poll, events, status)

    def _apply_poll(self, events: list, status) -> None:
        """Apply polled data to widgets (main thread)."""
        feed = self.query_one(EventFeed)
        for event in events:
            feed.add_event(event)
            if event.pending_action == "confirm" and not event.done:
                self.pending_confirm_id = event.id
        self.query_one(StatusBar).update_status(status)
