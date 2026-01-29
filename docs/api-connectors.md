# API Connectors

**Status**: Conceptual
**Created**: 2026-01-28
**Related**: [data-gateway.md](data-gateway.md)

## Overview

Extend db-mcp to onboard connectors for any API returning structured data (REST, GraphQL, gRPC) alongside existing SQL database support. This enables natural language queries against SaaS platforms (Stripe, HubSpot, Salesforce, Jira, etc.) and internal services, using the same knowledge vault, onboarding flow, and semantic layer that currently powers database connections.

## Problem Statement

Most organizations have critical data locked in SaaS tools and internal APIs with no SQL access. Today, querying this data requires:
- Reading API docs, writing code, handling pagination
- Manual joins between API data and database records
- No semantic layer — every query starts from scratch

Meanwhile, db-mcp already has a mature semantic layer (schema descriptions, domain models, business rules, examples) that is **mostly source-agnostic**. The knowledge layer doesn't care if "customers" lives in PostgreSQL or Stripe — it just needs structured metadata about the data source.

## Conceptual Mapping

API sources map cleanly onto the relational model that db-mcp already understands:

| SQL Concept | API Equivalent | Example |
|---|---|---|
| Catalog | API service name | `stripe`, `hubspot` |
| Schema | Resource group / API version | `/v1/billing`, `/v1/core` |
| Table | Endpoint returning a collection | `/customers`, `/invoices` |
| Column | Field in response object | `customer.name`, `invoice.amount` |
| Row | Single object in response array | One customer JSON object |
| Primary key | Resource ID | `customer.id` |
| Foreign key | ID reference between endpoints | `invoice.customer_id` -> `customer.id` |
| Sample data | `GET /endpoint?limit=5` | First 5 records |
| `SELECT * WHERE` | `GET /endpoint?filter=value` | Query parameters |

## Architecture

```
                    db-mcp
                      |
        +-------------+-------------+
        |                           |
   SQL Connector              API Connector
   (existing)                 (new)
        |                           |
   SQLAlchemy Engine          HTTP Client
        |                           |
   +----+----+              +-------+-------+
   |         |              |               |
  Query   Introspect     Execute Plan    Introspect
  (SQL)   (SHOW/DESC)   (HTTP calls)    (OpenAPI/probe)
                                |
                          +-----+-----+
                          |           |
                      Direct API   DuckDB
                      (simple)     (analytics)
```

### Connector Interface

A new abstraction layer sits between the tools and the execution engine:

```python
class Connector(Protocol):
    """Abstract connector for any data source."""
    connector_type: str                           # "sql" | "api"

    async def test_connection(self) -> dict: ...
    async def introspect(self) -> SourceSchema: ...
    async def execute(self, plan: ExecutionPlan) -> QueryResult: ...


class SQLConnector(Connector):
    """Current db-mcp implementation, refactored behind the interface."""
    connector_type = "sql"
    # Wraps SQLAlchemy — no behavior change


class APIConnector(Connector):
    """New: executes multi-step API call plans."""
    connector_type = "api"
    # HTTP client with auth, pagination, rate limiting
```

The tools layer (`tools/generation.py`, `tools/onboarding.py`) calls `Connector` methods without knowing the source type. The LLM context-building reads the same vault artifacts regardless.

## Onboarding an API Source

### Connection Setup

```bash
db-mcp init stripe --type api

# Interactive prompts:
#   Base URL: https://api.stripe.com
#   Auth type: bearer / api_key / oauth2
#   API key: sk_live_...
#   OpenAPI spec URL (optional): https://raw.githubusercontent.com/.../openapi/spec3.yaml
```

Stored in the vault:

```
~/.db-mcp/connections/stripe/
├── .env                          # API_KEY, BASE_URL (gitignored)
├── connector.yaml                # type: api, auth, spec_url, pagination strategy
├── schema/
│   └── descriptions.yaml         # endpoints described as "tables"
├── domain/
│   └── model.md                  # business entities
├── instructions/
│   └── business_rules.yaml       # "invoice.status=paid means finalized"
└── examples/
    └── *.yaml                    # intent -> API call plan
```

**`connector.yaml`** (new file, replaces `.env`-only config for API sources):

