---
hash: 56da082
short: 56da082
date: 2026-04-06
author: Leonid Belyaev
blocks: [tui]
transition: T8
type: feature
files_changed: 35
insertions: 2387
deletions: 1399
pr: 84
---

# feat: TUI onboarding — /doctor, /playground, /init, first-run detection (#84)

TUI becomes the primary onboarding surface for new users.

## Blocks affected
- [[tui#T8. Onboarding (2026-04-06 15:28)|tui → T8: active → expanded scope]]

## What shipped
- `/doctor` — preflight health checks (agent binary, daemon, connections)
- `/playground` — install Chinook sample database
- `/init` — first-time connection setup wizard
- First-run detection: if no connections exist, auto-trigger onboarding flow
- Externalized prompts as markdown files under `packages/terminal/src/prompts/`
