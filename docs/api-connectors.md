# Universal Connectors

**Status**: Design
**Created**: 2026-01-28
**Updated**: 2026-01-30
**Related**: [data-gateway.md](data-gateway.md), [metrics-layer.md](metrics-layer.md)

## Overview

Extend db-mcp to support three source types through a unified architecture:

| Source Type | Schema Discovery | Data Fetching | Examples |
|---|---|---|---|
| **SQL** (existing) | `SHOW TABLES` / `DESCRIBE` | SQL via SQLAlchemy | PostgreSQL, Trino, ClickHouse |
| **API** (new) | OpenAPI spec / endpoint probing | HTTP calls with pagination | Stripe, HubSpot, Jira |
| **File** (new) | Header inference / DuckDB `DESCRIBE` | DuckDB reads directly | CSV, Parquet, Excel, JSON |

All three source types share the same knowledge vault structure. The LLM sees identical `descriptions.yaml` regardless of source. Domain models, business rules, metrics, and examples work unchanged.

**The LLM is the planner.** There is no explicit execution plan format. The LLM decides what data it needs, calls the appropriate `get_data()` tool per source, and synthesizes results. For cross-source queries, DuckDB merges the pieces.


The insight that makes this work: API endpoints and files map cleanly onto the relational model that db-mcp already understands.

| SQL Concept | SQL Source | API Source | File Source |
|---|---|---|---|
| Catalog | Database catalog | Service name (`stripe`) | Directory name |
| Schema | Database schema | API version / group (`/v1`) | Subdirectory |
| Table | Database table | GET endpoint returning a collection | Individual file |
| Column | Table column | Response object field | CSV header / JSON key |
| Row | Table row | Single object in response array | File row / JSON object |
| Primary key | PK constraint | Resource `id` field | Row number or inferred |
| Foreign key | FK constraint | ID reference between endpoints | Matching column names |
| Sample data | `SELECT * LIMIT 5` | `GET /endpoint?limit=5` | First 5 rows |

Since the LLM context is built from `descriptions.yaml`, and that file uses the same format for all sources, the entire downstream pipeline (domain model generation, business rules, metrics mining, query examples) works without modification.

## How Each Source Type Works

### SQL Sources (Existing)

Today's implementation. No changes needed.

**Schema discovery**: SQLAlchemy `inspect()`, dialect-specific `SHOW` commands.
**Data fetching**: SQL query via `engine.execute(text(sql))`.
**What the LLM sees**: `descriptions.yaml` with tables and columns from introspection.

```
~/.db-mcp/connections/main_db/
├── .env                    # DATABASE_URL
├── connector.yaml          # type: sql (optional, inferred from .env)
├── schema/descriptions.yaml
├── domain/model.md
└── ...
```

### API Sources (New)

**Schema discovery** — three strategies in order of preference:

1. **OpenAPI / Swagger spec** (best). Parse the spec to extract GET endpoints as "tables" and response schema properties as "columns". OpenAPI specs are often richer than SQL introspection — they include human-written descriptions, parameter constraints, and example values.

2. **GraphQL introspection**. GraphQL APIs expose their full type system via the introspection query. Types map to tables, fields map to columns, with nullability and relationships included.

3. **Endpoint probing** (fallback). Call each known endpoint with `?limit=1`, infer schema from the response JSON. Detect field types from values, flatten nested objects with dot notation (`address.city`), detect ID references.

**Data fetching**: HTTP GET with auth, pagination, and rate limiting handled transparently. The fetcher returns rows (list of dicts) — same shape as SQL results.

**What the LLM sees**: Same `descriptions.yaml`. An API endpoint like `GET /v1/customers` appears as a table named `customers` with columns for each response field.

```
~/.db-mcp/connections/stripe/
├── .env                    # STRIPE_API_KEY (gitignored)
├── connector.yaml          # type: api, base_url, auth, pagination, spec_url
├── schema/descriptions.yaml
├── domain/model.md
└── ...
```

**Endpoint config fields (connector.yaml):**

- `path` supports path params like `/query/{query_id}/results` which are filled from `params`.
- `method` supports `GET` (default) and `POST`.
- `body_mode` (for POST): `json` to send params in JSON body, `query` to send as query params.
- `response_mode`: `data` (default) extracts rows from `data_field`/`results`, `raw` returns full JSON.