```yaml
type: api
base_url: https://api.stripe.com
auth:
  type: bearer                    # bearer | api_key | oauth2 | basic
  token_env: STRIPE_API_KEY       # reference to .env variable
  header: Authorization           # custom header name if needed
spec:
  type: openapi                   # openapi | graphql_introspection | manual
  url: https://raw.githubusercontent.com/.../spec3.yaml
  version: "3.0"
pagination:
  type: cursor                    # cursor | offset | page | link_header
  cursor_param: starting_after
  cursor_field: id
  page_size: 100
  has_more_field: has_more
rate_limit:
  requests_per_second: 25
  retry_on_429: true
  backoff_strategy: exponential
```

### Schema Discovery

Three introspection strategies, in order of preference:

**1. OpenAPI / Swagger spec** (best case)

Parse the spec to extract endpoints, request/response schemas, parameter types, descriptions. OpenAPI specs are richer than SQL introspection — they include human-written descriptions, parameter constraints, and example values.

```python
async def introspect_from_openapi(spec_url: str) -> SourceSchema:
    """Parse OpenAPI spec into db-mcp schema format.

    Extracts:
    - GET endpoints returning arrays -> "tables"
    - Response schema properties -> "columns" with types
    - Path/query parameters -> filterable fields
    - Descriptions -> column descriptions (often better than DB)
    - Nested objects -> flattened with dot notation (address.city)
    """
```

**2. GraphQL introspection** (self-describing)

GraphQL APIs expose their full type system via the introspection query. This maps directly to schema descriptions with types, nullability, and relationships.

**3. Endpoint probing** (fallback)

Call each known endpoint with `?limit=1`, infer schema from the response JSON. Less reliable but works for any REST API.

```python
async def introspect_from_probing(
    endpoints: list[str],
) -> SourceSchema:
    """Call each endpoint, infer schema from response.

    - Detect field types from values (string, number, bool, datetime)
    - Detect arrays vs objects
    - Detect ID references (fields ending in _id)
    - Flatten nested objects with dot notation
    """
```

### Onboarding Flow

The existing onboarding phases work with minimal changes:

| Phase | SQL (today) | API (new) |
|---|---|---|
| **INIT** | SQLAlchemy `test_connection()` | HTTP `GET /` or health endpoint |
| **SCHEMA** | `SHOW TABLES`, `DESCRIBE` | OpenAPI parse or endpoint probing |
| **DOMAIN** | LLM generates from descriptions | Same — source-agnostic |
| **BUSINESS_RULES** | User adds rules | Same |
| **QUERY_TRAINING** | User adds SQL examples | User adds API call examples |

The INIT and SCHEMA phases need connector-specific implementations. DOMAIN onward is identical.

## Query Execution

### The Core Difference: Plans vs Queries

SQL sources generate a single query string. API sources generate a **multi-step execution plan** because:

- No server-side joins — must fetch collections separately and join client-side
- Pagination — a single "query" may require dozens of HTTP calls
- Dependent fetches — get customer IDs first, then fetch their invoices
- Filtering varies — some APIs filter server-side, others require client-side

### Execution Plan Format

```python
class APICallStep(BaseModel):
    """One HTTP call in an execution plan."""
    method: str = "GET"
    endpoint: str                     # /v1/customers
    params: dict[str, str] = {}       # query parameters
    extract: list[str] = []           # fields to keep from response
    paginate: bool = True             # auto-paginate?
    alias: str                        # reference name for joins

class JoinStep(BaseModel):
    """Client-side join between two fetched collections."""
    left: str                         # alias of left collection
    right: str                        # alias of right collection
    left_key: str                     # join field
    right_key: str
    type: str = "inner"               # inner | left | right

class AggregateStep(BaseModel):
    """Client-side aggregation."""
    source: str                       # alias
    group_by: list[str]
    aggregations: dict[str, str]      # field -> function (SUM, COUNT, AVG)

class ExecutionPlan(BaseModel):
    """Complete API query plan."""
    steps: list[APICallStep | JoinStep | AggregateStep]
    output_fields: list[str]
    limit: int | None = None
```

### Example

User: "Show me total Stripe revenue by customer email this month"

LLM generates:

```yaml
steps:
  - method: GET
    endpoint: /v1/charges
    params:
      created[gte]: "1738368000"    # 2026-01-01
      status: succeeded
    extract: [id, amount, currency, customer]
    paginate: true
    alias: charges

  - method: GET
    endpoint: /v1/customers
    params:
      ids: "{charges.customer}"     # dependent fetch
    extract: [id, email]
    paginate: true
    alias: customers

  - left: charges
    right: customers
    left_key: customer
    right_key: id
    type: inner

  - source: joined_result
    group_by: [email]
    aggregations:
      amount: SUM
output_fields: [email, total_amount]
```

