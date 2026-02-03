# Pluggable Data Gateway Plan

**Status**: Draft
**Created**: 2026-02-02
**Owner**: db-mcp

## Summary

We will evolve db-mcp into a **pluggable data gateway**, not a universal gateway. The system will support a curated set of connectors through a stable, internal abstraction. End users will continue to “talk to the data” without needing to know whether a source is SQL-like or REST.

## Goals

- Keep the user-facing model consistent: tables, columns, rows.
- Support **two connector classes** internally:
  - **SQL-like** (Metabase, Superset, Dune, etc.)
  - **REST** (Stripe, HubSpot, Jira, GitHub, etc.)
- Hide connector type from users and LLM prompts.
- Make connectors **pluggable**: add new sources by implementing a stable interface, not by expanding ad hoc logic.

## Non-Goals

- We are not building a universal data gateway for all sources.
- We are not exposing connector types in the UI or tool surface.
- We are not introducing a generic “API wrapper” with limitless configuration.

## Key Principles

1. **Relational Envelope**
   All sources are represented as catalogs/schemas/tables/columns. Results are always tabular.

2. **Capability Hints, Not Type Exposure**
   The LLM sees capability metadata (supports SQL, supports filters, pagination) but not “SQL vs REST.”

3. **Pluggable Connectors**
   Each connector implements a small, typed interface. The registry routes calls based on source configuration.

## Connector Classes

### 1. SQL-Like Connectors

**Examples**: Metabase, Superset, Dune

**Core capability**: Accept SQL-ish queries and return tables.

Interface contract:
- `query(sql: str) -> TabularResult`
- `introspect() -> Schema` (if supported)
- `validate(sql: str) -> ValidationResult` (optional)

### 2. REST Connectors

**Examples**: Stripe, HubSpot, Jira, GitHub

**Core capability**: Fetch resources with filters/pagination and return tables.

Interface contract:
- `fetch(resource: ResourceSpec, filters: FilterSpec) -> TabularResult`
- `discover() -> Schema` (OpenAPI, introspection, or probing)

## Unified Tool Surface

The LLM and UI use the same tool surface regardless of connector type:

- `list_tables(source)`
- `describe_table(source, table)`
- `get_data(source, query_or_resource)`

The router decides how to satisfy the call.

## Schema Representation Rules

### SQL-Like Sources

- Introspection results map naturally to tables/columns.
- Table names are scoped by connector name (e.g., `metabase.orders`).

### REST Sources

- Each collection endpoint becomes a table.
- Nested objects are flattened using dot notation: `address.city` → `address_city`.
- Arrays become child tables with a synthetic FK back to the parent.
- IDs are treated as primary keys when possible.

## Capability Metadata (Internal Only)

Each source/table can include a minimal capability block to guide routing and planning:

- `supports_sql: bool`
- `supports_filters: bool`
- `supports_pagination: bool`
- `page_size_limit: int | null`

This is used internally and in prompts, but **not** exposed to the user as a connector type.

## Routing Strategy

A lightweight router chooses the connector based on:
- Source configuration
- Target table
- Tool invoked (`get_data` with SQL vs resource spec)

The routing logic must be deterministic and testable.

## Configuration

Connections remain in the vault structure with a connector config file, e.g.:

```
~/.db-mcp/connections/{name}/
├── connector.yaml
├── schema/descriptions.yaml
├── domain/model.md
└── ...
```

Proposed `connector.yaml` shape (draft):

```yaml
type: sql_like | rest
provider: metabase | superset | stripe | github | ...
capabilities:
  supports_sql: true
  supports_filters: false
  supports_pagination: false
```

### Metabase Connector Example

`connector.yaml`:

```yaml
type: metabase
base_url: https://metabase.example.com
database_id: 12
database_name: analytics
auth:
  username_env: MB_USERNAME
  password_env: MB_PASSWORD
```

`.env` in the same connection directory:

```
MB_USERNAME=demo@example.com
MB_PASSWORD=supersecret
```

## Implementation Phases

### Phase 1: Abstraction Layer

- Add base connector interfaces for SQL-like and REST.
- Add a registry and router.
- Keep existing SQL connectors working with zero UX change.

### Phase 2: REST Prototype

- Implement one REST connector end-to-end (e.g., Stripe).
- Generate `descriptions.yaml` from OpenAPI or endpoint probing.

### Phase 3: SQL-Like Prototype

- Implement one SQL-like connector (e.g., Metabase or Superset).
- Ensure `query(sql)` works with validation and row limits.

### Phase 4: UX Integration

- Hide type in UI; show sources uniformly.
- Ensure all tooling uses unified surface.

## Open Questions

- Which SQL-like connector should be first: Metabase or Superset?
- Which REST connector should be first: Stripe or GitHub?
- Where should capability metadata live: in `connector.yaml` or generated in `descriptions.yaml`?
- How do we version connector schemas and handle migrations?
