# Testing

## Overview

db-mcp has three layers of testing across Python and TypeScript:

| Layer | Tool | Location | Tests | What it covers |
|-------|------|----------|-------|----------------|
| Python unit | pytest | `packages/core/tests/` | 49 | Core logic: onboarding, config, dialect, introspection, server |
| UI unit | Vitest | `packages/ui/src/__tests__/` | 20 | Pure functions: BICP client, utilities, link parsing |
| UI E2E | Playwright | `packages/ui/e2e/` | 24 | Full user flows: connectors, context viewer, navigation |

**Total: 93 tests**

## Running Tests

### Python

```bash
cd packages/core

# Run all tests
uv run pytest tests/ -v

# Run a specific file
uv run pytest tests/test_onboarding_flow.py -v

# Coverage report
uv run pytest tests/ --cov=db_mcp --cov-report=term-missing
```

Requires dev dependencies: `uv sync --all-extras`

### UI Unit Tests

```bash
cd packages/ui

# Run all unit tests
bun run test

# Watch mode (re-runs on file changes)
bun run test:watch

# Coverage report
bunx vitest run --coverage
```

### UI E2E Tests

```bash
cd packages/ui

# Run all E2E tests (headless, starts dev server automatically)
bunx playwright test

# Interactive UI mode (best for debugging)
bunx playwright test --ui

# Watch tests run in browser
bunx playwright test --headed

# Run a single spec
bunx playwright test connectors.spec.ts
```

First-time setup: `bunx playwright install chromium`

## CI/CD

All tests run automatically via GitHub Actions:

| Workflow | File | Trigger | What it runs |
|----------|------|---------|--------------|
| Lint & Unit Tests | `.github/workflows/lint.yml` | Push to `main`, all PRs | Ruff + pytest (Python), ESLint + tsc + Vitest (UI) |
| E2E Tests | `.github/workflows/e2e.yml` | Push to `main`, PRs touching `packages/ui/**` | Playwright (Chromium only) |
| Release | `.github/workflows/release.yml` | Version tags (`v*`) | Platform binary builds |

## Test Architecture

### Python Unit Tests

Standard pytest with `pytest-asyncio` for async tool functions. Tests use temporary directories and mock database connections — no real database required.

**Key fixtures:**
- `temp_connection_dir` — creates a temp dir and sets `CONNECTION_PATH` env var
- `mock_db_connection` — patches `test_connection` to return success without a real DB
- `mock_introspection` — patches catalog/schema/table/column discovery functions
- `temp_resources_dir` — creates temp dialect YAML files for dialect tests

**Test files:**

| File | Tests | Coverage area |
|------|-------|---------------|
| `test_onboarding_flow.py` | 13 | Start, discover (two-phase), reset, full flow integration |
| `test_onboarding_state.py` | 6 | State CRUD, progress calculation |
| `test_ignore.py` | 10 | `.db-mcpignore` pattern matching and filtering |
| `test_database.py` | 7 | Dialect detection, URL normalization |
| `test_dialect.py` | 5 | Dialect file loading, rule parsing |
| `test_introspection.py` | 6 | Table discovery, Trino/PostgreSQL handling |
| `test_server.py` | 2 | MCP server creation, tool registration |

### UI Unit Tests (Vitest)

Fast, isolated tests for exported pure functions. Uses jsdom environment with `@testing-library/jest-dom` matchers. Fetch is mocked via `vi.stubGlobal`.

**Test files:**

| File | Tests | Coverage area |
|------|-------|---------------|
| `bicp.test.ts` | 7 | `bicpCall` (JSON-RPC format, errors, config), `initialize` |
| `utils.test.ts` | 7 | `cn` utility (class merging, tailwind dedup, edge cases) |
| `parse-db-link.test.ts` | 6 | `parseDbLink` (full/partial links, invalid inputs) |

### UI E2E Tests (Playwright)

Browser-level tests that mock all BICP (JSON-RPC) calls at the network layer via `page.route()`. No real backend needed — tests are fast and deterministic.

**Key infrastructure:**
- `e2e/fixtures/bicp-mock.ts` — `BICPMock` class with default happy-path handlers, per-test overrides (`.on()`, `.onError()`), and call recording (`.getCalls()`)
- `e2e/fixtures/mock-data.ts` — All mock response constants (connections, context tree, file content, git history)
- `e2e/fixtures/index.ts` — Re-exports `test`, `expect`, `mockData`
- The `bicpMock` fixture uses `{ auto: true }` so it installs on every test automatically

**Test files:**

| File | Tests | Coverage area |
|------|-------|---------------|
| `navigation.spec.ts` | 4 | Root redirect, tab rendering, switching, active highlight |
| `connectors.spec.ts` | 10 | Connection list, create/edit/delete, test URL, switch, errors |
| `context.spec.ts` | 10 | Tree rendering, folder expansion, file loading, create modal, errors |

## Coverage

### Python (15% overall, higher on tested modules)

| Module | Coverage | Notes |
|--------|----------|-------|
| `onboarding/state.py` | 85% | Well-covered |
| `config.py` | 74% | Well-covered |
| `dialect.py` | 67% | Good |
| `tools/onboarding.py` | 48% | Two-phase discover covered |
| `onboarding/ignore.py` | 51% | Pattern matching covered |
| `server.py` | 54% | Tool registration covered |
| `cli.py`, `bicp/agent.py`, `ui_server.py` | 0% | Integration-heavy, needs running server |

### UI (Vitest)

| Module | Stmts | Branch | Funcs | Lines |
|--------|-------|--------|-------|-------|
| `lib/utils.ts` | 100% | 100% | 100% | 100% |
| `lib/bicp.ts` | 36% | 60% | 20% | 36% |
| `SchemaExplorer.tsx` | 6% | 7% | 2% | 6% |

`bicp.ts` is low because schema/git wrapper functions and the `useBICP` hook aren't unit-tested — they're thin wrappers covered by E2E tests. `SchemaExplorer.tsx` is 800+ lines of React component; only `parseDbLink` is unit-testable as a pure function.

## Writing New Tests

### Python

1. Create a test file in `packages/core/tests/test_*.py`
2. Use `temp_connection_dir` fixture for tests that need file I/O
3. Mock external dependencies (database, network) — don't require real services
4. Use `@pytest.mark.asyncio` for async functions
5. Run: `uv run pytest tests/test_your_file.py -v`

### UI Pure Functions

1. Export the function from its module
2. Create a test file in `packages/ui/src/__tests__/*.test.ts`
3. Import from `@/...` (alias configured in `vitest.config.ts`)
4. Mock `fetch` with `vi.stubGlobal` if needed
5. Run: `bun run test`

### UI Pages/Flows

1. Create a spec file in `packages/ui/e2e/*.spec.ts`
2. Import `{ test, expect, mockData }` from `./fixtures`
3. Override BICP responses with `bicpMock.on("method", handler)` for non-happy-path tests
4. Use `bicpMock.getCalls("method")` to assert the UI sent correct params
5. Run: `bunx playwright test your-file.spec.ts`
