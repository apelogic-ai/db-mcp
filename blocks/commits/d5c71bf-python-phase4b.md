---
hash: d5c71bf
short: d5c71bf
date: 2026-04-03
author: Leonid Belyaev
blocks: [tui, acp-integration]
transition: T3
type: implementation
files_changed: 5
insertions: 171
pr: null
---

# feat: TUI Phase 4b — ACP insider agent integration

Plain-text input routes to ACP agent subprocess. Final phase of the
29-minute Python build.

## Decision
Agent as subprocess, not embedded. Agent connects to `/mcp` endpoint
independently. TUI doesn't proxy — it renders what happens.

## Blocks affected
- [[tui#T3. First implementation (2026-04-03 20:31 → 21:00)|tui → T3 (final)]]

## Key files created
- `packages/cli/src/db_mcp_cli/tui/acp_client.py` — ACP session manager

## Note
Python TUI is now feature-complete. 11 source files, 33 tests.
It will be superseded 14 hours later in [[commits/3b747f8-ts-pivot|the TypeScript pivot]].
