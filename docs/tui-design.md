# TUI Design: Terminal Sidekick

## Concept

The TUI is a companion screen for users working with **Claude Code** in a terminal
workflow, in the same way the web UI is a companion for users working with
**Claude Desktop**.

The user runs Claude Code in one pane. The TUI runs alongside — a live feed of
everything db-mcp is doing, styled to feel native to the same terminal environment.

**Not** a dashboard. **Not** panels. A feed that looks and feels like Claude Code's
own output, with a command line at the bottom.

---

## Layout

Matches Claude Code's visual language: `●` for events, `⎿` for sub-lines, spinner
while in-flight, result inline when done. No borders. No boxes.

```
● query: monthly revenue by region
  ⎿  validating…
  ⎿  ✓ auto  |  38ms  |  1,240 rows

● query: top customers last 30 days
  ⎿  running…
  ⎿  ✓ auto  |  112ms  |  500 rows

● ⚠ confirm required: total refunds this month
  ⎿  estimated 4.2M rows  |  cost tier: confirm
  ⎿  /confirm to execute · /cancel to skip

● gap: "fiscal_year"
  ⎿  suggested rule: always filter fiscal_year to the current year
  ⎿  /add-rule to save · /dismiss to ignore

● rule added: "active users exclude soft-deleted accounts"

> _
────────────────────────────────────────────────────────────────
● prod  │  42 examples  7 rules  2 gaps  │  ✓
```

---

## Elements

### Event feed

Scrolling stream, new events at the bottom. Each event is a `●` line with `⎿`
sub-lines for detail. Spinner on the `⎿` line while in-flight, replaced by result
when done — same pattern as Claude Code's tool call display.

| Event | Lines |
|---|---|
| Query (running) | `● query: <intent>` / `⎿ running…` |
| Query (done) | `⎿ ✓ auto \| 38ms \| 1,240 rows` |
| Query (failed) | `⎿ ✗ <error message>` |
| Confirm required | `● ⚠ confirm required: <intent>` / `⎿ estimated N rows` / `⎿ /confirm · /cancel` |
| Gap detected | `● gap: "<term>"` / `⎿ suggested rule: …` / `⎿ /add-rule · /dismiss` |
| Rule added | `● rule added: "<text>"` |
| Connection switch | `● → connection: <name>` |
| Server event | `● server connected` / `● server disconnected` |

### Suggestion lines

Not bubbles — just `⎿` lines beneath the relevant event, same as any other sub-line.
Appear when an action is available (confirm gate, gap with suggestion). Disappear from
new events once acted on; old events in the feed stay as-is.

### Command input

```
> _
```

Single line, always visible just above the status bar. Same `>` prompt as Claude
Code. Tab-completion for `/`-commands.

Two input modes:

**Plain text** — routed to the insider agent (see below). Submitting `top customers
last 30 days` is equivalent to asking Claude Code to run that query: it appears in
the feed as a `● query:` event, confirms if required, streams the result inline.

**`/`-prefixed commands** — operational control:

| Command | Effect | CLI equivalent |
|---|---|---|
| `/confirm` | approve the pending confirm-gate query | — |
| `/cancel` | cancel the pending confirm-gate query | — |
| `/add-rule <text>` | add a business rule to the vault | — |
| `/dismiss` | dismiss the most recent pending gap | — |
| `/use <name>` | switch active connection | `db-mcp use <name>` |
| `/list` | list available connections | `db-mcp list` |
| `/status` | show connection + vault stats | `db-mcp status` |
| `/clear` | clear the feed | — |
| `/help` | list commands | — |
| `q` / `Ctrl-C` | quit | — |

### Insider agent

When the user submits plain text, the TUI acts as a first-class query client — not
just a monitor — via **ACP (Agent Client Protocol, Zed Industries)**.

ACP is agent-agnostic. The TUI is an ACP client; any ACP-compatible agent (e.g.
Claude Code, Gemini CLI, Goose) can serve as the reasoning layer. The agent binary
is configurable in `~/.db-mcp/config.yaml` — db-mcp does not hardcode one.

