# Changelog

All notable changes to **db-mcp** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- _Add entries here during development._

## [0.7.1] - 2026-03-18

## Highlights
- Added an executor-style daemon MCP mode built around a strict two-step task surface: `prepare_task` followed by `execute_task`.
- Added `db-mcp up` as the daemon-first local control plane entrypoint, with the daemon MCP path benchmarked directly over HTTP.
- Made daemon execution synchronous for read queries by resolving async execution handles inline through the shared execution lifecycle.

## Breaking changes
- None

## Features
- PR #59: added daemon task tools so the daemon MCP surface exposes only `prepare_task(question, connection?, context?)` and `execute_task(task_id, sql, confirmed=False)`.
- PR #59: added `db-mcp up` local-service wiring so UI/runtime HTTP and the daemon MCP endpoint share one local control plane.
- PR #59: added daemon benchmark coverage for the executor-style HTTP MCP path and compact structured task context assembly.

## Fixes
- Fixed daemon task context assembly to serialize YAML-derived `date` and `datetime` values safely in structured prepare payloads.
- Fixed daemon benchmark/tool flow so the executor-style path no longer exposes shell/code polling artifacts such as `get_task`.
- Fixed daemon `execute_task(...)` to resolve async read executions inline via the shared `_get_result(...)` lifecycle instead of leaking submitted handles back to the client.
- Removed an accidental tracked `demo.db` artifact from the repository and ignored local root-level demo databases.

## Security
- None

## Upgrade notes
- Claude/Desktop-style daemon users should prefer `db-mcp up` plus the daemon MCP endpoint for the new executor-style path.
- Legacy `start` modes and benchmark scenarios remain available for compatibility and comparison.

## Known issues
- `uv run pytest tests/ -v` still reports the existing `PytestReturnNotNoneWarning` in `tests/test_database.py::test_connection`.

## [0.7.0] - 2026-03-18

## Highlights
- Added first-class code runtime surfaces across MCP, CLI, host sessions, and native benchmarked runtime flows.
- Introduced standalone runtime commands and a host/session API so `db-mcp` can be used outside MCP while reusing the same connector-backed execution path.
- Expanded the benchmark harness to compare `db_mcp`, `exec_only`, `code_mode`, `runtime_code`, `runtime_native`, and `raw_dsn` on both `playground` and `top-ledger`.

## Breaking changes
- None

## Features
- PR #58: added `db-mcp runtime prompt`, `runtime run`, `runtime serve`, and `runtime exec` for standalone code-runtime usage.
- PR #58: added shared code-runtime modules for contracts, sessions, host integration, HTTP endpoints, native adapter bootstrap, and Python host client support.
- PR #58: added explicit runtime interfaces (`native`, `mcp`, `cli`) so one shared runtime core can power multiple frontends without changing connection semantics.
- PR #58: added benchmark-native runtime coverage for `runtime_code` and `runtime_native`, including per-attempt skills, invocation capture, and runtime artifacts.

## Fixes
- Fixed host runtime SDK execution to route through the shared connector layer instead of ad hoc child-process SQLAlchemy setup, preserving support across supported dialects.
- Fixed packaged `runtime serve` startup and benchmark runtime lifecycle handling for frozen binaries, including readiness waiting and process-group teardown.
- Fixed benchmark recovery and validation around runtime-native and runtime-code attempts so successful runtime work is not discarded because of fragile final structured output.
- Fixed process runtime Python resolution so packaged binaries and CI environments do not accidentally execute `db-mcp` in place of a real Python interpreter.

## Security
- None

## Upgrade notes
- Existing MCP connections, vault state, and onboarding artifacts remain compatible.
- Native runtime users can now choose between `native`, `mcp`, and `cli` interface contracts while reusing the same connection metadata and connector behavior.
- Benchmark users should rebuild the packaged binary before comparing runtime scenarios locally so `runtime serve` and packaged benchmark paths use the latest runtime fixes.

## Known issues
- `uv run pytest tests/ -v` still reports the existing `PytestReturnNotNoneWarning` in `tests/test_database.py::test_connection`.


## [0.6.10] - 2026-03-16

## Highlights
- Added an `exec-only` MCP server mode that exposes a single `exec` tool over the existing connection vault layout.
- Added a benchmark harness with first-class `db_mcp`, `exec_only`, and `raw_dsn` scenarios for side-by-side comparison.
- Hardened `exec-only` backend selection so OCI runtimes are used only when they are actually reachable, with automatic fallback to local process mode otherwise.

## Breaking changes
- None

## Features
- PR #57: added `db-mcp start --mode exec-only`, session-scoped `exec(connection=..., command=...)`, protocol-read enforcement, and the container/process sandbox runtime.
- PR #57: added benchmark support for the `exec_only` scenario so the single-tool mode can be compared directly against structured `db_mcp` and naked `raw_dsn` flows.
- PR #56: added the benchmark runner, scoring, case-pack loader, CLI entrypoint, and bundled benchmark case packs for `playground` and `top-ledger`.

## Fixes
- Fixed `exec-only` backend auto-detection so `docker`/`podman`/`nerdctl` are selected only when the runtime CLI exists and `runtime info` succeeds.
- Fixed the local benchmark harness to keep `raw_dsn` as a DSN-only baseline while letting `exec_only` run through the single MCP tool path.
- Fixed `exec-only` protocol handling so agents must read `PROTOCOL.md` before running arbitrary commands, and must re-read it if the file changes.

## Security
- None

## Upgrade notes
- Existing connections and knowledge vault directories remain compatible.
- `exec-only` mode now works on machines without a reachable OCI daemon by falling back to the built-in process backend automatically.
- Strong isolation is still best-effort on process fallback; install a reachable OCI runtime if you want container-backed execution.

## Known issues
- `uv run pytest tests/ -v` still reports the existing `PytestReturnNotNoneWarning` in `tests/test_database.py::test_connection`.


## [0.6.9] - 2026-03-13

## Highlights
- Added knowledge vault usage visibility in the explorer so high-value files and folders show actual access counts instead of raw byte size.
- Hardened connection navigation across Next dev, staged static UI, and packaged `db-mcp ui` so release-path routing is tested and gated before builds ship.
- Enabled agent trace capture by default and auto-generated a stable trace user ID on first capture so persisted traces appear without manual setup.

## Breaking changes
- None

## Features
- PR #55: fetched and rendered `context/usage` in the connection Knowledge workspace, with usage-first explorer badges and regression coverage in both core and UI tests.
- Expanded backend usage aggregation to include root vault files, traced file-path references, and more context surfaces so usage counts better reflect what the agent actually touched.
- Added explicit static UI staging/provenance validation and static navigation smoke coverage to align shipped `db-mcp ui` assets with the checked-in Next source.

## Fixes
- Fixed connection tab navigation so pretty URLs, internal app routes, and packaged static navigation no longer drift across dev and release paths.
- Fixed the mocked Playwright entry-path regression for connection tabs and made the CI failure reporter visible.
- Fixed the trace startup gap where enabled agent traces would still fail to persist if no `user_id` had been configured yet.
- Restored the preserved design/runtime docs that were missing from the branch after cleanup.

## Security
- None

