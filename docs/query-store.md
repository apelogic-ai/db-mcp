# Query Template Store

**Status**: Conceptual
**Created**: 2026-02-04

## Overview

A generalized abstraction for saved, parameterized, cacheable queries across analytical backends. Today, each system — Dune, Metabase, Superset, Looker, Redash — has its own model for "stored queries." The differences are real but shallow: parameter syntax, sync-vs-async execution, caching strategy, and result pagination. The core concept is the same everywhere: a named SQL template with typed parameters, an execution model, and a result set.

This document defines a `QueryStore` protocol that normalizes these differences, allowing db-mcp to treat any analytical backend as a query template source — surfacing saved questions from Metabase, stored queries from Dune, or charts from Superset through a single interface.

**Relationship to Data Gateway**: The Query Store is a focused component within the broader [Semantic Data Gateway](data-gateway.md) vision. Where the gateway addresses multi-source federation, the Query Store addresses the narrower problem of *reusable query management* across backends.

---

## Problem Statement

Users have valuable queries scattered across analytical tools:

- **Dune**: Saved queries with `{{param}}` parameters, async execution, 90-day result caching
- **Metabase**: "Saved Questions" (Cards) with field-filter parameters, sync execution, TTL caching
- **Superset**: Charts + SQL Lab queries with Jinja parameters, Redis caching
- **Looker**: Looks + Explores with LookML-defined filters
- **Redash**: Queries with `{{param}}` parameters, async job polling

Today, db-mcp has no concept of "stored queries." Each interaction starts fresh — generate SQL, validate, execute. There is no way to:

1. Surface existing queries from connected BI tools
2. Save and reuse queries with parameterized variants
3. Leverage backend caching to avoid redundant computation
4. Present non-SQL users with fill-in-the-blank query interfaces

---

## Comparative Analysis

### How Each System Models Stored Queries

| Aspect | Dune | Metabase | Superset | Redash | Looker |
|--------|------|----------|----------|--------|--------|
| **Unit** | Saved Query | Card (Question) | Chart / SQL Lab | Query | Look / Explore |
| **ID** | Numeric | Numeric | Numeric | Numeric | Numeric |
| **Parameters** | `{{name}}` mustache | `{{name}}` + field filters | Jinja `{{ }}` | `{{name}}` | LookML filters |
| **Param types** | text, number, date, enum, list | text, number, date, category, field filter | text, number, date (Jinja) | text, number, date, enum, date-range | dimension filters |
| **Execution** | Async (execution_id + poll) | Sync (POST → results) | Sync or async | Async (job_id + poll) | Sync or async |
| **Caching** | Last execution (explicit refresh) | TTL (configurable per-question) | Redis TTL (chart-level) | Manual / scheduled refresh | Per-query TTL |
| **Result format** | `{result: {rows: [...]}}` | `{data: {rows: [...]}}` | `{data: [...]}` | `{query_result: {data: {rows: [...]}}}` | `[{...}, ...]` |
| **Pagination** | Offset-based | N/A (full result) | Offset-based | N/A (full result) | Offset-based |

### Convergence Points

Despite API differences, every system converges on the same five concepts:

1. **Query Template** — Named SQL with parameter placeholders and metadata
2. **Parameter Schema** — Typed inputs with defaults, constraints, and optional UI hints
3. **Execution Model** — Submit query, get results (sync or async, unified at the abstraction)
4. **Cache Semantics** — Freshness control (use cached, force refresh, max-age tolerance)
5. **Result Set** — Typed columns, row data, pagination, execution metadata

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       MCP Tools / UI                            │
│  list_templates()  execute_template()  get_latest_results()     │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      QueryStore Protocol                        │
│                                                                 │
│  Template CRUD        Execution         Results                 │
│  ─────────────        ─────────         ───────                 │
│  create()             execute()         get_results()           │
│  get()                get_status()      get_latest_results()    │
│  update()             cancel()                                  │
│  delete()                                                       │
│  list()                                                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  DuneQueryStore  │ │MetabaseQueryStore│ │ LocalQueryStore  │
│                  │ │                  │ │                  │
│ • Async execute  │ │ • Sync execute   │ │ • YAML-backed    │
│ • Poll for       │ │ • Field filters  │ │ • Executes via   │
│   results        │ │   → typed params │ │   Connector      │
│ • Last-execution │ │ • TTL cache      │ │ • File cache     │
│   cache          │ │                  │ │                  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

