---
hash: d2e68ea
short: d2e68ea
date: 2026-04-05
author: Leonid Belyaev
blocks: [tui]
transition: T6
type: cleanup
files_changed: 27
insertions: 588
deletions: 2210
pr: null
---

# feat: fix TUI tool details, permissions, and query execution

Misleading commit message — this is primarily a **cleanup commit** that
deletes the Python TUI and finalizes the TypeScript version.

## What was deleted
- `packages/cli/src/db_mcp_cli/tui/` — entire Python TUI (11 source files)
- `packages/cli/tests/test_tui_*.py` — 8 test files
- `textual` dependency from `pyproject.toml`
- **2,210 lines removed**

## What was added
- Enhanced TS terminal with 51 Vitest tests
- Fixed ACP permission handling (use "allow" not "allow_once")
- Improved agent system prompt

## Blocks affected
- [[tui#T6. All phases complete (2026-04-05 15:52)|tui → T6 (cleanup)]]

## Note
The 2,210 deleted lines are the Python TUI's entire codebase — a
complete implementation that lived for ~2 days before being superseded
by the TypeScript version.
