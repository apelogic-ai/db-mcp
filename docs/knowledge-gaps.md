# Knowledge Gaps — Detection, Persistence, and Mitigation

## Summary

Add a persistent `knowledge_gaps.yaml` file to each connection's vault that tracks unmapped business terms and schema jargon. Populate it from three sources:

1. **Proactive schema scan** (during onboarding) — LLM analyzes column/table names for abbreviations, jargon, and non-obvious terms
2. **Reactive trace analysis** (existing) — vocabulary gap detection from agent search patterns
3. **MCP tool** — `get_knowledge_gaps` lets an analyst work through gaps conversationally

Gaps have statuses (`open` / `resolved`) and are marked resolved when corresponding business rules are added.

## Architecture

```
Sources                          Persistent File                    Consumers
────────                         ───────────────                    ─────────
Schema scan (onboarding)  ──┐
                             ├──▶  knowledge_gaps.yaml  ──┬──▶  Insights UI (existing card, enhanced)
Trace analysis (insights) ──┘     (in connection vault)   ├──▶  MCP tool: get_knowledge_gaps
                                                          └──▶  Onboarding: gap review phase
```

## File Format

`~/.db-mcp/connections/{name}/knowledge_gaps.yaml`

```yaml
version: "1.0.0"
provider_id: nova
gaps:
  - id: "a1b2c3d4"
    term: "CUI"
    status: open              # open | resolved
    source: traces            # schema_scan | traces
    detected_at: "2026-01-28T15:47:00"
    context: "searched 4x in session abc12345"
    related_columns:
      - dwh.public.cdrs.chargeable_user_identity
      - dwh.public.cdr_agg_day.wifi_chargeable_user_identity
    suggested_rule: "chargeable_user_identity, CUI are synonyms."
    resolved_at: null
    resolved_by: null         # "business_rules" | "schema_description" | "manual"

  - id: "e5f6g7h8"
    term: "bh_d"
    status: open
    source: schema_scan
    detected_at: "2026-01-28T10:00:00"
    context: "abbreviation detected in column name"
    related_columns:
      - dwh.public.cdr_agg_day.bh_d
    suggested_rule: null
    resolved_at: null
    resolved_by: null
```

## Implementation Steps

### 1. Add Pydantic model for KnowledgeGap

**File**: `packages/models/src/db_mcp_models/gaps.py` (NEW)

```python
class GapStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"

class GapSource(str, Enum):
    SCHEMA_SCAN = "schema_scan"
    TRACES = "traces"

class KnowledgeGap(BaseModel):
    id: str
    term: str
    status: GapStatus = GapStatus.OPEN
    source: GapSource
    detected_at: datetime
    context: str | None = None
    related_columns: list[str] = []
    suggested_rule: str | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None

class KnowledgeGaps(BaseModel):
    version: str = "1.0.0"
    provider_id: str
    gaps: list[KnowledgeGap] = []
```

Export from `packages/models/src/db_mcp_models/__init__.py`.

### 2. Add gaps store module

**File**: `packages/core/src/db_mcp/gaps/store.py` (NEW)

Follow the training store pattern:
- `get_gaps_file_path(provider_id) -> Path`
- `load_gaps(provider_id) -> KnowledgeGaps`
- `save_gaps(gaps: KnowledgeGaps) -> dict`
- `add_gap(provider_id, term, source, ...) -> KnowledgeGap` — deduplicates by term (case-insensitive)
- `resolve_gap(provider_id, gap_id, resolved_by) -> dict`
- `merge_trace_gaps(provider_id, trace_gaps: list[dict]) -> int` — takes output from `_detect_vocabulary_gaps()`, adds new gaps, skips existing terms, returns count added

Also add `packages/core/src/db_mcp/gaps/__init__.py`.

### 3. Add LLM-based schema scan function

**File**: `packages/core/src/db_mcp/gaps/scanner.py` (NEW)

```python
async def scan_schema_for_gaps(ctx: Context) -> list[KnowledgeGap]:
    """Analyze schema column/table names for jargon and abbreviations.

    Uses MCPSamplingModel to ask the LLM to identify:
    - Abbreviations (bh_d, hmh, nas_id, cui)
    - Domain jargon (greenfield, brownfield, hotspot)
    - Non-obvious names (columns where name doesn't self-explain)
    - Animal/restaurant/code names used as business terms

    Returns list of KnowledgeGap objects to be saved.
    """
```

Implementation:
- Load `schema/descriptions.yaml`
- Build a prompt listing all table and column names (grouped by table)
- Ask LLM via `MCPSamplingModel`: "Identify abbreviations, jargon, and non-obvious terms. For each, give the term, which columns it appears in, and your best guess at what it means."
- Parse structured output into `KnowledgeGap` objects with `source=schema_scan`
- Use a Pydantic output model for structured parsing:

```python
class DetectedGap(BaseModel):
    term: str
    columns: list[str]
    explanation: str  # LLM's best guess at meaning

class SchemaGapScanResult(BaseModel):
    gaps: list[DetectedGap]
```

### 4. Wire trace analysis into gaps file

**File**: `packages/core/src/db_mcp/bicp/traces.py` (MODIFY)

In `analyze_traces()`, after `_detect_vocabulary_gaps()`:
- If `connection_path` is available, call `merge_trace_gaps()` to persist newly detected gaps
- Add `knowledgeGaps` to the return dict (read from the persisted file, not just in-memory detection) — this ensures the UI shows all gaps including previously detected ones

**File**: `packages/core/src/db_mcp/bicp/agent.py` (MODIFY)

