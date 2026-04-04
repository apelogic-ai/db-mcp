"""StatusBar widget — bottom line showing connection and server state."""

from __future__ import annotations

from textual.widgets import Static

from db_mcp_cli.tui.events import StatusSnapshot


class StatusBar(Static):
    """Bottom status line showing connection and health."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._snapshot = StatusSnapshot()

    def update_status(self, snapshot: StatusSnapshot) -> None:
        """Update the status bar with new data."""
        self._snapshot = snapshot
        health = "[green]\u25cf[/]" if snapshot.server_healthy else "[red]\u25cf[/]"
        conn = snapshot.connection or "none"
        self.update(
            f"{health} {conn}  |  {snapshot.execution_count} executions"
        )
