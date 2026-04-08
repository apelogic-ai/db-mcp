---
id: tui
type: component
title: Terminal UI
status: active
created: 2026-04-03
---

# Terminal UI

Real-time event feed and command interface for db-mcp. Runs alongside
Claude Code (or any ACP agent) as a live companion showing query
executions, knowledge gaps, and system status. Plain-text input routes
to an ACP agent for natural language queries.

## Current state

TypeScript app using `@mariozechner/pi-tui` + `chalk`. Launched as a
subprocess by `db-mcp tui`, which auto-starts the daemon if needed.
Polls the REST API for events; spawns an ACP agent subprocess for
natural language input.

## Artifacts

### Active
- Code: [[packages/terminal/src/index.ts]] (main app, 23.7KB)
- ACP agent: [[packages/terminal/src/acp/agent.ts]]
- CLI command: [[packages/cli/src/db_mcp_cli/commands/services.py#tui_cmd]]
- Tests: 51 Vitest tests across 4 files
- Vendored ACP bridge: [[packages/terminal/src/vendor/acp-bridge/]]

### Stale (describe reality inaccurately)
- Design doc: [[docs/tui-design.md]] — references Python/Textual, not TypeScript
- Implementation plan: [[docs/tui-implementation.md]] — references Python paths,
  Textual widgets, `packages/cli/src/db_mcp_cli/tui/` (deleted)

### Deleted
- Python TUI: `packages/cli/src/db_mcp_cli/tui/` — 11 source files, 8 test files
  removed in commit d2e68ea (2026-04-05)

## Depends on

- [[blocks/daemon]] — unified HTTP server (MCP + REST + UI on port 8080)
- [[blocks/acp-integration]] — agent subprocess for NL queries
- [[blocks/rest-api]] — `/api/executions`, `/api/gaps`, `/api/connections/use`

## Commands

| Command | What it does |
|---|---|
| `/help` | List available commands |
| `/status` | Connection + agent status |
| `/connections` | List available connections |
| `/use <name>` | Switch active connection |
| `/schema` | Show table descriptions |
| `/rules` | List business rules |
| `/metrics` | List metric definitions |
| `/gaps` | Show knowledge gaps |
| `/agent` | Agent connection status |
| `/doctor` | Preflight health checks |
| `/playground` | Install sample database |
| `/init` | First-time connection setup |
| `/clear` | Clear feed |
| `/quit` | Exit |

## Key decisions

### Single-port daemon (2026-04-03)
Originally planned two ports (MCP :7421, UI :8080). Built as single port
with FastMCP ASGI mounted at `/mcp`. Simpler — one process, one URL.

### Python → TypeScript pivot (2026-04-04)
Python/Textual TUI was built in 29 minutes (Phases 2-4, 2026-04-03
20:31→21:00). Pivoted to TypeScript the next day. Reasons: faster
iteration, better async model, pi-tui cleaner than Textual's RichLog,
TypeScript strict typing caught bugs earlier.

### Pure polling client (2026-04-03)
TUI polls REST API every 1.5s. No WebSocket, no server push. Simpler,
stateless. If latency becomes an issue, SSE or WebSocket is a future
option.

### ACP as subprocess, not embedded (2026-04-04)
Agent is a child process communicating over stdio (ACP protocol).
Agent connects to `/mcp` endpoint independently. TUI doesn't proxy
agent traffic — it just renders what happens.

## History

- **2026-04-03** ○ → idea
  By: Leonid + Claude. Evidence: [[docs/tui-design.md]] created.
  Concept: Textual (Python) terminal companion for Claude Code.
  Event feed with `●`/`⎿` styling, command input, ACP insider agent.

- **2026-04-03** idea → planned
  By: Leonid + Claude. Evidence: [[docs/tui-implementation.md]] created.
  4-phase plan: Phase 0 event contract, Phase 1 HTTP transport,
  Phase 2 read-only feed, Phase 3 commands, Phase 4 ACP + gaps.

- **2026-04-03** planned → active (Python, short-lived)
  By: Leonid + Claude. Evidence: commits c7aeea5→d5c71bf (29 minutes).
  All 4 phases built in Python/Textual in one evening.
  11 source files, 8 test files, 33 tests.

- **2026-04-03** active → active (styling iteration)
  By: Leonid + Claude. Evidence: 9 commits (21:40→21:56).
  CommandInput widget styling: borders, padding, visibility.

- **2026-04-04** active (Python) → superseded (Python), ○ → active (TypeScript)
  By: Leonid. Evidence: commit 3b747f8.
  **PIVOT:** Complete rewrite in TypeScript using pi-tui.
  Reason: faster iteration, better async, stricter types.
  The Python TUI was 14 hours old when it was replaced.

- **2026-04-05** active → active (TypeScript, all phases complete)
  By: Leonid + Claude. Evidence: PR #83, commit 90c331d.
  All 4 phases re-implemented in TypeScript.
  Python TUI deleted: commit d2e68ea (11 source files, 8 test files removed).

- **2026-04-04 → 2026-04-06** active (rapid evolution)
  75 commits to packages/terminal/. Key additions:
  - ACP agent lifecycle management
  - Codex-ACP support + runtime detection
  - Terminal reset (Kitty protocol handling)
  - Binary packaging for PyInstaller

- **2026-04-06** active (onboarding features)
  By: Leonid + Claude. Evidence: PR #84, commit 56da082.
  Added: `/doctor` preflight checks, `/playground` sample DB,
  `/init` first-time setup wizard, first-run detection.

- **2026-04-08** active (docs stale)
  Detected: tui-design.md and tui-implementation.md still reference
  Python/Textual. Code is TypeScript. Design docs need update or
  archival marker.

## Evolution chain

```
docs/tui-design.md (2026-04-03, idea)
  → Python/Textual TUI (2026-04-03, 29 min lifespan)
    → TypeScript/pi-tui TUI (2026-04-04, current)
      → + onboarding features (2026-04-06)
```
