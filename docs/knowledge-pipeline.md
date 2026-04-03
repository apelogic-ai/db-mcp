# Knowledge Pipeline

## Concept

Query execution in db-mcp has a strong pre-execution knowledge path — before
SQL runs, `answer_intent` consults examples, rules, and schema. The
post-execution path is weak: inflow (results, errors, gaps) sits disconnected
from the knowledge layer. Approved examples, new rules, and gap resolutions
require explicit agent tool calls that most sessions never make.

The knowledge pipeline makes the return path explicit. It treats every
execution outcome as a structured signal that *may* update knowledge, routed
through a confirmation gate before anything is written.

**Ebb and flow framing:**
- **Stones** — the knowledge vault: examples, rules, schema descriptions,
  metrics, gaps
- **Outflow** — execution: SQL generation, API calls, validation
- **Inflow** — results, errors, 0-row responses, timeouts
- **Deposition** — inflow that adds knowledge: new examples, resolved gaps,
  inferred rules
- **Erosion** — inflow that marks knowledge stale: failing rules, invalid
  examples, new gaps

---

## What signals the pipeline emits

Each execution outcome maps to one or more `KnowledgeSignal` events:

| Outcome | Signal kind | Candidate action |
|---|---|---|
| Success, high-confidence SQL | `candidate_example` | Save as approved example |
| Success, 0 rows returned | `zero_row_flag` | Possible rule violation or stale filter |
| Gap hit during generation | `gap_opened` | Queue for gap resolution |
| Gap resolved (rule added) | `gap_closed` | Dismiss gap, record rule |
| SQL failed (parse/runtime) | `negative_signal` | Candidate negative example or rule |
| Confirmed query executed | `confirmed_execution` | High-confidence example candidate |
| Rule applied, query succeeded | `rule_validated` | Reinforce rule confidence |

Signals are emitted asynchronously after `ExecutionEngine` completes. They
do not block the query response path.

---

## Architecture

```
intent
  ↓
[pre: knowledge consulted]            examples + rules + schema → SQL
  ↓
generation → validation → execution   (outflow)
  ↓
results / error / 0-row               (inflow)
  ↓
SignalEmitter  (async, non-blocking)
  ↓
KnowledgeSignal stream
  ├──► inline suggestion (surfaced to agent in same session)
  └──► background consumer (knowledge extraction agent, batch)
  ↓
Schema registry  (vault-write-unification — validation + write gate)
  ↓
Knowledge vault updated
```

The signal emitter fires after `ExecutionEngine.mark_succeeded()` /
`mark_failed()`. It has no return value and never raises into the execution
path.

The schema registry (see `vault-write-unification.md`) is the write gate.
Signals that cross the confidence threshold enter the registry's pre-hook
validation before anything touches disk.

---

## KnowledgeSignal model

```python
@dataclass
class KnowledgeSignal:
    signal_id: str
    kind: str                        # candidate_example, gap_opened, ...
    execution_id: str                # source execution
    connection: str
    intent: str | None               # original NL intent, if known
    sql: str | None                  # executed SQL
    confidence: float                # 0.0–1.0
    suggested_write: dict | None     # schema_key + content for vault_write_typed()
    metadata: dict                   # rows_returned, duration_ms, error_code, ...
    timestamp: datetime
    disposition: str = "pending"     # pending | confirmed | discarded | auto_applied
```

`suggested_write` is a ready-to-apply `vault_write_typed()` call payload.
Confirming a signal is: validate + apply via schema registry.

---

## Confirmation model

**Signals are never auto-applied** for knowledge writes. Every write goes
through a confirmation step:

| Path | Mechanism |
|---|---|
| Agent in session | Signal surfaced as MCP tool response annotation; agent calls `query_approve` or a new `signal_confirm` tool |
| TUI user | Signal appears as a feed event with `/confirm` action (same confirm gate as query execution) |
| Background agent | Knowledge extraction agent reviews signal stream, applies with high-confidence threshold |
| Discarded | Signal expires after TTL with no action — no write |