## Upgrade notes
- Existing connections and vault content remain compatible.
- First agent startup after upgrade may write a new `user_id` into `~/.db-mcp/config.yaml` and begin creating `traces/<user_id>/YYYY-MM-DD.jsonl` files automatically.
- Release and packaged UI verification now depend on the static navigation smoke passing before binaries are built.

## Known issues
- `uv run pytest packages/core/tests/ -v` still reports the existing `PytestReturnNotNoneWarning` in `packages/core/tests/test_database.py::test_connection`.
- `bun run lint` still reports existing React hook warnings in `packages/ui/src/components/context/CodeEditor.tsx` and `packages/ui/src/components/context/SchemaExplorer.tsx`.


## [0.6.8] - 2026-03-09

## Highlights
- Rebuilt the web UI around connection-first navigation, with every connection getting a first-class workspace and URL.
- Added a multi-step connection setup wizard for new and incomplete connections, including inline connector configuration editing.
- Improved onboarding state tracking across the drawer, Overview, and wizard so setup progress is clearer and more consistent.

## Breaking changes
- None

## Features
- PR #52: new `/connections`, `/connection/:name`, and `/connection/new` flows with a persistent connection drawer and per-connection Overview, Insights, and Knowledge surfaces.
- PR #52: new connection setup wizard with `Connect and Test`, `Discover`, and `Sample Data` steps, plus connection-scoped resume behavior for configure/re-configure actions.
- PR #52: inline `connector.yaml` create/edit support directly inside the wizard, including draft connection support before the initial save.
- PR #52: operator-facing Overview redesign with a shared connection summary card, semantic-layer progress, and recommended actions tied to onboarding checkpoints.

## Fixes
- Fixed direct `/connection/...` UI routing and nested connection pages in the backend UI server.
- Fixed wizard test behavior to merge draft DB URL values with `connector.yaml` settings so connection checks follow the same path as the MCP server.
- Fixed discovery/sample persistence so re-configure reuses saved schema state instead of losing prior onboarding progress.
- Fixed BICP JSON serialization for `date` values returned from sampling results.
- Updated real and mocked Playwright coverage to follow the new wizard-based onboarding flow.

## Security
- None

## Upgrade notes
- Existing connections remain compatible and now open in the new connection workspace automatically.
- Hosts serving the exported UI should continue to route `/connection/:name` and nested connection URLs through the Python UI server.

## Known issues
- The broad mocked GitHub Playwright workflow can still hang before surfacing the first failing spec, even though targeted local connection E2E and real config smoke runs pass.
- `bun run lint` still reports existing React hook warnings in `packages/ui/src/components/context/CodeEditor.tsx` and `packages/ui/src/components/context/SchemaExplorer.tsx`.

## [0.6.7] - 2026-03-05

## Highlights
- Added progressive MCP tool discovery with `search_tools`, allowing agents to find relevant tools from the active runtime tool surface.
- Added `export_tool_sdk` to generate focused async Python wrappers from active db-mcp tools.
- Updated GitBook docs with a broad accuracy pass and new connector profile guidance.

## Breaking changes
- None

## Features
- PR #51: new `search_tools` and `export_tool_sdk` tools, plus `tool_catalog` introspection/rendering helpers.
- PR #51: coverage updates for unit, server, and MCP e2e tool-surface tests.
- PR #50: documentation audit refresh and connector profile docs expansion.

## Fixes
- Improved tool-surface discoverability for code-execution workflows by enabling discover-then-generate usage patterns.
- Added coverage-audit expectations for new core tools to prevent accidental regression.

## Security
- None

## Upgrade notes
- Existing integrations remain backward-compatible.
- If your agent enforces strict tool allowlists, add:
  - `search_tools`
  - `export_tool_sdk`

## Known issues
- `uv run pytest tests/ -v` still reports an existing warning in `tests/test_database.py::test_connection` (`PytestReturnNotNoneWarning`).


## [0.6.6] - 2026-03-04

## Highlights
- Introduced connector profiles as first-class runtime behavior (`sql_db`, `api_sql`, `api_openapi`, `api_probe`, `file_local`, `hybrid_bi`) with normalized defaults across CLI and server tool gating.
- Added a versioned connector contract (`spec_version`) and published JSON schema artifacts under `packages/core/contracts/connector/v1`.
- Added a new CLI validator command: `db-mcp connector validate <connector.yaml>`.
- Shipped operator-first UI navigation foundation (`Home`, `Setup`, `Knowledge`, `Insights`, `Advanced`) and essentials/advanced view mode.

## Breaking changes
- None

## Features
- PR #49: connector profiles + versioned connector contract support, runtime validation, schema export pipeline, connector docs update.
- PR #44: operator-first home dashboard and navigation IA update with progressive disclosure foundations.
- New script: `packages/core/scripts/export_connector_contract_schema.py`.
- New command group: `db-mcp connector ...`.

## Fixes
- PR #48: API critical bugfix follow-up and CI version consistency enforcement (`scripts/check_version_consistency.py`).
- Improved connector contract safety: if `spec_version` is present, invalid contracts fail fast during connector loading.
- Playground/API/BICP-generated connector files now persist explicit contract/version metadata.

## Security
- None

## Upgrade notes
- Existing connector files without `spec_version` continue to work.
- To adopt the contract explicitly, add:
  - `spec_version: 1.0.0`
  - appropriate `type` and `profile`
- Validate connector files before rollout:
  - `db-mcp connector validate ~/.db-mcp/connections/<name>/connector.yaml`

## Known issues
- `uv run pytest tests/ -v` still reports an existing warning in `tests/test_database.py::test_connection` (`PytestReturnNotNoneWarning`).


## [0.6.5] - 2026-03-04

## Overview
v0.6.5 is a patch release that fixes critical API connector execution-path mismatches and adds first-class API onboarding in `db-mcp init`. It unifies capability handling, reconnects `run_sql -> get_result` behavior for API execution IDs, and improves error surfacing for failed remote SQL executions.

## Highlights
- `db-mcp init` now supports API connector setup directly with connector type selection and API scaffolding.
- Legacy API capability keys (`sql`, `validate_sql`, `async_jobs`) are normalized to canonical runtime keys, preventing SQL capability drift.
- `get_result` now resolves API execution IDs produced by API SQL endpoints, including status/results polling fallback.
- Failed API execution states now surface explicit errors instead of appearing as empty result sets.

## Bug Fixes
- Fixed missing API connector onboarding path in CLI init flow.
- Fixed capability-key mismatch that caused SQL execution to be incorrectly disabled for API connectors.
- Fixed disconnected execution-ID paths between API SQL submission and `get_result` retrieval.
- Fixed API status/result parsing so failure payloads preserve error detail.

## New Features
- Added API connector type selection and config/env scaffolding during `db-mcp init`.
- Added capability alias normalization layer for connector/runtime/tool-registration consistency.
- Added regression coverage for API execution-ID resolution and failure-state extraction.

