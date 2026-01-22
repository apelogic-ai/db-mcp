# Semantic Data Gateway

**Status**: Conceptual  
**Created**: 2026-01-21

## Vision

A local MCP gateway that provides unified, semantic-aware access to data across multiple sources. Not just text-to-SQL, but a full data platform stack that runs locally.

**Positioning**: The "local data IDE" — like having a personal data team that understands your entire data landscape.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                 Claude Desktop / Agent                       │
└─────────────────────────────┬───────────────────────────────┘
                              │ MCP (single endpoint)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    SEMANTIC DATA GATEWAY                     │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    Router / Orchestrator                │ │
│  │  • Intent classification                                │ │
│  │  • Source selection                                     │ │
│  │  • Multi-step coordination                              │ │
│  └────────────────────────────────────────────────────────┘ │
│                              │                               │
│  ┌───────────────────────────┴───────────────────────────┐  │
│  │                 UNIFIED KNOWLEDGE LAYER                │  │
│  │  schema/ metrics/ relationships/ examples/ rules/      │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                               │
│     ┌────────────┬──────────┴───────────┬────────────┐     │
│     ▼            ▼                      ▼            ▼     │
│  ┌──────┐    ┌──────┐    ┌──────────┐    ┌──────┐         │
│  │db-mcp│    │csv   │    │superset  │    │dbt   │   ...   │
│  │ MCP  │    │ MCP  │    │  MCP     │    │ MCP  │         │
│  └──────┘    └──────┘    └──────────┘    └──────┘         │
│     │            │              │            │              │
└─────┼────────────┼──────────────┼────────────┼──────────────┘
      ▼            ▼              ▼            ▼
   Databases    CSV/Parquet    Superset     dbt project
   (PG, CH,     files          API          (transforms)
   Trino)