### Relationship to Existing Connector Protocol

The `Connector` protocol handles **schema introspection** and **ad-hoc SQL execution**. The `QueryStore` protocol handles **saved query management** and **parameterized execution**. They are complementary:

```
Connector (existing)              QueryStore (new)
────────────────────              ──────────────────
get_tables()                      list()
get_columns()                     get()
execute_sql(raw_sql)              execute(template_id, params)
                                  create(sql, params_schema)
```

A single backend can implement both. For example, `MetabaseConnector` implements `Connector` for schema introspection and `MetabaseQueryStore` implements `QueryStore` for saved questions. For backends like Dune where the primary interaction *is* stored queries, the `QueryStore` may be the more natural interface.

For purely SQL-backed connections (PostgreSQL, ClickHouse), a `LocalQueryStore` stores templates as YAML files in the connection directory and executes via the existing `Connector.execute_sql()`.

---

## Protocol Definition

### QueryTemplate

```python
@dataclass
class QueryParameter:
    """Schema for a single query parameter."""
    key: str
    type: str              # text | number | date | enum | boolean | date_range
    label: str = ""        # Human-readable name
    description: str = ""
    required: bool = False
    default: Any = None
    # Constraints
    enum_options: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None
    # UI hints (optional — ignored by execution layer)
    ui_widget: str | None = None       # dropdown, calendar, slider, etc.
    bound_column: str | None = None    # Metabase field-filter binding


@dataclass
class QueryTemplate:
    """A saved, parameterized query."""
    id: str                            # Backend-native ID (stringified)
    name: str
    sql: str                           # SQL with parameter placeholders
    parameters: list[QueryParameter]
    # Metadata
    description: str = ""
    tags: list[str] = field(default_factory=list)
    owner: str = ""
    created_at: str = ""
    updated_at: str = ""
    source: str = ""                   # "dune", "metabase", "local", etc.
    source_url: str = ""               # Link to query in native UI
```

### Execution Model

```python
@dataclass
class CachePolicy:
    """Controls cache behavior for query execution."""
    strategy: str = "auto"             # auto | fresh | max_age | cached_only
    max_age_seconds: int | None = None # Accept results up to N seconds old
    force_refresh: bool = False        # Ignore cache, re-execute


@dataclass
class ExecutionRequest:
    """Request to execute a query template."""
    template_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    cache_policy: CachePolicy = field(default_factory=CachePolicy)
    row_limit: int | None = None       # Cap result rows


@dataclass
class ExecutionHandle:
    """Handle returned from execute() — may contain results or poll info."""
    execution_id: str
    status: str                        # pending | running | completed | failed | cached
    results: ResultSet | None = None   # Present if sync or cached
    error: str | None = None           # Present if failed


@dataclass
class ResultSet:
    """Query result data."""
    columns: list[dict[str, str]]      # [{name, type}]
    rows: list[dict[str, Any]]
    row_count: int
    execution_time_ms: int | None = None
    cached: bool = False
    cached_at: str | None = None       # ISO timestamp
    expires_at: str | None = None      # ISO timestamp
    truncated: bool = False            # True if row_limit was applied
```

### QueryStore Protocol

