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
- **Electron Desktop App** (`electron-port-feasibility.md`) - Desktop GUI with Electron shell + dbmcp sidecar
- **Semantic Data Gateway** (`data-gateway.md`) - Unified gateway for multiple data sources (CSV, BI tools, dbt)

## Repository Structure

This is a Python monorepo managed with UV workspaces:

```
db-mcp/
├── packages/
│   ├── core/                    # Main application package (dbmcp)
│   │   ├── src/dbmcp/           # Source code
│   │   ├── tests/               # Test suite
│   │   ├── scripts/             # Build scripts
│   │   └── pyproject.toml       # Package config
│   └── models/                  # Shared data models (dbmcp-models)
│       ├── src/dbmcp_models/
│       └── pyproject.toml
├── docs/                        # GitHub Pages documentation
├── scripts/                     # Installation scripts
├── .github/workflows/           # CI/CD (release.yml)
├── pyproject.toml               # Workspace root config
└── uv.lock                      # Dependency lockfile
```

### Core Package (`packages/core/src/dbmcp/`)

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

### Models Package (`packages/models/src/dbmcp_models/`)

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
uv run dbmcp --help

# Initialize a connection
uv run dbmcp init [NAME]

# Start MCP server (stdio mode)
uv run dbmcp start

# Check configuration
uv run dbmcp status
```

### Testing

```bash
cd packages/core
pytest tests/
```

### Linting

```bash
# From root or packages/core
uv run ruff check . --fix
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
| `~/.dbmcp/config.yaml` | Global CLI config, active connection |
| `~/.dbmcp/connections/{name}/.env` | Database credentials (gitignored) |
| `~/.dbmcp/connections/{name}/schema/` | Schema descriptions |
| `~/.dbmcp/connections/{name}/domain/` | Domain model |
| `~/.dbmcp/connections/{name}/training/` | Query examples |

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
| `dbmcp init [NAME]` | Configure new database connection |
| `dbmcp start` | Start MCP server |
| `dbmcp status` | Show current configuration |
| `dbmcp list` | List all connections |
| `dbmcp use NAME` | Switch active connection |
| `dbmcp config` | Open config in editor |
| `dbmcp console` | Open trace viewer UI |
| `dbmcp edit [NAME]` | Edit connection credentials |
| `dbmcp git-init [NAME]` | Enable git sync |
| `dbmcp sync [NAME]` | Sync with git remote |
| `dbmcp pull [NAME]` | Pull from git |
| `dbmcp rename OLD NEW` | Rename connection |
| `dbmcp remove NAME` | Remove connection |

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

- **Local**: Filesystem (`~/.dbmcp/`)
- **S3**: AWS S3 with configurable bucket/prefix
- **Git**: Optional sync for team collaboration

## Release Process

CI/CD via `.github/workflows/release.yml`:
1. Tag with `v*` pattern triggers build
2. Builds platform binaries (macOS arm64/x64, Linux x64, Windows x64) via PyInstaller
3. Creates GitHub Release with binaries

Binary build artifacts:
- PyInstaller spec: `packages/core/dbmcp.spec`
- Build script: `packages/core/scripts/build.py`
- Output: `~67MB` platform-specific binary

## Ground Rules

- **NEVER switch git branches unless explicitly told to do so by the user**
- **NEVER commit changes unless explicitly told to do so by the user**
- Stay on the current branch for the entire session
- If a task seems to require a different branch, ask the user first
- If you think changes should be committed, ask the user first

## After Every Code Change

Always run linting after making code changes:

```bash
cd packages/core
uv run ruff check . --fix
```

Fix any errors before considering the task complete.

## Documentation

The `docs/` directory contains design documents (not user-facing docs):

| Document | Purpose |
|----------|---------|
| `metrics-layer.md` | Design for semantic metrics layer (DAU, revenue, retention definitions) |
| `knowledge-extraction-agent.md` | Background agent that extracts learnings from OTel traces |
| `electron-port-feasibility.md` | Analysis and decision for Electron desktop app (sidecar pattern chosen) |
| `data-gateway.md` | Vision for unified data gateway across multiple sources |

These are planning documents for future features, not implementation guides.
