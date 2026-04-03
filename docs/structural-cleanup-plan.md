# Structural Cleanup Plan

Targeted fixes identified during architectural review. Grouped into two areas:
CLI/MCP boundary issues and `packages/data/` internal structure issues.
Everything not listed here should be left alone.

---

## Part A — CLI / MCP Boundary

### A1. Unify connection resolution (bug risk)

**Problem**

The CLI and MCP server resolve the active connection through divergent mechanisms:

- CLI: `db_mcp_cli.connection.get_active_connection()` reads `~/.db-mcp/config.yaml`
- MCP: `ConnectionRegistry.get_instance()` reads env vars (`CONNECTION_NAME`, `CONNECTION_PATH`)

Any operation that works in the CLI but routes differently in MCP (or vice versa) will
produce silent "works locally, fails in Claude" bugs. This is the highest-risk divergence
in the codebase.

**Fix**

Make `ConnectionRegistry` the single source of truth for both surfaces:

- CLI commands that call service-layer functions should resolve through
  `ConnectionRegistry.get_instance()`, not the parallel CLI helpers
- CLI-specific write operations (`set_active_connection`, writing `config.yaml`) remain
  in the CLI — those are presentation concerns, not resolution concerns
- The registry should be able to bootstrap from `config.yaml` as a fallback when env
  vars are absent, so CLI usage without env vars continues to work

**Files**

- `packages/cli/src/db_mcp_cli/connection.py` — CLI resolution path
- `packages/core/src/db_mcp/services/connection.py` — service-layer resolution
- `packages/core/src/db_mcp/registry.py` — `ConnectionRegistry`, target for unification

---

### A2. Deduplicate `_resolve_connection` helpers

**Problem**

At least 8 CLI command modules contain an identical (or near-identical) 4-line helper:

```
schema_cmd.py, query_cmd.py, examples_cmd.py, rules_cmd.py,
gaps_cmd.py, metrics_cmd.py, domain_cmd.py, discover_cmd.py
```

Each defines its own `_resolve_connection()` locally. Any fix or change has to be
applied 8 times.

**Fix**

Extract to `db_mcp_cli.connection._resolve_connection()` and replace all 8 local copies
with an import. Once A1 is done, this helper should delegate to `ConnectionRegistry`.

---

## Part B — `packages/data/` Internal Structure

### B1. Fix `APIConnector` inheritance

**Problem**

`APIConnector` extends `FileConnector` to reuse DuckDB for executing SQL over fetched
API data. This is implementation inheritance, not a conceptual is-a relationship. A REST
API connector is not a file connector. The type system lie forces the gateway dispatcher
to explicitly order `APIAdapter` before `FileAdapter` to prevent misrouting — a fragile
implicit dependency.

**Fix**

Extract the DuckDB in-memory execution path into a standalone `DuckDBExecutor` (or
`DuckDBQueryMixin`) in `packages/data/src/db_mcp_data/db/duckdb.py`. Both
`FileConnector` and `APIConnector` compose it rather than inheriting it. The inheritance
link between `APIConnector` and `FileConnector` is severed. The dispatcher ordering
constraint can then be removed or made explicit via `can_handle()` logic rather than
load order.

**Files**

- `packages/data/src/db_mcp_data/connectors/api.py`
- `packages/data/src/db_mcp_data/connectors/file.py`
- `packages/data/src/db_mcp_data/gateway/dispatcher.py`
- New: `packages/data/src/db_mcp_data/db/duckdb.py`

---

### B2a. Clean up QueryStore naming and dead code

Low-risk, purely cosmetic. Do this first, in isolation.

**Fix**

- Delete dead `Task*` aliases (`TaskStatus`, `QueryTask`, `QueryTaskStore`,
  `get_task_store`). Grep for callers, update them.
- Rename `QueryStatus` states to avoid collision with `ExecutionState`:

| Current | Rename to |
|---|---|
| `VALIDATED` | `READY` |
| `PENDING` | `DISPATCHED` |
| `RUNNING` | (drop — terminal status read from `ExecutionStore`) |
| `COMPLETE` | (drop — terminal status read from `ExecutionStore`) |
| `ERROR` | (drop — terminal status read from `ExecutionStore`) |
| `EXPIRED` | `EXPIRED` (keep) |

