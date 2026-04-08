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

### Stale
- [[docs/tui-design.md]] — references Python/Textual, not TypeScript
- [[docs/tui-implementation.md]] — references deleted Python paths

### Deleted
- `packages/cli/src/db_mcp_cli/tui/` — 11 source + 8 test files (d2e68ea)

## Depends on

- [[blocks/daemon]] — unified HTTP server (MCP + REST + UI on :8080)
- [[blocks/acp-integration]] — agent subprocess for NL queries
- [[blocks/rest-api]] — event polling, confirm gate, connection switching

## Timeline

```
2026-04-03                              04-04         04-05              04-06         04-08
    │                                     │             │                  │             │
    ▼                                     ▼             ▼                  ▼             ▼
    ○ ─── idea ─── planned ─── active ────┐             │                  │             │
    │     │        │           (Python)   │             │                  │             │
    │  design   impl plan    29 min       │             │                  │             │
    │  doc      4 phases     build        │             │                  │             │
    │                                     │             │                  │             │
    │              DECISION: pivot to TS ─┘             │                  │             │
    │              "faster iteration,                   │                  │             │
    │               better async,                      │                  │             │
    │               stricter types"                    │                  │             │
    │                                     │             │                  │             │
    │                          ○ ─── active ─────────────────────────────────── active ──►
    │                               (TypeScript)       │                  │
    │                                     │          all phases        onboarding
    │                                     │          complete +        /doctor
    │                                     │          Python deleted    /playground
    │                                     │          PR #83            /init
    │                                     │                           PR #84
    │                                     │
    │              DECISION: single port ─┘
    │              "one process, one URL
    │               instead of MCP:7421 + UI:8080"
    │
    │              DECISION: polling, not WebSocket
    │              "simpler, stateless client"
    │
    │              DECISION: ACP as subprocess
    │              "agent connects to /mcp independently,
    │               TUI just renders what happens"
```

## Transitions

Each entry is a state change. Decisions are the WHY behind transitions.
Commit links point to detailed notes in [[blocks/commits/]].

### T1. Concept (2026-04-03 15:19)
```
○ → idea
```
- **By:** Leonid + Claude
- **Commit:** [[blocks/commits/b804d5f-design-docs]]
- **What:** Terminal companion for Claude Code. Event feed with `●`/`⎿`
  styling, command input, ACP insider agent.
- **Decision:** use Textual (Python) framework. Rationale: Rich already
  a dependency, feed maps to RichLog widget.

### T2. Plan (2026-04-03 ~16:00)
```
idea → planned
```
- **By:** Leonid + Claude
- **Commit:** [[blocks/commits/0a1ee8a-unified-daemon]]
- **What:** 4-phase plan. Phase 0: event contract. Phase 1: HTTP transport.
  Phase 2: read-only feed. Phase 3: commands + confirm. Phase 4: ACP + gaps.
- **Decision:** single-port daemon — mount MCP at `/mcp` on the same port
  as REST API, instead of separate ports. Rationale: one process, one URL.
- **Decision:** pure polling (1.5s interval) over REST API, no WebSocket.
  Rationale: simpler, stateless. Can upgrade later if latency matters.

### T3. First implementation (2026-04-03 20:31 → 21:00)
```
planned → active (Python)
```
- **By:** Leonid + Claude
- **Commits:** [[blocks/commits/c7aeea5-python-phase2|Phase 2]] →
  [[blocks/commits/493e6dc-python-phase3|Phase 3]] →
  [[blocks/commits/7d46670-python-phase4a|Phase 4a]] →
  [[blocks/commits/d5c71bf-python-phase4b|Phase 4b]] (29 minutes)
- **What:** All 4 phases built in Python/Textual. 11 source files,
  8 test files, 33 tests. Feed, commands, confirm gate, gap handling,
  ACP integration — everything in one evening session.
- **Decision:** ACP agent as subprocess, not embedded. Agent connects
  to `/mcp` independently; TUI doesn't proxy. Rationale: clean separation,
  simpler lifecycle.

### T4. Styling polish (2026-04-03 21:40 → 21:56)
```
active → active (polish)
```
- **By:** Leonid + Claude
- **Commits:** 9 commits in 16 minutes (c9dbebc + 8 others)
- **What:** CommandInput widget refinement — borders, padding, height,
  visibility, invisible border tricks.

### T5. Pivot to TypeScript (2026-04-04 12:56)
```
active (Python) → superseded
○ → active (TypeScript)
```
- **By:** Leonid
- **Commit:** [[blocks/commits/3b747f8-ts-pivot]]
- **What:** Complete rewrite in TypeScript using `@mariozechner/pi-tui`.
  The Python TUI was 14 hours old.
- **Decision: PIVOT.** Python/Textual → TypeScript/pi-tui.
  - Faster iteration cycle (bun hot reload vs Python restart)
  - Better async model for ACP communication
  - pi-tui's markdown rendering cleaner than Textual's RichLog
  - TypeScript strict typing caught integration bugs earlier
  - The 29-minute Python build proved the design; the rewrite proved
    a better stack for maintaining it.

### T6. All phases complete (2026-04-05 15:52)
```
active → active (feature-complete)
```
- **By:** Leonid + Claude
- **Commits:** [[blocks/commits/90c331d-ts-complete|PR #83]] +
  [[blocks/commits/d2e68ea-python-deleted|Python deletion]]
- **What:** All 4 phases re-implemented in TypeScript. 51 Vitest tests.
  Python TUI deleted: 11 source files, 8 test files, 2,210 lines removed.

### T7. Rapid evolution (2026-04-04 → 2026-04-06)
```
active → active (hardening)
```
- **Commits:** 75 commits to packages/terminal/ (see Dataview query below)
- **What:**
  - ACP agent lifecycle management
  - Codex-ACP support + runtime-aware preflight checks
  - Terminal reset on exit (Kitty protocol handling)
  - Binary packaging for PyInstaller distribution
  - Second-tier slash command autocomplete

### T8. Onboarding (2026-04-06 15:28)
```
active → active (expanded scope)
```
- **By:** Leonid + Claude
- **Commit:** [[blocks/commits/56da082-onboarding|PR #84]]
- **What:** TUI becomes the primary onboarding surface:
  - `/doctor` — preflight health checks
  - `/playground` — install sample database
  - `/init` — first-time connection setup wizard
  - First-run detection triggers onboarding flow

### T9. Docs drift detected (2026-04-08)
```
active → active (stale docs)
```
- **Detected by:** manual review
- **What:** tui-design.md and tui-implementation.md still describe
  Python/Textual. Code is TypeScript. Docs need update or archival
  marker. This is a staleness signal — the block is active but its
  design artifacts have drifted.

## Commit log

All commits related to this block, queryable with Obsidian Dataview:

```dataview
TABLE date, author, type, transition, insertions, deletions
FROM "blocks/commits"
WHERE contains(blocks, "tui")
SORT date ASC
```

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
