# API Connector DuckDB Cleanup

## Problem

`APIConnector` contains a silent DuckDB fallback in the SQL execution path.
When a connector has `supports_sql: false` and `submit_sql()` is called, it
delegates to an internal `FileConnector` instance that queries synced JSONL
files via an in-memory DuckDB connection:

```python
# current behaviour in APIConnector.submit_sql()
if not supports_sql:
    rows = self._file_connector.execute_sql(sql, None)   # ← silent DuckDB
    return {"mode": "sync", "rows": rows}
```

This is a write-only dead end. The in-memory DuckDB instance is private to
the connector; nothing outside it can query the same store. The only plausible
use case — cross-connection aggregation across multiple API fetches in a
meta-query — does not exist in the codebase. Until it does, placing API data
into DuckDB serves no purpose.

### Consequences

- **Silent staleness.** `submit_sql` silently executes against JSONL files
  from the last `sync()` call. If sync has not been run, there are no views
  and DuckDB raises a `CatalogException`. If it has been run, the data may be
  arbitrarily old. Neither case is visible to the caller.
- **Sync is a hidden prerequisite.** There is no indication at the call site
  that `sync()` must precede `submit_sql`. Agents and CLI users discover the
  requirement via failure.
- **Dead end.** The DuckDB store is in-process and has no external API. Data
  written there cannot be reached by any other query path.

### What DuckDB is legitimately used for

`FileConnector` uses DuckDB to query local CSV, Parquet, and JSONL files.
That is its natural purpose and is unaffected by this plan.

---

## What is not changing

- `FileConnector` and `DuckDBExecutor` — untouched.
- `APIConnector.sync()` — remains as a standalone utility for pulling API
  data to disk. Useful independently of query execution.
- `APIConnector._file_connector` — stays for schema introspection fallbacks
  (`get_tables`, `get_columns`, etc. fall back to JSONL-based schema when
  the API has no schema endpoint). This is separate from SQL execution.
- All `supports_sql: true` connectors (Dune, etc.) — unaffected. Their SQL
  execution path sends SQL to the API directly and does not touch DuckDB.

---

## Plan

### Step 1 — Remove the SQL execution fallback

**File:** `packages/data/src/db_mcp_data/connectors/api.py`

In `APIConnector.submit_sql()`, replace the DuckDB fallback branch with a
clear error:

```python
# before
if not supports_sql:
    rows = self._file_connector.execute_sql(sql, None)
    return {"mode": "sync", "rows": rows}

# after
if not supports_sql:
    raise ValueError(
        "This connector does not support SQL execution. "
        "Use api_query to fetch endpoint data directly."
    )
```

Same change applies in `CatalogRoutingAPIConnector.submit_sql()` in
`packages/data/src/db_mcp_data/connectors/api_sql.py` — the identical
fallback branch is present there.

**Tests:** Update any unit tests that exercise the DuckDB fallback path.
Add a test asserting the new error is raised for a non-SQL connector.

### Step 2 — Verify no connector relies on the fallback

Grep for connector YAML files with `supports_sql: false` (or absent) that are
used with `run_sql`. If any are found, those connectors need migration:
- If the intent is REST endpoint access: use `api_query`.
- If the intent is SQL over synced data: document as unsupported until a
  cross-connection meta-query feature is built.

```bash
# find connector configs
grep -r "supports_sql" ~/.db-mcp/connections/
# find uses of run_sql / submit_sql in connection-specific scripts
```

### Step 3 — Assess `_file_connector` for schema introspection (follow-on)

Determine whether any deployed connector actually exercises the
`_file_connector` schema fallback path — i.e., whether `get_tables()` or
`get_columns()` falls through to JSONL-based introspection in practice.

If no connector does, `_file_connector` can be removed from `APIConnector`
entirely. Schema introspection would then come exclusively from the API's
own schema endpoint, or return empty.

This is a follow-on cleanup in a separate PR, not part of Steps 1–2.

---

## Future: explicit DuckDB for cross-connection aggregation

If a meta-query feature is built that aggregates across multiple API
connections, DuckDB becomes the right in-process store for that. At that
point, the API for it should be explicit:

```python
# hypothetical future API
result = await meta_query.run(
    sources={"orders": ("api_conn_a", "orders"), "customers": ("api_conn_b", "customers")},
    sql="SELECT o.id, c.name FROM orders o JOIN customers c ON o.customer_id = c.id",
)
```

This is out of scope here. The removal in Step 1 does not foreclose it —
it just ensures the capability is built intentionally rather than discovered
as a side effect of a silent fallback.

---

## Sequencing

```
Step 1  →  Step 2  →  Step 3 (separate PR, lower priority)
```

Steps 1 and 2 are a single PR. Step 2 is a verification gate before merging,
not a separate change.

Step 3 is independent and can be deferred until there is a reason to touch
`APIConnector.__init__`.

---

## Files changed (Steps 1–2)

| File | Change |
|---|---|
| `packages/data/src/db_mcp_data/connectors/api.py` | Remove DuckDB fallback in `submit_sql` |
| `packages/data/src/db_mcp_data/connectors/api_sql.py` | Same, in `CatalogRoutingAPIConnector.submit_sql` |
| `packages/data/tests/` | Update/add tests for the error path |
