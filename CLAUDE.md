# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

db-mcp is an MCP (Model Context Protocol) server that enables Claude Desktop to query databases using natural language. It was extracted from the [semantic-grid](https://github.com/apelogic-ai/semantic-grid) project as a standalone component.

The server:
- Introspects database schemas automatically
- Builds a semantic understanding of data through interactive onboarding
- Generates and validates SQL from natural language
- Supports multiple database backends

### Roadmap Vision

The `docs/` directory contains design documents for planned features:
- **Metrics Layer** (`metrics-layer.md`) - Semantic metrics definitions for consistent business KPIs
- **Knowledge Extraction Agent** (`knowledge-extraction-agent.md`) - Background agent that learns from query traces
- **Electron Desktop App** (`electron-port-feasibility.md`) - Desktop GUI with Electron shell + db-mcp sidecar
- **Semantic Data Gateway** (`data-gateway.md`) - Unified gateway for multiple data sources (CSV, BI tools, dbt)

## Repository Structure

This is a Python monorepo managed with UV workspaces:

```
db-mcp/
├── packages/
│   ├── core/                    # Main application package (db-mcp)
│   │   ├── src/db_mcp/          # Source code
│   │   ├── tests/               # Test suite
│   │   ├── scripts/             # Build scripts
│   │   └── pyproject.toml       # Package config
│   ├── models/                  # Shared data models (db-mcp-models)
│   │   ├── src/db_mcp_models/
│   │   └── pyproject.toml
│   └── ui/                      # Next.js UI application
│       ├── app/                 # App Router pages
│       ├── components/          # React components
│       ├── lib/                 # BICP client, contexts
│       └── package.json
├── docs/                        # Design documents
├── scripts/                     # Installation scripts
├── .github/workflows/           # CI/CD (release.yml)
├── pyproject.toml               # Workspace root config
└── uv.lock                      # Dependency lockfile
```

### Core Package (`packages/core/src/db_mcp/`)

| Module | Purpose |
|--------|---------|
| `cli.py` | Command-line interface (main entry point) |
| `server.py` | FastMCP server initialization and tool registration |
| `config.py` | Settings management (connections, storage) |
| `dialect.py` | SQL dialect detection |
| `db/` | Database abstraction (connection, introspection) |
| `tools/` | MCP tools (database, generation, onboarding, validation, training) |
| `onboarding/` | Schema discovery and documentation workflow |
| `training/` | Query examples and feedback management |
| `tasks/` | Query/task history storage |
| `vault/` | Storage backends (local filesystem, S3) |
| `console/` | Trace viewer UI |
| `validation/` | SQL validation and cost estimation |
| `bicp/` | BICP agent for UI communication (JSON-RPC handler) |
| `ui_server.py` | FastAPI server for UI + BICP endpoint |
| `migrations/` | Database-style migrations for connection data |
| `metrics/` | Business metrics storage and retrieval |

### UI Package (`packages/ui/`)

Next.js application providing a local control plane for db-mcp.

**IMPORTANT: The UI package uses `bun` as its package manager. Always use `bun add`, `bun install`, `bunx` etc. — never `yarn` or `npm`.**

| Directory | Purpose |
|-----------|---------|
| `app/` | Next.js App Router pages |
| `app/connectors/` | Connection management UI |
| `app/context/` | Context viewer (file browser + editor) |
| `components/ui/` | shadcn/ui components |
| `components/context/` | TreeView and CodeEditor components |
| `lib/` | BICP client, React contexts, hooks |

### Models Package (`packages/models/src/db_mcp_models/`)

Shared Pydantic models: `OnboardingState`, `QueryResult`, `Task`, `QueryExample`, `GridSpec`, etc.

## Technology Stack

- **Python**: 3.13+
- **MCP Framework**: FastMCP (>=2.0.0)
- **AI/LLM**: Pydantic AI with MCPSamplingModel
- **Database**: SQLAlchemy 2.0, SQLGlot
- **CLI**: Click, Rich
- **Observability**: OpenTelemetry

### Supported Databases

PostgreSQL, ClickHouse, Trino, MySQL, SQL Server

## Development Commands

### Setup

```bash
# Install dependencies
uv sync

# Install with dev dependencies
cd packages/core
uv sync --all-extras
```

### Running Locally

```bash
cd packages/core

# Run CLI
uv run db-mcp --help

# Initialize a connection
uv run db-mcp init [NAME]

# Start MCP server (stdio mode)
uv run db-mcp start

# Check configuration
uv run db-mcp status
```

### Testing

```bash
# Python unit tests (49 tests)
cd packages/core
uv run pytest tests/ -v

# Python coverage
uv run pytest tests/ --cov=db_mcp --cov-report=term-missing

# UI unit tests (20 tests, Vitest)
cd packages/ui
bun run test

# UI coverage
bunx vitest run --coverage

# UI E2E tests (24 tests, Playwright — requires dev server)
cd packages/ui
bunx playwright test
bunx playwright test --ui       # interactive mode
bunx playwright test --headed   # watch in browser
```

### Linting

```bash
# Python
cd packages/core
uv run ruff check . --fix

# UI
cd packages/ui
bun run lint
bunx tsc --noEmit
```

### Building Binary

```bash
cd packages/core
uv run python scripts/build.py
```

Output: Platform-specific binary in `dist/`

## Configuration

### File Locations

| Path | Purpose |
|------|---------|
| `~/.db-mcp/config.yaml` | Global CLI config, active connection |
| `~/.db-mcp/migrations.yaml` | Migration tracking (which migrations have run) |
| `~/.db-mcp/connections/{name}/.env` | Database credentials (gitignored) |
| `~/.db-mcp/connections/{name}/schema/` | Schema descriptions |
| `~/.db-mcp/connections/{name}/domain/` | Domain model |
| `~/.db-mcp/connections/{name}/training/` | Query examples and feedback |
| `~/.db-mcp/connections/{name}/training/examples/` | Individual example files |
| `~/.db-mcp/connections/{name}/instructions/` | Business rules for SQL generation |
| `~/.db-mcp/connections/{name}/metrics/` | Business metric definitions |

### Knowledge Vault Structure

Each connection directory forms a "knowledge vault" with semantic layer components:

```
~/.db-mcp/connections/{name}/
├── .env                          # Database credentials (gitignored)
├── schema/
│   └── descriptions.yaml         # Table/column descriptions
├── domain/
│   └── model.yaml               # Domain model (entities, relationships)
├── training/
│   ├── examples/                # Query examples (one file per example)
│   │   └── *.yaml
│   └── feedback.yaml            # Query feedback log
├── instructions/
│   └── business_rules.yaml      # Business rules for SQL generation
├── metrics/
│   └── catalog.yaml             # Business metric definitions (DAU, revenue, etc.)
└── README.md
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Connection string (required) |
| `CONNECTION_NAME` | Active connection name |
| `CONNECTION_PATH` | Full path to connection directory |
| `TOOL_MODE` | "detailed" or "shell" |
| `LOG_LEVEL` | Logging level (default: INFO) |

## CLI Commands Reference

| Command | Description |
|---------|-------------|
| `db-mcp init [NAME]` | Configure new database connection |
| `db-mcp start` | Start MCP server |
| `db-mcp ui` | Start UI server and open browser |
| `db-mcp status` | Show current configuration |
| `db-mcp list` | List all connections |
| `db-mcp use NAME` | Switch active connection |
| `db-mcp config` | Open config in editor |
| `db-mcp console` | Open trace viewer UI |
| `db-mcp edit [NAME]` | Edit connection credentials |
| `db-mcp git-init [NAME]` | Enable git sync |
| `db-mcp sync [NAME]` | Sync with git remote |
| `db-mcp pull [NAME]` | Pull from git |
| `db-mcp rename OLD NEW` | Rename connection |
| `db-mcp remove NAME` | Remove connection |

## Code Style

- **Line length**: 99 characters
- **Linter**: Ruff (rules: E, F, I, W)
- **Quote style**: Double quotes
- **Python version**: 3.13+
- **Type hints**: Encouraged, Pydantic models for validation

Run `uv run ruff check . --fix` before committing.

## Key Architectural Patterns

### MCP Tools Structure

Tools are registered in `server.py` and implemented in `tools/`:
- `database.py` - Connection, schema discovery
- `generation.py` - SQL generation from natural language
- `onboarding.py` - Interactive schema setup
- `validation.py` - SQL validation, cost analysis
- `training.py` - Query examples and feedback
- `domain.py` - Domain model generation
- `shell.py` - Shell mode operations

### Onboarding Flow

1. **Discovery**: Introspect database schema (catalogs, schemas, tables, columns)
2. **Review**: User describes tables/columns, sets ignore patterns
3. **Domain Building**: Generate domain model from descriptions
4. **Complete**: Ready for query generation

State tracked in `OnboardingState` (phases: discovery, review, domain-building, complete)

### Storage Backends

- **Local**: Filesystem (`~/.db-mcp/`)
- **S3**: AWS S3 with configurable bucket/prefix
- **Git**: Optional sync for team collaboration

## Release Process

CI/CD via `.github/workflows/release.yml`:
1. Tag with `v*` pattern triggers build
2. Builds platform binaries (macOS arm64/x64, Linux x64, Windows x64) via PyInstaller
3. Creates GitHub Release with binaries

Binary build artifacts:
- PyInstaller spec: `packages/core/db-mcp.spec`
- Build script: `packages/core/scripts/build.py`
- Output: `~67MB` platform-specific binary

## Ground Rules

- **NEVER switch git branches unless explicitly told to do so by the user**
- **NEVER commit changes unless explicitly told to do so by the user**
- **NEVER start dev servers or run dev.sh unless explicitly asked by the user**
- Stay on the current branch for the entire session
- If a task seems to require a different branch, ask the user first
- If you think changes should be committed, ask the user first

## After Every Code Change

Always run linting and tests after making code changes.

### Python changes (`packages/core/`)

```bash
cd packages/core
uv run ruff check . --fix       # Lint (required)
uv run pytest tests/ -v          # Unit tests (required)
```

### UI changes (`packages/ui/`)

```bash
cd packages/ui
bun run lint                     # ESLint (required)
bunx tsc --noEmit                # Type check (required)
bun run test                     # Unit tests (required)
bunx playwright test             # E2E tests (required for UI changes)
```

### Requirements before considering a task complete

1. All linting errors must be fixed
2. All existing tests must still pass
3. **New code must have tests** — this is mandatory, not optional:
   - Python: add tests in `packages/core/tests/`
   - UI pure functions/utilities: add Vitest tests in `packages/ui/src/__tests__/`
   - UI pages/flows: add Playwright E2E tests in `packages/ui/e2e/`
4. Type hints should be added for new Python functions/methods

## Documentation

The `docs/` directory contains design and implementation documents:

| Document | Purpose |
|----------|---------|
| `ui-spec.md` | UI specification and implementation status |
| `migrations.md` | Database-style migrations system documentation |
| `metrics-layer.md` | Design for semantic metrics layer (DAU, revenue, retention definitions) |
| `knowledge-extraction-agent.md` | Background agent that extracts learnings from OTel traces |
| `electron-port-feasibility.md` | Analysis and decision for Electron desktop app (sidecar pattern chosen) |
| `data-gateway.md` | Vision for unified data gateway across multiple sources |
| `testing.md` | Testing strategy, infrastructure, and coverage report |
