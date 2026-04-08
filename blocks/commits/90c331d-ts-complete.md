---
hash: 90c331d
short: 90c331d
date: 2026-04-05
author: Leonid Belyaev
blocks: [tui, daemon, acp-integration]
transition: T6
type: milestone
files_changed: 42
insertions: 4444
deletions: 152
pr: 83
---

# feat: TypeScript TUI with ACP agent integration (#83)

All 4 phases complete in TypeScript. Squash merge of the TS TUI branch.

## Blocks affected
- [[tui#T6. All phases complete (2026-04-05 15:52)|tui → T6: active → feature-complete]]

## What shipped
- Phase 1: unified daemon (MCP + REST on single port)
- Phase 2: event feed + status bar (TS)
- Phase 3: commands + confirm gate (TS)
- Phase 4a: gap commands + connection switcher (TS)
- Phase 4b: ACP agent + plain-text routing (TS)
- 51 Vitest tests

## Note
4444 insertions — this is the squash merge containing ~30 individual
commits from the TS TUI development branch.
