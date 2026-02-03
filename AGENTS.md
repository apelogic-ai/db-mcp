# AGENTS.md

This file mirrors the repo guidance in `CLAUDE.md` and serves as the main agent handbook for working on db-mcp. Do not remove `CLAUDE.md`.

## Project Overview

`db-mcp` is an MCP (Model Context Protocol) server that enables Claude Desktop to query databases using natural language. It was extracted from the `semantic-grid` project as a standalone component.

Core capabilities:
- Introspects database schemas automatically
- Builds a semantic understanding of data through interactive onboarding
- Generates and validates SQL from natural language
- Supports multiple database backends

## Repository Structure (Monorepo)

```
packages/
  core/    # Main application package (db-mcp)
  models/  # Shared data models (db-mcp-models)
  ui/      # Next.js UI application
```

Key paths:
- `packages/core/src/db_mcp/` - primary Python source
- `packages/models/src/db_mcp_models/` - shared Pydantic models
- `packages/ui/` - Next.js UI
- `docs/` - design documents

## Technology Stack

- Python 3.13+
- FastMCP (>=2.0.0)
- Pydantic AI with MCPSamplingModel
- SQLAlchemy 2.0, SQLGlot
- Click + Rich for CLI
- OpenTelemetry for observability

Supported databases: PostgreSQL, ClickHouse, Trino, MySQL, SQL Server

## Key Modules (Core)

- `cli.py` - CLI entry point
- `server.py` - FastMCP server initialization and tool registration
- `config.py` - Settings and connection management
- `dialect.py` - SQL dialect detection
- `db/` - database abstraction and introspection
- `tools/` - MCP tools (database, generation, onboarding, validation, training)
- `onboarding/` - schema discovery and documentation workflow
- `training/` - query examples and feedback
- `tasks/` - query/task history storage
- `vault/` - storage backends (local filesystem, S3)
- `console/` - trace viewer UI
- `validation/` - SQL validation and cost estimation
- `bicp/` - BICP agent for UI communication
- `ui_server.py` - FastAPI server for UI + BICP endpoint
- `migrations/` - data migrations for connection storage
- `metrics/` - business metrics storage and retrieval

## UI Package Notes

The UI uses `bun` as its package manager. Always use `bun` commands in `packages/ui` (never `npm` or `yarn`).

## Code Style

- Line length: 99
- Linter: Ruff (E, F, I, W)
- Quote style: Double quotes
- Python 3.13+
- Type hints encouraged

## Ground Rules

- Never switch git branches unless explicitly told to do so.
- Never commit changes unless explicitly told to do so.
- Never start dev servers or run `dev.sh` unless explicitly asked.
- Stay on the current branch for the entire session.
- If a task requires a different branch, ask the user first.

## After Every Code Change

Always run linting and tests after making code changes.

### Python changes (`packages/core/`)

```bash
cd packages/core
uv run ruff check . --fix
uv run pytest tests/ -v
```

### UI changes (`packages/ui/`)

```bash
cd packages/ui
npx next lint
npx next build
npx playwright test
```

## Test-Driven Development (TDD)

All new Python code must follow TDD:
1. Write tests first
2. Run tests to confirm failure
3. Implement minimal change
4. Refactor
5. Repeat

Bug fixes should start with a failing test that reproduces the issue.

## Documentation

See `docs/` for design and implementation documents, including:
- `docs/ui-spec.md`
- `docs/migrations.md`
- `docs/metrics-layer.md`
- `docs/knowledge-extraction-agent.md`
- `docs/electron-port-feasibility.md`
- `docs/data-gateway.md`
- `docs/testing.md`
