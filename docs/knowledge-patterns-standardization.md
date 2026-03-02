# db-mcp Internal Knowledge Layer: Current Design vs Standardized Patterns

## Objective

Evaluate whether db-mcp should standardize its internal knowledge layer around
`AGENTS.md`, `SKILL.md`, and `MEMORY.md`, and compare that with the current
vault-first approach implemented in code.

## Current db-mcp Knowledge System (As Implemented)

db-mcp already has a structured, persistent, per-connection knowledge system
under `~/.db-mcp/connections/{name}/` (or an equivalent configured path).

### Canonical knowledge artifacts

| Artifact | Role | Primary producers | Primary consumers |
|---|---|---|---|
| `PROTOCOL.md` | Operating protocol for query work | `vault/init.py` (system-managed, overwritten) | Agent instructions, `shell`, MCP resources |
| `schema/descriptions.yaml` | Semantic schema cache (tables/columns/descriptions/status) | Onboarding discovery + approvals | SQL generation context, UI context viewer |
| `domain/model.md` | Human-readable domain model | Domain generation/approval tools | Agent query planning and joins reasoning |
| `instructions/sql_rules.md` | Dialect/hierarchy/query guardrails | Vault templates + manual curation | Agent behavior before SQL generation |
| `instructions/business_rules.yaml` | Business term mappings and constraints | `query_add_rule`, imports | SQL generation and gap resolution |
| `examples/*.yaml` | NL->SQL exemplars | Query approval/corrections, manual append | Few-shot context and reuse |
| `feedback_log.yaml` | Feedback history on generated SQL | Query feedback tools | Rule distillation and analysis |
| `knowledge_gaps.yaml` | Open/resolved vocabulary gaps | Schema scan + trace merge + manual dismissal | Insights and gap-review workflows |
| `metrics/catalog.yaml`, `metrics/dimensions.yaml` | Approved semantic metrics and dimensions | Metrics tools + approvals | KPI query guidance and UI |
| `learnings/*.md`, `learnings/failures/*.yaml` | Unstructured and failure learnings | Protocol-guided append, migrations | Humans and agent via shell search |
| `state.yaml` | Onboarding workflow state/progress | Onboarding tools | Onboarding UX, connection discovery |
| `.insights.json` | Pending insight queue from trace analysis | Insight detector | `db-mcp://insights/pending`, review prompt |

### Lifecycle and flow

1. Onboarding builds schema and state (`state.yaml`, `schema/descriptions.yaml`).
2. Domain and rules are curated (`domain/model.md`, `instructions/*`).
3. Query execution captures examples and feedback (`examples/*.yaml`, `feedback_log.yaml`).
4. Trace/insight pipeline detects patterns and gaps (`.insights.json`, `knowledge_gaps.yaml`).
5. Metrics mining/approval promotes reusable KPI definitions (`metrics/*`).
6. Collaboration sync classifies changes as additive vs shared-state for merge policy.

### Strengths of current design

- Strong domain fit: artifacts are database-centric, not generic agent docs.
- High observability: knowledge usage/capture is instrumented in query flows.
- Practical governance: additive vs shared-state file classification supports team workflows.
- Git-friendly persistence: mostly YAML/Markdown, easy diff/review.
- Backward-compatibility strategy: migrations are built in and explicit.

### Weaknesses and drift in current design

- Documentation drift across files:
  - Some docs still describe `training/examples.yaml` patterns while runtime uses `examples/*.yaml`.
- Path-model inconsistency:
  - Some modules resolve paths via settings/connection path, others hardcode `~/.db-mcp/connections/{provider_id}`.
- Partial backward-compatibility seams:
  - Some analytics logic still checks old `training/...` locations.
- Protocol mutability constraints:
  - `PROTOCOL.md` is overwritten by system initialization, so manual edits are fragile.
- “Memory” is fragmented:
  - Session/working memory is split across `state.yaml`, `.insights.json`, trace events, and in-memory stores.