## Files Changed
| File | Change |
|---|---|
| `packages/core/src/db_mcp/cli/init_flow.py` | Added API connector onboarding flow in interactive init |
| `packages/core/src/db_mcp/connectors/__init__.py` | Applied normalized capability resolution across connector loading |
| `packages/core/src/db_mcp/capabilities.py` | Added canonical capability defaults and legacy-alias normalization |
| `packages/core/src/db_mcp/connectors/api.py` | Improved API SQL status/result/error handling for flat and failure payloads |
| `packages/core/src/db_mcp/tools/generation.py` | Unified execution fallback so `get_result` can resolve API-submitted execution IDs |
| `packages/core/src/db_mcp/server.py` | Updated capability scan to use normalized connector capabilities |
| `packages/core/tests/test_run_sql.py` | Added regressions for API execution-ID resolution and error surfacing |
| `packages/core/tests/test_api_connector.py` | Added API status/result/error extraction regressions |
| `packages/core/tests/test_connectors.py` | Added capability alias normalization regression coverage |
| `packages/core/tests/test_cli/test_init_flow.py` | Added API init-flow coverage |
| `packages/core/pyproject.toml` | Bumped core package version to `0.6.5` |
| `packages/core/src/db_mcp/__init__.py` | Updated exported package version to `0.6.5` |

## Testing
- `cd packages/core && uv run ruff check . --fix`
- `cd packages/core && uv run pytest tests/ -v`
- Focused regression checks in release prep:
  - `uv run --with pytest-asyncio pytest tests/test_run_sql.py tests/test_api_connector.py tests/test_connectors.py tests/test_server.py -k "get_result_can_read_direct_sql_execution_result or get_result_resolves_api_execution_ids_not_in_query_store or get_result_surfaces_api_execution_failures or api_capabilities_normalize_legacy_sql_flag or query_endpoint_keeps_flat_execution_status_payload or query_endpoint_surfaces_failed_execution_errors" -v`


## [0.6.4] - 2026-03-02

## Overview
v0.6.4 is a patch release that hardens API connector auth behavior in long-lived MCP sessions by adding connector cache invalidation and one-shot retry on auth failures.

## Highlights
- Added `ConnectionRegistry.invalidate_connector()` and `refresh_connector()` to explicitly refresh cached connector instances.
- `api_query` now retries once on auth-style failures (`401`/`Unauthorized`) after invalidating the cached connector.
- `api_mutate` now applies the same retry-on-auth-failure behavior.

## Bug Fixes
- Fixed stale API connector cache behavior where MCP sessions could keep returning auth failures even when a fresh runtime connection succeeded.
- Improved resilience for API write flows that depend on re-auth after long-running sessions.

## New Features
- Added regression tests for:
  - connector cache invalidation and forced refresh behavior,
  - `api_query` retry after auth errors,
  - `api_mutate` retry after auth errors.

## Files Changed
| File | Change |
|---|---|
| `packages/core/src/db_mcp/registry.py` | Added connector cache invalidation/refresh helpers |
| `packages/core/src/db_mcp/tools/api.py` | Added one-time auth-error retry with connector refresh for `api_query` and `api_mutate` |
| `packages/core/tests/test_registry.py` | Added registry invalidation regression tests |
| `packages/core/tests/test_resolve_connection.py` | Added `api_query` auth-retry regression test |
| `packages/core/tests/test_api_connector.py` | Added `api_mutate` auth-retry regression test |
| `packages/core/pyproject.toml` | Bumped core package version to `0.6.4` |
| `packages/core/src/db_mcp/__init__.py` | Updated exported version to `0.6.4` |
| `docs/releases/v0.6.4.md` | Added release notes |

## Testing
- `uv run pytest tests/test_registry.py tests/test_resolve_connection.py tests/test_api_connector.py -k "invalidate_connector or retries_once_on_auth_error" -v`
- `uv run ruff check . --fix`
- `uv run pytest tests/ -v`

## [0.6.3] - 2026-03-02

## Overview
v0.6.3 is a patch release that fixes two API tooling issues discovered during dashboard automation workflows: path-template ID resolution for non-GET endpoints and overly strict parameter typing in `api_query`.

## Highlights
- `api_query` now supports non-string parameter values (booleans, numbers, nested JSON-compatible values) instead of requiring string-only dictionaries.
- `id` values now correctly substitute `{id}` placeholders in endpoint paths for non-GET methods (for example, `PUT /dashboard/{id}`).
- Added guardrails for invalid `id` usage on non-templated non-GET endpoints.

## Bug Fixes
- Fixed `api_query` tool signature/type expectations to accept generic parameter values and pass them through correctly.
- Fixed `APIConnector.query_endpoint()` path rendering so `id` is used to resolve templated endpoint paths instead of being treated as a GET-only suffix pattern.
- Improved `id` error messaging for unsupported non-GET endpoint configurations.

## New Features
- Added regression tests for:
  - non-GET templated path substitution with `id`,
  - invalid `id` usage on non-templated non-GET endpoints,
  - forwarding non-string `api_query` parameter values through tool dispatch.

## Files Changed
| File | Change |
|---|---|
| `packages/core/src/db_mcp/connectors/api.py` | Fixed generic `id` template substitution and non-GET `id` handling in endpoint query flow |
| `packages/core/src/db_mcp/tools/api.py` | Relaxed `api_query` parameter typing to accept generic JSON-compatible values |
| `packages/core/tests/test_api_connector.py` | Added path-template/non-GET `id` regressions |
| `packages/core/tests/test_resolve_connection.py` | Added `api_query` non-string params dispatch regression |
| `packages/core/pyproject.toml` | Bumped core package version to `0.6.3` |

## Testing
- `uv run pytest tests/test_api_connector.py tests/test_resolve_connection.py -k "id_substitutes_templated_path_for_put or non_get_id_without_template_errors or allows_non_string_param_values" -v`
- `uv run pytest tests/test_api_connector.py -v`
- `uv run ruff check src/db_mcp/connectors/api.py src/db_mcp/tools/api.py tests/test_api_connector.py tests/test_resolve_connection.py`
- Live smoke on patched runtime against `wifimetrics-superset`:
  - `update_dashboard` with endpoint path `/dashboard/{id}` and `id=4` succeeded


## [0.6.2] - 2026-03-02

## Overview
v0.6.2 is a patch release focused on fixing REST API write behavior for API connectors, with Superset as the primary validation target. It ensures write payloads are routed as JSON bodies when appropriate, improves response extraction for `result` wrappers, and adds regression coverage so API-based create workflows remain stable.

## Highlights
- Fixed API write routing so Superset-style create calls no longer send POST payloads as URL query parameters.
- Added compatibility for list/result wrappers that return rows under `result`.
- Added API config loader default for non-GET endpoints to use `body_mode: json` when omitted.
- Included internal design note on standardizing db-mcp knowledge patterns.

## Bug Fixes
- Fixed `_load_api_config()` to default non-GET endpoints to JSON body mode unless explicitly overridden.
- Fixed `APIConnector.query_endpoint()` to infer JSON body for write endpoints when the endpoint declares no query parameters and caller passes `params`.
- Fixed API response extraction to support `result` list wrappers (common in Superset responses) in standard endpoint querying flows.

## New Features
- Added regression tests covering:
  - Superset-style `{result: [...]}` response parsing.
  - POST payload inference to JSON body when endpoint query params are not declared.
  - Preservation of query-string behavior when endpoint query params are explicitly declared.

## Files Changed
| File | Change |
|---|---|
| `packages/core/src/db_mcp/connectors/__init__.py` | Defaulted non-GET API endpoints to `body_mode: json` during config load |
| `packages/core/src/db_mcp/connectors/api.py` | Fixed write payload routing and response row extraction for `result` wrappers |
| `packages/core/tests/test_api_connector.py` | Added Superset/write-path regressions and loader default coverage |
| `packages/core/pyproject.toml` | Bumped core package version to `0.6.2` |
| `docs/knowledge-patterns-standardization.md` | Added internal knowledge-layer standardization analysis |

