---
hash: 0a1ee8a
short: 0a1ee8a
date: 2026-04-03
author: Leonid Belyaev
blocks: [tui, daemon]
transition: T2
type: backend
files_changed: 11
insertions: 405
deletions: 141
pr: null
---

# feat: unified single-port daemon + MCP server factory extraction

Backend prerequisite for TUI. Single port serves MCP + REST + UI.

## Decision
Mount MCP at `/mcp` on the same port as REST API (8080) instead of
separate ports (MCP :7421, UI :8080). One process, one URL.

## Blocks affected
- [[blocks/tui#T2. Plan (2026-04-03 ~16:00)|tui → T2: idea → planned]]
- [[blocks/daemon]] (created)

## Key files
- `packages/mcp-server/src/db_mcp_server/server.py` — `create_mcp_server()` factory
- `packages/core/src/db_mcp/ui_server.py` — unified ASGI mount
- `packages/cli/src/db_mcp_cli/commands/services.py` — `db-mcp up` + `db-mcp tui`