```python
@runtime_checkable
class QueryStore(Protocol):
    """Protocol for saved query management across backends."""

    # -- Template CRUD --

    def list_templates(
        self, tags: list[str] | None = None, limit: int = 50
    ) -> list[QueryTemplate]:
        """List available query templates, optionally filtered by tags."""
        ...

    def get_template(self, template_id: str) -> QueryTemplate:
        """Get a single query template by ID."""
        ...

    def create_template(
        self,
        name: str,
        sql: str,
        parameters: list[QueryParameter] | None = None,
        description: str = "",
        tags: list[str] | None = None,
    ) -> QueryTemplate:
        """Create a new query template."""
        ...

    def update_template(
        self, template_id: str, **kwargs: Any
    ) -> QueryTemplate:
        """Update an existing template (partial update)."""
        ...

    def delete_template(self, template_id: str) -> None:
        """Delete a query template."""
        ...

    # -- Execution --

    def execute(self, request: ExecutionRequest) -> ExecutionHandle:
        """Execute a query template with parameters.

        Returns an ExecutionHandle that either contains results (sync/cached)
        or can be polled via get_status() / get_results().
        """
        ...

    def get_status(self, execution_id: str) -> ExecutionHandle:
        """Check execution status (for async backends)."""
        ...

    def get_results(
        self, execution_id: str, offset: int = 0, limit: int = 1000
    ) -> ResultSet:
        """Fetch results for a completed execution, with pagination."""
        ...

    def get_latest_results(self, template_id: str) -> ResultSet | None:
        """Get the most recent cached results for a template.

        Returns None if no cached results exist.
        """
        ...

    def cancel(self, execution_id: str) -> None:
        """Cancel a running execution (if supported)."""
        ...
```

### Capabilities Declaration

```python
@dataclass
class QueryStoreCapabilities:
    """Declares what a QueryStore backend supports."""
    supports_create: bool = True       # Can create new templates
    supports_update: bool = True       # Can modify existing templates
    supports_delete: bool = True       # Can delete templates
    supports_execute: bool = True      # Can execute queries
    supports_cancel: bool = False      # Can cancel running executions
    supports_cache_control: bool = False  # Respects CachePolicy
    supports_pagination: bool = False  # Supports offset/limit on results
    execution_mode: str = "sync"       # sync | async | both
    parameter_syntax: str = "mustache" # mustache | jinja | colon | qmark
    read_only: bool = False            # True = can list/get but not create/update
```

---

## Backend Mapping

### How Each Backend Maps to the Protocol

#### Dune Analytics

| Protocol method | Dune API mapping |
|-----------------|------------------|
| `list_templates()` | `GET /api/v1/user/queries` |
| `get_template(id)` | `GET /api/v1/query/{id}` |
| `create_template()` | `POST /api/v1/query` |
| `execute()` | `POST /api/v1/query/{id}/execute` → returns `execution_id` |
| `get_status()` | `GET /api/v1/execution/{id}/status` |
| `get_results()` | `GET /api/v1/execution/{id}/results` |
| `get_latest_results()` | `GET /api/v1/query/{id}/results` (last execution) |
| `cancel()` | `POST /api/v1/execution/{id}/cancel` |

- **Execution mode**: async (always returns execution_id, poll for results)
- **Cache**: Last execution result. `force_refresh=true` → re-execute. `cached_only` → last result.
- **Parameter syntax**: `{{param_name}}` (mustache)
- **Capabilities**: Full CRUD, async, cancel, no pagination control

#### Metabase

| Protocol method | Metabase API mapping |
|-----------------|----------------------|
| `list_templates()` | `GET /api/card` (filtered by `model=question`) |
| `get_template(id)` | `GET /api/card/{id}` |
| `create_template()` | `POST /api/card` |
| `execute()` | `POST /api/card/{id}/query` with parameters → sync results |
| `get_status()` | N/A (sync) → always returns `completed` |
| `get_results()` | Inline in execute response |
| `get_latest_results()` | `POST /api/card/{id}/query` with empty params (uses cache) |
| `cancel()` | N/A |

- **Execution mode**: sync (results in response)
- **Cache**: TTL-based, configurable per card. `force_refresh=true` → bypass cache.
- **Parameter syntax**: `{{param}}` with field-filter extensions
- **Capabilities**: Full CRUD, sync only, no cancel, cache control via TTL

#### Superset