### Two Execution Modes

**Direct API execution** — For simple lookups and small datasets:
- Execute the plan step by step
- In-memory joins using Python dicts
- Good for: "Get customer X", "List recent invoices"

**DuckDB federation** — For analytics and cross-source joins:
- Fetch API data into DuckDB temp tables
- Generate and execute SQL against DuckDB
- Good for: "Revenue by segment", joins with database tables

```python
async def execute_plan(plan: ExecutionPlan) -> QueryResult:
    """Execute API call plan.

    For simple plans (single fetch, no aggregation):
        -> Direct HTTP calls, return results

    For complex plans (joins, aggregations, cross-source):
        -> Fetch all collections
        -> Load into DuckDB as temp tables
        -> Generate SQL for joins/aggregations
        -> Execute in DuckDB
        -> Return results
    """
```

The LLM doesn't need to decide which mode — the execution engine picks based on plan complexity.

## Mixing and Merging Data from Different Sources

### Cross-Source Relationships

A new vault artifact maps relationships between sources:

```yaml
# ~/.db-mcp/connections/{name}/relationships/cross_source.yaml

mappings:
  - name: stripe_customer_to_db_user
    left:
      source: stripe           # connection name
      collection: customers    # endpoint / table
      field: email
    right:
      source: main_db
      collection: public.users
      field: email
    type: one_to_one
    confidence: high           # user-confirmed

  - name: hubspot_contact_to_stripe
    left:
      source: hubspot
      collection: contacts
      field: properties.stripe_id
    right:
      source: stripe
      collection: customers
      field: id
    type: one_to_one
    confidence: detected       # auto-detected from field names
```

These mappings are:
- **Auto-detected** during onboarding (fields named `*_id`, matching email fields, etc.)
- **User-confirmed** through the onboarding flow or business rules
- **Used by the LLM** when generating cross-source query plans

### Cross-Source Query Flow

```
User: "Show me Stripe revenue by customer segment from our database"

1. Intent analysis:
   - "Stripe revenue" -> stripe connection, /v1/charges
   - "customer segment" -> main_db connection, public.users.segment
   - Cross-source join needed

2. Plan generation:
   Step 1: GET stripe /v1/charges?created[gte]=... -> charges
   Step 2: SQL main_db SELECT id, email, segment FROM users -> segments
   Step 3: Load both into DuckDB
   Step 4: DuckDB SQL:
           SELECT s.segment, SUM(c.amount)/100 as revenue
           FROM charges c
           JOIN segments s ON c.customer_email = s.email
           GROUP BY 1

3. Execution:
   - API connector fetches Stripe charges (paginated)
   - SQL connector runs users query
   - DuckDB joins and aggregates
   - Return unified result
```

### Unified Domain Model

The domain model spans all connected sources:

```markdown
# Domain Model

## Customer
A person or organization that uses our product.

**Sources:**
- `main_db.public.users` — account info, segment, created_at
- `stripe.customers` — billing info, payment methods, subscription status
- `hubspot.contacts` — marketing info, lifecycle stage, last activity

**Join keys:**
- main_db.users.email = stripe.customers.email = hubspot.contacts.email

**Business rules:**
- "customer" always means the merged entity from all sources
- Segment comes from main_db (source of truth)
- Revenue comes from Stripe (source of truth)
- When a user says "active customer", check both main_db.users.status = 'active'
  AND stripe.customers.delinquent = false
```

### Conflict Resolution

When the same concept exists in multiple sources:

| Conflict | Strategy |
|---|---|
| Same field, different values | Define canonical source per field in business rules |
| Same metric, different calculation | User picks during onboarding, document in rules |
| Different naming | Business rules synonyms ("Stripe 'charge' = our 'payment'") |
| Different granularity | Define aggregation rules (daily vs per-event) |

## Challenges

### 1. No Composable Query Language

SQL is declarative and composable — one statement can express complex logic. APIs are imperative: fetch, paginate, filter, join client-side. The LLM must generate **execution plans** instead of queries.

**Mitigation**: The plan format is structured (Pydantic models), and the LLM is good at generating structured output. For analytics queries, DuckDB provides SQL composability after data is fetched.

### 2. Pagination and Rate Limits