This preserves the current design intent: knowledge writes are intentional,
not automatic side effects of execution.

---

## Relationship to existing plans

| Plan | Relationship |
|---|---|
| `vault-write-unification.md` | Schema registry is the write gate for confirmed signals — build this first |
| `tui-implementation.md` | TUI Phase 4 surfaces signals as feed events; `/confirm` extends to signal confirmation |
| `knowledge-extraction-agent.md` | Background consumer of the same signal stream; batch path for signals that expire without inline confirmation |
| `structural-cleanup-plan.md` | A1 (connection resolution) must be clean before signal emitter can reliably identify which connection produced a signal |

---

## TUI sequencing: precursor or successor?

Neither is a strict dependency of the other. The question is which delivers
more value first and which design is better informed by the other.

**Pipeline first** advantages:
- Signals accumulate in the background even before TUI exists — knowledge
  improves passively from day one
- TUI Phase 2+ can show knowledge signals in the feed from the start, rather
  than retrofitting them later
- Schema registry (already planned) can be built alongside, giving the
  pipeline its write gate early

**TUI first** advantages:
- TUI Phases 1–3 (read-only feed, confirm gate) need nothing from the
  pipeline — they ship faster independently
- "What does a knowledge signal look like in the feed?" is a UX question
  better answered with a real feed to look at
- The pipeline's inline confirmation UX (Phase 4 of TUI) is informed by
  building the confirm gate for query execution first (Phase 3 of TUI)

**Recommended sequencing:**

```
TUI Phase 1–2  ──────────────────────────────────────┐
(HTTP transport, read-only feed)                      │
                                                      │  converge here
Schema registry  ──► Knowledge pipeline (signals)  ───┤
(vault-write-unification)                             │
                                                      ▼
                                            TUI Phase 3–4
                                            (confirm gate + ACP insider agent
                                             + knowledge signal feed events)
```

TUI Phases 1–2 and the schema registry + pipeline can run in parallel.
They converge at TUI Phase 3, where the confirm gate is built to handle
both query confirmations and knowledge signal confirmations through the
same UI primitive.

Building the pipeline before TUI Phase 3 means the signal confirmation UX
is designed once, not retrofitted. Building TUI Phases 1–2 first means
there is a working feed to test against before adding signal events to it.

---

## Implementation phases

### Phase 1 — KnowledgeSignal model + SignalEmitter (no writes yet)

1. Define `KnowledgeSignal` in `packages/models/src/db_mcp_models/`
2. Implement `SignalEmitter` in `packages/core/src/db_mcp/pipeline/emitter.py`
   — hooks into `ExecutionEngine` post-completion, fires async, logs signals
3. No writes. No schema registry integration yet. Signals are emitted and
   logged; nothing consumes them.

**Gate:** signals appear in OTel traces / logs with correct fields. No
execution path latency impact measurable.

### Phase 2 — Schema registry integration + inline confirmation

1. Schema registry from `vault-write-unification.md` must be done first
2. `SignalEmitter` populates `suggested_write` for high-confidence signals
3. Confirmed signals call `vault_write_typed()` via schema registry
4. New MCP tool `signal_confirm(signal_id, action: confirm | discard)`
5. `answer_intent` surfaces pending signals as annotations on its response

**Gate:** an approved example can be created purely from execution outcome,
without the agent calling `query_approve` explicitly.

### Phase 3 — TUI integration + background consumer

1. Signals appear as feed events in TUI (requires TUI Phase 2+)
2. `/confirm` in TUI handles both query confirmations and signal confirmations
3. Background consumer connects signal stream to knowledge extraction agent

---

## Files (Phase 1)

| File | Change |
|---|---|
| `packages/models/src/db_mcp_models/signals.py` | New — `KnowledgeSignal` model |
| `packages/core/src/db_mcp/pipeline/__init__.py` | New package |
| `packages/core/src/db_mcp/pipeline/emitter.py` | New — `SignalEmitter` |
| `packages/data/src/db_mcp_data/execution/engine.py` | Modified — call emitter post-completion |