| Protocol method | Superset API mapping |
|-----------------|----------------------|
| `list_templates()` | `GET /api/v1/saved_query/` + `GET /api/v1/chart/` |
| `get_template(id)` | `GET /api/v1/saved_query/{id}` |
| `create_template()` | `POST /api/v1/saved_query/` |
| `execute()` | `POST /api/v1/sqllab/execute/` → sync or async |
| `get_status()` | `GET /api/v1/sqllab/results/{key}` |
| `get_results()` | `GET /api/v1/sqllab/results/{key}` |
| `get_latest_results()` | Chart data endpoint with cache |
| `cancel()` | `DELETE /api/v1/sqllab/{id}` |

- **Execution mode**: both (sync for small, async for large)
- **Cache**: Redis TTL, chart-level configuration
- **Parameter syntax**: Jinja (`{{ filter_values("col") }}`)
- **Capabilities**: Full CRUD, cancel, cache control, pagination

#### Redash

| Protocol method | Redash API mapping |
|-----------------|---------------------|
| `list_templates()` | `GET /api/queries` |
| `get_template(id)` | `GET /api/queries/{id}` |
| `create_template()` | `POST /api/queries` |
| `execute()` | `POST /api/query_results` → returns `job.id` or inline result |
| `get_status()` | `GET /api/jobs/{id}` |
| `get_results()` | `GET /api/query_results/{id}` |
| `get_latest_results()` | `GET /api/queries/{id}/results` |
| `cancel()` | `DELETE /api/jobs/{id}` |

- **Execution mode**: async (job polling) or sync (if cached result is fresh)
- **Cache**: Explicit TTL per query. Scheduled refresh via "refresh schedule."
- **Parameter syntax**: `{{param}}` (mustache)
- **Capabilities**: Full CRUD, async, cancel

#### Local (db-mcp native)

| Protocol method | Implementation |
|-----------------|----------------|
| `list_templates()` | Read YAML files from `{connection}/templates/*.yaml` |
| `get_template(id)` | Read `{connection}/templates/{id}.yaml` |
| `create_template()` | Write YAML file |
| `execute()` | Rewrite params → `Connector.execute_sql()` → sync result |
| `get_status()` | Always `completed` (sync) |
| `get_results()` | Return from execute |
| `get_latest_results()` | Read from `{connection}/cache/{id}.json` if fresh |
| `cancel()` | N/A |

