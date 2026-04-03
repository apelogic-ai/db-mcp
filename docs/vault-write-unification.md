# Schema Registry Plan

## Goal

Centralize validation and side-effect logic for knowledge vault writes into a shared
schema registry. The named MCP tools stay as the public API surface — this is an
internal refactor, not an API reduction.

## Problem

The MCP tools for managing the knowledge vault each contain their own validation and
side-effect logic scattered across 8 implementations:

| Tool | Operation |
|---|---|
| `query_approve` | Save approved example + append to feedback log |
| `query_feedback` | Record feedback + optionally save corrected SQL as example |
| `query_add_rule` | Append rule to business_rules.yaml |
| `metrics_add` / `metrics_approve` | Write metric or dimension to catalog |
| `metrics_remove` | Delete metric or dimension from catalog |
| `metrics_bindings_set` | Validate then write metric binding |
| `dismiss_knowledge_gap` | Dismiss gap(s) by ID, including group dismissal |

The validation rules (deduplication, cross-catalog checks, required fields) and
side effects (dual-writes, group resolution) are re-implemented per tool rather than
being owned by a single authoritative layer.

## What Is Not the Problem

These are **domain actions with business meaning**, not simple file writes:

- `query_approve` doing a dual-write (example + feedback log) is the point — that
  is the domain action, not an implementation detail
- `dismiss_knowledge_gap` operating on a group is collection mutation, not a
  path/content write
- `query_feedback` auto-saving corrected SQL as an example is a business rule

Replacing named tools with a generic `vault_write(schema=...)` surface would shift
too much burden onto prompt/protocol knowledge, make the system less self-describing,
and give agents a weaker, easier-to-misuse contract. **Collapse the implementation,
not the public API.**

## Proposed Solution

### 1. Schema registry

Create `db_mcp_knowledge/vault/schema_registry.py`:

```python
@dataclass
class SchemaEntry:
    model: type[BaseModel]          # Pydantic model for validation
    pre_hooks: list[Callable]       # run before write, can raise to abort
    post_hooks: list[Callable]      # run after write, for side effects
    path_template: str | None       # optional: enforce canonical path
```

Initial schema keys:

| Schema key | Pydantic model | Pre-hook | Post-hook |
|---|---|---|---|
| `approved_example` | `QueryExample` | — | append `FeedbackType.APPROVED` to feedback log |
| `corrected_feedback` | `FeedbackEntry` | — | save corrected SQL as new example |
| `business_rule` | `BusinessRule` | deduplicate check | — |
| `metric` | `Metric` | — | — |
| `dimension` | `Dimension` | — | — |
| `metric_binding` | `MetricBinding` | validate metric + dimensions exist in catalog | — |
| `gap_dismissal` | `GapDismissal` | resolve group members | write all group gap IDs as dismissed |

### 2. Internal write service

Add an internal `vault_write_typed(schema_key, content, provider_id, connection_path)`
function in `db_mcp_knowledge.vault`:

1. Look up schema key in registry
2. Validate `content` against the registered Pydantic model — raise before touching disk
3. Run pre-write hooks (can abort)
4. Write atomically
5. Run post-write hooks (side effects)

This is **not** a new MCP tool. It is the shared implementation layer the existing
named tools delegate to.

### 3. Read tools

`query_list_examples`, `query_list_rules`, and `metrics_list` are read-only. They
should stay as named tools — `shell` is not an adequate typed replacement for agents
that need structured, joinable responses. `metrics_list` in particular performs a
three-file join (`metrics/catalog.yaml` + `dimensions/catalog.yaml` +
`metrics/bindings.yaml`) with a computed `has_binding` field that cannot be replicated
cleanly via `shell`.

## What Does Not Change

- All 8 write tools and 3 read tools stay registered as named MCP tools
- `metrics_discover` — LLM-powered mining, unaffected
- `get_knowledge_gaps` — read with auto-resolve side effect, unaffected
- `metrics_bindings_validate` — standalone dry-run validation, unaffected
- `shell`, `protocol`, `vault_write`, `vault_append` — stay as primitives

## Implementation Steps

### Phase 1 — Schema registry (no breaking changes)

1. Create `db_mcp_knowledge/vault/schema_registry.py` with `SchemaEntry` and
   `register` / `lookup` API
2. Define the 7 initial schema entries (models + hooks)
3. Implement `vault_write_typed()` backed by the registry
4. Write tests: valid content passes, invalid content raises before disk write,
   post-hooks fire, pre-hooks can abort

### Phase 2 — Migrate tool internals one at a time

Refactor each tool to delegate its validation and side-effect logic to
`vault_write_typed`. The tool's public signature, name, and MCP registration are
unchanged. Do one tool at a time with parity tests before and after:

1. `query_add_rule` — delegate dedup check + write to `schema="business_rule"`
2. `metrics_add` / `metrics_approve` — delegate to `schema="metric"` or `"dimension"`
3. `metrics_bindings_set` — delegate cross-catalog validation to `schema="metric_binding"`
4. `query_approve` — delegate dual-write logic to `schema="approved_example"`
5. `query_feedback` — delegate corrected-example side effect to `schema="corrected_feedback"`
6. `metrics_remove` — delegate to registry with delete semantics
7. `dismiss_knowledge_gap` — delegate group resolution to `schema="gap_dismissal"`

### Phase 3 — Ongoing

New knowledge vault write operations start in the registry, not in the tool handler.
Tool handler becomes a thin MCP adapter: resolve connection, call `vault_write_typed`,
return structured response.

## Net Result

| Before | After |
|---|---|
| Validation scattered across 8 tool handlers | Single schema registry |
| Side effects implicit per tool | Explicit hooks registered against schema keys |
| 8 tool handlers each own business logic | Handlers are thin adapters over registry |
| Named tools on public MCP surface | Named tools on public MCP surface (unchanged) |
