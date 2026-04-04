"""TUI command dispatcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_mcp_cli.tui.app import DBMcpTUI


class CommandDispatcher:
    """Routes user input to the appropriate action."""

    async def dispatch(self, raw: str, app: DBMcpTUI) -> None:
        """Dispatch a command string to the appropriate handler."""
        from db_mcp_cli.tui.widgets.feed import EventFeed

        feed = app.query_one(EventFeed)

        # -- TUI commands --
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
            self._show_help(feed)
        elif raw in ("/quit", "q"):
            app.exit()

        # -- CLI commands --
        elif raw == "/connections":
            self._handle_connections(app, feed)
        elif raw == "/schema":
            self._handle_schema(app, feed)
        elif raw == "/rules":
            self._handle_rules(app, feed)
        elif raw == "/examples":
            self._handle_examples(app, feed)
        elif raw == "/metrics":
            self._handle_metrics(app, feed)
        elif raw == "/gaps":
            self._handle_gaps(app, feed)
        elif raw == "/status":
            self._handle_status(app, feed)
        elif raw == "/sync":
            self._handle_sync(app, feed)

        # -- ACP commands --
        elif raw == "/agent":
            self._handle_agent(app, feed)
        elif raw.startswith("/model"):
            await self._handle_model(raw[6:].strip(), app, feed)
        elif raw == "/session":
            self._handle_session(app, feed)

        elif raw.startswith("/"):
            feed.write(f"[red]unknown command:[/] {raw}")
        else:
            # Plain text -> ACP insider agent
            await self._handle_acp_prompt(raw, app, feed)

    # -----------------------------------------------------------------------
    # Help
    # -----------------------------------------------------------------------

    def _show_help(self, feed) -> None:
        feed.write(
            "[bold]Commands:[/]\n"
            "\n"
            "  [bold dim]Database[/]\n"
            "  /connections   — list all connections\n"
            "  /use NAME      — switch connection\n"
            "  /schema        — show tables\n"
            "  /rules         — list business rules\n"
            "  /examples      — list training examples\n"
            "  /metrics       — list metrics catalog\n"
            "  /gaps          — list knowledge gaps\n"
            "  /sync          — sync vault with git\n"
            "\n"
            "  [bold dim]Execution[/]\n"
            "  /confirm       — confirm pending execution\n"
            "  /cancel        — cancel pending execution\n"
            "  /add-rule TEXT — add a business rule\n"
            "  /dismiss       — dismiss pending gap\n"
            "\n"
            "  [bold dim]Agent[/]\n"
            "  /agent         — show agent status\n"
            "  /model NAME    — set agent model\n"
            "  /session       — show session info\n"
            "\n"
            "  [bold dim]General[/]\n"
            "  /status        — server status\n"
            "  /clear         — clear feed\n"
            "  /help          — this help\n"
            "  /quit, q       — exit"
        )

    # -----------------------------------------------------------------------
    # TUI commands
    # -----------------------------------------------------------------------

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

        action_name = action[1:]
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

    # -----------------------------------------------------------------------
    # CLI commands
    # -----------------------------------------------------------------------

    def _handle_connections(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        conns = app.client.list_connections()
        if not conns:
            feed.add_event(FeedEvent(
                id=f"conn-{datetime.now().timestamp()}",
                type="info",
                headline="no connections configured",
                timestamp=datetime.now(timezone.utc),
                done=True,
            ))
            return
        lines = []
        for c in conns:
            name = c.get("name", "?") if isinstance(c, dict) else str(c)
            active = c.get("active", False) if isinstance(c, dict) else False
            marker = " [green]\u25cf[/]" if active else ""
            lines.append(f"  {name}{marker}")
        feed.add_event(FeedEvent(
            id=f"conn-{datetime.now().timestamp()}",
            type="info",
            headline="connections",
            sub_lines=lines,
            timestamp=datetime.now(timezone.utc),
            done=True,
        ))

    def _handle_schema(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        tables = app.client.list_tables()
        if not tables:
            feed.add_event(FeedEvent(
                id=f"schema-{datetime.now().timestamp()}",
                type="info",
                headline="no tables found",
                timestamp=datetime.now(timezone.utc),
                done=True,
            ))
            return
        feed.add_event(FeedEvent(
            id=f"schema-{datetime.now().timestamp()}",
            type="info",
            headline=f"{len(tables)} tables",
            sub_lines=[f"  {t}" for t in tables],
            timestamp=datetime.now(timezone.utc),
            done=True,
        ))

    def _handle_rules(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        rules = app.client.list_rules()
        if not rules:
            feed.add_event(FeedEvent(
                id=f"rules-{datetime.now().timestamp()}",
                type="info",
                headline="no business rules",
                timestamp=datetime.now(timezone.utc),
                done=True,
            ))
            return
        feed.add_event(FeedEvent(
            id=f"rules-{datetime.now().timestamp()}",
            type="info",
            headline=f"{len(rules)} rules",
            sub_lines=[f"  {r}" for r in rules],
            timestamp=datetime.now(timezone.utc),
            done=True,
        ))

    def _handle_examples(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        examples = app.client.list_examples()
        count = len(examples)
        feed.add_event(FeedEvent(
            id=f"examples-{datetime.now().timestamp()}",
            type="info",
            headline=f"{count} training example(s)" if count else "no training examples",
            timestamp=datetime.now(timezone.utc),
            done=True,
        ))

    def _handle_metrics(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        metrics = app.client.list_metrics()
        if not metrics:
            feed.add_event(FeedEvent(
                id=f"metrics-{datetime.now().timestamp()}",
                type="info",
                headline="no metrics in catalog",
                timestamp=datetime.now(timezone.utc),
                done=True,
            ))
            return
        lines = [f"  {m.get('name', '?')}: {m.get('description', '')}" for m in metrics]
        feed.add_event(FeedEvent(
            id=f"metrics-{datetime.now().timestamp()}",
            type="info",
            headline=f"{len(metrics)} metrics",
            sub_lines=lines,
            timestamp=datetime.now(timezone.utc),
            done=True,
        ))

    def _handle_gaps(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        gaps = app.client.list_gaps()
        if not gaps:
            feed.add_event(FeedEvent(
                id=f"gaps-{datetime.now().timestamp()}",
                type="info",
                headline="no knowledge gaps",
                timestamp=datetime.now(timezone.utc),
                done=True,
            ))
            return
        lines = []
        for g in gaps:
            term = g.get("term", "?") if isinstance(g, dict) else str(g)
            lines.append(f"  {term}")
        feed.add_event(FeedEvent(
            id=f"gaps-{datetime.now().timestamp()}",
            type="info",
            headline=f"{len(gaps)} knowledge gaps",
            sub_lines=lines,
            timestamp=datetime.now(timezone.utc),
            done=True,
        ))

    def _handle_status(self, app: DBMcpTUI, feed) -> None:
        status = app.client.fetch_status()
        health = "\u2714 healthy" if status.server_healthy else "\u2718 disconnected"
        conn = status.connection or "none"
        feed.write(f"[dim]status:[/] {health}  |  connection: {conn}")

    def _handle_sync(self, app: DBMcpTUI, feed) -> None:
        success = app.client.sync_vault()
        if success:
            feed.write("[dim]vault synced[/]")
        else:
            feed.write("[red]vault sync failed[/]")

    # -----------------------------------------------------------------------
    # ACP commands
    # -----------------------------------------------------------------------

    def _handle_agent(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        connected = app.acp.session_id is not None
        status = "[green]connected[/]" if connected else "[dim]not connected[/]"
        lines = [
            f"  status: {status}",
            f"  command: {app.acp.agent_command}",
            f"  mcp: {app.acp.mcp_url}",
        ]
        if app.acp.session_id:
            lines.append(f"  session: {app.acp.session_id}")
        lines.append("  [dim]type any question to auto-connect[/]")
        feed.add_event(FeedEvent(
            id=f"agent-{datetime.now().timestamp()}",
            type="info",
            headline="agent",
            sub_lines=lines,
            timestamp=datetime.now(timezone.utc),
            done=True,
        ))

    async def _handle_model(self, model_name: str, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        if not model_name:
            feed.add_event(FeedEvent(
                id=f"err-model-{datetime.now().timestamp()}",
                type="error",
                headline="usage: /model MODEL_NAME",
                timestamp=datetime.now(timezone.utc),
                done=True,
            ))
            return

        if not app.acp.session_id:
            feed.write("[dim]agent not connected yet — type a question first[/]")
            return

        try:
            await app.acp._conn.set_session_model(
                model=model_name, session_id=app.acp.session_id
            )
            feed.write(f"[dim]model set to:[/] {model_name}")
        except Exception as e:
            feed.write(f"[red]failed to set model:[/] {e}")

    def _handle_session(self, app: DBMcpTUI, feed) -> None:
        from datetime import datetime, timezone

        from db_mcp_cli.tui.events import FeedEvent

        if not app.acp.session_id:
            feed.add_event(FeedEvent(
                id=f"session-{datetime.now().timestamp()}",
                type="info",
                headline="no active session",
                sub_lines=["  [dim]type any question to start a session[/]"],
                timestamp=datetime.now(timezone.utc),
                done=True,
            ))
            return
        feed.add_event(FeedEvent(
            id=f"session-{datetime.now().timestamp()}",
            type="info",
            headline=f"session {app.acp.session_id}",
            sub_lines=[
                f"  agent: {app.acp.agent_command}",
                f"  mcp: {app.acp.mcp_url}",
            ],
            timestamp=datetime.now(timezone.utc),
            done=True,
        ))

    # -----------------------------------------------------------------------
    # ACP prompt (plain text)
    # -----------------------------------------------------------------------

    async def _handle_acp_prompt(self, text: str, app: DBMcpTUI, feed) -> None:


        feed.write(f"[bold]\u25cf[/] {text}")
        feed.write("[dim]  \u23bf  thinking...[/]")

        result = app.client.query_nl(text)

        if "error" in result:
            feed.write(f"[red]  \u23bf  {result['error']}[/]")
            return

        # Show the response
        sql = result.get("sql", "")
        answer = result.get("answer", "")
        rows = result.get("rows", [])
        row_count = result.get("row_count", len(rows) if rows else 0)

        lines = []
        if sql:
            lines.append(f"[cyan]{sql}[/]")
        if answer:
            lines.append(answer)
        if row_count:
            lines.append(f"[dim]{row_count} row(s)[/]")

        if lines:
            for line in lines:
                feed.write(f"  [dim]\u23bf[/]  {line}")
        else:
            feed.write(f"  [dim]\u23bf[/]  {result}")