## Testing
- `uv run pytest tests/test_api_connector.py -v`
- `uv run ruff check src/db_mcp/connectors/__init__.py src/db_mcp/connectors/api.py tests/test_api_connector.py`
- Live smoke on patched runtime against `wifimetrics-superset`:
  - `create_dataset` succeeded (virtual dataset created)
  - `create_dashboard` succeeded
  - `create_chart` succeeded and linked to dashboard


## [0.6.1] - 2026-03-02

## Overview
v0.6.1 is a patch release focused on stabilizing SQL execution for SQL-like API connectors (notably Dune) and reducing behavior drift between database and API-backed SQL flows. The release fixes connector misclassification, corrects doctor/auth probing for API SQL endpoints, and unifies run/poll execution behavior so async provider responses are handled consistently through `run_sql` and `get_result`.

## Highlights
- API connectors are no longer misclassified as file connectors when computing runtime capabilities.
- `db-mcp doctor --connection dune --json` now correctly identifies `connector_type: api` and uses endpoint-aware auth checks.
- `run_sql` now uses a unified lifecycle for SQL-like APIs: providers that return execution IDs produce `submitted` responses even when configured as `api_sync`, and `get_result` polls them consistently.
- Tool docs now explicitly state that SQL-like APIs may return either immediate success or async submission for the same `run_sql` interface.

## Bug Fixes
- Fixed connector capability resolution order so `APIConnector` is matched before `FileConnector` in runtime capability normalization.
- Fixed doctor connector type reporting to prefer `api_config.type` over inherited file config type.
- Fixed API connector `test_connection()` to use endpoint HTTP method and send a lightweight SQL probe body for non-GET SQL execute endpoints.
- Fixed SQL API lifecycle handling so `get_result` polls executions when `external_execution_id` is present, not only when `sql_mode == api_async`.
- Fixed SQL API metadata propagation in polling to preserve connector mode in execution metadata.

## New Features
- Unified SQL-like API direct execution path in `run_sql`:
  - `submit_sql -> mode=sync` returns immediate `success`.
  - `submit_sql -> mode=async` returns `submitted` + `execution_id` and is resolved via `get_result`.

## Files Changed
| File | Change |
|---|---|
| `packages/core/src/db_mcp/connectors/__init__.py` | Corrected API vs file capability detection order |
| `packages/core/src/db_mcp/connectors/api.py` | Improved endpoint-aware API auth/test probing for SQL endpoints |
| `packages/core/src/db_mcp/cli/commands/core.py` | Fixed doctor connector type reporting precedence |
| `packages/core/src/db_mcp/tools/generation.py` | Unified SQL API execution lifecycle across `api_sync` and async provider behavior |
| `packages/core/tests/test_api_connector.py` | Added/updated API test_connection method coverage |
| `packages/core/tests/test_cli/test_doctor_command.py` | Added regression for API connector type reporting |
| `packages/core/tests/test_run_sql.py` | Added regressions for unified `run_sql/get_result` SQL-like API behavior |

## Testing
- `uv run ruff check src/db_mcp/tools/generation.py tests/test_run_sql.py`
- `uv run pytest tests/test_run_sql.py tests/test_execution_response_contracts.py -v`
- `uv run pytest tests/test_run_sql.py tests/test_cli/test_doctor_command.py tests/test_api_connector.py -v`
- Live smoke on patched runtime:
  - `uv run db-mcp doctor --json --connection dune`
  - `uv run db-mcp doctor --json --connection top-ledger`
  - `run_sql(connection='dune', sql='SELECT 1 AS ok') -> submitted`
  - `get_result(execution_id, connection='dune') -> complete`


## [0.5.0] - 2026-02-09

## Highlights

### Multi-Connection Support

db-mcp is no longer limited to one database connection per server. Query any connection by name, see all available schemas, and let the agent reason across multiple data sources.

**Connection Registry:**
- Automatic discovery of all connections in `~/.db-mcp/connections/`
- Lazy-loading and caching of connectors
- `list_connections` tool shows all available connections with type, dialect, and description

**`connection` parameter on tools:**
All query tools now accept an optional `connection` parameter:
```
run_sql(sql="SELECT ...", connection="warehouse")
list_tables(connection="analytics")
describe_table(table="orders", connection="postgres")
```

When omitted, tools use the default connection (backward compatible).