1. User submits plain text → TUI sends `session/prompt` to the configured agent
2. Agent makes MCP tool calls to db-mcp (over HTTP, port 7421)
3. db-mcp execution events appear in the feed via the normal poll loop
4. Agent streams `session/update` notifications back — rendered as a `● agent:`
   event with `⎿` sub-lines for each tool call
5. If confirmation is required, a `confirm_required` event appears — user types
   `/confirm` to proceed exactly as for any other query

**No new agent harness is built.** The harness is the ACP agent, accessed via the
standard protocol. db-mcp provides the MCP tool surface.

`db-mcp ask "top customers last 30 days"` is the non-interactive version: open ACP
session → `session/prompt` → stream output to terminal → close.

### Status bar

One line at the very bottom:

```
● prod  │  42 examples  7 rules  2 gaps  │  ✓
```

Connection name, vault counts (live-updated as events arrive), server health dot.

---

## Prerequisite: HTTP Transport Mode

The TUI requires the MCP server to run as a persistent HTTP daemon rather than a
stdio subprocess owned by Claude Code.

**Why:** In stdio mode the server's stdin/stdout are consumed by the MCP protocol.
There is nothing for a second process to attach to.

FastMCP supports `transport="streamable-http"` natively — one line in the server
launch. Claude Code's MCP config switches from `command: db-mcp start` to
`url: http://localhost:7421/mcp`.

**New CLI commands:**

```
db-mcp up     # start MCP server (HTTP) + UI server as persistent daemons
db-mcp down   # stop all daemons
db-mcp tui    # attach TUI to running server
```

`db-mcp start` keeps working as before (stdio, for Claude Desktop compatibility).

---

## Framework

**Textual** (Python). Rich is already a dependency. The feed + input pattern maps
directly to Textual primitives: `RichLog` for the scrolling feed, `Input` for the
command line, a static `Label` for the status bar.

Entry point: `db-mcp tui`, or evolve `db-mcp console`.

---

## Data Sources

**REST API polling** — poll `GET /api/executions?since=<timestamp>` every 1–2 seconds
for new events. Gap events from `GET /api/gaps?since=`. The existing FastAPI server
already exposes both.

**One new endpoint** — `POST /api/executions/{id}/confirm` for the confirm gate.

**Direct SQLite read** (optional) — if polling latency is too high, read
`{connection_path}/state/executions.sqlite` directly. SQLite supports concurrent
readers. No new IPC required either way.

---

## Implementation Phases

### Phase 1 — HTTP transport

- Add `transport="streamable-http"` to MCP server launch
- Add `db-mcp up` / `db-mcp down`
- Validate Claude Code works over HTTP before any TUI work

### Phase 2 — Feed + status bar

- `db-mcp tui` command, Textual dependency
- Scrolling event feed (poll REST API, render with `●` / `⎿` style)
- Status bar
- Read-only, no input yet

### Phase 3 — Command line + confirm gate

- Command input line
- `/confirm` / `/cancel` + `POST /api/executions/{id}/confirm` endpoint
- Confirm-required events show action `⎿` lines

### Phase 4 — Gap commands + insider agent

- Gap events show suggestion + `/add-rule` / `/dismiss` lines
- `/use`, `/list`, `/status`, `/clear`, `/help`
- Plain-text input → ACP session to Claude Code (`acp_client.py`)
- `db-mcp ask` CLI wrapper

---

## Open Questions

1. **Port:** What port does the HTTP MCP server use? Configurable in
   `~/.db-mcp/config.yaml`. (7421 is a placeholder.)

2. **Auth:** Localhost-only — sufficient for the MCP HTTP endpoint, or does it need
   a shared secret between server and TUI client?

3. **Claude Desktop + HTTP:** Claude Desktop supports MCP over HTTP. Users pointing
   both Claude Desktop and Claude Code at the same db-mcp instance should work —
   worth verifying FastMCP's streamable-http is compatible with Claude Desktop's
   MCP client.

4. **Event granularity:** Start conservative — completions, confirm-gates, and gaps
   only. Expand to validation steps and rule additions once the feed feels right.