**Nested data handling**: API responses with nested objects get flattened with dot notation. `customer.address.city` becomes column `address_city`. Arrays become separate virtual "tables" with parent ID references: `customer.subscriptions` becomes a `customer_subscriptions` table joinable on `customer_id`.

### File Sources (New)

**Schema discovery**: DuckDB can introspect any supported file format:

```sql
DESCRIBE SELECT * FROM 'data/sales.csv'
DESCRIBE SELECT * FROM 'data/events.parquet'
DESCRIBE SELECT * FROM read_json('data/records.json')
```

This returns column names and inferred types. For CSV, DuckDB auto-detects delimiters, headers, and types. For Parquet, the schema is embedded. For JSON, types are inferred from values.

**Data fetching**: DuckDB reads files directly — no loading step. A query against a CSV is just `SELECT * FROM 'path/to/file.csv' WHERE ...`.

**What the LLM sees**: Same `descriptions.yaml`. Each file appears as a table. A file `sales_2024.csv` with columns `date, product, amount, region` looks identical to a database table.

```
~/.db-mcp/connections/local_files/
├── connector.yaml          # type: file, paths: [~/exports/, ~/data/]
├── schema/descriptions.yaml
├── domain/model.md
└── ...
```

**Directory watching**: File connections can point at directories. New files matching configured patterns (e.g., `*.csv`, `*.parquet`) are auto-discovered and added to the schema on next introspection.

## Cross-Source Queries

When the LLM needs data from multiple sources, DuckDB acts as the merge engine.

### Flow

```
User: "Show me Stripe revenue by customer segment from our database"

LLM reasons:
  1. "revenue" → Stripe charges (API source)
  2. "customer segment" → internal DB users table (SQL source)
  3. Need to join on customer email

LLM actions:
  1. Calls get_data(source="stripe", intent="all charges this month")
     → API fetcher returns charges rows
  2. Calls get_data(source="main_db", intent="customer emails and segments")
     → SQL fetcher returns user rows
  3. Calls merge_data(
       datasets=["charges", "users"],
       join="charges.customer_email = users.email",
       query="SELECT segment, SUM(amount) as revenue GROUP BY 1"
     )
     → DuckDB loads both as temp tables, executes SQL, returns merged result
  4. LLM presents the result to the user
```

The LLM doesn't need to know about DuckDB. It just knows:
- `get_data()` fetches rows from any source
- `merge_data()` joins multiple fetched datasets using SQL

### DuckDB as Scratch Space

DuckDB runs in-memory, session-scoped. Each `get_data()` call optionally registers its results as a named temp table. The LLM can then write SQL against these tables for joins, aggregations, and transformations.

```
┌─────────────────────────────────────────────────────┐
│                    DuckDB (in-memory)                │
│                                                      │
│  temp.stripe_charges    ← API fetch results          │
│  temp.db_users          ← SQL query results          │
│  temp.sales_csv         ← File read results          │
│                                                      │
│  SELECT u.segment, SUM(c.amount) as revenue          │
│  FROM temp.stripe_charges c                          │
│  JOIN temp.db_users u ON c.email = u.email           │
│  GROUP BY 1                                          │
└─────────────────────────────────────────────────────┘
```

For file sources, DuckDB reads files directly without a temp table step — the file path *is* the table reference.

## MCP Tools

### Data Fetching (Source-Aware)

The existing `get_data()` and `run_sql()` tools evolve to be source-aware:

```
get_data(intent, source?)
  → If source is SQL: generates and executes SQL (current behavior)
  → If source is API: generates HTTP call plan, fetches, returns rows
  → If source is File: generates DuckDB SQL against file, returns rows
  → If source omitted: LLM picks based on schema context

run_sql(query_id)
  → Unchanged for SQL sources
  → For API/File: executes DuckDB SQL against fetched/file data

merge_data(datasets, query)
  → Load named datasets into DuckDB temp tables
  → Execute SQL query against them
  → Return merged results
```

### Schema Discovery (Source-Specific)

```
list_tables(source?)        → Tables/endpoints/files across sources
describe_table(table)       → Columns with types and descriptions
sample_table(table, limit)  → Sample rows from any source
```

These tools already exist for SQL. They extend to cover API endpoints and files using the same return format.

### Connection Management

```
db-mcp init stripe --type api
db-mcp init my-data --type file --path ~/exports/
db-mcp init main-db                          # type: sql (default, existing)
```

