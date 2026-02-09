# UI Enhancement Spec — db-mcp Electron App

**Author:** Auto-generated · 2026-02-09
**Audience:** Boris (frontend)
**Baseline:** Existing pages — Connectors, Context, Traces, Insights

---

## 1. Proactive Insights Notification

**Priority:** P0 · **Complexity:** S

### What
Surface pending insights (failed-query patterns, unmapped terms, etc.) as notifications so the user doesn't have to check the Insights page manually.

### Where
- **Insights tab label** — badge/counter when pending > 0
- **Insights page** — new "Pending Insights" section pinned above existing dashboard
- **Global** (optional) — toast notification on new insight arrival

### Backend
- MCP resource: `db-mcp://insights/pending`
- Returns: `Array<{ id, category, severity, message, details, timestamp }>`
- Source of truth: `<connection_dir>/.insights.json`
- Poll interval suggestion: 30s, or subscribe via MCP resource change notification if available

### UI Details
- **Tab badge:** red dot + count (e.g. `Insights (3)`). Disappears when all dismissed.
- **Pending section:** card list at top of Insights page
  - Each card: severity pill (`info` / `warning` / `critical`), category tag, message text, relative timestamp
  - "Dismiss" button per card → removes from `.insights.json` (call `dismiss_insight` tool or DELETE on resource)
  - "View Details" expands inline to show `details` field
- **Toast** (opt-in via settings): appears bottom-right, auto-dismiss after 8s, click navigates to Insights page
- Future: "Analyze" button → opens agent panel (ACP); stub the button now, wire later

---

## 2. Collaboration Diff View

**Priority:** P1 · **Complexity:** L

### What
Let the master user review incoming collaborator contributions before merge — a lightweight PR review inside the app.

### Where
- **Context page** — new "Changes" tab/panel next to the file tree (only visible when `.collab.yaml` exists in the vault root)

### Backend
- Git branches: `collaborator/{username}` per contributor
- `.collab.yaml` — manifest with participants, roles, enabled flag
- Classification system labels each changed file:
  - `additive` — new examples/learnings, auto-merged
  - `shared` — schema edits, rules, domain model; needs master review
- Need a backend endpoint or MCP tool that returns:
  ```
  Array<{
    collaborator: string,
    branch: string,
    files: Array<{ path, status (added|modified|deleted), classification, diff: string }>
  }>
  ```
- Review actions: `approve_change(collaborator, file?)`, `reject_change(collaborator, file?)`

### UI Details
- **Changes panel** (VS Code SCM-inspired):
  - Header: sync status indicator (✓ synced / ↻ syncing / ⚠ conflict) + last sync timestamp
  - Grouped by collaborator (avatar/icon + username)
  - Per file: path, status icon (A/M/D), classification badge (`additive` green, `shared` orange)
  - Click file → inline diff view (green additions, red deletions, mono font)
  - `additive` files: info-only ("auto-merged"), no action needed
  - `shared` files: **Approve** / **Reject** buttons per file, or bulk per collaborator
- **Badge on Changes tab** showing count of pending reviews
- Hide entire tab when `.collab.yaml` doesn't exist

---

## 3. Multi-Connection Schema Browser

**Priority:** P1 · **Complexity:** M

### What
Browse and compare knowledge vaults across all configured connections from one place.

### Where
- **Context page** — enhanced connection selector dropdown
- **Connectors page** — new "Overview" sub-view

### Backend
- `db-mcp://connections` → `Array<{ name, type, dialect, description }>`
- `db-mcp://schema/{connection}` → schema tree for any connection
- `list_connections` tool → same data
- Vault health stats: derive from file counts in each connection's vault directory (table count, example count, % of tables with descriptions)

### UI Details
- **Connection dropdown (Context page):**
  - Show ALL connections, not just active
  - Each item: name, type icon (Postgres 🐘, Trino △, MySQL 🐬, etc.), dialect label
  - Selecting a connection switches the file tree to that connection's vault
  - Current connection highlighted; others show mini-stats (e.g. "12 tables, 5 examples")
- **Connections Overview (Connectors page):**
  - Grid or list view, one card per connection
  - Card contents: name, db type icon, dialect, table count, example count, last activity timestamp, vault health bar (% of schema described)
  - Click card → navigates to Context page with that connection selected
- **Quick-switch:** anywhere a connection name appears (Traces, Insights), make it a link that jumps to Context for that connection

---

## Implementation Notes

| Feature | Priority | Complexity | Dependencies |
|---|---|---|---|
| Proactive Insights | P0 | S | `db-mcp://insights/pending` resource |
| Collaboration Diff | P1 | L | Git integration, classify system, `.collab.yaml` |
| Multi-Connection Browser | P1 | M | `db-mcp://connections` resource, multi-vault support |

**Suggested order:** Insights notifications → Multi-connection browser → Collab diff view
