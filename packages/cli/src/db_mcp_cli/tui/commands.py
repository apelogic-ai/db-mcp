"""TUI command dispatcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_mcp_cli.tui.app import DBMcpTUI

_COMMANDS = {"/confirm", "/cancel", "/clear", "/help", "/quit", "/status", "q"}


class CommandDispatcher:
    """Routes user input to the appropriate action."""

    def is_command(self, raw: str) -> bool:
        """Return True if the input is a recognized command."""
        return raw in _COMMANDS or raw.startswith("/")

    async def dispatch(self, raw: str, app: DBMcpTUI) -> None:
        """Dispatch a command string to the appropriate handler."""
        from db_mcp_cli.tui.widgets.feed import EventFeed

        feed = app.query_one(EventFeed)

        if raw in ("/confirm", "/cancel"):
            await self._handle_confirm(raw, app, feed)
        elif raw == "/clear":
            feed.clear_events()
        elif raw == "/help":
            feed.write(
                "[bold]Commands:[/]\n"
                "  /confirm  — confirm pending execution\n"
                "  /cancel   — cancel pending execution\n"
                "  /clear    — clear the feed\n"
                "  /status   — show server status\n"
                "  /help     — show this help\n"
                "  /quit, q  — exit"
            )
        elif raw in ("/quit", "q"):
            app.exit()
        elif raw == "/status":
            status = app.client.fetch_status()
            health = "\u2714 healthy" if status.server_healthy else "\u2718 disconnected"
            conn = status.connection or "none"
            feed.write(f"[dim]status:[/] {health}  |  connection: {conn}")
        else:
            feed.write(f"[red]unknown command:[/] {raw}")

    async def _handle_confirm(self, action: str, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        if not app.pending_confirm_id:
            evt = FeedEvent(
                id=f"err-no-pending-{datetime.now().timestamp()}",
                type="error",
                headline=f"no pending execution to {action[1:]}",
                timestamp=datetime.now(timezone.utc),
                done=True,
            )
            feed.add_event(evt)
            return

        action_name = action[1:]  # "confirm" or "cancel"
        success = app.client.confirm_execution(app.pending_confirm_id, action_name)
        if success:
            feed.write(f"[dim]{action_name}ed execution {app.pending_confirm_id}[/]")
        else:
            feed.write(f"[red]failed to {action_name} execution {app.pending_confirm_id}[/]")
        app.pending_confirm_id = None