## What Standardized Patterns Add

### Pattern intent

- `AGENTS.md`: stable operating contract and instruction precedence.
- `SKILL.md`: reusable workflow modules for specific tasks.
- `MEMORY.md`: compact, rolling, short-horizon context.

### Mapping to current db-mcp model

| Standard pattern | Closest current equivalent | Gap |
|---|---|---|
| `AGENTS.md` | `PROTOCOL.md` + server instructions + `instructions/sql_rules.md` | Current contract is mixed between generated markdown, runtime instructions, and tool descriptions; no single precedence model per connection |
| `SKILL.md` | `examples/*.yaml`, `learnings/*.md`, onboarding/generation procedures in protocol text | Existing knowledge is mostly data/examples, not task-modular executable playbooks with explicit I/O expectations |
| `MEMORY.md` | `state.yaml` + `.insights.json` + query lifecycle store | No single concise “working memory” artifact optimized for next-turn reasoning |

## Comparison: Current vs Standardized

| Dimension | Current vault-first design | Standardized patterns |
|---|---|---|
| Domain specificity | Very high (schema/rules/examples first-class) | Medium unless heavily customized |
| Agent portability | Medium | High |
| Operational clarity for contributors | Medium (many files, some drift) | High if strict templates are enforced |
| Runtime grounding quality | High (direct schema/rules/examples) | Medium-high (depends on linkage to vault artifacts) |
| Governance and change control | Medium-high (git + classifier) | Medium by default; needs policy integration |
| Drift resistance | Medium | Medium-high with explicit ownership and precedence |
| Adoption cost from current state | Low (stay as-is) | Medium (overlay) to high (full migration) |

## Recommendation

Adopt a **hybrid model**: keep the current vault artifacts as canonical domain knowledge, and add standardized patterns as an orchestration layer.

### Recommended shape

1. Keep canonical data files unchanged (`schema/`, `domain/`, `instructions/`, `examples/`, `metrics/`, gaps, insights).
2. Add a stable `AGENTS.md` template for connection-level operational policy:
   - precedence and allowed tools
   - required read order
   - write-back rules and transparency rules
3. Add curated `SKILL.md` modules for repeated workflows:
   - onboarding recovery
   - query generation and validation loop
   - knowledge-gap resolution
   - insight triage and metrics approval
4. Add ephemeral `MEMORY.md` (or generated equivalent) for short-horizon context only:
   - recent decisions
   - active assumptions
   - pending follow-ups
5. Define ownership:
   - system-managed files vs human-managed files vs generated summaries.

## Pros and Cons of Standardization in db-mcp

### Pros

- Reduces instruction sprawl across `PROTOCOL.md`, tool descriptions, and server prompts.
- Improves onboarding for new contributors and new agents.
- Makes behavior contracts easier to test and review.
- Creates cleaner separation between durable semantic knowledge and short-term working context.

### Cons

- Adds another abstraction layer to an already rich vault model.
- Risk of duplication if standardized files mirror existing artifacts without clear ownership.
- Requires migration and tooling to keep standardized files in sync with canonical YAML/Markdown artifacts.
- Poorly designed `MEMORY.md` can become stale/noisy quickly.

## Suggested Adoption Path

1. Normalize current path/format drift first (documentation and loader consistency).
2. Introduce `AGENTS.md` as a generated/stable contract that references canonical vault artifacts.
3. Pilot 2-3 `SKILL.md` workflows with concrete success criteria.
4. Introduce `MEMORY.md` as non-git, short TTL, auto-pruned context.
5. Add tests/checks that validate alignment between standardized docs and canonical vault schema.

## Bottom Line

Standardized patterns have clear merit for db-mcp, but as an overlay, not a replacement.
The existing vault model is strong for domain grounding; standardization should improve
governance, portability, and contributor ergonomics without diluting the current semantic layer.
