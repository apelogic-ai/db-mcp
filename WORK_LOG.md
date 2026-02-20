# db-mcp Work Log

## 2026-02-20: Multi-Connection QA (v0.5.21)

**Agent:** sub-qa-dbmcp  
**Duration:** 41 minutes  
**Environment:** Source build at ~/dev/db-mcp, v0.5.21

### Summary

Executed comprehensive QA testing of the multi-connection feature. Found 2 critical bugs in MCP tool layer that make the feature unusable for Claude Desktop users, despite BICP/CLI working correctly.

### Key Findings

1. **BUG: list_connections MCP tool missing connections** - Only returns 2/3 connections. The rna-research connection (which lacks connector.yaml) is omitted. CLI and BICP correctly show all 3 connections.

2. **BUG: connection parameter crashes on 'description' field** - SQLConnectorConfig doesn't support the `description` field in connector.yaml. When a connection has this field (chinook-copy), all MCP tools crash with: `SQLConnectorConfig.__init__() got an unexpected keyword argument 'description'`

3. **BICP works perfectly** - All 3 connections visible, switching works, no crashes. This confirms the bug is in the MCP tool layer, not the core connection management.

4. **Test suite healthy** - 840/840 Python tests passing, but they don't cover multi-connection scenarios with varying connector.yaml schemas.

### What Works

✅ CLI connection management (`db-mcp list`, `db-mcp use <name>`)  
✅ BICP protocol (`connections/list`, `connections/switch`, `connections/get`)  
✅ MCP tools for connections WITHOUT description field (playground)  
✅ Shell tool (doesn't load connector config, so no crash)  
✅ All 840 unit tests

### What's Broken

⛔ MCP `list_connections` - Missing connections without connector.yaml  
⛔ MCP tools with `connection` param - Crash on unsupported YAML fields  
⚠️ Error messages - Generic "validation required" instead of "connection not found"

### Root Cause

**MCP tool layer** strictly requires valid connector.yaml and crashes on schema variations.  
**BICP layer** is more robust - reads from state.yaml + directory structure, doesn't crash on extra fields.

This is a **code path divergence** - the two interfaces (MCP stdio vs BICP HTTP) use different connection loading logic with different error handling.

### Impact Assessment

**For Claude Desktop users:** Multi-connection is **broken**. The list_connections tool doesn't show all connections, and any connection with a description field crashes tools.

**For UI users:** Multi-connection **works**. BICP protocol handles all edge cases correctly.

**For release:** **Not production-ready** for Claude Desktop. Needs BUG-1 and BUG-2 fixed + integration tests before release.

### Testing Performed

**Phase A: CLI** (PASS)
- List connections, switch active, verify state changes

**Phase B: MCP Tools via mcporter** (FAIL)
- list_connections: Missing rna-research
- run_sql with connection param: Works for playground, crashes for chinook-copy
- mcp_setup_status with connection param: Same behavior
- shell with connection param: Works (doesn't load connector)

**Phase D: BICP Protocol** (PASS)
- connections/list: All 3 connections returned
- connections/switch: Works correctly
- connections/get: Works correctly

**Phase 1: CLI Smoke Tests** (PASS)
- Version, help, status, list all work

**Phase 3: MCP Basic Tests** (PASS)
- ping, run_sql (single connection) work

**Phase 6: Python Test Suite** (PASS)
- 840/840 tests passing in 52s

### Recommendations

**Priority 1 (Blockers):**
1. Add `description: Optional[str] = None` to SQLConnectorConfig dataclass
2. Fix list_connections to work without connector.yaml (use state.yaml)
3. Add integration tests for multi-connection MCP tool dispatch

**Priority 2 (UX):**
4. Better error messages for invalid/missing connections
5. Document connector.yaml schema (required/optional fields)
6. Add `db-mcp validate <connection>` command

**Priority 3 (Long-term):**
7. Consolidate BICP/MCP connection loading (single code path)
8. Add mutation tests for malformed configs
9. Require connector.yaml (generate on init if missing)

### Assumptions Made

1. The 3 connections (playground, chinook-copy, rna-research) represent real user scenarios:
   - playground: standard setup with connector.yaml
   - chinook-copy: copy with description field added
   - rna-research: legacy setup without connector.yaml

2. mcporter correctly simulates Claude Desktop's MCP stdio protocol

3. The `description` field was added intentionally (not a typo) and should be supported

### E2E Verification Needed

After fixing bugs:
1. Re-test all MCP tools with chinook-copy (description field)
2. Re-test list_connections - should return all 3
3. Test error message for nonexistent connection
4. Run full test suite to ensure no regressions
5. Test in real Claude Desktop (not just mcporter simulation)

### Files Modified

None - QA is read-only. Report written to `~/.openclaw/workspace/memory/product-qa/2026-02-20-multi-connection-qa.md`

### Cleanup Performed

- Killed UI server (port 18090)
- Restored mcporter.json backup
- No temp files left behind

### Next Steps

Main session should:
1. Review the QA report
2. File GitHub issues for BUG-1 and BUG-2
3. Create PRs to fix both bugs
4. Add integration tests for multi-connection edge cases
5. Re-run this QA after fixes to verify
