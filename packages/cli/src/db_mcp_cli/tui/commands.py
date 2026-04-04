"""TUI command dispatcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_mcp_cli.tui.app import DBMcpTUI

_COMMANDS = {
    "/confirm", "/cancel", "/clear", "/help", "/quit", "/status",
    "/dismiss", "/list", "q",
}


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
        elif raw.startswith("/add-rule"):
            await self._handle_add_rule(raw[9:].strip(), app, feed)
        elif raw == "/dismiss":
            await self._handle_dismiss(app, feed)
        elif raw.startswith("/use"):
            await self._handle_use(raw[4:].strip(), app, feed)
        elif raw == "/clear":
            feed.clear_events()
        elif raw == "/help":
            feed.write(
                "[bold]Commands:[/]\n"
                "  /confirm       — confirm pending execution\n"
                "  /cancel        — cancel pending execution\n"
                "  /add-rule TEXT — add a business rule (or use suggested)\n"
                "  /dismiss       — dismiss pending knowledge gap\n"
                "  /use NAME      — switch connection\n"
                "  /clear         — clear the feed\n"
                "  /status        — show server status\n"
                "  /help          — show this help\n"
                "  /quit, q       — exit"
            )
        elif raw in ("/quit", "q"):
            app.exit()
        elif raw == "/status":
            status = app.client.fetch_status()
            health = "\u2714 healthy" if status.server_healthy else "\u2718 disconnected"
            conn = status.connection or "none"
            feed.write(f"[dim]status:[/] {health}  |  connection: {conn}")
        elif raw.startswith("/"):
            feed.write(f"[red]unknown command:[/] {raw}")
        else:
            # Plain text → ACP insider agent
            await self._handle_acp_prompt(raw, app, feed)

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
            feed.write(
                f"[red]failed to {action_name} execution {app.pending_confirm_id}[/]"
            )
        app.pending_confirm_id = None

    async def _handle_add_rule(self, text: str, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        if not text and app.pending_gap:
            # Extract suggested rule from gap sub_lines
            for line in app.pending_gap.sub_lines:
                if line.startswith("suggested: "):
                    text = line[len("suggested: "):]
                    break

        if not text:
            evt = FeedEvent(
                id=f"err-no-rule-{datetime.now().timestamp()}",
                type="error",
                headline="no rule text provided and no pending gap with suggestion",
                timestamp=datetime.now(timezone.utc),
                done=True,
            )
            feed.add_event(evt)
            return

        success = app.client.add_rule(text)
        if success:
            feed.write(f"[dim]rule added:[/] {text}")
        else:
            feed.write(f"[red]failed to add rule:[/] {text}")
        app.pending_gap = None

    async def _handle_dismiss(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        if not app.pending_gap:
            evt = FeedEvent(
                id=f"err-no-gap-{datetime.now().timestamp()}",
                type="error",
                headline="no pending gap to dismiss",
                timestamp=datetime.now(timezone.utc),
                done=True,
            )
            feed.add_event(evt)
            return

        success = app.client.dismiss_gap(app.pending_gap.id)
        if success:
            feed.write(f"[dim]dismissed gap {app.pending_gap.id}[/]")
        else:
            feed.write(f"[red]failed to dismiss gap {app.pending_gap.id}[/]")
        app.pending_gap = None

    async def _handle_use(self, name: str, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        if not name:
            evt = FeedEvent(
                id=f"err-no-conn-{datetime.now().timestamp()}",
                type="error",
                headline="usage: /use CONNECTION_NAME",
                timestamp=datetime.now(timezone.utc),
                done=True,
            )
            feed.add_event(evt)
            return

        success = app.client.switch_connection(name)
        if success:
            feed.write(f"[bold]\u25cf[/] \u2192 connection: {name}")
        else:
            feed.write(f"[red]failed to switch to {name}[/]")

    async def _handle_acp_prompt(self, text: str, app: DBMcpTUI, feed) -> None:
        feed.write(f"[bold]\u25cf[/] {text}")

        def on_update(update_text: str) -> None:
            app.call_from_thread(feed.write, f"  [dim]\u23bf[/]  {update_text}")

        try:
            await app.acp.prompt(text, on_update=on_update)
        except Exception as e:
            feed.write(f"[red]agent error:[/] {e}")
