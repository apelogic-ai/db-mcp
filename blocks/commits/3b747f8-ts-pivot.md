---
hash: 3b747f8
short: 3b747f8
date: 2026-04-04
author: Leonid Belyaev
blocks: [tui]
transition: T5
type: pivot
files_changed: 8
insertions: 660
pr: null
---

# feat: TS TUI scaffold with pi-tui — feed, editor, status bar

**THE PIVOT.** Complete rewrite from Python/Textual to TypeScript/pi-tui.
The Python TUI was 14 hours old.

## Decision: Python → TypeScript
- Faster iteration (bun hot reload vs Python restart)
- Better async model for ACP communication
- pi-tui markdown rendering cleaner than Textual's RichLog
- TypeScript strict typing caught integration bugs earlier
- The 29-minute Python build proved the design was sound;
  the rewrite moved it to a better stack for long-term maintenance

## Blocks affected
- [[blocks/tui#T5. Pivot to TypeScript (2026-04-04)|tui → T5: active (Python) → superseded; ○ → active (TypeScript)]]

## Key files created
- `packages/terminal/src/index.ts` — main TUI app
- `packages/terminal/src/feed.ts` — event feed
- `packages/terminal/src/status-bar.ts` — status display
- `packages/terminal/src/commands.ts` — slash command routing
- `packages/terminal/src/theme.ts` — chalk styling
- `packages/terminal/package.json` — new TS package