**Tools with connection parameter:**
- `run_sql`, `validate_sql`, `export_results`
- `list_catalogs`, `list_schemas`, `list_tables`, `describe_table`, `sample_table`
- `shell` (sets working directory to the connection's vault)

**MCP Resources:**
- `db-mcp://connections` — lists all available connections with metadata
- `db-mcp://schema/{connection}` — returns schema for any connection

**PROTOCOL.md:**
Updated template includes multi-connection guidance, instructing the agent to use `list_connections` and the `connection` parameter for cross-source queries.

## Breaking changes
- None. Single-connection users are unaffected.

## Features
- Connection registry with auto-discovery, lazy-loading, and caching
- `list_connections` tool
- `connection` parameter on all SQL/query/shell tools
- `db-mcp://connections` resource
- `db-mcp://schema/{connection}` resource
- PROTOCOL.md multi-connection queries section

## Fixes
- None

## Test Coverage
- 38 new tests (18 registry + 13 multi-connection + 7 multi-schema resource)
- Full suite: 570 tests passing

## Upgrade notes
- PROTOCOL.md will be updated on next vault init with multi-connection guidance
- Existing connections work unchanged; no migration needed
- To use multi-connection: ensure multiple connections exist in `~/.db-mcp/connections/`


## [0.4.57] - 2026-02-09

## Highlights

### Proactive Insights via MCP Resources

db-mcp now detects noteworthy patterns in query traces and surfaces them as MCP resources for the connected agent to analyze. This bridges the gap between the reactive MCP experience (user has to ask) and proactive analysis (system flags what matters).

**How it works:**
1. Trace analysis detects patterns (repeated queries, errors, knowledge gaps)
2. Insights are stored and exposed via `db-mcp://insights/pending` resource
3. PROTOCOL.md instructs the agent to check this resource on every session start
4. Agent mentions important insights to the user and helps resolve them
5. Resolved insights are dismissed via `dismiss_insight` tool

**What gets detected:**
- Repeated queries (3+ times) — save as examples for reuse
- High validation failure rate (>30%) — missing schema context or rules
- Unmapped business terms — vocabulary gaps needing rules
- Low example reuse — knowledge vault needs more examples
- Unsaved error patterns — learning opportunities being missed
- Stagnant knowledge vault — no captures from recent usage

**Philosophy:** The agent does the deep thinking. db-mcp just flags what's worth thinking about. No embedded LLM, no API keys, pure MCP.

### `init` as attach synonym

`db-mcp init <name> <repo>` now works when the connection already exists — it seamlessly attaches the shared repo (same as `db-mcp collab attach`).

## Breaking changes
- None

## Features
- `db-mcp://insights/pending` MCP resource for pending trace insights
- `review-insights` MCP prompt template for one-click insight review
- `dismiss_insight` tool for marking insights as resolved
- Insight detector: 6 detection categories, deterministic, no LLM calls
- PROTOCOL.md updated with insight-checking instruction (step 6)
- `db-mcp init <name> <repo>` as synonym for `collab attach` when connection exists

## Fixes
- None

## Security
- None

## Upgrade notes
- PROTOCOL.md is system-managed and will be overwritten on upgrade. The new step 6 (check insights) will be added automatically.

## Known issues
- None

## Test Coverage
- 14 new insight detector tests
- Full suite: 532 tests passing


## [0.4.56] - 2026-02-09

## Highlights

### Collab Attach / Detach
New commands for retrofitting existing connections with shared team knowledge:

```
db-mcp collab attach git@github.com:org/db-knowledge.git
db-mcp collab detach
```

**Attach** merges a team's shared knowledge repo into an existing local connection. Your local files are preserved, the team's examples/learnings/schema are merged alongside, and you're automatically registered as a collaborator. Conflicts are detected and reported for manual resolution.

**Detach** cleanly removes the repo link while keeping all local files intact. Re-attachable anytime.

This enables the key onboarding flow: a user sets up db-mcp locally, builds their own knowledge, and later connects to a team repo without losing anything.

## Breaking changes
- None

## Features
- `db-mcp collab attach <url>` — merge shared repo into existing connection
- `db-mcp collab detach` — remove repo link, keep local files
- `db-mcp init` now suggests `collab attach` when connection already exists (instead of a generic error)

## Fixes
- None

## Security
- None

## Upgrade notes
- None

## Known issues
- None


## [0.4.55] - 2026-02-09

## Highlights

### Depth-Aware File Classification
The additive file classifier now respects directory depth. Previously, `examples/*.yaml` would match files at any depth (e.g., `examples/nested/deep.yaml`) due to Python's `fnmatch` treating `*` as matching `/`. Now `*` only matches within a single directory level, and `**` is supported for recursive matching. This prevents nested files from being auto-merged when they shouldn't be.

### Selective Additive Merge
When a collaborator branch contains both additive and shared-state changes, additive files are now selectively merged to main while shared-state changes go through the PR review flow. Previously, any shared-state file on the branch would block all additive files from merging.

### Merge Conflict Recovery
Auto-merge operations (both `collaborator_push` and `master_merge_all`) now catch merge conflicts gracefully. On conflict, the merge is aborted and the changes fall back to the PR flow instead of crashing the sync pipeline.

### .collab.yaml Auto-Merge
Member additions to `.collab.yaml` are now treated as auto-mergeable. When a collaborator joins and the only shared-state change is `.collab.yaml`, it auto-merges without requiring a master PR review. If it conflicts, the merge conflict handler falls back to PR.

### Merge-Base Diffing
Collaborator diffs now use `git merge-base` instead of diffing against HEAD of main. This means only the collaborator's actual changes are classified, not accumulated drift from other merges or master-pushed files.

### Branch Pruning
New `db-mcp collab prune` command and `prune_merged_branches()` function. Finds remote `collaborator/*` branches fully merged into main and deletes them. Also runs automatically at the end of `master_merge_all()`.

### Force-With-Lease Push
Collaborator branch pushes now use `--force-with-lease` to handle re-pushes when the remote branch already exists, without risking data loss.

## Breaking changes
- None

## Features
- Depth-aware `_match_pattern()` replacing `fnmatch` in file classification
- `is_auto_mergeable_shared()` for `.collab.yaml` auto-merge detection
- Selective file checkout (`git checkout <branch> -- <file>`) for mixed additive/shared branches
- `git.merge_base()` for accurate collaborator diffs
- `git.checkout_file()` for selective file merging
- `git.merge_abort()` for conflict recovery
- `git.delete_remote_branch()` for branch cleanup
- `git.list_merged_remote_branches()` for finding prunable branches
- `git.push_branch()` now supports `force_with_lease` parameter
- `db-mcp collab prune` CLI command
- Auto-pruning in `master_merge_all()`

## Fixes
- `fnmatch` `*` matching across directory separators (e.g., `examples/*.yaml` matching `examples/nested/file.yaml`)
- Additive files blocked by shared-state on same branch
- Merge conflicts crashing sync pipeline
- `.collab.yaml` member additions requiring unnecessary PR review
- Collaborator diffs polluted by master-pushed files already on both branches
- `push_branch` failing when remote branch already exists

## Security
- None

## Upgrade notes
- None

## Known issues
- None

## Test Coverage
- Python: 105 collab tests passing
- Integration test: 15/17 scenarios passing (2 minor push-coordination issues in local bare repo test setup)


## [0.4.54] - 2026-02-06

**Release Date:** February 6, 2026

## Overview

Fixes collaborator sync crashes and makes the onboarding flow more resilient. Sync commands now auto-create missing branches and fall back to the user_id hash when no user_name is configured.

## Highlights

### Crash-Free Collaborator Sync

Collaborator sync no longer crashes when the `collaborator/{name}` branch doesn't exist yet. The new `_ensure_branch()` helper tries checkout first, then falls back to creating the branch automatically. This handles the common case where a collaborator cloned the repo but registration didn't fully complete.

### Graceful Fallback for Missing User Names

All sync paths — `collab sync`, `collab daemon`, and server session hooks — now fall back to the `user_id` hash (e.g. `collaborator/6adf5513`) when no `user_name` is configured, instead of refusing to run.

## Fixes

### Auto-create collaborator branch on sync

`collab sync`, session hooks, and `collab daemon` now automatically create the `collaborator/{name}` branch if it doesn't exist, instead of crashing with a `git checkout` error. This handles the case where a collaborator cloned the repo but registration didn't fully complete.

### Fall back to user_id when user_name is missing

If a collaborator never set their `user_name`, all sync paths (`collab sync`, `collab daemon`, server lifespan hooks) now fall back to the `user_id` hash (e.g. `collaborator/6adf5513`) instead of refusing to run. A dim notice is printed so they know to set a proper name later.

## Changes

### Added

- **`_ensure_branch()`** helper in `collab/sync.py` — tries checkout, falls back to `create=True`

### Changed

- **`collaborator_pull()`** and **`collaborator_push()`** use `_ensure_branch()` instead of bare `git.checkout()`
- **`collab sync`** CLI falls back to `user_id` if no `user_name` is set
- **`collab daemon`** CLI falls back to `user_id` if no `user_name` is set
- **Server lifespan** uses `member.user_name or user_id` for session sync hooks

## Test Coverage

- Python: 481 tests passing


## [0.4.53] - 2026-02-06

**Release Date:** February 6, 2026

## Overview

Improves the collaborator onboarding experience for the collaborative git sync protocol. Adds a `collab join` command and moves the user name prompt earlier in the brownfield init flow.

## Highlights

### `db-mcp collab join`

New command for collaborators who already have a connection cloned but weren't registered (or need to re-register). Prompts for name, creates the collaborator branch, and pushes. No need to delete and re-clone.

```bash
db-mcp use dune
db-mcp collab join
```

### Early Name Prompt in Brownfield Init

`db-mcp init <name> <url>` now prompts for user name immediately after cloning, before asking for credentials. Previously the prompt was buried in auto-registration and could be missed if anything interrupted the flow.

## Changes

### Added

- **`db-mcp collab join`** command -- register as collaborator on an existing connection with `.collab.yaml`

### Changed

- **Brownfield init** prompts for `user_name` right after clone, before credential prompts

## Test Coverage

- Python: 481 tests passing
- UI E2E: 77 tests passing (Playwright)


## [0.4.52] - 2026-02-06

**Release Date:** February 6, 2026

## Overview

Renames the UI "Connectors" page to "Config" and adds an Agent Configuration section that lets users manage db-mcp integration with MCP-compatible agents (Claude Desktop, Claude Code, OpenAI Codex) directly from the browser UI.

## Highlights

### Connectors -> Config Rename

The navigation route, page title, and all internal references have been renamed from "Connectors" to "Config" to better reflect the page's expanding scope beyond just database connections.

### Agent Configuration UI

A new section at the bottom of the Config page shows all detected MCP agents with their installation and configuration status. Users can:

- **See detected agents** with Installed / Configured badges
- **Add db-mcp** to an agent's MCP config with one click
- **Remove db-mcp** from an agent's config
- **Edit the MCP config snippet** directly in the browser with Save/Cancel, including server-side JSON/TOML validation that prevents saving malformed configs

### Editable Config Snippets

Clicking "Edit Config" opens the agent's MCP servers section in an inline editor. On save, the backend validates the snippet (JSON parse for Claude Desktop/Code, TOML parse for Codex) and only writes if valid. Other config keys outside the MCP section are preserved.

## Changes

### Added

- **`remove_dbmcp_from_agent()`** in `agents.py` -- counterpart to `configure_agent_for_dbmcp()`
- **`get_db_mcp_binary_path()`** moved from `cli.py` to `agents.py` to avoid heavy CLI imports in BICP agent
- **5 BICP handlers**: `agents/list`, `agents/configure`, `agents/remove`, `agents/config-snippet`, `agents/config-write`
- **`AgentConfig`** React component (`src/components/AgentConfig.tsx`)
- **17 Python tests** for BICP agent handlers (list, configure, remove, snippet, config-write with validation)
- **8 E2E tests** for agent UI (display badges, add/remove, edit/save/cancel, validation errors, empty state)

### Changed

- **Route**: `/connectors` -> `/config`
- **Nav label**: "Connectors" -> "Config"
- **Page heading**: "Data Connectors" -> "Configuration"
- **E2E specs**: `connectors.spec.ts` -> `config.spec.ts`, `real-connectors.spec.ts` -> `real-config.spec.ts`
- **Playwright configs**: updated `testIgnore`/`testMatch` patterns

## Test Coverage

- Python: 481 tests passing
- UI E2E: 77 tests passing (Playwright)
- UI: lint + type check + build clean


## [0.4.51] - 2026-02-06

### Added

- **Auto-registration on brownfield init**: `db-mcp init <name> <repo-url>` detects `.collab.yaml` and registers collaborator automatically
- **`db-mcp collab daemon`**: long-running periodic sync command with `--interval` flag
- **Session mode sync hooks**: `server_lifespan()` pulls on startup, pushes on shutdown via `asyncio.to_thread()`

### Changed

- **Server lifespan**: replaced periodic `CollabSyncLoop` with one-shot pull/push hooks (session mode)

### Removed

- **`db-mcp collab join`**: redundant with existing `db-mcp init <name> <repo-url>` brownfield flow

## [0.4.50] - 2026-02-06

### Added

- **Collaborative git sync protocol**: master/collaborator model for shared knowledge vaults via git
- **`.collab.yaml` manifest**: tracks team members, roles, and sync configuration
- **`db-mcp collab` CLI group**: `init`, `join`, `sync`, `merge`, `status`, `members` subcommands
- **Smart file classification**: auto-merge additive files (examples, learnings, traces); PR for shared-state (schema, rules, metrics)
- **Background sync loop**: periodic pull/push in MCP server lifespan (default 60m, configurable)
- **GitHub PR integration**: auto-opens PRs for shared-state changes via `gh` CLI
- **Git branch operations**: `checkout`, `fetch`, `merge`, `cherry_pick`, `current_branch`, `branch_exists`, `diff_names`, `push_branch` on `NativeGitBackend`
- **Migration**: updates existing `.gitignore` to allow `.collab.yaml`

## [0.4.49] - 2026-02-06

### Fixed

- **Codex TOML round-trip**: `_dict_to_toml` now recursively handles arbitrary nesting depth, preserving `env` maps and other nested structures in `~/.codex/config.toml`
- **Spurious `[mcp_servers]` header**: intermediate-only tables no longer emit empty section headers in generated TOML

## [0.4.48] - 2026-02-04

**Release Date:** February 4, 2026

## Overview

This release overhauls the Insights page with a unified **SQL Patterns** card, a new **Save as Learning** flow for auto-corrected errors, and several fixes for API connectors and the training pipeline.

## Highlights

### Unified SQL Patterns Card

The separate "Repeated Queries" and "Errors & Failures" cards have been merged into a single **SQL Patterns** card with expandable accordion rows. Each row shows:

- Tool label and badges (e.g. `4x`, `auto-corrected`)
- Truncated SQL preview (click to expand full multiline SQL)
- Timestamps (first/last seen)
- Save action (`Save as Example` or `Save as Learning`)

Sections within the card: Repeated Queries, Auto-corrected Errors, Hard Errors, Validation Failures.

### Save as Learning for Auto-corrected Errors

Auto-corrected SQL errors (soft failures) now show the failing SQL and a **Save as Learning** button. Clicking it expands the row to reveal:

- Full multiline SQL in a scrollable `<pre>` block
- Pre-filled description extracted from the error message (e.g. "Table 'lending.deposits' does not exist -- use correct table name")
- Save/Cancel buttons

Saved learnings are stored as training examples with an `[ERROR PATTERN]` prefix, helping the agent avoid the same mistakes in future sessions.

### Saved State Persists Across Refresh

Previously, saving an example or learning showed a brief "Saved" state that reverted on the next 5-second auto-refresh. Now the backend's `insights/analyze` response includes `is_saved` for errors whose SQL matches a saved training example, so the saved state persists correctly.

### Improved Knowledge Capture Card

The Knowledge Capture card now shows intent descriptions inline instead of hiding them behind click-to-expand. Error patterns and regular examples are displayed in separate labeled sections with distinct icons.

## Bug Fixes

### API Connector: Correct Dialect Display

API connectors (e.g. Dune Analytics) previously showed "duckdb" as the dialect in the connectors list. Now they display the API title from discovery (e.g. "Dune Analytics API") or derive a name from the base URL.

### `get_provider_dir` Fixed for Named Connections

`get_provider_dir(provider_id)` was ignoring the provider_id argument and always returning the active connection path. This caused `is_example` checks and save operations to fail when the provider_id didn't match the active connection. Fixed to return `~/.db-mcp/connections/{provider_id}` when a provider_id is given.

### SQL Extraction from `api_execute_sql` Spans

`_extract_sql()` now parses SQL from the `attrs.args` JSON field (where `api_execute_sql` stores its arguments), in addition to the existing `attrs.sql` and `attrs.sql.preview` paths. This enables the Save as Learning feature for SQL-like API connectors.

### Playwright E2E Port Conflict

Fixed E2E tests failing when port 3000 was occupied by another application. Changed default dev server port to 3177 and set `reuseExistingServer: false`.

## Files Changed

| File | Change |
|------|--------|
| `packages/ui/src/app/insights/page.tsx` | Unified SQL Patterns card, Save as Learning flow, improved Knowledge Capture card |
| `packages/ui/src/lib/bicp.ts` | Added `sql`, `is_saved`, `example_id` fields to error type |
| `packages/ui/e2e/insights.spec.ts` | 4 new E2E tests for SQL Patterns and save flows |
| `packages/ui/playwright.config.ts` | Port fix (3177), `reuseExistingServer: false` |
| `packages/core/src/db_mcp/bicp/traces.py` | SQL extraction from args JSON, `is_saved` for errors, SQL attached to error traces |
| `packages/core/src/db_mcp/bicp/agent.py` | API title display for connectors, API connection test improvements |
| `packages/core/src/db_mcp/connectors/api.py` | Store `api_title` from discovery, use it as dialect |
| `packages/core/src/db_mcp/onboarding/state.py` | Fix `get_provider_dir` to respect provider_id |
| `packages/core/tests/test_traces.py` | 13 new tests for SQL extraction and `is_saved` behavior |

## Testing

- **362 Python tests** passing (13 new)
- **69 E2E tests** passing (4 new)
- Lint clean (ruff, ESLint, TypeScript)


## [0.4.47] - 2026-02-04

**Release Date:** February 4, 2026

## Overview

This release introduces **multi-agent configuration support**, making it easier to set up db-mcp across different MCP-compatible AI agents. Instead of manually editing JSON/TOML config files, you can now configure db-mcp for Claude Desktop, Claude Code, and OpenAI Codex with a single command.

## Highlights

### Automatic Agent Detection & Configuration

db-mcp now automatically detects which MCP-compatible agents are installed on your system and offers to configure them all at once:

```bash
db-mcp init mydb
# Detects: Claude Desktop [yes], Claude Code [yes], OpenAI Codex [no]
# Prompts: Configure db-mcp for which agents?
#   [1] All detected agents  ← default
#   [2] Select specific agents
#   [3] Skip agent configuration
```

### New `db-mcp agents` Command

Manage agent configurations anytime with the new dedicated command:

```bash
# Interactive selection
db-mcp agents

# List detected agents
db-mcp agents --list

# Configure all detected agents
db-mcp agents --all

# Configure specific agents
db-mcp agents -A claude-desktop
db-mcp agents -A claude-code -A codex
```

## New Features

### 1. Multi-Agent Registry

A centralized agent registry with auto-detection for:

| Agent | Config Location | Format | Detection Method |
|-------|----------------|--------|------------------|
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` | JSON | Config file or app presence |
| **Claude Code** | `~/.claude.json` | JSON | Config file or `claude` CLI |
| **OpenAI Codex** | `~/.codex/config.toml` | TOML | Config directory or `codex` CLI |

### 2. Intelligent Configuration

- **Preserves existing servers**: Only adds/updates the `db-mcp` entry, keeps all other MCP servers intact
- **Legacy cleanup**: Automatically removes old `dbmeta` entries
- **Cross-platform**: Works on macOS, Windows, and Linux

### 3. Flexible TOML Support

- Uses Python's built-in `tomllib` for reading TOML (Python 3.11+)
- Custom TOML writer implementation (no external dependencies)
- Full support for OpenAI Codex's config format

## Usage Examples

### First-Time Setup

```bash
# Initialize a new connection
db-mcp init production

# db-mcp detects installed agents and prompts:
# Detected MCP-compatible agents:
#   [1] Claude Desktop
#   [2] Claude Code
#
# Configure db-mcp for which agents?
# Choice [1]: ← press Enter to configure all
#
# [yes] Claude Desktop configured
# [yes] Claude Code configured
# [yes] Configured 2/2 agent(s)
```

### Reconfigure Agents Later

```bash
# List what's installed
db-mcp agents --list
# Detected MCP agents:
#   [yes] Claude Desktop
#     Config: ~/Library/Application Support/Claude/claude_desktop_config.json
#   [yes] Claude Code
#     Config: ~/.claude.json

# Configure all detected agents
db-mcp agents --all
# [yes] Claude Desktop configured
# [yes] Claude Code configured
# [yes] Configured 2/2 agent(s)
```

### Configure Specific Agents

```bash
# Only configure Claude Desktop
db-mcp agents -A claude-desktop

# Configure multiple specific agents
db-mcp agents -A claude-code -A codex
```

## Technical Details

### Agent Detection Logic

1. **Config File Check**: Looks for agent config files in standard locations
2. **App/CLI Check**: Falls back to checking if app is installed or CLI is available
3. **Platform-Aware**: Adjusts paths based on OS (macOS/Windows/Linux)

### Configuration Process

For each agent:

1. Load existing config (if any)
2. Add/update `db-mcp` server entry with correct binary path
3. Remove legacy `dbmeta` entry (if present)
4. Save config while preserving all other servers

### Config Format Examples

**Claude Desktop/Code (JSON)**:
```json
{
  "mcpServers": {
    "db-mcp": {
      "command": "/usr/local/bin/db-mcp",
      "args": ["start"]
    }
  }
}
```

**OpenAI Codex (TOML)**:
```toml
[mcp_servers.db-mcp]
command = "/usr/local/bin/db-mcp"
args = ["start"]
```

## Testing

This release includes comprehensive test coverage:

- **21 new tests** for agent detection, configuration, and TOML handling
- All tests passing [ok]
- No regressions in existing functionality

## Important Notes

### ChatGPT Desktop Not Supported

ChatGPT Desktop uses UI-only configuration (Settings → Connectors → Developer mode) and does not support local config file configuration. You'll need to configure it manually through the UI.

### Binary Path Detection

db-mcp intelligently detects the binary path:
- If running from PyInstaller bundle: uses the executable path
- If symlinked at `~/.local/bin/db-mcp`: uses the symlink (for auto-updates)
- Otherwise: uses `db-mcp` command

## Upgrade Instructions

### From v0.4.45

1. Update to v0.4.47:
   ```bash
   # If installed via pip
   pip install --upgrade db-mcp
   
   # If using binary
   # Download new binary and replace existing one
   ```

2. Reconfigure agents (optional but recommended):
   ```bash
   db-mcp agents --all
   ```

3. Restart your MCP agents (Claude Desktop, Claude Code, etc.)

## Bug Fixes

- None (feature-only release)

## Security

- No security changes in this release

## Documentation Updates

- Added agent registry documentation
- Updated CLI command reference
- Added multi-agent setup examples

## Credits

This feature was developed in response to user feedback requesting easier configuration across multiple AI agents.

## Full Changelog

See [CHANGELOG.md](../../CHANGELOG.md#0446---2026-02-04) for complete details.

## Coming Soon

Stay tuned for upcoming features:
- Additional agent support (Cursor, Windsurf, etc.)
- Config validation and health checks
- Agent-specific settings and preferences

---

**Questions or Issues?** Report them at https://github.com/apelogic-ai/db-mcp/issues


## [0.4.46] - 2026-02-04

## Highlights
- Multi-agent configuration support - automatically configure db-mcp for Claude Desktop, Claude Code, and OpenAI Codex

## Breaking changes
- None

## Features
- **New `db-mcp agents` command** - Interactive configuration for multiple MCP-compatible agents
  - `db-mcp agents` - Interactive selection of detected agents
  - `db-mcp agents --list` - Show all detected agents on your system
  - `db-mcp agents --all` - Configure all detected agents at once
  - `db-mcp agents -A claude-desktop -A codex` - Configure specific agents
- **Auto-detection of installed agents** - Detects Claude Desktop, Claude Code, and OpenAI Codex
- **Integrated into `db-mcp init`** - Automatically prompts to configure detected agents during setup
- **Support for multiple config formats**:
  - JSON for Claude Desktop and Claude Code (`mcpServers`)
  - TOML for OpenAI Codex (`mcp_servers`)
- **Preserves existing MCP servers** - Only adds/updates db-mcp entry, keeps other servers intact
- **Legacy cleanup** - Automatically removes old `dbmeta` entries when configuring

## Fixes
- None

## Security
- None

## Upgrade notes
After upgrading, you can reconfigure agents at any time with:
```bash
db-mcp agents --all  # Configure all detected agents
```

Supported agents:
- **Claude Desktop** (`~/.../Claude/claude_desktop_config.json`)
- **Claude Code** (`~/.claude.json`)
- **OpenAI Codex** (`~/.codex/config.toml`)

Note: ChatGPT Desktop uses UI-only configuration and is not supported for auto-configuration.

## Known issues
- None

## [0.4.45] - 2026-02-03

## Highlights
- New `api_execute_sql` tool for SQL-like APIs (Dune Analytics, etc.)

## Breaking changes
- None

## Features
- Added `api_execute_sql(sql="...")` tool specifically for SQL-like API connectors
- Keeps SQL execution separate from REST endpoint queries (`api_query`) and true SQL databases (`run_sql`)

## Fixes
- Fixed async polling to handle Dune's `QUERY_STATE_COMPLETED` status format
- Added support for `is_execution_finished` flag in status responses

## Security
- None

## Upgrade notes
For Dune Analytics and similar SQL-like APIs, use `api_execute_sql`:
```
api_execute_sql(sql="SELECT * FROM dex_solana.trades LIMIT 10")
```

## Known issues
- None


## [0.4.44] - 2026-02-03

## Highlights
- 

## Breaking changes
- None

## Features
- 

## Fixes
- 

## Security
- None

## Upgrade notes
- None

## Known issues
- None


## [0.4.43] - 2026-02-03

## Highlights
- Fixed Dune Analytics async polling to correctly detect query completion

## Breaking changes
- None

## Features
- None

## Fixes
- Fixed async polling to handle Dune's `QUERY_STATE_COMPLETED` status format (was only checking lowercase `complete`)
- Added support for `is_execution_finished` flag in status responses

## Security
- None

## Upgrade notes
- None

## Known issues
- None


## [0.4.42] - 2026-02-03

## Highlights
- SQL-like API connectors (Dune Analytics, etc.) now fully supported with direct SQL execution

## Breaking changes
- None

## Features
- Added `execute_sql()` support for API connectors with `supports_sql: true` capability
- Automatic handling of async SQL APIs that return execution IDs and require polling
- Configurable `sql_field` per endpoint (defaults to `sql` for Dune compatibility)
- Response extraction handles multiple formats: Dune (`result.rows`), standard REST (`data`, `rows`, `results`), and columnar (`columns` + `rows` arrays)

## Fixes
- None

## Security
- None

## Upgrade notes
To use with Dune Analytics, configure your `connector.yaml`:

```yaml
type: api
base_url: https://api.dune.com/api/v1
auth:
  type: header
  header_name: X-DUNE-API-KEY
  token_env: API_KEY
capabilities:
  supports_sql: true
  sql_mode: api_sync

endpoints:
  - name: execute_sql
    path: /sql/execute
    method: POST
    body_mode: json
  - name: execution_status
    path: /execution/{execution_id}/status
  - name: execution_results
    path: /execution/{execution_id}/results
```

## Known issues
- None


## [0.4.41] - 2026-02-03

## Highlights
- Fixed macOS binary being killed on launch due to corrupted code signature

## Breaking changes
- None

## Features
- None

## Fixes
- Fixed macOS binaries failing to launch with "Killed: 9" error. The GitHub Actions runner's PyInstaller was producing binaries with invalid adhoc signatures. Added explicit `codesign --force --sign -` step after build to ensure valid signatures.

## Security
- None

## Upgrade notes
- If you previously installed 0.4.40 and it wouldn't run, simply re-install: `curl -fsSL https://download.apelogic.ai/db-mcp/install.sh | sh`

## Known issues
- None


## [0.4.40] - 2026-02-02

## Highlights
- API connectors: treat SQL-like endpoints correctly (stops misclassifying certain API endpoints as SQL)

## Breaking changes
- None

## Features
- None

## Fixes
- Core: improve SQL detection/handling for API connectors (fixes edge cases around “SQL-like” endpoints)

## Security
- None

## Upgrade notes
- None

## Known issues
- None


## [0.4.39] - 2026-02-02

## Highlights
- CI: stabilize Playwright E2E workflows (use Bun, avoid `npm ci` lock mismatch)
- E2E: make the `/bicp` dev-server proxy disable-able so mocked tests don’t depend on a local backend

## Breaking changes
- None

## Features
- UI: configurable BICP proxy target via `BICP_PROXY_TARGET` (defaults to `http://localhost:8080`)

## Fixes
- CI: `e2e-real-connectors` workflow now uses Bun (`bun install`, `bunx playwright ...`)
- CI/E2E: disable Next rewrites in mocked E2E via `DISABLE_BICP_PROXY=1` to prevent `ECONNREFUSED` during Playwright route mocking

## Security
- None

## Upgrade notes
- If you run the UI dev server with a non-default BICP backend, set `BICP_PROXY_TARGET`.
- For mocked Playwright E2E runs, set `DISABLE_BICP_PROXY=1`.

## Known issues
- None


## [0.4.38] - 2026-02-02

## Highlights
- Expanded connector support: **Metabase connector** + improved API/file/sql connector plumbing.
- Added **real E2E connector tests** (Playwright) and CI workflow scaffolding.

## Breaking changes
- None

## Features
- Core: add **Metabase connector**.
- Core: generalize SQL handling and improve connector abstractions.
- UI/CI: add Playwright **real connectors** E2E coverage (Postgres + Polymarket + file connector).

## Fixes
- Connector/server: improve API connector and server/tool integration.
- Tests: add coverage for run_sql/server/connectors.

## Security
- None

## Upgrade notes
- None

## Known issues
- macOS Gatekeeper may block running the downloaded release binary unless the artifact is signed/notarized.


## [0.4.37] - 2026-02-02

## Highlights
- Improved API connector auth configuration: you can now specify a **custom header name** (e.g. `X-Api-Key`).

## Breaking changes
- None

## Features
- UI: API connector form now supports **Header Name** when auth type is `header`.
- UI: auth field labeling is smarter for `query_param` (shows “Query Param Name” and defaults placeholder to `api_key`).

## Fixes
- Connector generation: when auth type is `header`, connector config now persists `header_name` to `connector.yaml`.

## Security
- None

## Upgrade notes
- None

## Known issues
- None