A SQL query returns all matching rows. An API query for the same data might require 50+ paginated calls with rate limiting.

**Mitigation**: `connector.yaml` defines pagination strategy per source. The execution engine handles pagination transparently. Rate limiters with exponential backoff prevent 429s. Caching avoids re-fetching unchanged data.

### 3. Data Volume Limits

APIs are not designed for bulk analytics. Fetching 1M Stripe charges via API is impractical.

**Mitigation**:
- Cost estimation before execution ("This will require ~500 API calls and take ~2 minutes. Proceed?")
- Encourage users to set up data warehousing for large-scale analytics (Fivetran/Airbyte -> warehouse -> db-mcp SQL connector)
- Cache fetched data in DuckDB for repeat queries within a session
- Time-range filters to limit data volume

### 4. Schema Instability

API responses can change without notice. Fields get added, deprecated, or restructured.

**Mitigation**:
- Periodic re-introspection (compare current response schema to stored schema)
- Knowledge gaps detection works here too — if the LLM references a field that no longer exists, it surfaces as a gap
- Pin to API versions where available (`/v1/`, `/v2/`)

### 5. Authentication Complexity

APIs use diverse auth: API keys, OAuth2 (with refresh), JWT, HMAC signatures, custom headers.

**Mitigation**: Auth is configured in `connector.yaml` and handled by the HTTP client layer. Start with bearer/API key (covers 80% of APIs). Add OAuth2 flow later.

### 6. Nested / Non-Tabular Data

API responses often have nested objects and arrays that don't map cleanly to flat tables.

**Mitigation**:
- Flatten with dot notation: `address.city`, `address.zip`
- Arrays become separate "tables" with parent ID references: `customer.subscriptions` -> virtual `customer_subscriptions` endpoint
- Let the LLM understand nesting through schema descriptions

### 7. Write Safety

SQL has `EXPLAIN` for read-only validation. APIs have no equivalent — a POST creates real data.

**Mitigation**:
- Default to read-only (GET only) unless explicitly enabled
- Write operations require explicit user confirmation
- `connector.yaml` has `allow_writes: false` by default
- Sandbox/test mode detection (Stripe test keys, HubSpot sandbox, etc.)

## Opportunities

### 1. Knowledge Layer is Already Source-Agnostic

Domain models, business rules, examples, metrics, knowledge gaps — all plain text that works regardless of data source. No changes needed to these components.

### 2. OpenAPI Specs Are Richer Than SQL Introspection

An OpenAPI spec provides endpoint descriptions, parameter types, response schemas with descriptions, example values, and deprecation notices. This is better metadata than `SHOW TABLES` + `DESCRIBE` gives for most databases.

### 3. SaaS Data Becomes Queryable

Critical business data locked in Stripe, HubSpot, Salesforce, Jira, GitHub, etc. becomes accessible through the same natural language interface. This is data that most teams can't query today without writing custom code.

### 4. Cross-Source Joins Unlock New Insights

"Revenue by customer segment" requires Stripe (revenue) + internal DB (segments). Today this requires a data engineer to build a pipeline. With API connectors + DuckDB federation, the LLM handles it.

### 5. Pre-Built Connector Templates

Common SaaS APIs have well-known schemas. We can ship templates:

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
    key_fields: [id, email, name, created, delinquent]
  charges:
    endpoint: /v1/charges
    description: "Payment charges"
    key_fields: [id, amount, currency, customer, status, created]
  # ...