## Connection Configuration

### `connector.yaml`

Each connection has a `connector.yaml` that defines source-specific settings.

**SQL** (optional — `.env` with `DATABASE_URL` is sufficient):

```yaml
type: sql
# Everything else comes from .env DATABASE_URL
```

**API**:

```yaml
type: api
base_url: https://api.stripe.com
auth:
  type: bearer                    # bearer | api_key | oauth2 | basic
  token_env: STRIPE_API_KEY       # references .env variable
  header: Authorization
spec:
  type: openapi                   # openapi | graphql | manual
  url: https://raw.githubusercontent.com/.../spec3.yaml
pagination:
  type: cursor                    # cursor | offset | page | link_header
  cursor_param: starting_after
  cursor_field: id
  page_size: 100
  has_more_field: has_more
rate_limit:
  requests_per_second: 25
  retry_on_429: true
allow_writes: false               # safety: GET-only by default
```

**File**:

```yaml
type: file
paths:
  - ~/exports/                    # directories to scan
  - ~/data/quarterly_report.csv   # individual files
patterns:
  - "*.csv"
  - "*.parquet"
  - "*.json"
ignore:
  - "*.tmp"
  - "._*"
```

### Pre-Built Templates

Common APIs have well-known schemas. Ship templates so users skip manual config:

```bash
db-mcp init my-stripe --template stripe
# Prompts only for API key, everything else pre-configured
```

```yaml
# templates/stripe.yaml
base_url: https://api.stripe.com
auth:
  type: bearer
  header: Authorization
pagination:
  type: cursor
  cursor_param: starting_after
  has_more_field: has_more
collections:
  customers:
    endpoint: /v1/customers
    description: "People or businesses that purchase from you"
  charges:
    endpoint: /v1/charges
    description: "Payment charges"
  invoices:
    endpoint: /v1/invoices
    description: "Invoices sent to customers"
```

## Cross-Source Relationships

A vault artifact maps how entities relate across sources:

```yaml
# ~/.db-mcp/connections/{name}/relationships/cross_source.yaml
mappings:
  - name: stripe_to_db_customer
    left:
      source: stripe
      table: customers
      field: email
    right:
      source: main_db
      table: public.users
      field: email
    type: one_to_one
    confidence: confirmed         # confirmed | detected

  - name: csv_sales_to_db_products
    left:
      source: sales_files
      table: sales_2024.csv
      field: product_id
    right:
      source: main_db
      table: public.products
      field: id
    type: many_to_one
    confidence: detected
```

These mappings are:
- **Auto-detected** during onboarding (matching column names, `*_id` patterns, email fields)
- **User-confirmed** through onboarding or business rules
- **Used by the LLM** when planning cross-source queries

## Onboarding Flow

The existing onboarding phases work for all source types with minimal changes:

| Phase | SQL (today) | API (new) | File (new) |
|---|---|---|---|
| **Init** | `test_connection()` | HTTP GET health check | Verify paths exist |
| **Schema** | `SHOW TABLES`, `DESCRIBE` | OpenAPI parse / probe | DuckDB `DESCRIBE` |
| **Review** | User describes tables | User describes endpoints | User describes files |
| **Domain** | LLM generates model | Same | Same |
| **Rules** | User adds rules | Same | Same |

Init and Schema need source-specific implementations. Review onward is identical — the LLM works from `descriptions.yaml` regardless of source.

## Challenges and Mitigations

### API-Specific

| Challenge | Mitigation |
|---|---|
| No server-side joins | DuckDB handles joins client-side after fetching |
| Pagination / rate limits | `connector.yaml` defines strategy; fetcher handles transparently |
| Data volume limits | Cost estimation before fetch ("~500 API calls, ~2 min"); encourage warehousing for bulk analytics |
| Schema instability | Periodic re-introspection; pin to API versions; knowledge gaps detection |
| Auth complexity | Start with bearer/API key (80% of APIs); add OAuth2 flow later |
| Nested responses | Flatten with dot notation; arrays become virtual tables |
| Write safety | `allow_writes: false` default; GET-only unless explicitly enabled |

### File-Specific

| Challenge | Mitigation |
|---|---|
| Schema inference errors | DuckDB is good at type inference; user can override in descriptions.yaml |
| Large files | DuckDB handles multi-GB files efficiently; streaming reads |
| File format variations | DuckDB supports CSV, Parquet, JSON, Excel natively |
| Files changing on disk | Re-introspect on access; warn if schema changed since last onboarding |

