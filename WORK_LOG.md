# WORK_LOG

## 2026-02-20: Fix connection routing bugs (PR #25)

**Branch:** `fix/connection-routing-explain-sql`
**PR:** https://github.com/apelogic-ai/db-mcp/pull/25

### What was done
Fixed 5 call sites where `get_connector()` was called without `connection_path`, causing multi-connection routing to silently use the default connection:

1. **`explain_sql()`** — Added `connection_path` parameter, passed to `get_connector()`
2. **`_validate_sql` caller** — Now passes `connection_path=_resolve_connection_path(connection)` to `explain_sql`
3. **`_get_data` caller** — Same fix
4. **`_test_connection`** — Added `connection` parameter, routes through `_resolve_connection_path`
5. **`_discover_tables_background`** — Added `connection_path` parameter, both call sites updated

### Deferred
BICP agent methods (`_detect_dialect`, `execute_query`, `list_schemas`, etc.) — added TODO comment. Needs design decision on multi-connection BICP sessions.

### Tests
- Baseline: 864 passed
- Final: 867 passed (+3 new tests, 0 regressions)

### Assumptions
- `connection_path=None` preserves existing default-connection behavior (verified by reading `get_connector` implementation)
- BICP agent multi-connection is out of scope for this PR