```

## The Five Layers

### 1. Knowledge Layer

**Purpose**: Unified semantic understanding across all sources.

**Sources that contribute:**
- DB introspection (db-mcp)
- BI tool APIs (Superset, Metabase, Tableau)
- User input (onboarding, corrections)
- Learning loop (traces, feedback)

**Artifacts produced:**
- `schema/descriptions.yaml` — merged schema with semantic annotations
- `domain/model.md` — business domain documentation
- `metrics/catalog.yaml` — metric definitions (portable)
- `relationships/mappings.yaml` — cross-source joins, foreign keys
- `instructions/rules.md` — query patterns, guardrails
- `examples/*.yaml` — known-good queries

**MCPs**: db-mcp, superset-mcp, tableau-mcp, metabase-mcp

### 2. Query Layer

**Purpose**: Generate and execute SQL using knowledge layer context.

**Capabilities:**
- SQL generation with semantic awareness
- Query execution with cost guards
- Query caching (dedup identical queries)
- Result caching (share across requests)

**MCPs**: db-mcp (query tools), csv-mcp

### 3. Aggregation Layer

**Purpose**: Federate data across sources locally.

**Engine**: DuckDB (embedded)

**Capabilities:**
- Cross-source joins (CSV + DB, DB + DB)
- Local compute (no round-trips to warehouse)
- In-memory analytics
- Register remote tables as virtual tables

**Example:**
```sql
-- DuckDB federating across sources
SELECT c.segment, SUM(s.amount) as revenue
FROM csv_scan('sales.csv') s
JOIN postgres_scan('customers') c ON s.customer_id = c.id
GROUP BY 1
```

### 4. Transformation Layer

**Purpose**: Persistent transforms and materializations.

**Capabilities:**
- Run dbt models
- Materialize query results
- Pipeline orchestration

**MCPs**: dbt-mcp (or direct dbt CLI integration)

### 5. Output Layer

**Purpose**: Format and export results.

**Capabilities:**
- Result formatting (tables, charts)
- Export (CSV, Excel, Parquet, JSON)
- Push to BI tools (create Superset chart)
- Claude artifacts (React components)

**MCPs**: export-mcp, visualization-mcp

---

## MCP Inventory

| MCP | Layer | Function | Status |
|-----|-------|----------|--------|
| **db-mcp** | Knowledge + Query | DB introspection, semantic layer, SQL gen, execute | ✅ Exists |
| **csv-mcp** | Query | Load CSVs, infer types, register with DuckDB | New |
| **superset-mcp** | Knowledge | Pull metrics, dashboards, charts from Superset API | New |
| **metabase-mcp** | Knowledge | Pull questions, models from Metabase API | New |
| **tableau-mcp** | Knowledge | Pull from Tableau REST API | New |
| **dbt-mcp** | Transform | Run dbt, introspect models, get lineage | New |
| **export-mcp** | Output | Export to various formats | New |
| DuckDB | Aggregation | Local federation engine | Embedded in gateway |

---

## Data Flow Examples

### Example 1: Simple Query (Single Source)

```
User: "What's our revenue by region?"

Gateway:
├── Checks knowledge layer: "revenue" defined in metrics/catalog.yaml
├── Source: main_db only
├── Routes to: db-mcp (query layer)
└── Returns: result table
```

### Example 2: Cross-Source Join

```
User: "Join my sales.csv with customer database and show top 10"

Gateway:
├── Checks knowledge layer: relationship exists (sales.customer_id → db.customers.id)
├── Sources: csv-mcp + db-mcp
├── Routes to: aggregation layer (DuckDB)
│   ├── csv-mcp.register("sales.csv") → DuckDB
│   ├── db-mcp.register("customers") → DuckDB
│   └── DuckDB executes federated query
└── Returns: result table
```

### Example 3: Metric from BI Tool

```
User: "Show me the DAU metric from our Superset"

Gateway:
├── Checks knowledge layer: superset-mcp has DAU metric defined
├── Routes to: superset-mcp
│   └── Either: fetch cached chart data
│   └── Or: get metric SQL, execute via query layer
└── Returns: result + link to Superset dashboard
```

### Example 4: Transform + Query

```
User: "Run the customer_segments dbt model and show results"

Gateway:
├── Routes to: dbt-mcp (transformation layer)
│   └── dbt run --select customer_segments
├── Then routes to: db-mcp (query layer)
│   └── SELECT * FROM customer_segments LIMIT 100
└── Returns: result table
```

### Example 5: Full Pipeline

```
User: "Take my sales.csv, join with customers, calculate revenue by segment, save as Parquet"

Gateway:
├── csv-mcp: load sales.csv
├── db-mcp: introspect customers table
├── aggregation (DuckDB): 
│   └── SELECT segment, SUM(amount) FROM sales JOIN customers... GROUP BY 1
├── export-mcp: write to parquet
└── Returns: file path + summary
```

---

## Key Design Decisions

### 1. Knowledge Layer: Centralized vs Federated

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **Centralized** | Gateway owns unified knowledge | Single source of truth, conflict resolution | Manual sync, drift |
| **Federated** | Each MCP contributes via introspection | Always fresh, no sync | Merge complexity, runtime cost |
| **Hybrid** ✓ | Gateway owns unified layer, MCPs contribute via introspection | Best of both | Complexity |

**Decision**: Hybrid — Gateway maintains unified artifacts, MCPs contribute via introspection tools. Gateway merges and resolves conflicts.

### 2. Caching Strategy

| Cache Type | Location | Rationale |
|------------|----------|-----------|
| Query cache | Gateway | Dedupe identical queries across sources |
| Result cache | Gateway | Share results across requests |
| Schema cache | Per-MCP | Each source knows its own schema best |
| Metric cache | Knowledge layer | Metrics are cross-source |

### 3. DuckDB: Embedded vs Separate MCP

| Approach | Pros | Cons |
|----------|------|------|
| **Embedded** ✓ | Simpler, no extra process, direct memory | Couples federation to gateway |
| Separate MCP | Modular, replaceable | IPC overhead, more moving parts |

**Decision**: Embedded initially. DuckDB is a library, not a service. Extract to separate MCP later if needed.

### 4. Gateway as MCP Proxy vs Direct Connection

| Approach | Description |
|----------|-------------|
| **Proxy** ✓ | Claude → Gateway → [child MCPs] |
| Direct | Claude → Gateway (routing) + Claude → MCPs (direct) |

**Decision**: Proxy. Gateway spawns child MCP servers, aggregates tools, proxies calls. Simpler for user (one MCP to configure).

---

## File Structure

```
~/.db-mcp/                            # config directory
├── config.yaml                       # global settings, source registry
│
├── knowledge/                        # UNIFIED KNOWLEDGE LAYER
│   ├── schema/
│   │   └── descriptions.yaml         # merged from all sources
│   ├── metrics/
│   │   └── catalog.yaml              # portable metric definitions
│   ├── relationships/
│   │   └── mappings.yaml             # cross-source relationships
│   ├── domain/
│   │   └── model.md                  # business domain documentation
│   ├── instructions/
│   │   └── rules.md                  # query patterns, guardrails
│   └── examples/
│       └── *.yaml                    # known-good queries
│
├── sources/                          # SOURCE-SPECIFIC CONFIG
│   ├── main_db/                      # db-mcp connection
│   │   ├── .env                      # credentials (gitignored)
│   │   ├── config.yaml               # connection settings
│   │   └── state.yaml                # onboarding state
│   │
│   ├── sales_csv/                    # CSV source
│   │   ├── config.yaml               # file path
│   │   └── inferred_schema.yaml      # auto-detected types
│   │
│   └── superset_prod/                # Superset connection
│       ├── .env                      # API token (gitignored)
│       ├── config.yaml               # API endpoint
│       └── cached_metrics.yaml       # pulled from API
│
├── cache/
│   ├── queries/                      # query result cache
│   └── schemas/                      # schema introspection cache
│
└── learnings/
    ├── patterns.md                   # learned query patterns
    └── failures/                     # failed queries for improvement
```

---

## Implementation Approach

### Phase 0: Foundation (2 weeks)

**Goal**: Gateway that wraps existing db-mcp.

- [ ] `sg-gateway` CLI (or `sg` for short)
- [ ] Gateway MCP server that proxies to db-mcp
- [ ] Unified config structure (`~/.db-mcp/`)
- [ ] `sg init` wizard (wraps `db-mcp init`)

**Result**: Drop-in replacement for db-mcp with new structure.

### Phase 1: CSV Support (1 week)

**Goal**: Add local file support.

- [ ] csv-mcp: load CSVs, infer schema, register with DuckDB
- [ ] DuckDB embedded in gateway
- [ ] Cross-source queries (CSV + DB)
- [ ] Parquet/Excel support

**Result**: "Join my spreadsheet with the database"

### Phase 2: BI Tool Integration (2 weeks)

**Goal**: Pull semantics from existing BI tools.

- [ ] superset-mcp: connect to Superset API
  - Pull datasets, metrics, saved queries
  - Contribute to knowledge layer
- [ ] metabase-mcp: connect to Metabase API
  - Pull questions, models, segments

**Result**: "What dashboards use the orders table?"

### Phase 3: Unified Knowledge Layer (2 weeks)

**Goal**: Semantic layer that spans all sources.

- [ ] Schema merging across sources
- [ ] Cross-source relationship mapping
- [ ] Metric deduplication (same metric from DB vs BI tool)
- [ ] Conflict resolution UI

**Result**: "Show me revenue" works regardless of whether metric is defined in DB, Superset, or manually.

### Phase 4: Transform Integration (1 week)

**Goal**: dbt integration.

- [ ] dbt-mcp: run models, get lineage
- [ ] Materialize query results as dbt models
- [ ] Lineage visualization

**Result**: "Run my dbt models and show the customer segments"

### Phase 5: Output & Export (1 week)

**Goal**: Rich output options.

- [ ] export-mcp: CSV, Excel, Parquet, JSON
- [ ] Chart generation (simple visualizations)
- [ ] Push to BI tools (create Superset chart from query)

**Result**: "Export this as Parquet" or "Create a Superset dashboard from these results"

---

## Open Questions

### 1. Naming & Branding

Options:
- `db-mcp` — current project name
- `dataconn` — generic, memorable
- Something else?

### 2. Local-Only vs Hybrid

Some sources can't run locally:
- Looker (SaaS only)
- Cloud-hosted Superset/Metabase
- Snowflake, BigQuery, etc.

Should gateway:
- **Local-only**: Only support locally-runnable sources
- **Hybrid**: Connect to remote APIs where needed (most practical)
- **Sync mode**: Pull remote data to local DuckDB for offline work

### 3. Gateway Runtime

Options:
- **Python** (like db-mcp): Leverage existing code, PyInstaller binary
- **TypeScript**: Better Electron integration if we build desktop app
- **Rust**: Fast, small binary, but harder to write MCP servers

**Recommendation**: Python initially (reuse db-mcp), consider Rust for v2.

### 4. Plugin Architecture

How do users add new MCPs?

Options:
- **Config-based**: List MCPs in config, gateway spawns them
- **Discovery**: Gateway scans for installed MCPs
- **Bundled**: Ship gateway with all MCPs built-in

### 5. Multi-Tenant / Team Use

Should gateway support:
- Multiple users with different permissions?
- Shared knowledge layer (git-synced)?
- Central gateway server vs local-per-user?

---

## Relationship to Existing Components

| Component | Becomes |
|-----------|---------|
| db-mcp | Core MCP for database sources |
| db-mcp CLI | Subsumed by `sg` CLI |
| db-mcp desktop (Electron) | Becomes `sg-desktop` |
| Flow Manager | Separate concern (agentic workflows) |

The gateway **doesn't replace** db-mcp — it wraps and extends it.

---

## Success Metrics

1. **Single `sg init`** configures all data sources
2. **Cross-source queries** work transparently
3. **Knowledge layer** understands metrics from multiple sources
4. **< 5 minute setup** for new source
5. **Works offline** for local sources

---

## Competitive Landscape

| Tool | What It Does | Our Differentiation |
|------|--------------|---------------------|
| dbt | Transform layer | We integrate dbt, not replace |
| Cube | Semantic layer (cloud) | We're local-first |
| Metabase/Superset | BI tools | We connect to them, not replace |
| Airbyte | Data movement | We query in place, not ETL |
| LangChain SQL | Text-to-SQL | We're MCP-native, semantic-aware |

**Our unique angle**: Local-first, MCP-native, semantic layer that **connects** existing tools rather than replacing them.
