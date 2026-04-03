# TUI Implementation Plan

See `tui-design.md` for the user-facing design. This document covers architecture,
module layout, and the phased build plan.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  db-mcp up                                                  │
│  ├── MCP server  (FastMCP streamable-http, port 7421)       │
│  └── UI server   (FastAPI, port 8080)                       │
└───────────────────────────┬─────────────────────────────────┘
                            │  REST API  (existing /api/*)
                            │  + POST /api/executions/{id}/confirm  (new)
              ┌─────────────▼────────────┐
              │   db-mcp tui             │
              │   Textual app            │
              │   ├── EventFeed          │
              │   ├── CommandInput       │
              │   └── StatusBar          │
              └──────────────────────────┘
```

The TUI is a Textual application that polls the existing FastAPI server for events.
No new transport. No WebSocket. No direct MCP protocol involvement. It is a REST
client with a terminal UI.

---

## Out of scope for this plan

The following are related but distinct features. They share infrastructure with the
TUI but are not part of it and should not be built in the same effort:

- **Daemon orchestration** (`db-mcp up` / `db-mcp down` / `db-mcp ps`) — process
  management, PID files, log tailing. A useful operational tool independent of the TUI.
- **`db-mcp ask`** — non-interactive ACP query submission from the shell. Shares
  `acp_client.py` with the TUI but is its own CLI command and UX.

Both are worth building. Neither blocks the TUI or belongs inside this plan.

---

## Phase 0 — Backend Event Contract (prerequisite, no TUI code)

**Do this before writing any Textual code.**

The TUI feed is only as reliable as the event API it polls. The current
`/api/executions` and `/api/gaps` endpoints were built for the web UI, not for a
polling feed client. Before building the TUI, produce a short contract document
(or annotate the existing handler code) that answers:

| Question | Why it matters |
|---|---|
| What is the stable dedup key per event? | Prevents duplicate feed entries across polls |
| What fields distinguish in-flight from terminal state? | Controls spinner lifecycle |
| Are timestamps server-assigned and monotonic? | Polling cursor correctness |
| What does a `confirm_required` event look like? | TUI must detect and track it |
| What does a gap event look like, including suggested rule text? | Gap commands depend on it |
| Is the `/api/executions?since=` cursor inclusive or exclusive? | Off-by-one in the poll loop |
| What connection-switch events (if any) appear in the stream? | Status bar updates |

Without clear answers, the Textual app will encode backend quirks in ad-hoc
conditionals that become hard to fix later.

**Deliverable:** a short written contract (inline doc or a `docs/api-event-contract.md`)
covering the fields above, validated against the actual handler code.

**Files to read before writing:**
- `packages/core/src/db_mcp/api/handlers/executions.py`
- `packages/core/src/db_mcp/api/handlers/gaps.py` (or equivalent)
- `packages/data/src/db_mcp_data/execution/store.py` — actual SQLite schema

---

## Phase 1 — HTTP Transport

### 1a. FastMCP HTTP server launch

Add a new launch mode to `packages/mcp-server/src/db_mcp_server/server.py`:

```python
def run_http(host: str = "127.0.0.1", port: int = 7421) -> None:
    """Launch MCP server in streamable-http mode."""
    mcp.run(transport="streamable-http", host=host, port=port)
```

Wire via a new CLI flag or sub-command. The simplest starting point is
`db-mcp start --http` rather than a full daemon system.

Config keys added to `~/.db-mcp/config.yaml`:
```yaml
daemon:
  mcp_port: 7421
  ui_port: 8080
```

**Files:**
- Modified: `packages/mcp-server/src/db_mcp_server/server.py`
- Modified: `packages/cli/src/db_mcp_cli/commands/server_cmd.py` — add `--http` flag
- Modified: `packages/core/src/db_mcp/config.py` — add daemon config keys

### 1b. Validation

Verify that an MCP client connects over streamable-http and all existing tools
work end-to-end. Test with a real query session before writing any TUI code.

This is the gate. If HTTP mode has rough edges, fix them here rather than
discovering them through the TUI.

---

## Phase 2 — Read-only TUI: Feed + Status Bar

Build only a read-only observer. No input widget. No commands. If the event feed
is wrong, this is where it surfaces — without the complexity of command handling
on top.

### Package location

```
packages/cli/src/db_mcp_cli/tui/
├── __init__.py
├── app.py          # DBMcpTUI(App) — root Textual application
├── widgets/
│   ├── feed.py     # EventFeed — scrolling RichLog
│   └── status.py   # StatusBar — bottom line
├── events.py       # FeedEvent model + rendering to Rich markup
└── client.py       # APIClient — REST polling, response parsing
```

Lives in `db_mcp_cli` because it is accessed via `db-mcp tui`. No new package needed.

Add `textual>=0.60` to `packages/cli/pyproject.toml` as an optional dependency:
```toml
[project.optional-dependencies]
tui = ["textual>=0.60"]
```

Install with `uv sync --extra tui`.

### Event model

```python
@dataclass
class FeedEvent:
    id: str                      # stable dedup key (from event contract)
    type: str                    # "query", "confirm_required", "gap", "rule_added", ...
    headline: str                # text for the ● line
    sub_lines: list[str]         # text for each ⎿ line
    pending_action: str | None   # "confirm" | "gap" | None
    timestamp: datetime
    done: bool                   # spinner stops when True
```

The field names here must be validated against the event contract from Phase 0
before this model is finalized.

### Rendering

`FeedEvent` renders to Rich markup:

```
[bold]●[/bold] query: monthly revenue by region
  [dim]⎿[/dim]  ✓ auto  |  38ms  |  1,240 rows
```

In-flight events show a spinner on the `⎿  running…` line. When the poll loop
receives the completion event, it replaces that line in the `RichLog` by index.

### APIClient

```python
class APIClient:
    base_url: str               # http://localhost:8080
    last_execution_ts: float    # polling cursor
    last_gap_ts: float

    async def fetch_events(self) -> list[FeedEvent]: ...
    async def fetch_status(self) -> StatusSnapshot: ...
    async def list_connections(self) -> list[str]: ...
    async def switch_connection(self, name: str) -> None: ...
```

Polling cursor: `GET /api/executions?since={last_execution_ts}` and
`GET /api/gaps?since={last_gap_ts}`. Poll interval: 1.5 seconds.

### app.py skeleton

```python
class DBMcpTUI(App):
    CSS = """
    EventFeed { height: 1fr; }
    StatusBar { height: 1; dock: bottom; }
    """

    def compose(self) -> ComposeResult:
        yield EventFeed()
        yield StatusBar()

    def on_mount(self) -> None:
        self.set_interval(1.5, self.poll)

    async def poll(self) -> None:
        events = await self.client.fetch_events()
        feed = self.query_one(EventFeed)
        for event in events:
            feed.add_event(event)
        status = await self.client.fetch_status()
        self.query_one(StatusBar).update(status)
```

**Files:**
- All new under `packages/cli/src/db_mcp_cli/tui/`
- Modified: `packages/cli/src/db_mcp_cli/main.py` — register `db-mcp tui` command

**Gate before Phase 3:** the feed renders correctly, dedup works across poll
boundaries, in-flight spinner transitions to done cleanly, status bar reflects
live state.

---

## Phase 3 — Command Input + Confirm Gate

Add command input only after the read-only feed is stable. This phase is scoped to
confirm/cancel only — the minimum useful interactive feature.

### New REST endpoint

```
POST /api/executions/{execution_id}/confirm
     body: {"action": "confirm" | "cancel"}
```

**Files:**
- New or modified: `packages/core/src/db_mcp/api/handlers/executions.py`
- Modified: `packages/core/src/db_mcp/api/__init__.py` — register route

### CommandInput widget

```python
class CommandInput(Input):
    placeholder = "> "

    async def on_submitted(self, event: Input.Submitted) -> None:
        await self.app.dispatch_command(event.value.strip())
        self.clear()
```

Docked above the status bar. Tab-completion for `/confirm`, `/cancel`, `/add-rule`,
`/dismiss`, `/use`, `/list`, `/status`, `/clear`, `/help`.

Plain text (no `/` prefix) is routed to the ACP insider agent path (Phase 4),
not `CommandDispatcher`.

### CommandDispatcher

```python
class CommandDispatcher:
    async def dispatch(self, raw: str, app: DBMcpTUI) -> None:
        if not raw.startswith("/") and raw not in ("q",):
            await app.acp.prompt(raw)   # Phase 4 — no-op until then
            return

        if raw in ("/confirm", "/cancel"):
            await self._handle_confirm(raw, app)
        elif raw.startswith("/add-rule "):
            await self._handle_add_rule(raw[10:], app)
        elif raw == "/dismiss":
            await self._handle_dismiss(app)
        elif raw.startswith("/use "):
            await self._handle_switch(raw[5:], app)
        elif raw == "/list":
            await self._handle_list(app)
        elif raw == "/status":
            await self._handle_status(app)
        elif raw == "/clear":
            app.query_one(EventFeed).clear()
        elif raw == "/help":
            app.query_one(EventFeed).add_help()
        elif raw in ("q", "/quit"):
            app.exit()
        else:
            app.query_one(EventFeed).add_error(f"unknown command: {raw}")
```

**Confirm gate:** TUI tracks `pending_confirm_id: str | None`. When a
`confirm_required` event arrives, `pending_confirm_id` is set. `/confirm` or
`/cancel` calls `APIClient.confirm_execution(pending_confirm_id, action)` and
clears it.

**Files:**
- New: `packages/cli/src/db_mcp_cli/tui/commands.py`
- New: `packages/cli/src/db_mcp_cli/tui/widgets/input.py`
- Modified: `packages/cli/src/db_mcp_cli/tui/app.py` — wire input + dispatcher
- Modified: `packages/cli/src/db_mcp_cli/tui/client.py` — add `confirm_execution`

---

## Phase 4 — Gap Commands + ACP Insider Agent

Two distinct additions bundled as a polish phase. Either can ship independently.

### Gap commands

TUI tracks `pending_gap: FeedEvent | None`. When a gap event arrives with a
suggested rule, it is stored. `/add-rule` without arguments uses the suggested
rule text. `/dismiss` calls `APIClient.dismiss_gap(pending_gap.id)`.

**Files:**
- Modified: `packages/cli/src/db_mcp_cli/tui/client.py` — add `add_rule`, `dismiss_gap`

### `/use` switcher

`APIClient.switch_connection(name)` calls `POST /api/connections/use`. On success,
feed appends `● → connection: <name>` and status bar updates.

### Reconnect handling

If `fetch_events()` raises a connection error, feed appends `● server disconnected`
and status bar shows `✗`. On next successful response: `● server reconnected`.

### ACP insider agent

ACP (Agent Client Protocol, Zed Industries) is agent-agnostic. Any ACP-compatible
agent (Claude Code, Gemini CLI, Goose, etc.) can serve as the reasoning layer.
The agent binary is configurable; db-mcp does not hardcode one.

```yaml
# ~/.db-mcp/config.yaml
daemon:
  agent_command: claude   # any ACP-compatible agent binary or adapter
```

**Architecture:**

```
User types plain text
         │
         ▼ session/prompt  (JSON-RPC over stdio — ACP)
  ACP-compatible agent  (configured subprocess)
         │
         ▼ MCP tool calls  (HTTP, port 7421)
  db-mcp MCP server
         │
         ▼ execution events → REST polling
  TUI feed  (unified with all other events)
```

**What needs to be specified before implementation:**

- **Permission flow**: agent may call `session/request_permission` for file/terminal
  ops. TUI must handle these — either auto-allow, auto-deny, or surface to user.
- **Adapter variance**: agents may not natively expose ACP over stdio and require an
  adapter binary (e.g. `@zed-industries/claude-agent-acp` for Claude Code). The
  `agent_command` config should point to the adapter, not the agent itself.
- **Session lifecycle**: persistent session across multiple prompts, or new session
  per prompt? Persistent is better UX; requires the agent to maintain conversation state.
- **Feed normalization**: `session/update` notifications from the agent must be
  mapped to `FeedEvent` objects and merged into the same feed as db-mcp execution
  events. The mapping (what agent update types → what feed event types) needs to be
  defined explicitly.

**Python SDK:** `agent-client-protocol` (PyPI).

```python
from agent_client_protocol import spawn_agent_process, Client, text_block

class TUIAgentClient(Client):
    async def session_update(self, session_id, update, **kwargs):
        feed.add_agent_line(update)          # normalize → FeedEvent
    async def request_permission(self, options, session_id, tool_call, **kwargs):
        return {"outcome": {"outcome": "allow"}}   # policy TBD

async with spawn_agent_process(TUIAgentClient(), agent_cmd) as (conn, _proc):
    await conn.initialize(protocol_version=1)
    session = await conn.new_session(
        cwd=".",
        mcp_servers=[{"url": "http://localhost:7421/mcp"}]
    )
    await conn.prompt(session_id=session.session_id,
                      prompt=[text_block(intent)])
```

**Files:**
- New: `packages/cli/src/db_mcp_cli/tui/acp_client.py` — ACP session manager
- Modified: `packages/cli/src/db_mcp_cli/tui/app.py` — wire ACP client
- Modified: `packages/core/src/db_mcp/config.py` — add `daemon.agent_command` key
- Modified: `packages/cli/pyproject.toml` — add `agent-client-protocol` to `tui` dep

### Polish items

- Spinner frames on in-flight `⎿` lines
- Color: `⚠` yellow, `✗` red, `✓` green, dim `⎿` prefix
- Feed scroll-lock: auto-scrolls unless user has scrolled up
- `Ctrl-C` / `q` exits cleanly

---

## Module Map (final state)

```
packages/
├── cli/src/db_mcp_cli/
│   └── tui/
│       ├── app.py                 # DBMcpTUI(App)               (new)
│       ├── events.py              # FeedEvent model             (new)
│       ├── client.py              # APIClient — REST polling     (new)
│       ├── acp_client.py          # ACP session manager         (new, Phase 4)
│       ├── commands.py            # CommandDispatcher           (new)
│       └── widgets/
│           ├── feed.py            # EventFeed                   (new)
│           ├── input.py           # CommandInput                (new)
│           └── status.py         # StatusBar                   (new)
├── mcp-server/src/db_mcp_server/
│   └── server.py                  # + run_http()               (modified)
└── core/src/db_mcp/
    ├── config.py                  # + daemon config keys        (modified)
    └── api/handlers/
        └── executions.py          # + confirm endpoint          (modified)
```

Note: `daemon_cmd.py` and `ask_cmd.py` are not listed here — they belong to the
daemon orchestration and `db-mcp ask` efforts respectively.

---

## Testing

**Phase 0:** No code — validate event API contract manually or with `curl`.

**Phase 1:** Connect an MCP client over HTTP, run a query end-to-end. All existing
tools must work before proceeding.

**Phase 2:** Textual `pilot` tests:
- `APIClient` response parsing → `FeedEvent` conversion
- Poll loop deduplication (same event not added twice across poll boundaries)
- `FeedEvent` → Rich markup rendering
- Spinner → done transition by index

**Phase 3:** Pilot tests:
- `/confirm` with pending → calls `confirm_execution`
- `/confirm` with no pending → error line
- `/cancel` → calls with `"cancel"`

**Phase 4:** Pilot tests for `/add-rule`, `/dismiss`, `/use`, reconnect handling.
ACP: integration test — spawn a real ACP agent subprocess, send a prompt, verify
execution event appears in feed.

---

## Dependencies Added

| Package | Version | Where | Why |
|---|---|---|---|
| `textual` | `>=0.60` | `cli[tui]` optional | TUI framework |
| `agent-client-protocol` | latest | `cli[tui]` optional | ACP client — agent-agnostic |

No other new dependencies. FastMCP already supports streamable-http. The REST API
the TUI polls already exists.
