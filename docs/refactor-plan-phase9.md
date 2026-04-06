# Refactor Plan — Phase 9: Cleanup & Layering

Post-Phase-8 housekeeping. Five workstreams, ordered by risk (lowest first).

---

## 1. Remove compatibility shims

**Effort**: Small (16 call sites across the repo)
**Risk**: Low — mechanical find-and-replace

Four files in `packages/data/` are pure re-export shims left over from the Phase 8 split:

| Shim file | Re-exports from | Call sites |
|-----------|----------------|------------|
| `db_mcp_data/connector_templates.py` | `connectors.templates` | 0 |
| `db_mcp_data/dialect.py` | `connectors.dialect` | 0 |
| `db_mcp_data/contracts/connector_contracts.py` | `db_mcp_models.connector` | 12 |
| `db_mcp_data/contracts/response_contracts.py` | `db_mcp_models.execution_contracts` | 4 |

**Steps**:
1. Grep for each shim's import path, update to the canonical module
2. Update `unittest.mock.patch` strings in tests (the import path must match the call site)
3. Delete the shim files
4. Run full test suite across all packages

---

## 2. Narrow exception handling in connection.py

**Effort**: Small (4 sites)
**Risk**: Low — each has an obvious narrow type

Four `except Exception: pass` blocks in `packages/core/src/db_mcp/services/connection.py`:

| Line | Context | Narrow to |
|------|---------|-----------|
| 219 | YAML config load | `(FileNotFoundError, yaml.YAMLError)` |
| 242 | URL parsing | `(ValueError, AttributeError)` |
| 257 | .env file read | `(FileNotFoundError, ValueError)` |
| 266 | State YAML load | `(FileNotFoundError, yaml.YAMLError)` |

**Steps**:
1. Replace each `except Exception` with the narrow types
2. Add `logger.debug` for unexpected failures (not `pass`)
3. Verify with connection tests

---

## 3. Split god files

**Effort**: Medium (6 files, largest 1,864 lines)
**Risk**: Medium — requires test path updates

| File | Lines | Split strategy |
|------|-------|---------------|
| `benchmark/runner.py` | 1,864 | Extract `BenchmarkReport`, `QueryExecutor`, `ScoreCalculator` |
| `useWizardState.ts` | 1,769 | Already split once; remainder is cohesive. Low priority. |
| `tools/generation.py` | 1,602 | Extract `PromptBuilder`, `SqlGenerator`, `ResponseFormatter` |
| `connectors/api.py` | 1,569 | Already split once (auth, pagination, schema, config extracted). Extract execution path. |
| `services/vault.py` | 1,001 | Extract `VaultReader` (read ops) from `VaultWriter` (mutations) |
| `commands/connection_cmd.py` | 715 | Borderline — could extract `doctor` subcommand |

**Priority**: `generation.py` > `vault.py` > `api.py` > `runner.py` > `connection_cmd.py` > `useWizardState.ts`

**Steps per file**:
1. Identify cohesive groups of functions/classes
2. Extract to new module with re-exports from original (temporary)
3. Update imports across repo
4. Remove re-exports
5. Update `monkeypatch.setattr` paths in tests

---

## 4. Fix leaky layering (CLI/mcp-server → knowledge/data)

**Effort**: Large (96 import lines across 26 files)
**Risk**: Medium-high — touches many modules, needs service wrappers

CLI and mcp-server import directly from `db_mcp_knowledge` and `db_mcp_data` instead of going through `db_mcp.services.*`. This makes the package boundaries soft.

| Layer | db_mcp_knowledge | db_mcp_data | Total |
|-------|-----------------|-------------|-------|
| CLI (packages/cli/) | 49 lines / 11 files | 17 lines / 7 files | 66 |
| MCP-server | 16 lines / 4 files | 14 lines / 4 files | 30 |
| **Total** | **65** | **31** | **96** |

**Top offenders in CLI**:
- `metrics_cmd.py` — imports knowledge metrics directly
- `schema_cmd.py` — imports knowledge vault directly
- `examples_cmd.py` — imports knowledge training directly
- `connection_cmd.py` — imports both data and knowledge
- `init_flow.py` — imports data connectors directly

**Steps**:
1. For each direct import, check if a `core/services/` wrapper already exists
2. If yes, switch the import
3. If no, create a thin service function in `core/services/` that delegates
4. Update all call sites (CLI + mcp-server)
5. Update mock paths in tests
6. Verify with full test suite

**Incremental approach**: Do one CLI command file at a time, not a big-bang refactor.

---

## 5. Remove tracked `_next` build output

**Effort**: Small
**Risk**: Low — but requires CI/packaging change

`packages/core/static/_next/` (24 files, 900KB) is git-tracked frontend build output. Last updated 2026-01-26.

Currently needed because PyInstaller bundles it into the binary. But it:
- Adds churn on every UI rebuild
- Pollutes diffs and reviews
- Is a build artifact, not source

**Steps**:
1. Add `packages/core/static/_next/` to `.gitignore`
2. Update CI release workflow to run `scripts/stage_ui_static.sh` before PyInstaller (already done)
3. Remove from git: `git rm -r --cached packages/core/static/_next/`
4. Verify PyInstaller still bundles the staged output correctly
5. Update `db-mcp.spec` if the path assumption changed

---

## Execution order

```
Phase 9a: Shims + exceptions          (1-2 hours, low risk)
Phase 9b: God file splits             (1 day, medium risk, incremental)
Phase 9c: Leaky layering              (2-3 days, medium risk, one file at a time)
Phase 9d: Remove tracked _next        (30 min, low risk)
```

9a and 9d can be done in parallel. 9b and 9c are independent and can interleave.