```

Users run `db-mcp init my-stripe --template stripe`, enter their API key, and the connection is immediately usable with pre-configured schema, pagination, and sample descriptions.

## Implementation Path

### Phase 1: Connector Abstraction

Extract interfaces from SQL-specific code. Create `Connector`, `Introspector` protocols. Move current SQLAlchemy code behind them. No behavior change — just structural refactoring.

**Files:**
- `connectors/__init__.py` — Protocol definitions
- `connectors/sql.py` — Current implementation, refactored
- `db/connection.py` — Delegates to connector
- `db/introspection.py` — Delegates to connector

### Phase 2: API Connector Core

Implement the API connector with HTTP client, auth, pagination, and OpenAPI introspection.

**Files:**
- `connectors/api/__init__.py`
- `connectors/api/connector.py` — HTTP client with auth and rate limiting
- `connectors/api/introspector.py` — OpenAPI parser + endpoint probing
- `connectors/api/pagination.py` — Cursor, offset, page strategies
- `connector.yaml` schema in models package

### Phase 3: Execution Plans

Replace single-query generation with plan generation for API sources. Add DuckDB as local compute engine for joins and aggregations.

**Files:**
- `connectors/api/planner.py` — LLM generates ExecutionPlan
- `connectors/api/executor.py` — Execute plan (direct or via DuckDB)
- Models: `ExecutionPlan`, `APICallStep`, `JoinStep`, `AggregateStep`

### Phase 4: Cross-Source Federation

DuckDB federation layer. Cross-source relationship mapping. Unified query planning across SQL + API sources.

**Files:**
- `federation/duckdb.py` — DuckDB session management, virtual tables
- `federation/planner.py` — Multi-source query planning
- `relationships/cross_source.yaml` — Vault artifact
- Onboarding updates for relationship detection

### Phase 5: Templates and Polish

Pre-built connector templates for popular APIs. Auto-detection of API type from URL. Improved onboarding UX for API sources.

**Files:**
- `templates/stripe.yaml`, `templates/hubspot.yaml`, etc.
- `connectors/api/templates.py` — Template loader
- Onboarding flow updates for `--template` flag

## Key Design Decisions

### 1. Query Language for API Sources

| Option | Description | Pros | Cons |
|---|---|---|---|
| API call plans (JSON) | LLM generates structured HTTP call sequences | Natural for APIs, precise | New execution engine, no composability |
| SQL against DuckDB | Fetch data first, then SQL | Reuses SQL generation | Requires pre-fetching, wasteful for simple lookups |
| **Hybrid** | Simple lookups -> direct API; analytics -> DuckDB SQL | Best of both | More complex routing logic |

**Decision**: Hybrid. The execution engine decides based on plan complexity. Simple lookups (single endpoint, no joins) go direct. Anything with joins or aggregations routes through DuckDB.

### 2. Schema Storage Format

| Option | Description |
|---|---|
| Separate format for APIs | New `api_schema.yaml` with endpoint-specific fields |
| **Unified format** | Same `descriptions.yaml`, API endpoints stored as "tables" |

**Decision**: Unified. API endpoints are stored as tables in `descriptions.yaml` with a `source_type: api` annotation. This means the entire LLM context-building pipeline works unchanged.

### 3. DuckDB Lifecycle

| Option | Description |
|---|---|
| Persistent | DuckDB database file per connection |
| **Session-scoped** | In-memory DuckDB, populated per query |
| Cached | Persist fetched data across queries, invalidate on TTL |

**Decision**: Start session-scoped (simplest). Add caching in Phase 5 for repeated queries against the same API data.

### 4. Connector Config Location

| Option | Description |
|---|---|
| Extend `.env` | Add API fields to existing env file |
| **New `connector.yaml`** | Dedicated config for connector-specific settings |

**Decision**: New `connector.yaml`. SQL connections continue using `.env` for DATABASE_URL. API connections use `connector.yaml` for base URL, auth type, pagination strategy, rate limits — settings that are too structured for flat env vars. `.env` still holds secrets (API keys).

## Relationship to Data Gateway

This doc focuses on adding API connector support **within db-mcp itself**. The [data-gateway.md](data-gateway.md) describes a broader vision where multiple MCP servers (db-mcp, csv-mcp, superset-mcp) are orchestrated by a gateway.

These are complementary:
- **This doc**: db-mcp natively supports SQL + API sources, with DuckDB for cross-source joins
- **Data gateway**: Multiple specialized MCPs behind a unified proxy, each handling different source types

The API connector work here could later be extracted into a standalone `api-mcp` if the gateway architecture is adopted. Or it stays in db-mcp as a built-in capability. Either path works.

## Open Questions

1. **GraphQL as first-class citizen?** GraphQL has its own query language and type system. Should it get a dedicated connector type (`--type graphql`) rather than being treated as a REST variant?

2. **Webhook / streaming APIs?** Some APIs push data (WebSockets, SSE, webhooks). Out of scope for now, but worth considering for real-time dashboards.

3. **API versioning?** When an API ships v2 with breaking changes, how do we handle schema migration? Auto-detect? User-triggered re-introspection?

4. **Credential management for OAuth2?** Token refresh flows require persistent state and sometimes a browser-based auth flow. How does this work in a CLI tool?

5. **Cost tracking?** Some APIs charge per call (Twilio, AWS). Should the execution engine estimate API call costs the way SQL validation estimates query costs?
