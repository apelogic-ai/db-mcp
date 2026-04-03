# Architecture Review & Restructuring Plan

**Status**: Draft
**Created**: 2026-03-30
**Context**: Full codebase review of db-mcp (v0.8.10, ~48,700 lines in core)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Design Goals](#design-goals) (DG-1 through DG-7)
3. [Current Architecture](#current-architecture)
4. [Identified Layers](#identified-layers)
5. [Code Quality Issues](#code-quality-issues)
6. [BICP Assessment](#bicp-assessment)
7. [Concept Placement](#concept-placement)
8. [Data Gateway Abstraction](#data-gateway-abstraction)
9. [Proposed Package Structure](#proposed-package-structure)
10. [Layer Independence & Separate Shipping](#layer-independence--separate-shipping)
11. [Migration Path](#migration-path) (6 phases, 85 commits)
12. [MCP Tool Audit](#mcp-tool-audit)
13. [Open Questions](#open-questions)
14. [Appendix: Module Line Counts](#appendix-module-line-counts)

---

## Executive Summary

db-mcp has clean separation at the storage level — knowledge modules and data
retrieval modules have **zero cross-imports**. But 63% of the codebase (30,700
lines) sits in an undifferentiated "glue" layer where three protocol entry
points (MCP, BICP, CLI) each wire into both layers independently, with
significant duplication.

The proposed restructuring:
- Extract a **services layer** from the tools/BICP/CLI overlap
- Introduce a **gateway module** for typed data retrieval
- Split into **four packages**: models, core, mcp-server, cli
- Reduce BICP agent from 4,648 lines to a thin protocol adapter
- **Design goal:** knowledge layer and data retrieval layer must be
  independently shippable as separate packages with no mutual dependency

---

## Design Goals

### DG-1: Layer Independence

The **knowledge layer** (schema descriptions, metrics, examples, rules,
collaboration) and the **data retrieval layer** (connectors, execution engine,
validation, gateway) must have **zero imports from each other**.

This is already true today at the storage level. The restructuring must
preserve this invariant and extend it to the services layer.

**Service classification:**

- **Pure services** import from exactly one layer. Examples:
  `services/schema.py` (data only), `services/context.py` (knowledge only).
- **Bridge services** are the *only* services permitted to import from both
  layers. They must be explicitly marked as bridges and kept to a minimum.
  The allowed bridge services are:
  - `services/onboarding.py` — populates knowledge from live DB (Bridge 2)
  - `orchestrator/engine.py` — resolves knowledge plans into data execution (Bridge 3)
  - `code_runtime/backend.py` — exposes both layers to sandboxed code (Bridge 4)

  Bridge 1 (context assembly) is *not* a bridge service — it is a pure
  knowledge service (`services/context.py`) whose output is consumed by
  the LLM, which then produces SQL for a pure data service
  (`services/query.py`). The LLM is the bridge, not the service.

- Any new service that needs both layers must be justified as a bridge
  and added to the list above. This is a design review gate, not a
  runtime check.

### DG-2: Separate Shipping

It must be possible to package and ship knowledge and data retrieval as
independent Python packages:

```
pip install db-mcp-knowledge    # no sqlalchemy, no DB drivers
pip install db-mcp-data          # no yaml knowledge files needed
pip install db-mcp               # full product (depends on both)
```

This means:
- Neither layer may call `get_settings()` or depend on application config.
  Every function takes `connection_path: Path` explicitly.
- Neither layer may depend on the registry, CLI, MCP, BICP, or any entry point.
- Shared types live in `packages/models/` — the only common dependency.

### DG-3: Thin Entry Points

MCP server, CLI, and BICP/UI backend must be thin protocol adapters over
a shared services layer. Business logic lives in services; protocol-specific
concerns (tool registration, `inject_protocol`, Click decorators, JSON-RPC
dispatch) live in the entry point packages.

### DG-4: Typed Data Boundary

All data retrieval goes through a typed gateway facade (`DataRequest` →
`DataResponse`). No entry point or service constructs ad-hoc result dicts
from raw connector output. The gateway normalizes return shapes across
SQL, API, and file connectors.

The `DataResponse` envelope must be extensible beyond simple result sets.
The initial SCALAR/VECTOR cardinality model covers query results, but the
type must accommodate future needs without breaking changes:
- **Pagination** — cursor/offset for partial result sets
- **Streaming** — incremental record delivery
- **Warnings** — query planner warnings, cost advisories
- **Rich API responses** — metadata, rate-limit headers, nested objects

Design principle: start with SCALAR/VECTOR as the cardinality hint, but
make `DataResponse` a Pydantic model with optional fields. New capabilities
are additive (new fields with defaults), never breaking.

### DG-5: Single Execution FSM

One execution lifecycle implementation (`execution/`), one state machine,
one persistent store. No parallel in-memory query stores. The gateway is
the sole caller of the execution engine.

### DG-6: Import Boundary Enforcement

Layer independence (DG-1) and separate shipping (DG-2) must be enforced
by automated checks, not just convention.

**Enforcement mechanisms:**

1. **CI test:** A pytest fixture asserts that knowledge modules have zero
   imports from data modules and vice versa. This runs on every PR.
   ```python
   def test_knowledge_does_not_import_data():
       """DG-1 enforcement: knowledge → data imports are forbidden."""
       violations = find_imports("packages/knowledge/", forbidden_prefixes=[
           "db_mcp_data.", "db_mcp.connectors.", "db_mcp.db.",
           "db_mcp.execution.", "db_mcp.validation.",
       ])
       assert violations == [], f"Knowledge imports data: {violations}"
   ```
2. **CI test:** Neither layer imports `db_mcp.config` or `db_mcp.registry`.
3. **Bridge service audit:** A test enumerates all services and asserts that
   only the declared bridge services import from both layers.
4. **Dependency check:** After Phase 6, `pip install db-mcp-knowledge`
   must succeed in a venv without sqlalchemy. `pip install db-mcp-data`
   must succeed without dulwich. These are CI jobs.

### DG-7: API Stability

The library APIs exposed by `packages/knowledge/` and `packages/data/`
are **internal-first, stable-second**.

- **Phase 1–5:** APIs are internal. Function signatures may change freely.
  External consumers are not supported.
- **Phase 6:** APIs become public. From this point:
  - Public functions are documented with docstrings and type hints.
  - Breaking changes require a deprecation cycle (warn for one minor
    version, remove in the next).
  - The CLI examples in this document are illustrative of intended usage
    but do not constitute a stable CLI contract until Phase 6 ships.

This is stated explicitly: do not build external tooling against
`db_mcp_knowledge` or `db_mcp_data` imports until Phase 6 is complete.

---

## Current Architecture

### Repository Structure (Monorepo)

```
packages/
  models/   # Shared Pydantic types          (~1,400 lines)
  core/     # Everything else                 (~48,700 lines)
  ui/       # Next.js UI                      (~59 TS/TSX files)
```

### Core Package Breakdown

```
48,718 lines total
├── 30,781  glue / entry points / tools  (63%)  ← the problem
├──  7,446  data retrieval               (15%)  ← clean
├──  6,866  knowledge layer              (14%)  ← clean
├──  1,895  infrastructure                (4%)  ← clean
└──  1,730  observability                 (4%)  ← clean
```

### Three Entry Points

| Entry Point | Protocol | Lines | How it accesses layers |
|-------------|----------|-------|----------------------|
| `server.py` + `tools/` | MCP (stdio/HTTP) | 9,763 | Via tool functions that reach into both layers |
| `bicp/agent.py` | BICP (JSON-RPC) | 5,882 | Directly into both layers, bypasses tools entirely |
| `cli/` | Click CLI | 4,933 | Directly into both layers, overlaps with tools and BICP |

All three reach into the same shared stores from different angles, each with
their own wiring, error handling, and connection resolution logic.

---

## Identified Layers

### The Clean Seam

At the store/module level, two groups have **zero cross-imports**:

```
KNOWLEDGE LAYER (0 data imports)     DATA RETRIEVAL LAYER (0 knowledge imports)
────────────────────────────────     ──────────────────────────────────────────
onboarding/                          connectors/ (SQL, API, File)
training/                            connector_plugins/
metrics/                             db/ (SQLAlchemy)
vault/                               validation/ (EXPLAIN, policy)
gaps/                                execution/ (FSM + SQLite store)
semantic/                            contracts/
insights/                            capabilities.py
collab/                              connector_compat.py
planner/                             connector_templates.py
business_rules.py                    dialect.py
```

### Bridge Points

Exactly four operations cross the knowledge/data seam. All four are
legitimate — they are the product’s core value. The architecture must
make them **explicit and narrow**, not eliminate them.

#### Bridge 1: Query Context Assembly (K → LLM → D)

The primary workflow. Knowledge artifacts are assembled into a context
packet, an LLM generates SQL from it, and the SQL is executed against
the data layer.

```
Knowledge                          Data
─────────                          ────
load_schema_descriptions() ─┐
load_examples()             ├──► context ─► LLM ─► SQL ─► gateway.execute()
load_instructions()         │
load_metrics()             ─┘
```

**Where today:** `_get_data()` in `tools/generation.py`, `prepare_task()`
in `tools/daemon_tasks.py`, `_build_*_context()` helpers.

**After restructuring:** `services/context.py` builds the context packet
from knowledge. `services/query.py` sends SQL to the gateway. The LLM
sits between them — outside both layers.

#### Bridge 2: Schema Discovery / Onboarding (D → K)

Live database introspection populates the knowledge vault. The connector
fetches real table/column metadata; onboarding writes it to
`schema/descriptions.yaml`. This is the **only** direction where data
flows into knowledge.

```
Data                              Knowledge
────                              ─────────
connector.get_tables()     ──►    save_schema_descriptions()
connector.get_columns()    ──►    save_state()
```

**Where today:** `tools/onboarding.py` `_onboarding_discover()`.

**After restructuring:** `services/onboarding.py` calls
`gateway.introspect()` (data) and writes to knowledge stores.

#### Bridge 3: Metric-Aware Query Execution / Orchestrator (K → D)

The orchestrator resolves a natural language intent into a metric
execution plan using the semantic core (knowledge), then executes
the compiled SQL (data).

```
Knowledge                              Data
─────────                              ────
load_connection_semantic_core() ─┐
compile_metric_intent()          ├──►  resolved SQL ──► gateway.execute()
resolve_metric_execution_plan() ─┘
```

**Where today:** `orchestrator/engine.py`.

**After restructuring:** Orchestrator imports from `knowledge.semantic`
and `knowledge.planner`, calls `services/query.py` which calls
`gateway.execute()`. Clean bridge.

#### Bridge 4: Code Sandbox Runtime (K + D → User)

The code runtime builds a `dbmcp` helper object that gives sandboxed
Python code access to **both** layers: it reads vault files (knowledge)
and executes SQL (data).

```
Knowledge                  Data
─────────                  ────
read PROTOCOL.md      ┐    connector.execute_sql() ┐
read schema/           ├──► dbmcp helper object  ◄──┤
read examples/         │    connector.get_tables()  │
read business_rules    ┘                            ┘
```

**Where today:** `code_runtime/backend.py` (`HostDbMcpRuntime`, 1,353 lines).

**After restructuring:** The runtime consumes `knowledge` and `data`
packages. Reads vault files directly (YAML/MD) and calls
`gateway.execute()` for SQL.

#### Non-Bridge: `inject_protocol`

`inject_protocol` in `tools/shell.py` staples knowledge-layer reminders
onto data retrieval results. This is **not** a legitimate bridge — it is
an MCP presentation concern. After restructuring it lives only in
`mcp-server/protocol.py`.

#### Bridge Summary

| # | Bridge | Direction | Purpose | After Restructuring |
|---|--------|-----------|---------|---------------------|
| 1 | Context assembly | K → LLM → D | Build prompt, generate SQL, execute | `services/context.py` → LLM → `services/query.py` |
| 2 | Schema discovery | D → K | Populate vault from live DB | `services/onboarding.py` |
| 3 | Metric orchestration | K → D | Resolve intent to SQL, execute | `orchestrator/` → `services/query.py` |
| 4 | Code sandbox | K + D → user | Sandboxed code with full access | `code_runtime/` consumes both packages |

Every other module is purely one side or the other:

| Pure Knowledge | Pure Data | Pure Neither |
|---------------|-----------|-------------|
| training tools | database tools | CLI commands |
| metrics tools | API tools | config / registry |
| gaps tools | dialect tools | traces / console |
| domain tools | validation | agents.py |
| collab | execution engine | insider |
| shell (vault access) | | |

### Layer Map

```
┌─────────────────────────────────────────────────────────────┐
│                  OPERATIONAL LAYER                           │
│  traces.py, console/, insights/ (observe, don't participate)│
└─────────────────────────────────────────────────────────────┘

┌────────────────────────────┐  ┌─────────────────────────────┐
│     KNOWLEDGE LAYER        │  │   DATA RETRIEVAL LAYER      │
│                            │  │                              │
│  schema descriptions       │  │  connectors/ (SQL, API, File)│
│  metrics / dimensions      │  │  db/ (SQLAlchemy)            │
│  instructions / rules      │  │  validation/ (EXPLAIN)       │
│  training examples         │  │  execution/ (FSM + store)    │
│  domain model              │  │  exec_runtime (sandbox)      │
│  knowledge gaps            │  │                              │
│  planner / meta-query      │  │  Query (immutable request)   │
│  semantic core             │  │  Execution (stateful FSM)    │
│  collab                    │  │                              │
└────────────┬───────────────┘  └──────────────┬──────────────┘
             │                                  │
             │  ┌───────────────────────────┐   │
             │  │      4 BRIDGES            │   │
             └─►│  1. context assembly      │◄──┘
                │  2. schema discovery      │
                │  3. metric orchestration  │
                │  4. code sandbox          │
                └───────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE                              │
│  config.py, registry.py, connection (addressing + caps)     │
└─────────────────────────────────────────────────────────────┘
```

---

## Code Quality Issues

### Critical (🔴)

**1. God Object: `bicp/agent.py` (4,648 lines, 82 methods)**

Reimplements most of `tools/*` — schema loading, state management, connection
resolution, git operations, onboarding, training. Has 55 calls to shared stores
and 5 scattered `from db_mcp.git_utils import git` lazy imports. A parallel
application that duplicates the MCP tools layer for the BICP protocol.

**2. Mega Function: `_run_sql` (605 lines)**

Lines 854–1459 in `tools/generation.py`. Single async function with deeply
nested branching for SQL connectors, API connectors, sync/async paths, fallback
logic, and inline helper closures. Extremely hard to test or reason about.

**3. Monolithic Server Factory: `_create_server` (~850 lines)**

Registers ~90 tools with complex conditional logic based on modes, profiles,
and capabilities. Inline function definitions make tools untestable in
isolation. Contains 5 large instruction string constants (~200 lines of
prompt templates).

### Structural (🟠)

**4. Dead `workflow/` module** — Directory contains only `__pycache__`, no
source files.

**5. Duplicated `_report_progress`** — Identical helper in both
`tools/generation.py:564` and `tools/onboarding.py:349`.

**6. Four variants of connection resolution:**
- `tools/utils.py` → `resolve_connection()`, `_resolve_connection_path()`, `require_connection()`
- `tools/daemon_tasks.py` → `_resolve_connection_name()`
- `cli/commands/insider.py` → `_resolve_connection()`
- `bicp/agent.py` → `_resolve_connection_context()`

**7. Vestigial `database_url` parameters** — 5 functions in `tools/database.py`
accept `database_url: str | None = None` that's effectively unused.

**8. Copy-paste boilerplate in `tools/database.py`** — 6 functions with
identical pattern: `get_connector(...)` → call method → `inject_protocol(success)`
/ `except: inject_protocol(error)`.

### Design Smells (🟡)

**9. Lazy imports for circular dependency avoidance** —
`tools/domain.py` does `from db_mcp.tools.utils import resolve_connection`
inside 4 separate function bodies. Same pattern in `generation.py`, `server.py`,
and throughout `bicp/agent.py`.

**10. Instructions as giant string constants** — 5 prompt templates (~200 lines
total) embedded in `server.py`. The `templates/prompts/` directory exists but
isn't used for these.

**11. Broad `except Exception` everywhere** — `generation.py` has 19
`try/except` blocks, `onboarding.py` has 10. No consistent error handling
strategy: some log, some `pass`, some return error dicts, some set span status.

**12. SSL verify hardcoded off** — `db/connection.py:107` has
`"verify": False, # TODO: Make configurable for production`.

**13. `tasks/store.py` duplicates `execution/store.py`** — Two parallel
query lifecycle stores with different FSMs and storage (in-memory vs SQLite).

---

## BICP Assessment

### What is BICP?

BICP (Business Intelligence Client Protocol) is a JSON-RPC protocol from an
external package (`bicp-agent`, ~1,127 lines) for BI client UIs to talk to a
backend agent. The base `BICPAgent` class defines 9 standard methods for a
query lifecycle:

```
initialize → schema/list → query/create → query/candidates →
query/approve → query/result → semantic/search
```

### How db-mcp Uses It

`DBMCPAgent` subclasses `BICPAgent` and serves as the backend for the Next.js
UI via `POST /bicp` JSON-RPC and `WebSocket /bicp/stream`.

### The Problem: Protocol Overload

The agent has **48 `_handle_*` methods**, of which only ~5 implement actual
BICP protocol. The other 43 are custom extensions tunneled through JSON-RPC:

| Category | Count | BICP spec? |
|----------|-------|-----------|
| Connection CRUD | 13 | No |
| Context/vault editing | 7 | No |
| Git operations | 3 | No |
| Traces/observability | 3 | No |
| Insights | 2 | No |
| Metrics CRUD | 6 | No |
| Agent config | 5 | No |
| Schema browsing | 5 | Partially |
| Playground | 2 | No |
| Query lifecycle | 2 | Yes |

### Assessment

| Aspect | Verdict |
|--------|---------|
| UI needs a non-MCP backend API | ✅ Legitimate |
| Using BICP for query lifecycle | ✅ Reasonable |
| 43 custom handlers tunneled through BICP | 🔴 Should be REST API |
| 4,648-line God Object | 🔴 Unmaintainable |
| Duplicates entire tools layer | 🔴 DRY violation |
| External dependency for ~5 methods | 🟡 Questionable ROI |

### Recommendation

Extract shared service functions from both `tools/*` and `bicp/agent.py`.
Expose them through a normal FastAPI router for the UI. Keep BICP only for
the actual query lifecycle (if at all).

---

## Concept Placement

### Connection — Infrastructure

A configured endpoint descriptor (name, type, path, capabilities). Not
knowledge (doesn't teach AI about data) and not data retrieval (doesn't fetch
anything). The addressing system both layers depend on.

Currently mostly stateless — `SQLConnector` creates fresh engines per call,
`ConnectionRegistry` caches instances but holds no session state.

**Belongs in:** Infrastructure layer. Standalone concern that both knowledge
and data retrieval depend on.

### Execution — Data Retrieval Layer

Stateful FSM: `PRECHECK → VALIDATED → SUBMITTED → RUNNING → SUCCEEDED/FAILED`.

Currently fragmented across three systems:

| System | Storage | FSM |
|--------|---------|-----|
| `execution/` models + store | SQLite | Clean `ExecutionState` enum |
| `tasks/store.py` | In-memory (lost on restart) | Separate FSM |
| `tools/generation.py` `_run_sql` | Inline logic | Ad-hoc state transitions |

**Belongs in:** Purely data retrieval layer. The `execution/` module has it
right — zero knowledge imports. `tasks/store.py` should be eliminated.

### Query — Data Retrieval Layer (Three Concepts)

Today `tasks/store.py::Query` conflates request, validation, and execution
in one mutable object. The gateway introduces three distinct types:

- **DataRequest** — caller intent (immutable value object, not persisted)
- **ValidatedQuery** — persisted, immutable record with stable `query_id`.
  Can be executed multiple times. Holds cost tier, validation metadata.
- **Execution** — one attempt to run a validated query. Has its own
  `execution_id`, FSM state, timing, and result.

Query identity and execution identity are separate: one `ValidatedQuery`
can have many `Execution` attempts. This avoids the `tasks/store.py`
mistake of mixing "what to run" with "what happened when we ran it."

**Belongs in:** Data retrieval layer. `DataRequest` and `ValidatedQuery`
are in `gateway/`. `Execution` and `ExecutionResult` are in `execution/`.

### Meta-Query — Knowledge Layer (Bridge at Boundary)

Semantic intent resolved through knowledge: match metrics, detect dimensions,
compile SQL from templates. `MetaQueryPlan` and `MetricExecutionPlan` are pure
knowledge-layer objects (zero connector imports).

The orchestrator is the **legitimate bridge**: transforms a knowledge-layer
plan into a data-retrieval-layer execution.

**Belongs in:** Knowledge layer for planning/resolution. Orchestrator bridges
to data retrieval.

### Metrics / Dimensions — Knowledge Layer (Pure)

YAML definitions with SQL templates, parameters, display names, dimension
bindings. Zero data-layer imports. The SQL template is just a string until
the orchestrator hands it to execution.

**Belongs in:** Knowledge layer. Already clean.

### Data Schema — Knowledge Layer (Populated by Bridge)

Cached schema (`descriptions.yaml`) with semantic annotations. Read by tools,
orchestrator, BICP, prompt builders. Zero data-layer imports in store modules.

The bridge is `_onboarding_discover()`, which calls `get_connector().get_tables()`
(data) and writes to `descriptions.yaml` (knowledge). Inherently cross-cutting
but well-defined.

**Belongs in:** Knowledge layer for storage/serving. Discovery is a bridge.

### OTel Traces — Operational Layer

Observes both layers but belongs to neither. JSONL span exporter, console
viewer, insights detector. `traces.py` has no knowledge or connector imports.

**Belongs in:** Operational/observability layer (third layer).

### Instructions, Rules, Business Rules — Knowledge Layer (Pure)

YAML/Markdown encoding human expertise: dialect quirks, synonyms, filters,
unit conversions. Zero data-layer imports.

**Belongs in:** Knowledge layer. Already clean.

---

## Data Gateway Abstraction

### The Problem

Every connector returns data differently. `_run_sql()` is 605 lines because
it does ad-hoc shape unification across SQL engines, sync APIs, async APIs,
and file connectors — with 30+ different return dict shapes.

### Return Type Modeling

All data retrieval results can be modeled as:

- **SCALAR** — single record (COUNT, SUM, latest price)
- **VECTOR** — rows × columns (table data, time series)

This maps directly to existing `ExpectedCardinality.ONE/MANY` in the models
package.

### Typed Request/Response with Two-Step Query Lifecycle

All query types — SQL, API endpoint, API SQL, file SQL — follow the
same two-step lifecycle: **create** (validate and record) then **execute**.

The gateway contract defines three distinct concepts:

```
DataRequest          →  gateway.create()  →  ValidatedQuery
  (what to run)                                  (persisted, immutable)
                                                       │
                         gateway.execute() ──────────┘
                              │
                              ▼
                         Execution
                         (one attempt, with result)
```

- **DataRequest** — the caller's intent. Immutable value object, not persisted.
- **ValidatedQuery** — persisted record of a validated request. Has a stable
  `query_id`. Can be executed multiple times. Never mutated after creation.
- **Execution** — one attempt to run a validated query. Has its own
  `execution_id`. Tracks FSM state, timing, result, and errors. Multiple
  executions can reference the same `query_id`.

#### Concept 1: DataRequest (caller intent)

```python
@dataclass(frozen=True)
class DataRequest:
    connection: str
    query: SQLQuery | EndpointQuery    # discriminated union

@dataclass(frozen=True)
class SQLQuery:
    sql: str
    params: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class EndpointQuery:
    endpoint: str
    params: dict[str, Any] = field(default_factory=dict)
    method: str = "GET"
    max_pages: int = 1
```

#### Concept 2: ValidatedQuery (persisted, immutable)

`gateway.create(request)` validates the request and persists it.

```python
@dataclass(frozen=True)
class ValidatedQuery:
    query_id: str                      # stable ID, survives restarts
    connection: str
    query_type: str                    # "sql" | "endpoint" | "api_sql" | "file_sql"
    request: DataRequest               # frozen original request
    cost_tier: str                     # "low" | "confirm" | "reject" | "unknown"
    validated_at: datetime
    # SQL-specific (when available)
    sql: str | None = None
    estimated_rows: int | None = None
    explain_plan: list[str] | None = None
    # API-specific (when available)
    endpoint: str | None = None
```

A `ValidatedQuery` is never mutated. It is the **definition** of what to
run. `query_id` is the primary key for re-execution, history lookup,
and named query aliases.

#### Concept 3: Execution (one attempt)

`gateway.execute(query_id, options)` creates an execution attempt for a
validated query. Per-execution overrides are passed via `RunOptions` —
this keeps `ValidatedQuery` immutable while allowing execution-time
decisions like cost gate overrides.

```python
@dataclass(frozen=True)
class RunOptions:
    confirmed: bool = False            # override cost gate for this run
    export_format: str | None = None   # "csv" | "json" | None
    timeout_seconds: int | None = None # per-execution timeout

@dataclass
class Execution:
    execution_id: str                  # unique per attempt
    query_id: str                      # references ValidatedQuery
    state: ExecutionState              # RUNNING → SUCCEEDED | FAILED
    options: RunOptions                # overrides for this attempt
    started_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    error: ExecutionError | None
    metadata: dict[str, Any]           # adapter-specific details

@dataclass
class ExecutionResult:
    execution_id: str
    query_id: str
    state: ExecutionState              # SUCCEEDED | FAILED
    cardinality: Cardinality           # SCALAR | VECTOR (hint, extensible)
    columns: list[ColumnMeta]
    records: list[dict[str, Any]]
    total_records: int
    duration_ms: float | None
    error: ExecutionError | None
    provenance: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    cursor: str | None = None          # pagination (future)
```

`confirmed` lives on `RunOptions`, not on `DataRequest` or `ValidatedQuery`.
This is intentional: the validated query records *what* to run; execution
options control *how* to run it this time. A rejected-cost query can be
re-executed with `confirmed=True` without creating a new query definition.

Multiple `Execution` records can reference the same `query_id`. This is
how re-runs, retries, and comparison work.

#### Convenience: One-Step Run

```python
# create + execute in one call (auto-runs if cost tier allows)
result = gateway.run(
    DataRequest(connection="prod", query=SQLQuery(sql="...")),
    options=RunOptions(),  # optional, defaults to no overrides
)
# returns ExecutionResult (ValidatedQuery created internally)

# override cost gate in one-shot mode
result = gateway.run(
    DataRequest(connection="prod", query=SQLQuery(sql="SELECT * FROM big_table")),
    options=RunOptions(confirmed=True),
)
```

#### Identity Model

```
ValidatedQuery (1) ────< (N) Execution
     query_id                   execution_id
     │                           │
     ├─ what to run              ├─ one attempt
     ├─ immutable                ├─ has FSM state
     ├─ cost_tier                ├─ has timing + result
     └─ survives restarts        └─ may succeed or fail
```

CLI implications:
- `query list` lists ValidatedQueries (what was asked)
- `query show <query-id>` shows the query definition + all its executions
- `query run <query-id>` creates a new Execution for an existing query
- `query run <query-id> --confirmed` overrides cost gate (via RunOptions)
- `execution show <execution-id>` shows one specific execution attempt
- `execution list --query <query-id>` lists all attempts for a query

#### What "Validated" Means Per Query Type

| Type | Validation step | What it checks |
|------|----------------|----------------|
| SQL | Parse + EXPLAIN + policy | Syntax, tables exist, cost estimated, read-only |
| API endpoint | Resolve + param check | Endpoint exists, required params present, auth configured |
| API SQL (Dune-style) | Parse + policy | Syntax valid, read-only (no EXPLAIN — remote engine) |
| File (DuckDB) | Parse + EXPLAIN | Same as SQL, DuckDB validates locally |

API queries get `cost_tier: "unknown"` by default since there is no
EXPLAIN plan. Endpoint config in `connector.yaml` can override this
(e.g., mark expensive endpoints). The auto-run convenience treats
`"unknown"` as `"low"` unless overridden by execution policy.

### What Already Exists Pointing This Direction

| Concept | Where | What it reaches for |
|---------|-------|-------------------|
| `ExpectedCardinality.ONE/MANY` | models/meta_query.py | SCALAR vs VECTOR |
| `ObservedCardinality` | models/meta_query.py | Runtime validation |
| `ResultShape` | models/orchestration.py | Expected vs observed contract |
| `ExecutionRequest` | execution/models.py | Typed immutable request |
| `ExecutionResult` | execution/models.py | Typed normalized response |
| `ExecutionState` FSM | execution/models.py | Stateful lifecycle |
| `ConfidenceVector` | models/orchestration.py | Provenance metadata |

### Implementation: Gateway Module (Not Separate Package)

```
packages/core/src/db_mcp/gateway/
├── __init__.py          # public API: create(), execute(), run(), introspect()
├── adapter.py           # ConnectorAdapter protocol + per-type adapters
├── request.py           # DataRequest, SQLQuery, EndpointQuery
├── query.py             # ValidatedQuery (immutable validated query)
└── response.py          # DataResponse, Cardinality
```

The gateway sits between connectors and tools:

```
  tools / bicp / cli
          │
  gateway.create(request)              ← validate, return ValidatedQuery
  gateway.execute(query_id, options)   ← run validated query, return ExecutionResult
  gateway.run(request, options)        ← convenience: create + execute
          │
   ┌──────┼──────┐
   ▼      ▼      ▼
 SQL    API    File              ← adapters (validate + execute per type)
   │      │      │
   ▼      ▼      ▼
 connectors/                     ← physical implementations
          │
 execution/engine.py             ← FSM + persistent store
```

### What This Kills

| Today | After |
|-------|-------|
| `_run_sql()` 605 lines | ~50-line dispatch through gateway |
| Duplicate policy checks in `_api_execute_sql` | Single policy check in adapter |
| BICP 33 direct connector calls | `gateway.execute()` + `gateway.introspect()` |
| 6× boilerplate in `database.py` | `gateway.introspect(connection, scope=tables)` |
| `inject_protocol` in data layer | Presentation concern stays in MCP server |
| `tasks/store.py` parallel FSM | Dead — `execution/` is the only FSM |

### What Doesn't Fit

- **API mutations** (POST/PUT/PATCH/DELETE) — side effects, not retrieval
- **API endpoint discovery** — introspection, not queries
- **Streaming/pagination** — needs cursor support (future extension)

---

## Proposed Package Structure

### Overview

```
packages/
  models/        # Pure types                    (~1,400 lines)
  core/          # Services + layers             (~28,000 lines)
  mcp-server/    # MCP protocol adapter          (~2,500 lines)
  cli/           # Click CLI app                 (~3,500 lines)
  ui/            # Next.js (unchanged)
```

Dependency graph (all arrows point down):

```
packages/models/
    ▲
packages/core/
    ▲         ▲         ▲
packages/     packages/  packages/ui/
mcp-server/   cli/       (BICP stays in core)
```

### Core Package (Lean)

```
packages/core/src/db_mcp/
│
│  ── NEW: Typed Data Facade ──────────────────────────
├── gateway/
│   ├── __init__.py           # execute(), introspect()
│   ├── adapter.py            # ConnectorAdapter + SQL/API/File adapters
│   ├── request.py            # DataRequest, SQLQuery, EndpointQuery
│   └── response.py           # DataResponse, Cardinality
│
│  ── NEW: Extracted Business Logic ────────────────────
├── services/
│   ├── query.py              # validate + run + poll (from generation.py)
│   ├── schema.py             # list/describe tables (from database.py)
│   ├── context.py            # build schema/examples/rules context
│   ├── connection.py         # resolve/require connection (from utils.py)
│   └── onboarding.py         # discover + approve flow
│
│  ── Data Retrieval (unchanged) ───────────────────────
├── connectors/               # SQL, API, File physical connectors
├── connector_plugins/        # Metabase, Superset plugins
├── contracts/                # Connector contract validation
├── db/                       # SQLAlchemy connection + introspection
├── execution/                # FSM + SQLite store
├── validation/               # EXPLAIN, cost estimation, policy
├── capabilities.py
├── connector_compat.py
├── connector_templates.py
├── dialect.py
│
│  ── Knowledge (unchanged) ────────────────────────────
├── onboarding/               # Schema discovery + state
├── training/                 # Examples + feedback
├── metrics/                  # Metric/dimension store + mining
├── vault/                    # Directory structure + migration
├── gaps/                     # Knowledge gap detection
├── semantic/                 # Semantic core loader
├── collab/                   # Git-based collaboration
├── planner/                  # Meta-query planning + resolution
├── business_rules.py         # Rule parsing
│
│  ── Bridge ────────────────────────────────────────────
├── orchestrator/             # Intent → plan → SQL → execute
│
│  ── Observability ─────────────────────────────────────
├── traces.py                 # OTel span exporter
├── console/                  # Trace viewer
├── insights/                 # Trace-derived pattern detection
│
│  ── Infrastructure ────────────────────────────────────
├── config.py                 # Pydantic settings
├── registry.py               # Connection discovery + caching
├── git_utils.py              # Dulwich git operations
├── migrations/               # Data migration scripts
│
│  ── Sandbox ───────────────────────────────────────────
├── exec_runtime.py           # Container sandbox (Podman/Docker)
├── code_runtime/             # In-process Python sandbox
│
│  ── Other ─────────────────────────────────────────────
├── insider/                  # Background vault quality agent
├── agents.py                 # MCP client detection (Claude, Cursor, etc.)
├── bicp/                     # BICP agent (UI backend, consumes services/)
├── ui_server.py              # FastAPI serving UI + BICP endpoint
├── benchmark/                # Standalone benchmark harness
├── importer/                 # Bootstrap semantics from benchmarks
└── playground.py             # Demo connection installer
```

### MCP Server Package (Thin)

```
packages/mcp-server/src/db_mcp_server/
├── server.py                 # FastMCP setup, lifespan, mode dispatch
├── instructions.py           # 5 instruction templates (DETAILED, SHELL, etc.)
├── resources.py              # MCP resources (ground-rules, sql-rules, etc.)
├── protocol.py               # inject_protocol (MCP presentation concern)
├── tool_catalog.py           # Tool introspection + SDK generation
└── tools/                    # Thin wrappers (5-15 lines each)
    ├── database.py           #   → core.services.schema
    ├── generation.py         #   → core.services.query
    ├── onboarding.py         #   → core.services.onboarding
    ├── training.py           #   → core.knowledge.training
    ├── metrics.py            #   → core.knowledge.metrics
    ├── gaps.py               #   → core.knowledge.gaps
    ├── domain.py             #   → core.knowledge.onboarding
    ├── shell.py              #   vault bash access
    ├── api.py                #   → core.gateway
    ├── daemon.py             #   → core.services.context + query
    ├── exec.py               #   → core.sandbox
    └── code.py               #   → core.sandbox
```

### CLI Package (Thin)

```
packages/cli/src/db_mcp_cli/
├── main.py                   # Click group
├── utils.py                  # Rich console helpers
└── commands/
    ├── serve.py              # starts mcp-server
    ├── init.py               # → core.services.onboarding
    ├── discover.py           # → core.services.schema
    ├── collab.py             # → core.knowledge.collab
    ├── git.py                # → core.git_utils
    ├── agents.py             # → core.agents
    ├── traces.py             # → core.traces
    ├── runtime.py            # → core.sandbox
    ├── services.py           # daemon management
    ├── connector.py          # → core.connectors
    └── insider.py            # → core.insider
```

### What Each Package Depends On

| Package | Depends on | External deps |
|---------|-----------|---------------|
| `models` | nothing | pydantic |
| `core` | models | sqlalchemy, sqlglot, pyyaml, dulwich, duckdb, pydantic-ai, opentelemetry, bicp-agent |
| `mcp-server` | core, models | fastmcp |
| `cli` | core, models | click, rich |
| `ui` | nothing (talks HTTP) | next.js, tailwind |

---

## Layer Independence & Separate Shipping

### Current State

Knowledge and data retrieval modules have **zero cross-imports** today:

```
Knowledge Layer                    Data Retrieval Layer
───────────────                    ────────────────────
onboarding/                        connectors/
training/                          connector_plugins/
metrics/                           db/
vault/                             execution/
gaps/                              validation/
semantic/                          capabilities.py
collab/                            contracts/
planner/                           connector_compat.py
business_rules.py                  connector_templates.py
                                   dialect.py

External deps:                     External deps:
  pydantic, yaml, sqlglot            sqlalchemy, requests, duckdb
  dulwich (collab only)              pydantic, yaml
```

### Remaining Coupling: `get_settings()`

Five knowledge files and two data files call `get_settings()` for path
resolution. Each already accepts `connection_path` as an optional parameter:

| Module | Layer | Why it calls `get_settings()` |
|--------|-------|-------------------------------|
| `onboarding/state.py` | Knowledge | Find connection directory |
| `onboarding/ignore.py` | Knowledge | Find connection directory |
| `metrics/store.py` | Knowledge | Find `metrics/catalog.yaml` |
| `semantic/core_loader.py` | Knowledge | Find `business_rules.yaml` |
| `vault/migrate.py` | Knowledge | Find connection directory |
| `connectors/__init__.py` | Data | Find `connector.yaml` |
| `db/connection.py` | Data | Get `DATABASE_URL` fallback |

**Fix:** Make `connection_path` required (no default) in all these functions.
Remove `get_settings()` fallback. Callers in services/tools/CLI pass the
resolved path from the registry. This is a ~20-line change per file.

### Target Package Structure

```
packages/
  models/              ← pure types, no deps
      ▲       ▲
      │       │
  knowledge/  data/    ← independently shippable, no mutual deps
      ▲       ▲
      │       │
  core/                ← services, orchestrator, config, registry
      ▲     ▲     ▲
      │     │     │
  mcp-server/ cli/ ui/
```

**`packages/knowledge/`** — depends only on `models`, `pyyaml`, `sqlglot`,
`dulwich`:

```
packages/knowledge/src/db_mcp_knowledge/
├── onboarding/          # schema discovery state + store
├── training/            # examples + feedback
├── metrics/             # metric/dimension store + mining
├── vault/               # directory structure + migration
├── gaps/                # knowledge gap detection
├── semantic/            # semantic core loader
├── collab/              # git-based collaboration
├── planner/             # meta-query planning + resolution
├── business_rules.py    # rule parsing
└── insights/            # trace-derived pattern detection
```

**`packages/data/`** — depends only on `models`, `sqlalchemy`, `requests`,
`duckdb`, `pyyaml` (connectors read `connector.yaml`):

```
packages/data/src/db_mcp_data/
├── connectors/          # SQL, API, File physical connectors
├── connector_plugins/   # Metabase, Superset
├── contracts/           # Connector contract validation
├── db/                  # SQLAlchemy connection + introspection
├── execution/           # FSM + SQLite store
├── validation/          # EXPLAIN, cost estimation, policy
├── gateway/             # Typed DataRequest/DataResponse facade
├── capabilities.py
├── connector_compat.py
├── connector_templates.py
└── dialect.py
```

### Use Cases This Enables

| Scenario | Package(s) | Example |
|----------|-----------|----------|
| Knowledge-only | `knowledge` | Vault curator edits examples, metrics, rules — no DB credentials |
| Data-only | `data` | Ops tool connects to DBs, runs SQL, introspects — no semantic layer |
| Embedded knowledge | `knowledge` | External tool reads metric definitions or business rules |
| Embedded data gateway | `data` | External tool runs typed queries across SQL/API/File sources |
| Full product | `core` + all | Everything, as today |

### Verification Criteria

The split is valid when:
1. `packages/knowledge/` can be installed and all its tests pass without
   `sqlalchemy`, `requests`, or `duckdb` in the environment.
2. `packages/data/` can be installed and all its tests pass without
   `dulwich`, `sqlglot` (beyond what pydantic needs), or any knowledge
   module in the import path.
3. Neither package imports `db_mcp.config`, `db_mcp.registry`, or any
   module from the other package.

### CLI-Only Usage (No MCP Server Required)

A direct consequence of DG-2 is that both layers work as plain Python
libraries callable from any frontend. After the split, every operation
available through MCP tools is also available as a CLI command or a
direct function call — no server process needed.

CLI commands follow a **noun-verb** pattern: `db-mcp <layer> <resource> <action>`.
This makes commands discoverable (`db-mcp knowledge metrics --help` lists
all metric operations) and mirrors the library package structure.

#### Knowledge CLI

```
db-mcp knowledge -c prod metrics list
db-mcp knowledge -c prod metrics add --name "revenue" --sql "SELECT ..."
db-mcp knowledge -c prod metrics remove revenue
db-mcp knowledge -c prod metrics discover

db-mcp knowledge -c prod examples list
db-mcp knowledge -c prod examples search --grep "revenue"
db-mcp knowledge -c prod examples add --intent "..." --sql "..."

db-mcp knowledge -c prod rules list
db-mcp knowledge -c prod rules add --rule "1 GB = 1073741824 bytes"

db-mcp knowledge -c prod schema show
db-mcp knowledge -c prod schema export --format yaml

db-mcp knowledge -c prod gaps list
db-mcp knowledge -c prod gaps dismiss <id>

db-mcp knowledge -c prod domain show

db-mcp knowledge -c prod collab pull
db-mcp knowledge -c prod collab push
db-mcp knowledge -c prod collab status

db-mcp knowledge -c prod export --format yaml
```

#### Data CLI (Two-Step Query)

The data CLI exposes the two-step query lifecycle. SQL, API endpoint,
and file queries all use the same `query` resource:

```
# Step 1: Create (validate, get query ID)
$ db-mcp data -c prod query create "SELECT count(*) FROM orders"
Query q-3f8a created (sql, cost: low)

$ db-mcp data -c metabase query create --endpoint dashboards --param status=active
Query q-7b2c created (endpoint, cost: unknown)

# Step 2: Execute
$ db-mcp data query run q-3f8a
$ db-mcp data query run q-7b2c --export csv > results.csv
$ db-mcp data query run q-7b2c --confirmed      # override cost gate

# Convenience: one-shot (create + auto-run if cost allows)
$ db-mcp data -c prod query "SELECT count(*) FROM orders"

# Query history
$ db-mcp data -c prod query list --last 10
$ db-mcp data query show q-3f8a

# Schema introspection
$ db-mcp data -c prod schema catalogs
$ db-mcp data -c prod schema schemas
$ db-mcp data -c prod schema tables
$ db-mcp data -c prod schema describe orders
$ db-mcp data -c prod schema sample orders --limit 5

# Schema introspection includes connection test
$ db-mcp data -c prod test
```

The same `query create` + `query run` pattern works for all connector
types. The connection's type determines validation behavior, but the
lifecycle is identical.

Query identity and execution identity are separate: `query show q-3f8a`
shows the validated query definition and all its execution attempts.
`query run q-3f8a` creates a new execution for the same query.

**Note:** Connection management (`connectors list`, `connectors show`)
is infrastructure, not data retrieval. It appears under the top-level
`db-mcp` group, not under `db-mcp data`. See the full CLI tree below.

#### Bridge Commands (Require Both Layers)

```
db-mcp discover -c prod                         # Bridge 2: D→K
db-mcp ask "revenue by region" -c prod           # Bridge 1: K→LLM→D
db-mcp intent "daily active users" -c prod       # Bridge 3: K→D
```

#### Library API

Each CLI command is a thin Click wrapper over a library function.
The three concepts (DataRequest, ValidatedQuery, Execution) map directly:

```python
# Step 1: Create → ValidatedQuery
vq = gateway.create(DataRequest(connection="prod", query=SQLQuery(sql="...")))
# vq.query_id = "q-3f8a", vq.cost_tier = "low", vq.validated_at = ...

# Step 2: Execute → ExecutionResult (new Execution attempt)
result = gateway.execute(vq.query_id)
# result.execution_id = "ex-001", result.query_id = "q-3f8a"
# result.state = SUCCEEDED, result.records = [...], result.duration_ms = 42

# Re-run same query → new Execution, same ValidatedQuery
result2 = gateway.execute(vq.query_id)
# result2.execution_id = "ex-002", result2.query_id = "q-3f8a"

# Override cost gate for a specific execution (RunOptions)
result3 = gateway.execute(vq.query_id, options=RunOptions(confirmed=True))

# One-step convenience (creates ValidatedQuery internally)
result = gateway.run(DataRequest(connection="prod", query=SQLQuery(sql="...")))

# API endpoint query — same three concepts
vq = gateway.create(DataRequest(
    connection="metabase",
    query=EndpointQuery(endpoint="dashboards", params={"status": "active"}),
))
result = gateway.execute(vq.query_id)
```

This means the MCP server is one possible frontend, not a prerequisite.
Users can script against the libraries directly, use them in notebooks,
or build entirely different UIs without any MCP dependency.

#### Full CLI Tree

```
db-mcp
├── knowledge                        # Knowledge layer
│   ├── -c, --connection             # Global: connection name or path
│   ├── metrics
│   │   ├── list
│   │   ├── add
│   │   ├── remove
│   │   └── discover
│   ├── dimensions
│   │   ├── list
│   │   └── add
│   ├── examples
│   │   ├── list
│   │   ├── search --grep "..."
│   │   └── add
│   ├── rules
│   │   ├── list
│   │   └── add --rule "..."
│   ├── schema
│   │   ├── show
│   │   └── export --format yaml|md
│   ├── gaps
│   │   ├── list
│   │   └── dismiss <id>
│   ├── domain
│   │   └── show
│   ├── collab
│   │   ├── pull
│   │   ├── push
│   │   └── status
│   └── export --format yaml
│
├── data                             # Data retrieval layer
│   ├── -c, --connection             # Global: connection name or path
│   ├── query
│   │   ├── create <sql|--endpoint>   # Validate, return query_id
│   │   ├── run <query-id>           # New execution for validated query
│   │   │   ├── --confirmed          # Override cost gate (RunOptions)
│   │   │   └── --export csv|json    # Stream results to file
│   │   ├── list                     # List ValidatedQueries
│   │   ├── show <query-id>          # Query definition + all executions
│   │   └── (bare: create + auto-run) # db-mcp data -c prod query "SQL"
│   ├── execution
│   │   ├── show <execution-id>      # One specific execution attempt
│   │   └── list --query <query-id>  # All attempts for a query
│   ├── schema
│   │   ├── catalogs
│   │   ├── schemas
│   │   ├── tables
│   │   ├── describe <table>
│   │   └── sample <table> --limit N
│   └── test                         # Test connection
│
├── connections                       # Infrastructure (not layer-specific)
│   ├── list                         # List configured connections
│   ├── show <name>                  # Show connector config + status
│   └── test <name>                  # Test connectivity
│
├── discover -c <conn>               # Bridge: D→K
├── ask "question" -c <conn>         # Bridge: K→LLM→D
├── intent "metric query" -c <conn>  # Bridge: K→D
│
├── serve                            # Start MCP server
├── ui                               # Start UI server
├── init                             # Interactive setup wizard
└── agents                           # Register with Claude Desktop, etc.
```

**API stability note (DG-7):** The CLI commands and library functions shown
above are illustrative of the intended design. They do not constitute a
stable public API until Phase 6 is complete. Until then, function
signatures and CLI flags may change without deprecation.

---

## Migration Path

### Phase 1: Services Layer (No Package Split)

Extract business logic from `tools/` and `bicp/agent.py` into `services/`
within the existing core package. All three entry points call services.

**Key extractions:**
- `services/query.py` ← from `tools/generation.py` (`_run_sql`, `_validate_sql`)
- `services/schema.py` ← from `tools/database.py` (6 introspection functions)
- `services/connection.py` ← from `tools/utils.py` (`resolve_connection`, etc.)
- `services/context.py` ← from `tools/generation.py` (`_build_*_context`)
- `services/onboarding.py` ← from `tools/onboarding.py` (discovery + approval)

**Validation:** BICP agent methods shrink to thin wrappers over services.
`_run_sql()` shrinks dramatically. No package boundary changes.

### Phase 2: Gateway Module

Introduce `gateway/` with typed `DataRequest`/`DataResponse`. Adapt
`services/query.py` to use gateway instead of direct connector calls.

**Key changes:**
- Gateway adapters for SQL, API, File connectors
- `services/query.py` calls `gateway.execute()` instead of connector methods
- Kill `tasks/store.py` — `execution/` is the only FSM
- Remove `inject_protocol` from data paths (move to MCP-only)

**Validation:** `_run_sql` equivalent is now ~50 lines. All connector
dispatch is in adapters. Cross-connection queries become possible.

### Phase 3: Entry-Point Extraction

Once services and gateway are stable, extract MCP server and CLI into
separate packages.

**Key changes:**
- Move `server.py` + `tools/` → `packages/mcp-server/`
- Move `cli/` → `packages/cli/`
- Tools become thin wrappers over `core.services.*`
- CLI commands become thin wrappers over `core.services.*`
- `inject_protocol` lives only in mcp-server

**Validation:** Core has no MCP or Click dependencies. MCP server and CLI
are independently deployable.

### Phase 4: BICP Cleanup

With services layer in place, refactor BICP agent to consume services
instead of going direct to stores.

**Key changes:**
- 48 `_handle_*` methods become thin wrappers over services
- Consider replacing custom JSON-RPC handlers with FastAPI REST endpoints
- Keep BICP protocol only for query lifecycle (if retained at all)

**Validation:** BICP agent shrinks from 4,648 lines to ~500–800.

### Phase 5: Eliminate `get_settings()` From Layers

Remove the `get_settings()` fallback from all knowledge and data retrieval
modules. Make `connection_path: Path` a required parameter.

**Files to change** (7 total, ~20 lines each):
- Knowledge: `onboarding/state.py`, `onboarding/ignore.py`, `metrics/store.py`,
  `semantic/core_loader.py`, `vault/migrate.py`
- Data: `connectors/__init__.py`, `db/connection.py`

**Validation:** `grep -r 'from db_mcp.config' packages/knowledge/ packages/data/`
returns nothing. Both layers are config-free.

### Phase 6: Layer Extraction (DG-2)

Extract knowledge and data retrieval into independent packages.

**Key changes:**
- Move knowledge modules → `packages/knowledge/`
- Move data retrieval modules → `packages/data/`
- Core depends on both; neither depends on core or each other
- Update all imports (mechanical, aided by tooling)

**Verification (as defined in DG-2):**
1. `packages/knowledge/` installs and tests pass without `sqlalchemy`,
   `requests`, or `duckdb`.
2. `packages/data/` installs and tests pass without `dulwich`, `sqlglot`,
   or any knowledge module.
3. Neither package imports `db_mcp.config`, `db_mcp.registry`, or the
   other package.

### Phase Summary

| Phase | What | Enables | Breaks API? |
|-------|------|---------|-------------|
| 1 | Services layer | Shared business logic | No |
| 2 | Gateway module | Typed data retrieval | No |
| 3 | Entry-point extraction | MCP + CLI as separate packages | No |
| 4 | BICP cleanup | Thin UI backend | UI protocol may change |
| 5 | Remove `get_settings()` | Config-free layers | No (callers adapt) |
| 6 | Layer extraction | Knowledge + Data as separate packages (DG-2) | Import paths change |

### Step-by-Step Implementation Plan

Each item is one commit. Tests come first (TDD per AGENTS.md). Items within
a phase can be reordered; phases must be sequential.

#### Phase 1: Services Layer

```
1.01  Create services/ directory with __init__.py
1.02  Extract resolve_connection / require_connection → services/connection.py
      - Write tests for services/connection.py
      - Move logic from tools/utils.py
      - Update tools/utils.py to re-export from services (backward compat)
1.03  Extract _build_schema_context, _build_examples_context,
      _build_rules_context → services/context.py
      - Write tests for context building
      - Move from tools/generation.py
      - Update tools/generation.py to import from services
1.04  Extract schema introspection → services/schema.py
      - Write tests for list_tables, describe_table, etc.
      - Move logic from tools/database.py (eliminate 6× boilerplate)
      - Update tools/database.py to thin wrappers
1.05  Extract validate_sql logic → services/query.py
      - Write tests for SQL validation service
      - Move from tools/generation.py _validate_sql
      - Keep tools/generation.py _validate_sql as thin wrapper
1.06  Extract run_sql logic → services/query.py
      - Write tests for SQL execution service (mock connectors)
      - Move from tools/generation.py _run_sql
      - Keep tools/generation.py _run_sql as thin wrapper
1.07  Extract onboarding discovery → services/onboarding.py
      - Write tests for schema discovery service
      - Move from tools/onboarding.py
      - Keep tool as thin wrapper
1.08  Refactor BICP agent: connection methods → services/connection.py
      - Write tests for BICP connection handlers using services
      - Replace direct store access with service calls
1.09  Refactor BICP agent: schema methods → services/schema.py
      - Replace direct connector calls with service calls
1.10  Refactor BICP agent: context/knowledge methods → services
      - Replace direct vault reads with service calls
1.11  Delete duplicate _report_progress (keep one in services/,
      import from both tools/generation.py and tools/onboarding.py)
1.12  Delete tools/utils.py resolve_connection (now re-exported from services)
      Verify: all tools import from services/connection.py
```

#### Phase 2: Gateway Module

```
2.01  Add DataRequest, DataResponse, Cardinality types to packages/models/
      - Write tests for type construction and serialization
2.02  Create gateway/ directory with __init__.py
2.03  Define ConnectorAdapter protocol in gateway/adapter.py
      - Write tests for protocol compliance
2.04  Implement SQLAdapter
      - Write tests with mock SQLConnector
      - Adapter normalizes list[dict] → DataResponse
2.05  Implement APIAdapter
      - Write tests with mock APIConnector
      - Handle both sync and async API responses
2.06  Implement FileAdapter
      - Write tests with mock FileConnector
2.07  Implement gateway.execute() dispatcher
      - Write tests: routes DataRequest to correct adapter by connection type
2.08  Implement gateway.introspect() for schema discovery
      - Write tests for list_catalogs/schemas/tables/columns
2.09  Wire services/query.py to use gateway.execute()
      - Replace direct connector calls
      - Verify all existing query tests still pass
2.10  Wire services/schema.py to use gateway.introspect()
      - Replace direct get_connector() calls
      - Verify all existing schema tests still pass
2.11  Wire services/onboarding.py to use gateway.introspect()
      - Replace direct connector introspection calls
2.12  Wire orchestrator/engine.py to use services/query.py
      - Replace direct _run_sql / _validate_sql imports
2.13  Delete tasks/store.py
      - Migrate any remaining callers to execution/
      - Verify no imports remain
2.14  Move inject_protocol out of tools/shell.py
      - Create mcp-specific protocol.py (still in core for now)
      - Remove inject_protocol from services/ and gateway/ code paths
```

#### Phase 2 Known Gaps

These items were identified during Phase 2 review and are explicitly deferred:

**`services/query.py` still owns the query lifecycle (deferred to Phase 3)**

`validate_sql` registers queries in `QueryStore` itself; `run_sql` looks them up
and drives the `ExecutionEngine` FSM directly. Moving this to route through
`gateway.create()` / `gateway.execute()` requires the gateway to absorb:
protocol-ack gating, SQL permission validation, EXPLAIN cost estimation, write
confirmation policy, and async background execution (~600 lines of policy logic).
This is Phase 3 work — when tools become thin wrappers, the services layer can
be simplified to route through the gateway for all execution.

**`list_schemas_with_counts` and `validate_link` bypass the gateway (deferred to Phase 4)**

Both functions in `services/schema.py` use direct connector calls. They are
multi-step operations (fan-out across catalogs → schemas → tables, or cross-
referencing tables + columns) with no single gateway scope equivalent. Deferring
to Phase 4 (BICP cleanup) when the full connection resolution chain consolidates.
See inline comments in `services/schema.py` for the per-function rationale.

**`sample_table` is a permanent exception**

`sample_table` calls `connector.get_table_sample()` directly and is intentionally
not routed through the gateway. Row sampling is data retrieval, not schema
introspection; `get_table_sample()` has no gateway introspect scope equivalent.
This is documented in the `sample_table` docstring.

---

#### Phase 3: Entry-Point Extraction (MCP + CLI)

```
3.01  Create packages/mcp-server/ with pyproject.toml
      - Depends on db-mcp (core) and db-mcp-models
3.02  Move server.py → packages/mcp-server/
3.03  Move instruction templates → mcp-server/instructions.py
3.04  Move inject_protocol → mcp-server/protocol.py
3.05  Move tool_catalog.py → mcp-server/
3.06  Create thin MCP tool wrappers in mcp-server/tools/
      - Each tool: 5–15 lines calling core.services.*
      - One commit per tool group (database, generation, training,
        onboarding, metrics, gaps, domain, api, shell, daemon, exec, code)
3.07  Verify: core has no fastmcp import
      - grep -r 'from fastmcp\|import fastmcp' packages/core/
3.08  Create packages/cli/ with pyproject.toml
      - Depends on db-mcp (core) and db-mcp-models
3.09  Move cli/ → packages/cli/
3.10  Verify: core has no click or rich import
      - grep -r 'from click\|import click\|from rich\|import rich' packages/core/
3.11  Update pyproject.toml entry points for both packages
3.12  Verify: all existing tests pass from new package locations
```

#### Phase 4: BICP Cleanup

```
4.01  Audit BICP agent: list all _handle_* methods and map each to
      a service function or identify as protocol-only
4.02  Replace connection CRUD handlers with service calls (13 methods)
4.03  Replace context/vault handlers with service calls (7 methods)
4.04  Replace metrics handlers with service calls (6 methods)
4.05  Replace trace/insight handlers with service calls (5 methods)
4.06  Replace git handlers with service calls (3 methods)
4.07  Replace agent config handlers with service calls (5 methods)
4.08  Replace schema handlers with gateway.introspect() calls (5 methods)
4.09  Evaluate: convert remaining handlers to FastAPI REST endpoints
4.10  Delete dead code: any BICP handler that duplicates a service
4.11  Verify: bicp/agent.py is under 800 lines
```

#### Phase 5: Eliminate `get_settings()` From Layers

```
5.01  onboarding/state.py: make connection_path required
      - Update all callers to pass explicit path
5.02  onboarding/ignore.py: make connection_path required
5.03  metrics/store.py: make connection_path required
5.04  semantic/core_loader.py: make connection_path required
5.05  vault/migrate.py: make connection_path required
5.06  connectors/__init__.py: make connection_path required
5.07  db/connection.py: remove get_settings() fallback for database_url
5.08  Verify: grep -r 'from db_mcp.config' finds no hits in
      onboarding/ training/ metrics/ vault/ gaps/ semantic/
      collab/ planner/ connectors/ db/ execution/ validation/
```

#### Phase 6: Layer Extraction

```
6.01  Create packages/knowledge/ with pyproject.toml
      - deps: db-mcp-models, pyyaml, sqlglot, dulwich
6.02  Move onboarding/ → packages/knowledge/
6.03  Move training/ → packages/knowledge/
6.04  Move metrics/ → packages/knowledge/
6.05  Move vault/ → packages/knowledge/
6.06  Move gaps/ → packages/knowledge/
6.07  Move semantic/ → packages/knowledge/
6.08  Move collab/ → packages/knowledge/
6.09  Move planner/ → packages/knowledge/
6.10  Move business_rules.py → packages/knowledge/
6.11  Move insights/ → packages/knowledge/
6.12  Update all imports in core, mcp-server, cli
6.13  Verify: knowledge tests pass without sqlalchemy/requests/duckdb
6.14  Create packages/data/ with pyproject.toml
      - deps: db-mcp-models, sqlalchemy, requests, duckdb, pyyaml (connector.yaml)
6.15  Move connectors/ → packages/data/
6.16  Move connector_plugins/ → packages/data/
6.17  Move contracts/ → packages/data/
6.18  Move db/ → packages/data/
6.19  Move execution/ → packages/data/
6.20  Move validation/ → packages/data/
6.21  Move gateway/ → packages/data/
6.22  Move capabilities.py, connector_compat.py, connector_templates.py,
      dialect.py → packages/data/
6.23  Update all imports in core, mcp-server, cli
6.24  Verify: data tests pass without dulwich/sqlglot/knowledge modules
6.25  Verify: neither package imports db_mcp.config or db_mcp.registry
6.26  Add knowledge CLI commands to packages/cli/
6.27  Add data CLI commands to packages/cli/
6.28  Final: all tests green across all packages
```

---

## MCP Tool Audit

**Status:** Decided 2026-03-31

74 registered tools. Not all should survive. Groups with a ✅ verdict are
locked in; ⚠️ groups need a follow-up decision; 🔴 groups are scheduled for
removal.

### Tool Verdicts

| Group | Count | Verdict |
|-------|-------|---------|
| Core query (`run_sql`, `validate_sql`, `get_result`, `export_results`, `get_data`) | 5 | ✅ Keep — the product |
| Schema introspection (`list_catalogs/schemas/tables`, `describe_table`, `sample_table`) | 5 | ✅ Keep |
| Shell + protocol | 2 | ✅ Keep — vault access |
| API connector (`api_query`, `api_execute_sql`, `api_describe_endpoint`, `api_discover`, `api_mutate`) | 5 | ✅ Keep (`api_discover` and `api_mutate` could be full-profile only) |
| Metrics (`metrics_list/add/remove/approve/discover`, `metrics_bindings_*`) | 8 | ✅ Keep |
| Knowledge gaps (`get`/`dismiss`) | 2 | ✅ Keep |
| Training (`query_approve/feedback/add_rule/list_examples/list_rules/generate/status`) | 7 | ⚠️ Review — `query_generate` and `query_status` may be dead |
| Orchestrator (`answer_intent`) | 1 | ✅ Keep |
| Daemon mode (`prepare_task`, `execute_task`) | 2 | ✅ Keep (mode-specific) |
| Sandbox (`exec`, `code`) | 2 | ✅ Keep (mode-specific) |
| System (`ping`, `get_config`, `list_connections`, `search_tools`, `export_tool_sdk`) | 5 | ⚠️ `export_tool_sdk` and `search_tools` are niche |
| Onboarding (`mcp_setup_*` — 13 tools) | 13 | 🔴 Replace with onboarding skill + vault primitives (see below) |
| Domain (`mcp_domain_*` — 4 tools) | 4 | ⚠️ Could collapse to 2 (generate + approve) |
| Improvements (`mcp_list/suggest/approve_improvement`) | 3 | 🔴 Dead weight — backward-compat aliases for insights |
| Insights (`dismiss_insight`, `mark_insights_processed`) | 2 | ✅ Keep |
| Import (`import_instructions`, `import_examples`) | 2 | ⚠️ One-time migration — could be CLI-only |
| Test/debug (`detect_dialect`, `test_elicitation`, `test_sampling`, `get_dialect_rules`, `get_connection_dialect`) | 5 | 🔴 Debug tooling exposed as MCP tools |
| Connection health (`test_connection`) | 1 | ✅ Keep — needed by onboarding skill and UI; not debug tooling |

**Drop immediately (no phase dependency):**
- Improvements group (3): dead backward-compat aliases for insights tools
- Test/debug group (5): debug tooling — move to CLI only

**Caveat on "drop immediately":** safe only if MCP clients are internal.
If any external prompts, UI code, or third-party integrations reference these
tool names, do one release with profile-gating or no-op deprecation aliases
before hard removal.

**Drop as part of onboarding redesign:**
- Onboarding group (13): replaced by skill + vault primitives (see below)

---

### Onboarding: Skill + Primitives, Not 13 Tools

The 13 `mcp_setup_*` tools implement a server-side state machine
(`INIT → SCHEMA → DOMAIN`) that orchestrates what Claude can do itself using
the 5 existing introspection tools. The state machine belongs in a skill
prompt, not in server-side tools.

**What each tool actually is:**

| Tool | What it really does |
|------|---------------------|
| `mcp_setup_start` | `test_connection` + load ignore patterns |
| `mcp_setup_discover` (structure) | `list_catalogs` + `list_schemas` filtered by ignore patterns |
| `mcp_setup_discover` (tables) | `list_tables` + `describe_table` per schema (run in background) |
| `mcp_setup_discover_status` | Poll async background task |
| `mcp_setup_next` | `describe_table` + `sample_table` for next pending table |
| `mcp_setup_approve` | Write description to `schema/descriptions.yaml` |
| `mcp_setup_skip` | Mark table skipped in state |
| `mcp_setup_bulk_approve` | Batch-write descriptions |
| `mcp_setup_import_descriptions` | Parse + write pre-existing descriptions |
| `mcp_setup_add/remove_ignore_pattern` | Read/write `ignore.yaml` |
| `mcp_setup_import_ignore_patterns` | Read/write `ignore.yaml` from file |
| `mcp_setup_status` | Read state machine phase/progress |
| `mcp_setup_reset` | Delete state + schema files |

The background discovery task (`_discover_tables_background` + status polling)
exists because iterating all tables in a single MCP call risks timeouts. The
skill solves this naturally by chunking per schema — Claude iterates
schema-by-schema in its context window; no async job needed.

**After redesign:**

| Before | After |
|--------|-------|
| 13 `mcp_setup_*` tools | 0 new tools (existing introspection + `vault_write` + `vault_append`) |
| Server-side state machine | Claude's context window |
| Background task + polling | Schema-by-schema chunking in the skill |
| 3 ignore-pattern tools | `vault_write` for full rewrite; `vault_append` for markdown |

#### Resume semantics after interruption

Removing the server-side state machine does not remove the need for
resumability — it moves ownership to the skill and the vault files.

The skill's resume contract:

1. **Detect prior run** — on entry, call
   `shell("cat schema/descriptions.yaml")`. If the file exists, onboarding
   was previously started. Parse `status` fields to determine progress.

2. **Pending tables** — any table with `status: pending` was not yet
   described. The skill resumes from the first pending table in document
   order. No separate state file is needed.

3. **Skipped tables** — tables with `status: skipped` are left as-is unless
   the user explicitly asks to revisit. The skill surfaces the count at
   resume time: *"N tables were previously skipped — review them now?"*

4. **Partial schema across many schemas** — for large databases, the skill
   checkpoints after each schema by writing `descriptions.yaml` before
   moving to the next. An interruption mid-schema leaves the partial file;
   on resume the skill counts pending tables in the partially-written file
   and continues from there.

5. **Ignore patterns** — `ignore.yaml` is written before discovery starts
   and is not modified during table description. Safe to interrupt at any
   point.

6. **Hard reset** — the skill's default reset path is `vault_write` with an
   empty `SchemaDescriptions` scaffold (all tables set back to
   `status: pending`). This is safe, reversible, and validated. The skill
   must never suggest `shell("rm ...")` to the user. Direct file deletion
   is an operator escape hatch, available via CLI or shell only for cases
   where the file itself is corrupt or needs to be rebuilt from scratch
   outside a session.

---

### Vault Write Primitives

The `shell` tool cannot safely handle structured YAML files — it blocks `>`
overwrites and would produce fragile raw YAML without schema validation.
`vault_write` and `vault_append` are the authoritative write path for all
vault content, including markdown. The `shell >>` append remains available
as a low-level escape hatch (e.g., for ad-hoc annotations) but is not part
of the normal skill workflow. Two new tools replace all `save_*` store
functions as MCP primitives.

#### `vault_write(connection, path, content)`

Atomic full-file rewrite with document-driven validation. Used whenever Claude
reads a file, modifies it in context, and writes it back.

```
vault_write("prod", "schema/descriptions.yaml", updated_yaml)
vault_write("prod", "metrics/catalog.yaml",     updated_yaml)
vault_write("prod", "knowledge_gaps.yaml",      updated_yaml)
vault_write("prod", "instructions/business_rules.yaml", updated_yaml)
vault_write("prod", "ignore.yaml",              updated_yaml)
vault_write("prod", "domain/model.md",          markdown)   # whitelisted markdown path
```

#### `vault_append(connection, path, content)`

Used for **one-file-per-record creation** and **markdown block appends**.
Behaviour differs by target type:

| Target | File exists? | Behaviour |
|--------|--------------|-----------|
| `examples/*.yaml` (YAML record) | No | Create file, validate against `QueryExample` |
| `examples/*.yaml` (YAML record) | Yes | **Reject** — duplicate path is a caller error; the skill must generate a fresh UUID |
| `learnings/*.md` (markdown) | No | Create file, write content |
| `learnings/*.md` (markdown) | Yes | Append content to existing file |

**Atomicity:** YAML record creation is atomic (write to a temp file in the
same directory, then rename). Markdown append is a non-atomic `open("a")`
write — acceptable because markdown files are human-readable logs where a
partial final line is recoverable, not machine-parsed structures.

```
vault_append("prod", "examples/abc123.yaml",  example_yaml)        # create; error if exists
vault_append("prod", "learnings/patterns.md", "\n## Pattern\n...") # append; create if absent
```

#### Document-driven validation

Neither tool takes a `schema=` parameter. Validation is driven entirely by
the file path via a registry in `core/vault/registry.py`:

```python
# Exact paths → validated against Pydantic model
VAULT_SCHEMAS: dict[str, type[BaseModel]] = {
    "schema/descriptions.yaml":         SchemaDescriptions,
    "metrics/catalog.yaml":             MetricsCatalog,
    "metrics/dimensions.yaml":          DimensionsCatalog,
    "metrics/bindings.yaml":            MetricBindingsCatalog,
    "knowledge_gaps.yaml":              KnowledgeGaps,
    "instructions/business_rules.yaml": PromptInstructions,
    "feedback_log.yaml":                FeedbackLog,
}

# Glob patterns → validated against Pydantic model
VAULT_SCHEMAS_GLOB: dict[str, type[BaseModel]] = {
    "examples/*.yaml": QueryExample,
}

# Whitelisted markdown paths → plain write, no schema validation
VAULT_MARKDOWN_PATHS: set[str] = {
    "domain/model.md",
    "instructions/sql_rules.md",
    "learnings/patterns.md",
    "learnings/schema_gotchas.md",
    "learnings/trace-analysis-patterns.md",
}
# Glob for vault_append markdown targets
VAULT_MARKDOWN_GLOB: set[str] = {
    "learnings/*.md",
}

# Any path not in VAULT_SCHEMAS, VAULT_SCHEMAS_GLOB, VAULT_MARKDOWN_PATHS,
# or VAULT_MARKDOWN_GLOB is REJECTED. vault_write/vault_append are not
# general file writers.
```

**Validation layers, in order:**

1. **Structural** — `ModelClass.model_validate(yaml.safe_load(content))`.
   Free from Pydantic. Catches missing required fields, wrong types, enum
   violations. Rejects the write before touching the file.

2. **SQL expressions** — SQL fields are annotated in the models with a
   lightweight metadata marker:

   ```python
   # packages/models/src/db_mcp_models/
   SqlExpr = Annotated[str, Field(json_schema_extra={"is_sql": True})]

   class Metric(BaseModel):
       sql: SqlExpr = ...

   class MetricDimensionBinding(BaseModel):
       projection_sql: SqlExpr = ...
       filter_sql:     SqlExpr | None = ...
       group_by_sql:   SqlExpr | None = ...
   ```

   `vault_write` walks the validated model's fields, finds `is_sql=True`,
   and runs sqlglot on each value. Invalid SQL syntax rejects the write.

**Package boundary:** `packages/models/` stays pure (Pydantic only, no
sqlglot dependency). The `SqlExpr` annotation is metadata only. Sqlglot
validation runs in core, where it already lives.

**Existing domain tools are not replaced.** `metrics_add`, `query_approve`,
`query_add_rule`, etc. remain for non-onboarding workflows — they carry
extra logic (duplicate detection, UUID generation, SQL validation
orchestration) that is valuable when Claude works with an already-onboarded
connection. `vault_write` and `vault_append` are lower-level primitives used
primarily by the onboarding skill.

---

## Open Questions

### 1. BICP: Keep, Replace, or Hybrid?

The UI talks exclusively over BICP JSON-RPC. Options:

| Option | Effort | Benefit |
|--------|--------|---------|
| **Keep BICP, thin it out** | Low | Minimal UI changes |
| **Replace with FastAPI REST** | Medium | Standard tooling, typed OpenAPI |
| **Hybrid**: REST for CRUD, BICP for query lifecycle | Medium | Best of both |

The hybrid approach is likely best — 43 custom handlers become REST endpoints,
5 query lifecycle methods stay as BICP (if streaming/notifications are needed).

### 2. Where Does the Orchestrator Live?

The orchestrator imports `_run_sql`/`_validate_sql` from tools today. After
restructuring, it would import from `services/query.py`. This is an internal
core dependency (services → gateway → connectors), which is clean.

But should it be a service itself? `services/intent.py` calling
`services/query.py`? Or stay as a separate `orchestrator/` module?

**Recommendation:** Keep `orchestrator/` separate — it's a bridge module
with distinct responsibilities (semantic planning + execution coordination).
It calls services, it doesn't become one.

### 3. Benchmark: Core or Separate Package?

The benchmark (2,586 lines) is self-contained with its own CLI entry point
(`db-mcp-benchmark`). It could be `packages/benchmark/`.

**Recommendation:** Defer. Low priority, no architectural impact.

### 4. Insider: Core or Service?

The insider (1,784 lines) is a background agent that reads traces and writes
vault reviews. It depends only on `onboarding/` from the knowledge layer.

**Recommendation:** Keep in core. It's a clean knowledge-layer producer.

### 5. Config Dependency

`connectors/__init__.py` and `db/connection.py` import `get_settings()` to
resolve default paths. This ties the data layer to application config.

**Resolution:** Gateway receives resolved `connection_path` from registry.
Connectors never call `get_settings()` directly. Registry is the exclusive
path resolver.

### 6. What Happens to `tools/` in Core?

After extracting business logic to `services/` and MCP wrappers to
`mcp-server/tools/`, the `tools/` directory in core would be empty or
contain only `tools/shell.py` (vault bash access).

**Options:**
- Delete `tools/` from core entirely
- Keep `tools/shell.py` as `services/shell.py` (it's really a service)

### 7. Static UI Assets

Currently `packages/core/src/db_mcp/static/` contains the Next.js build
output served by `ui_server.py`. After the split, `ui_server.py` stays in
core (it's the BICP endpoint host).

**Recommendation:** Keep as-is. The static export build step copies from
`packages/ui/` to core's static directory. This is a deployment concern,
not an architecture concern.

### 8. Mutations in Gateway?

API mutations (POST/PUT/PATCH/DELETE via `_api_mutate`) don't fit the
SCALAR/VECTOR data retrieval model. They're side effects.

**Options:**
- Gateway ignores mutations, they stay as direct connector calls
- Gateway has a separate `mutate()` method with `MutationResponse`

**Recommendation:** Keep mutations outside gateway initially. They're
only used by the API tools and aren't part of the query lifecycle.

---

## Appendix: Module Line Counts

### Entry Points / Servers (7,714 lines)

| Module | Lines |
|--------|-------|
| `bicp/agent.py` | 4,648 |
| `server.py` | 1,324 |
| `bicp/traces.py` | 1,229 |
| `ui_server.py` | 499 |

### MCP Tools (8,439 lines)

| Module | Lines |
|--------|-------|
| `tools/generation.py` | 2,220 |
| `tools/onboarding.py` | 1,881 |
| `tools/daemon_tasks.py` | 1,003 |
| `tools/training.py` | 656 |
| `tools/domain.py` | 556 |
| `tools/metrics.py` | 539 |
| `tools/shell.py` | 383 |
| `tools/database.py` | 301 |
| `tools/api.py` | 274 |
| `tools/utils.py` | 212 |
| `tools/exec.py` | 201 |
| `tools/gaps.py` | 113 |
| `tools/dialect.py` | 45 |
| `tools/code.py` | 36 |
| `tools/intent.py` | 18 |

### CLI (4,933 lines)

| Module | Lines |
|--------|-------|
| `cli/commands/core.py` | 923 |
| `cli/commands/collab.py` | 554 |
| `cli/init_flow.py` | 531 |
| `cli/commands/services.py` | 404 |
| `cli/connection.py` | 304 |
| `cli/commands/runtime_cmd.py` | 291 |
| `cli/git_ops.py` | 253 |
| `cli/discovery.py` | 222 |
| `cli/commands/agents_cmd.py` | 201 |
| `cli/utils.py` | 197 |
| `cli/commands/insider.py` | 195 |
| `cli/commands/discover_cmd.py` | 166 |
| `cli/commands/git_cmds.py` | 163 |
| `cli/__init__.py` | 135 |
| `cli/commands/traces.py` | 133 |
| `cli/agent_config.py` | 128 |
| `cli/commands/connector_cmd.py` | 85 |

### Data Retrieval (7,446 lines)

| Module | Lines |
|--------|-------|
| `connectors/api.py` | 1,914 |
| `connectors/api_discovery.py` | 912 |
| `validation/explain.py` | 708 |
| `exec_runtime.py` | 547 |
| `connectors/__init__.py` | 312 |
| `connectors/api_sql.py` | 307 |
| `execution/store.py` | 299 |
| `connectors/file.py` | 224 |
| `db/connection.py` | 220 |
| `db/introspection.py` | 193 |
| `execution/engine.py` | 186 |
| `connector_templates.py` | 171 |
| `execution/policy.py` | 168 |
| `capabilities.py` | 161 |
| `connectors/sql.py` | 140 |
| `contracts/connector_contracts.py` | 128 |
| `execution/models.py` | 83 |
| `connector_compat.py` | 55 |
| `dialect.py` | 73 |

### Knowledge (6,866 lines)

| Module | Lines |
|--------|-------|
| `metrics/mining.py` | 908 |
| `metrics/store.py` | 707 |
| `training/store.py` | 602 |
| `vault/migrate.py` | 597 |
| `vault/init.py` | 564 |
| `business_rules.py` | 138 |
| `onboarding/ignore.py` | 366 |
| `onboarding/state.py` | 325 |
| `onboarding/description_parser.py` | 323 |
| `onboarding/schema_store.py` | 297 |
| `planner/meta_query.py` | 161 |
| `planner/resolver.py` | 179 |
| `semantic/core_loader.py` | 82 |
| `collab/merge.py` | 227 |
| `collab/sync.py` | 223 |
| `collab/manifest.py` | 130 |
| `collab/github.py` | 111 |
| `collab/classify.py` | 94 |
| `collab/background.py` | 76 |
| `gaps/store.py` | 200 |
| `gaps/scanner.py` | 168 |

### Observability (1,730 lines)

| Module | Lines |
|--------|-------|
| `console/collector.py` | 436 |
| `console/http_exporter.py` | 174 |
| `console/instrument.py` | 115 |
| `console/server.py` | 312 |
| `insights/detector.py` | 415 |
| `traces.py` | 189 |

### Infrastructure (1,895 lines)

| Module | Lines |
|--------|-------|
| `git_utils.py` | 668 |
| `registry.py` | 277 |
| `config.py` | 315 |
| `migrations/` | 635 |