In `_handle_insights_analyze()`:
- After `analyze_traces()`, also check if any gaps were resolved (by checking if their `suggested_rule` text now exists in `business_rules.yaml`)
- Auto-resolve gaps whose rules have been added

### 5. Add `get_knowledge_gaps` MCP tool

**File**: `packages/core/src/db_mcp/tools/gaps.py` (NEW)

```python
async def _get_knowledge_gaps() -> dict:
    """Get current knowledge gaps for the active connection.

    Returns open gaps with suggested rules, plus summary stats.
    Used by analysts to work through gaps conversationally.
    """
```

Returns:
```python
{
    "status": "success",
    "provider_id": "nova",
    "gaps": [...],  # list of open gaps
    "stats": {
        "total": 10,
        "open": 4,
        "resolved": 6,
    },
    "guidance": {
        "summary": "4 open knowledge gaps found.",
        "next_steps": [
            "Review each gap and confirm/correct the suggested rule",
            "Use query_approve to add confirmed rules",
            "Gaps will be auto-resolved when matching rules are added",
        ],
    },
}
```

**File**: `packages/core/src/db_mcp/server.py` (MODIFY)

Register the tool:
```python
server.tool(name="get_knowledge_gaps")(_get_knowledge_gaps)
```

### 6. Add schema scan to onboarding flow (optional post-explore phase)

**File**: `packages/core/src/db_mcp/tools/onboarding.py` (MODIFY)

After the SCHEMA phase completes (all tables approved/skipped), before DOMAIN:
- If `knowledge_gaps.yaml` doesn't exist yet, run `scan_schema_for_gaps(ctx)`
- Save detected gaps
- Return guidance suggesting the user review gaps before proceeding

This is NOT a new onboarding phase (no state machine change). It's a one-time scan that happens at the SCHEMA->DOMAIN transition. The gaps file is created and the user is prompted, but they can skip straight to domain building.

### 7. Auto-resolve gaps when rules are added

**File**: `packages/core/src/db_mcp/gaps/store.py` (in `merge_trace_gaps` or separate function)

```python
def auto_resolve_gaps(provider_id: str) -> int:
    """Check if any open gaps have been addressed by business rules.

    Scans business_rules.yaml for terms matching open gaps.
    Marks matching gaps as resolved with resolved_by="business_rules".
    Returns count of newly resolved gaps.
    """
```

Called from:
- `_handle_insights_analyze()` in agent.py (on each insights refresh)
- After writing a business rule via the UI "+ Add Rule" button

### 8. Update Insights UI to use persisted gaps

**File**: `packages/ui/src/app/insights/page.tsx` (MODIFY)

The `VocabularyGapsCard` already shows grouped terms. Enhance it:
- Show resolved gaps (dimmed, with checkmark) below open ones
- Show stats: "4 open / 6 resolved"
- When "+ Add Rule" succeeds, the gap will show as resolved on next refresh

No new components needed — just extend the existing card.

### 9. Update BICP types

**File**: `packages/ui/src/lib/bicp.ts` (MODIFY)

The `vocabularyGaps` type in `InsightsAnalysis` already has `terms`, `schemaMatches`, `suggestedRule`. Add:
- `id: string` — gap ID for resolution tracking
- `status: "open" | "resolved"` — so UI can show resolved state

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `packages/models/src/db_mcp_models/gaps.py` | CREATE | KnowledgeGap, KnowledgeGaps models |
| `packages/models/src/db_mcp_models/__init__.py` | MODIFY | Export new models |
| `packages/core/src/db_mcp/gaps/__init__.py` | CREATE | Package init |
| `packages/core/src/db_mcp/gaps/store.py` | CREATE | load/save/merge/resolve functions |
| `packages/core/src/db_mcp/gaps/scanner.py` | CREATE | LLM-based schema scan |
| `packages/core/src/db_mcp/tools/gaps.py` | CREATE | get_knowledge_gaps MCP tool |
| `packages/core/src/db_mcp/server.py` | MODIFY | Register new tool |
| `packages/core/src/db_mcp/bicp/traces.py` | MODIFY | Persist trace gaps, read from file |
| `packages/core/src/db_mcp/bicp/agent.py` | MODIFY | Auto-resolve on insights refresh |
| `packages/core/src/db_mcp/tools/onboarding.py` | MODIFY | Schema scan at SCHEMA->DOMAIN |
| `packages/core/src/db_mcp/vault/init.py` | MODIFY | Add gaps dir to CONNECTION_DIRS |
| `packages/ui/src/app/insights/page.tsx` | MODIFY | Show resolved state, stats |
| `packages/ui/src/lib/bicp.ts` | MODIFY | Add id, status to gap type |

## Verification

```bash
# 1. Python lint + tests
cd packages/core
uv run ruff check . --fix
uv run python -m pytest tests/ -v

# 2. UI lint + e2e tests
cd packages/ui
npx next lint
npx playwright test

# 3. Manual: MCP tool test
# In Claude Desktop with db-mcp running:
# Ask: "Show me knowledge gaps"
# Claude calls get_knowledge_gaps -> returns gaps list
# Ask: "Add a rule: CUI and chargeable_user_identity are synonyms"
# Claude calls query_approve or writes rule
# Ask: "Show me knowledge gaps again"
# -> CUI gap now shows as resolved

# 4. Manual: Schema scan test
# Run onboarding on a connection, complete SCHEMA phase
# -> knowledge_gaps.yaml created with detected abbreviations/jargon
# -> User prompted to review before domain building

# 5. Manual: Insights UI
# Open http://localhost:3000/insights
# -> Unmapped Terms card shows open gaps with "+ Add Rule"
# -> Click "+ Add Rule" -> gap resolves on next refresh
# -> Resolved gaps shown dimmed with checkmark
```