- **Execution mode**: sync (delegates to connector)
- **Cache**: File-based, configurable max-age per template
- **Parameter syntax**: `{{param}}` (rewritten to connector's native syntax at execution time)
- **Capabilities**: Full CRUD, sync, no cancel, basic cache

---

## Parameter Normalization

Parameter syntax is the most annoying divergence. The strategy is: **store in canonical form, rewrite at execution time.**

### Canonical Form

All templates stored internally use mustache syntax: `{{param_name}}`

### Rewrite Rules

| Backend | Native syntax | Rewrite from `{{name}}` |
|---------|---------------|------------------------|
| Dune | `{{name}}` | No-op |
| Metabase | `{{name}}` | No-op (field filters handled separately) |
| Superset | `{{ name }}` (Jinja) | Add spaces, or use `{{ filter_values('name') }}` for filters |
| Redash | `{{name}}` | No-op |
| PostgreSQL | `%(name)s` or `$1` | Positional rewrite |
| ClickHouse | `{name:Type}` | Add type annotation |
| MySQL | `%(name)s` | Named param rewrite |
| DuckDB | `$name` | Prefix rewrite |

The rewrite happens in the `QueryStore.execute()` implementation, not at the protocol level. Callers always pass `{key: value}` dicts.

---

## Unified Execution Flow

The protocol hides sync/async differences from callers. A higher-level helper unifies them:

```python
def execute_and_wait(
    store: QueryStore,
    template_id: str,
    params: dict[str, Any],
    cache_policy: CachePolicy | None = None,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
) -> ResultSet:
    """Execute a template and block until results are ready.

    Works identically for sync and async backends:
    - Sync (Metabase): Returns immediately with results
    - Async (Dune): Polls get_status() until completed, then fetches results
    - Cached: Returns cached results without execution
    """
    request = ExecutionRequest(
        template_id=template_id,
        parameters=params,
        cache_policy=cache_policy or CachePolicy(),
    )

    handle = store.execute(request)

    if handle.status in ("completed", "cached") and handle.results:
        return handle.results

    if handle.status == "failed":
        raise QueryExecutionError(handle.error)

    # Poll for async backends
    start = time.time()
    while (time.time() - start) < timeout:
        handle = store.get_status(handle.execution_id)
        if handle.status == "completed":
            return store.get_results(handle.execution_id)
        if handle.status == "failed":
            raise QueryExecutionError(handle.error)
        time.sleep(poll_interval)

    raise TimeoutError(f"Query did not complete within {timeout}s")
```

---

## Cache Strategy

### The Problem

Each backend caches differently, and the user may not know (or care) about the details. The abstraction needs to let callers express *intent* without knowing the backend's cache implementation.

### CachePolicy Semantics

| Strategy | Meaning | Dune behavior | Metabase behavior | Local behavior |
|----------|---------|---------------|-------------------|----------------|
| `auto` | Backend decides | Return last execution if <1h old, else re-execute | Use Metabase's TTL | Use file cache with default TTL |
| `fresh` | Always re-execute | `POST .../execute` | `POST` with `ignore_cache=true` | Execute via connector |
| `max_age(N)` | Accept results up to N seconds old | Check last execution timestamp | Check cache header | Check file mtime |
| `cached_only` | Only return if cached, never execute | Return last execution or None | Return cached or None | Return file cache or None |

### Cache Storage for Local Backend

```
~/.db-mcp/connections/{name}/
├── templates/
│   ├── daily-revenue.yaml          # Template definition
│   └── user-cohort.yaml
└── cache/
    ├── daily-revenue/
    │   └── a1b2c3.json             # Hash of parameter values → cached result
    └── user-cohort/
        └── d4e5f6.json
```

Cache key = SHA-256 of sorted parameter values. Cache metadata (timestamp, TTL) stored in the JSON alongside results.

---

## MCP Tool Surface

The QueryStore exposes three new MCP tools:

### `list_query_templates`

```
Lists saved query templates from connected analytical backends.

Args:
    source: Filter by source ("dune", "metabase", "local", or "all")
    tags: Filter by tags
    limit: Max results (default 20)

Returns:
    List of {id, name, description, source, parameter_count, tags}
```

### `run_query_template`

```
Executes a saved query template with parameters.

Args:
    template_id: ID of the template to execute
    parameters: Dict of parameter values
    cache: "auto" | "fresh" | "cached_only"

Returns:
    Query results as a table, plus metadata (cached, execution_time, row_count)
```

### `save_query_template`

```
Saves the current query as a reusable template.

Args:
    name: Template name
    sql: SQL query with {{param}} placeholders
    parameters: List of {key, type, description, default}
    description: What this query answers
    tags: Categorization tags

Returns:
    {id, name, source: "local"}
```

---

## Key Design Decisions

### 1. Protocol vs Base Class

| Approach | Pros | Cons |
|----------|------|------|
| **Protocol** (like Connector) | No inheritance required, duck-typing, flexible | No shared implementation |
| **Abstract base class** | Shared execute_and_wait(), param rewriting | Rigid hierarchy |
| **Protocol + mixin** | Protocol for typing, mixin for shared logic | Two things to manage |

**Decision**: Protocol + standalone helper functions (like `execute_and_wait()`). Matches the existing `Connector` pattern. Shared logic lives in module-level functions, not base classes.

### 2. Template Storage for Local Backend

| Approach | Pros | Cons |
|----------|------|------|
| **YAML files** (like training examples) | Human-readable, git-syncable, consistent with vault | Slower for large counts |
| **SQLite** | Fast queries, indexing | Another dependency, not git-friendly |
| **In-memory only** | Simple | Lost on restart |

**Decision**: YAML files in `{connection}/templates/`. Matches the existing vault pattern (training examples, metrics catalog, etc.). A connection with 100 templates is 100 small YAML files — well within filesystem comfort.

### 3. Parameter Syntax Normalization

| Approach | Pros | Cons |
|----------|------|------|
| **Store native, rewrite on import** | Templates are portable | Lossy — can't round-trip |
| **Store canonical, rewrite on execute** | Clean internal model | Must rewrite for every backend |
| **Store both** | Lossless | Complexity, drift |

**Decision**: Store canonical (`{{param}}`), rewrite on execute. The rewrite is simple string substitution and each backend implementation owns its own rewriter. Import from external backends normalizes to canonical on ingest.

### 4. QueryStore per Connection vs Global

| Approach | Pros | Cons |
|----------|------|------|
| **Per connection** | Clean separation, each backend has its own store | Can't cross-reference |
| **Global registry** | Single `list_templates()` across all sources | Merge complexity, ID collisions |

**Decision**: Per connection, with a thin registry that aggregates for `list_templates(source="all")`. Template IDs are namespaced: `{connection_name}:{template_id}`. The registry is a simple dict of `{connection_name: QueryStore}`, not a new abstraction.

---

## File Structure

```
packages/core/src/db_mcp/
├── query_store/
│   ├── __init__.py                  # QueryStore protocol, dataclasses
│   ├── local.py                     # LocalQueryStore (YAML + Connector)
│   ├── dune.py                      # DuneQueryStore
│   ├── metabase.py                  # MetabaseQueryStore
│   ├── superset.py                  # SupersetQueryStore
│   ├── helpers.py                   # execute_and_wait(), param rewriting
│   └── registry.py                  # Multi-store aggregation
├── tools/
│   └── templates.py                 # MCP tools (list, run, save)
└── ...

packages/models/src/db_mcp_models/
├── query_template.py                # Shared models (QueryTemplate, etc.)
└── ...

~/.db-mcp/connections/{name}/
├── templates/                       # Local query templates
│   └── *.yaml
└── cache/                           # Cached execution results
    └── {template_id}/
        └── {param_hash}.json
```

---

## Implementation Phases

### Phase 0: Protocol & Local Store

**Goal**: Define the protocol and implement YAML-backed local templates.

- [ ] Define `QueryStore` protocol, `QueryTemplate`, `QueryParameter`, `ExecutionHandle`, `ResultSet` dataclasses in `query_store/__init__.py`
- [ ] Shared Pydantic models in `packages/models/`
- [ ] Implement `LocalQueryStore` — YAML CRUD, execute via `Connector.execute_sql()`
- [ ] Parameter rewriting for SQL connectors (mustache → positional/named)
- [ ] File-based result caching with TTL
- [ ] MCP tools: `list_query_templates`, `run_query_template`, `save_query_template`
- [ ] Tests for protocol, local store, param rewriting, caching

**Result**: Users can save, list, and execute parameterized query templates against any SQL-backed connection.

### Phase 1: Metabase QueryStore

**Goal**: Surface Metabase saved questions through the QueryStore protocol.

- [ ] Implement `MetabaseQueryStore` wrapping existing `MetabaseConnector` API
- [ ] Map Metabase Cards → `QueryTemplate` (extract parameters from native SQL)
- [ ] Field-filter parameter handling (bind to column metadata)
- [ ] Cache policy mapping (Metabase TTL → `CachePolicy`)
- [ ] Read-only mode for Metabase (list/get/execute, no create from db-mcp)
- [ ] Tests with mocked Metabase API responses

**Result**: `list_query_templates(source="metabase")` returns saved questions from Metabase.

### Phase 2: Dune QueryStore

**Goal**: Surface Dune saved queries with async execution.

- [ ] Implement `DuneQueryStore` wrapping existing `APIConnector` async patterns
- [ ] Async execution flow: execute → poll → results
- [ ] `execute_and_wait()` integration for blocking callers
- [ ] Last-execution cache mapping
- [ ] Cancel support
- [ ] Tests with mocked Dune API responses

**Result**: Users can browse and execute Dune queries from db-mcp, with async polling handled transparently.

### Phase 3: Superset QueryStore

**Goal**: Surface Superset charts and saved queries.

- [ ] Implement `SupersetQueryStore`
- [ ] Map Charts → `QueryTemplate` (extract SQL from chart config)
- [ ] Map Saved Queries → `QueryTemplate`
- [ ] Jinja parameter normalization (Jinja ↔ mustache)
- [ ] Redis cache integration (via Superset's cache headers)
- [ ] Tests

**Result**: Superset charts and queries available alongside other template sources.

### Phase 4: Multi-Store Registry & UI

**Goal**: Unified template browsing across all connected backends.

- [ ] Registry that aggregates multiple `QueryStore` instances
- [ ] Namespaced template IDs (`metabase:42`, `dune:1234`, `local:daily-revenue`)
- [ ] `list_query_templates(source="all")` across backends
- [ ] UI page: template browser (list, search, execute with parameter form)
- [ ] UI page: template detail (SQL preview, parameter inputs, results table)

**Result**: Single interface to browse and execute templates from any connected analytical tool.

---

## Open Questions

### 1. Write-back to External Backends

Should `create_template()` and `update_template()` write back to Metabase/Superset, or only work locally?

- **Option A**: Read-only for external backends — templates can only be created in the native UI
- **Option B**: Full write-back — create a Metabase question from db-mcp
- **Option C**: Local fork — import from external, edit locally, no sync back

Recommendation: Start with **Option A** (read-only for external, full CRUD for local). Write-back is complex (permissions, validation, field mappings) and low-value in the short term.

### 2. Template Versioning

Should templates track version history?

- Local templates get git versioning for free (if git-sync is enabled)
- External backend templates are versioned by their native systems
- Do we need an explicit version field in the protocol?

Recommendation: No explicit versioning in V1. Rely on git for local, native versioning for external.

### 3. Template Discovery from Query History

Should db-mcp automatically suggest saving frequently-used queries as templates?

- Trace data already captures executed queries
- Pattern detection could identify "this query with different date ranges" → candidate for parameterization
- Related to the [Knowledge Extraction Agent](knowledge-extraction-agent.md) concept

Recommendation: Out of scope for initial implementation. Natural fit for the knowledge extraction agent.

### 4. Cross-Backend Template Portability

If a user has a Metabase question that queries PostgreSQL, should db-mcp be able to execute the same SQL directly against the database (bypassing Metabase)?

- Useful when Metabase is slow or down
- Requires the db-mcp connection to point to the same database
- Parameter syntax may differ

Recommendation: Support it opportunistically — if the SQL is portable and the database is connected, allow direct execution. Flag it as "executed locally" vs "executed via Metabase."

### 5. Access Control

External backends have their own permission models. Should the QueryStore respect them?

- Metabase: Collections, permissions, data sandboxes
- Superset: RBAC, row-level security
- Dune: Public vs private queries

Recommendation: Pass through the user's credentials. If the backend rejects a request, surface the error. Don't try to replicate permission models locally.

---

## Success Criteria

1. **Local templates work end-to-end** — save a query, list it, execute it with parameters, get cached results
2. **At least one external backend** (Metabase or Dune) surfaces templates through the same protocol
3. **Parameter types are normalized** — a template imported from Metabase can be executed with the same parameter dict as a local template
4. **Cache policy works** — `fresh` always re-executes, `cached_only` never executes, `max_age` checks timestamps
5. **Async is transparent** — caller uses `execute_and_wait()` and doesn't need to know whether the backend is sync or async
6. **Templates are discoverable** — `list_query_templates()` returns templates from all connected backends with consistent metadata

---

## References

- [Semantic Data Gateway](data-gateway.md) — broader multi-source vision
- [Metrics Layer](metrics-layer.md) — semantic metrics that templates can reference
- [Knowledge Extraction Agent](knowledge-extraction-agent.md) — automatic template discovery from traces
- Existing connector protocol: `packages/core/src/db_mcp/connectors/__init__.py`
- Existing Metabase connector: `packages/core/src/db_mcp/connectors/metabase.py`
- Existing API connector (Dune): `packages/core/src/db_mcp/connectors/api.py`