### Cross-Source

| Challenge | Mitigation |
|---|---|
| Join key discovery | Auto-detect matching column names; user confirms |
| Type mismatches | DuckDB casts types at join time; warn on lossy casts |
| Data freshness | API data is live per-query; file data is current on disk; SQL is live |
| Naming conflicts | Prefix with source name in DuckDB temp tables |

## Opportunities

1. **Knowledge layer is already source-agnostic.** Domain models, business rules, examples, metrics — all plain text that works regardless of source. No changes needed.

2. **OpenAPI specs are richer than SQL introspection.** They include endpoint descriptions, parameter types, response schemas with descriptions, example values, and deprecation notices.

3. **DuckDB reads files natively.** CSV, Parquet, JSON, Excel — zero config, zero loading. A file connection is the simplest onboarding possible.

4. **SaaS data becomes queryable.** Critical business data locked in Stripe, HubSpot, Salesforce, Jira becomes accessible through the same natural language interface.

5. **Cross-source joins unlock new insights.** "Revenue by customer segment" (Stripe + DB), "Sales vs targets" (CSV + DB) — queries that currently require a data engineer.

6. **Pre-built templates reduce friction.** Common APIs ship with known schemas, pagination configs, and sample descriptions.

## Implementation Phases

### Phase 1: Connector Abstraction

Extract a thin `Connector` protocol from existing SQL code. No behavior change — structural refactoring only.

- `connectors/__init__.py` — `Connector` protocol: `test_connection()`, `introspect()`, `fetch_data()`
- `connectors/sql.py` — Current SQLAlchemy implementation behind the protocol
- `connector.yaml` parsing in config
- Tools delegate to connector instead of calling SQLAlchemy directly

### Phase 2: File Connector

Simplest new source type. DuckDB does the heavy lifting.

- `connectors/file.py` — Scan directories, infer schema via DuckDB, read files
- `db-mcp init --type file` CLI flow
- DuckDB dependency added
- File-specific onboarding (directory scan → schema review → domain model)

### Phase 3: API Connector

- `connectors/api/connector.py` — HTTP client with auth and rate limiting
- `connectors/api/introspector.py` — OpenAPI parser + endpoint probing fallback
- `connectors/api/pagination.py` — Cursor, offset, page strategies
- `db-mcp init --type api` CLI flow
- Pre-built templates for common APIs

### Phase 4: Cross-Source Merge

- `merge/duckdb.py` — DuckDB session management, temp table registration
- `merge_data()` MCP tool — load datasets, execute SQL, return merged results
- Cross-source relationship detection during onboarding
- `relationships/cross_source.yaml` vault artifact

### Phase 5: Templates and Polish

- Pre-built connector templates (Stripe, HubSpot, Salesforce, GitHub, Jira)
- Auto-detection of source type from URL
- `connector.yaml` validation and migration
- Documentation and examples

## Relationship to Data Gateway

This doc describes adding API and file support **within db-mcp itself**. The [data-gateway.md](data-gateway.md) describes a broader vision where multiple specialized MCP servers are orchestrated by a gateway.

These are complementary:
- **This doc**: db-mcp natively handles SQL + API + file sources, with DuckDB for cross-source joins
- **Data gateway**: Multiple MCPs behind a unified proxy, each specializing in different source types

The connector work here stays within db-mcp. If the gateway architecture is adopted later, individual connectors could be extracted into standalone MCPs. Either path works — the unified schema format ensures compatibility.

## Open Questions

1. **GraphQL as first-class type?** GraphQL has its own query language and introspection. Dedicated `--type graphql` or treat as API variant?

2. **OAuth2 flows?** Token refresh requires persistent state and sometimes browser-based auth. How does this work in a CLI/MCP context?

3. **API cost tracking?** Some APIs charge per call (Twilio, AWS). Should the fetcher estimate API call costs the way SQL validation estimates query costs?

4. **File change detection?** Should file connections detect changes and re-introspect automatically, or only on explicit `onboarding_discover()`?

5. **DuckDB persistence?** Start session-scoped (in-memory). Add optional persistence for caching fetched API data across sessions?

6. **Streaming / real-time?** WebSocket and SSE APIs are out of scope for now, but worth considering for future dashboards.
