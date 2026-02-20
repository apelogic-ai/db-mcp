# Multi-Connection MCP Bugs Fix - Work Log

**Date:** 2026-02-20  
**Branch:** `fix/multi-connection-mcp`  
**Commit:** abbecdf  

## Summary

Fixed two HIGH-severity bugs in db-mcp v0.5.21 that made the multi-connection feature unusable for Claude Desktop (MCP stdio) users:

1. **Bug 1:** `discover()` skips connections without connector.yaml 
2. **Bug 2:** `SQLConnectorConfig` crashes on unknown fields (like `description`)

## Changes Made

### 1. Registry Discovery Fix (`packages/core/src/db_mcp/registry.py`)

**Problem:** The `discover()` method only found connections with `connector.yaml` files, missing connections that only had `state.yaml` and knowledge vault files.

**Solution:**
- Added `_detect_dialect_from_database_url()` helper function to extract SQL dialect from DATABASE_URL
- Modified `discover()` to check for either `connector.yaml` OR `state.yaml` (not just connector.yaml)
- Added dialect detection from `.env` file's `DATABASE_URL` when connector.yaml is missing
- Used `state.yaml` existence as the validation criterion for real connections
- Matched the behavior of BICP handler for consistency

**Key Changes:**
```python
# Before: Only checked connector.yaml
if not yaml_path.exists():
    continue

# After: Check connector.yaml OR state.yaml  
if not yaml_path.exists() and not state_yaml_path.exists():
    continue
```

### 2. Connector Config Field Support

**Problem:** `SQLConnectorConfig` and other connector configs crashed when `connector.yaml` contained a `description` field or other unknown fields.

**Solution:**
- Added `description: str = ""` field to `SQLConnectorConfig` (`packages/core/src/db_mcp/connectors/sql.py`)
- Added `description: str = ""` field to `FileConnectorConfig` (`packages/core/src/db_mcp/connectors/file.py`)
- Updated `_load_file_config` to handle description field (`packages/core/src/db_mcp/connectors/__init__.py`)
- Added defensive filtering to `_load_sql_config` using dataclass fields introspection to prevent future crashes from unknown fields

**Key Changes:**
```python
# Before: Passed all fields except type/capabilities (unsafe)
**{k: v for k, v in data.items() if k not in {"type", "capabilities"}}

# After: Only pass valid dataclass fields (safe)
valid_fields = {f.name for f in fields(SQLConnectorConfig) if f.init}
filtered_data = {k: v for k, v in data.items() if k in valid_fields}
```

### 3. Comprehensive Test Coverage

**New Test File:** `packages/core/tests/test_multi_connection_mcp_bugs.py`

Added 12 new tests covering:
- Discovering connections with only `state.yaml` 
- Skipping stray directories without `state.yaml`
- Preferring `connector.yaml` over `.env` detection when both exist
- Dialect detection from various DATABASE_URL formats
- Handling `description` field in SQL/File connector configs
- Defensive filtering of unknown fields 
- Error messages for invalid connection names
- Integration with `resolve_connection()` function

**Test Results:**
- All 852 tests pass (840 existing + 12 new)
- Zero regressions introduced

## Verification

### Manual Testing
✅ **CLI:** `uv run db-mcp list` now shows all 3 connections (was 2/3 before)  
✅ **Tests:** All new bug-specific tests pass  
✅ **Regression:** Full test suite passes with zero failures  
✅ **Linting:** Code style compliant with project standards  

### Expected MCP Tool Behavior (Post-Fix)
- `list_connections` MCP tool should return all 3 connections including `rna-research`
- Connections with `description` in `connector.yaml` should not crash MCP tools
- Invalid connection names should show helpful error messages with available connections

## Assumptions Made

1. **State.yaml as validation criterion:** Used existence of `state.yaml` to determine if a directory is a real connection (not just a stray folder). This matches the BICP handler logic.

2. **Connector.yaml takes precedence:** When both `connector.yaml` and `.env` exist, values from `connector.yaml` override dialect detection from `.env`. This maintains explicit configuration priority.

3. **Description field universally needed:** Added `description` field to both `SQLConnectorConfig` and `FileConnectorConfig` for consistency, since users might add descriptions to any connector type.

4. **Backwards compatibility:** All changes maintain backward compatibility - existing connections without description fields continue to work unchanged.

## What Needs E2E Verification

These changes fix the MCP tool layer bugs, but comprehensive E2E testing should verify:

1. **MCP stdio testing:** Test with actual Claude Desktop via mcporter or similar tool:
   - `mcporter call db-mcp list_connections` should return 3 connections
   - `mcporter call db-mcp run_sql --args '{"sql":"SELECT 1","connection":"chinook-copy"}'` should work (no description field crash)
   - `mcporter call db-mcp run_sql --args '{"sql":"SELECT 1","connection":"rna-research"}'` should work (no connector.yaml connection)

2. **BICP protocol parity:** Verify MCP tools now return the same connection list as BICP `connections/list`

3. **Real multi-connection scenarios:** Test switching between connections that have different configurations (some with connector.yaml, some without)

4. **Error handling:** Test that invalid connection names now show the expected error messages with available connections listed

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `packages/core/src/db_mcp/registry.py` | Modified | Added dialect detection helper, updated discover() method |
| `packages/core/src/db_mcp/connectors/sql.py` | Modified | Added description field to SQLConnectorConfig |
| `packages/core/src/db_mcp/connectors/file.py` | Modified | Added description field to FileConnectorConfig |
| `packages/core/src/db_mcp/connectors/__init__.py` | Modified | Updated load functions with defensive filtering |
| `packages/core/tests/test_multi_connection_mcp_bugs.py` | Created | Comprehensive test coverage for both bugs |

## Testing Summary

- **Total Tests:** 852 (840 existing + 12 new)
- **Pass Rate:** 100%
- **Test Runtime:** ~52 seconds
- **Lint Status:** ✅ All checks passed
- **Coverage:** Added tests for both MCP bugs and edge cases

## Next Steps

1. **Manual E2E verification** with mcporter and Claude Desktop
2. **Compare MCP vs BICP output** to ensure perfect parity  
3. **Consider adding integration tests** that test the full MCP protocol stack
4. **Update documentation** if connector.yaml schema now officially supports description field