- Convert `Query` from `@dataclass` to Pydantic model for consistency with
  `ExecutionStore` models. Drop the manual `to_dict()`.

**Files**

- `packages/data/src/db_mcp_data/execution/query_store.py`
- All callers of `get_task_store()` / `TaskStatus` / `QueryTask`

---

### B2b. Remove duplicate result storage

Safe behavioral change, no schema migration required.

**Context**

When execution completes, result data exists in both:
- `QueryStore._queries[query_id].result` (in-memory, GC'd after 1 hour)
- `ExecutionStore` `data_json` column (SQLite, persistent)

**Fix**

Drop the `result` field from `Query`. After `run_sql` dispatches to `ExecutionStore`,
callers that want results call `get_result(execution_id)` — they have no reason to read
from `QueryStore`. Update any callers that currently read `query.result` to use
`ExecutionStore.get_result()` instead.

**Files**

- `packages/data/src/db_mcp_data/execution/query_store.py`
- `packages/core/src/db_mcp/services/query.py` — callers of `query.result`

---

### B2c. Wire REST endpoint queries through ExecutionEngine

Behavioral change. Requires B2a and B2b to be done first.

**Context**

`api_query` (REST `EndpointQuery`) fires `connector.query_endpoint()` and returns.
No `execution_id`, no SQLite record, no `get_result` polling, no idempotency.
SQL-over-API queries (`sql_mode: api_sync/api_async`) already go through
`ExecutionEngine` correctly — the gap is only REST endpoint queries.

**Fix**

Wire `api_query` through `ExecutionEngine.submit_sync()`. The runner calls
`connector.query_endpoint()` instead of executing SQL. Return `execution_id` alongside
the result so the agent can poll `get_result` for large responses. The two-phase
`QueryStore` gate remains SQL-only — REST endpoint calls skip it and go directly to
`ExecutionEngine.submit_sync`.

**Files**

- `packages/core/src/db_mcp/tools/api.py`
- `packages/data/src/db_mcp_data/execution/engine.py`

---

### B2d. Generalize ExecutionRequest payload model (migration-focused PR)

Schema-breaking change. Requires B2c. Deserves its own focused PR.

**Context**

`ExecutionRequest` has `sql: str | None` and `sql_hash` as first-class fields.
`ExecutionStore` has `sql TEXT` and `sql_hash TEXT` columns. This works for SQL but
blocks REST endpoint queries from using the same store cleanly.

**Fix**

Replace `sql` + `sql_hash` in `ExecutionRequest` and the SQLite schema with:
- `query_type: str` — `"sql"`, `"endpoint"`, `"sql_api"`
- `payload: dict` — type-specific envelope (SQL string, or endpoint+params dict)
- `payload_hash: str | None` — SHA-256 of normalized payload for idempotency

Requires a SQLite schema migration for existing `executions.sqlite` files (add
`query_type`, `payload_json`, `payload_hash` columns; keep `sql` as a deprecated
read-only column during transition).

**Files**

- `packages/data/src/db_mcp_data/execution/models.py`
- `packages/data/src/db_mcp_data/execution/store.py`
- `packages/data/src/db_mcp_data/execution/engine.py`
- All `ExecutionRequest` construction sites across `packages/core/` and `packages/mcp-server/`

---

### B3. Relocate top-level loose modules

**Problem**

Four modules sit at the `db_mcp_data` package root with no coherent relationship:

| Module | Current location | Problem |
|---|---|---|
| `capabilities.py` | root | Connector configuration concern |
| `dialect.py` | root | Connector configuration concern |
| `connector_templates.py` | root | Connector catalog/factory concern |
| `connector_compat.py` | root | Metabase-specific normalization |

**Fix**

| Module | Move to |
|---|---|
| `capabilities.py` | `connectors/capabilities.py` |
| `dialect.py` | `connectors/dialect.py` |
| `connector_templates.py` | `connectors/templates.py` |
| `connector_compat.py` | `connector_plugins/builtin/metabase.py` (merge into existing file) or `connector_plugins/compat.py` |

Update all imports. Keep re-exports at the old paths for one release if anything outside
`packages/data/` imports from the root directly.

---

### B4. Move response contracts to `db_mcp_models`

**Problem**

`contracts/response_contracts.py` defines MCP tool response schemas:
`RunSqlSyncSuccessContract`, `RunSqlAsyncSubmittedContract`, `GetResultCompleteContract`,
etc. These are consumed by the MCP server and core services — they are shared models,
not data-layer concerns. They have no business being in `db_mcp_data`.

**Fix**

Move to `packages/models/src/db_mcp_models/execution.py` (or a new
`packages/models/src/db_mcp_models/contracts.py`). Update all imports in
`packages/core/` and `packages/mcp-server/`. The `contracts/` directory in
`packages/data/` can be removed once empty.

**Files**

- `packages/data/src/db_mcp_data/contracts/response_contracts.py` → `packages/models/`
- All importers in `packages/core/` and `packages/mcp-server/`

---

### B5. Move connector contract to `db_mcp_models`

**Problem**

`contracts/connector_contracts.py` contains `ConnectorContractV1`, a Pydantic model for
the serialized connector spec (the `connector.yaml` schema). This is a shared data
model used across CLI, core, and data packages. It belongs in `db_mcp_models` alongside
other shared Pydantic models.

**Fix**

Move to `packages/models/src/db_mcp_models/connector.py`. Update all imports.

**Files**

- `packages/data/src/db_mcp_data/contracts/connector_contracts.py` → `packages/models/`
- All importers across the repo

---

## Part C — Connector Capability Gaps

These are not structural cleanups — they are missing features in the connector layer.
Tracked here for completeness; implement separately from the cleanup work above.

### C1. JSON-RPC endpoint support

**Status:** Not supported. Gap.

`APIConnector` handles REST (GET with query params, POST with JSON/form body) and
SQL-over-API. It does not handle JSON-RPC, which uses a specific POST envelope:

```json
{"jsonrpc": "2.0", "method": "getLedger", "params": {"slot": 12345}, "id": 1}
```

Today a JSON-RPC endpoint could be configured as a `POST` with `body_mode: json`, but
the caller would need to manually embed `jsonrpc`, `method`, and `id` in the params,
and the response unwrapping (`result` vs `error` in the JSON-RPC envelope) is not
handled. It would be fragile and per-endpoint manual work.

**Fix**

Add `body_mode: jsonrpc` to `APIEndpointConfig` with a companion `rpc_method: str`
field:

```yaml
endpoints:
  - name: get_ledger
    path: /rpc
    method: POST
    body_mode: jsonrpc
    rpc_method: getLedger
    query_params:
      - name: slot
        ...
```

Connector logic change in `_send_non_get`:
1. Wrap params in `{"jsonrpc": "2.0", "method": rpc_method, "params": ..., "id": <uuid>}`
2. POST it
3. On response: return `response["result"]` on success, raise on `response["error"]`

This is a small, self-contained addition. No structural changes required.

**Files**

- `packages/data/src/db_mcp_data/connectors/api_config.py` — add `body_mode` variant + `rpc_method` field to `APIEndpointConfig`
- `packages/data/src/db_mcp_data/connectors/api.py` — branch in `_send_non_get`
- Connector template YAML files if any cover JSON-RPC APIs

---

## Sequencing

```
B4 + B5 ──┐
           ├──► B3 ──► A2 ──► A1 ──► B2a ──► B2b ──► B2c ──► B2d ──► B1 ──► C1
          (parallel)
```

1. **B4 + B5** (parallel) — move contracts to models; pure file moves, no logic changes
2. **B3** — relocate top-level modules within data; update internal imports
3. **A2** — deduplicate CLI helpers; mechanical, can run alongside B3
4. **A1** — connection resolution unification; do this before B2 work, not after —
   it is a boundary correction that reduces confusion for all subsequent work
5. **B2a** — dead alias removal + state renames + Pydantic conversion; safe, isolated
6. **B2b** — drop duplicate result storage; depends on B2a
7. **B2c** — wire REST queries through ExecutionEngine; depends on B2a + B2b
8. **B2d** — generalize payload model (migration PR); depends on B2c, own focused PR
9. **B1** — fix APIConnector inheritance; most invasive, own focused PR
10. **C1** — JSON-RPC support; independent feature slice, any time after B2c
