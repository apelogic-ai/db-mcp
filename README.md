# db-mcp

Database MCP server for Claude Desktop. Query your databases using natural language.

## Installation

```bash
curl -fsSL https://download.apelogic.ai/db-mcp/install.sh | sh
```

## Quick Start

```bash
# Configure your database and Claude Desktop
db-mcp init

# Check configuration
db-mcp status
```

## Supported Databases

- PostgreSQL
- ClickHouse
- Trino
- MySQL
- SQL Server

## How It Works

db-mcp is an MCP (Model Context Protocol) server that:

1. **Introspects** your database schema automatically
2. **Onboards** you through an interactive flow to describe tables and columns
3. **Generates** SQL from natural language using the semantic layer
4. **Validates** queries (EXPLAIN, cost estimation) before execution
5. **Returns** results to Claude Desktop with full lineage

### Key Features

- **Semantic Layer**: Build understanding of your data through interactive onboarding
- **Query Validation**: Cost guards and read-only enforcement
- **Team Collaboration**: Git-based sync for sharing semantic layers
- **Multi-Connection**: Manage multiple database connections
- **Training Examples**: Capture good queries to improve future generation

## Commands

### Setup & Configuration

| Command | Description |
|---------|-------------|
| `db-mcp init [NAME]` | Interactive setup wizard - configure database and Claude Desktop |
| `db-mcp status` | Show current configuration status |
| `db-mcp config` | Open config file in editor |

### Connection Management

| Command | Description |
|---------|-------------|
| `db-mcp list` | List all configured connections |
| `db-mcp use NAME` | Switch to a different connection |
| `db-mcp edit [NAME]` | Edit connection credentials (.env file) |
| `db-mcp rename OLD NEW` | Rename a connection |
| `db-mcp remove NAME` | Remove a connection |
| `db-mcp all COMMAND` | Run a command for all connections |

### Server & Diagnostics

| Command | Description |
|---------|-------------|
| `db-mcp start` | Start the MCP server (stdio mode for Claude Desktop) |
| `db-mcp console` | Start local trace console (view MCP server activity) |
| `db-mcp traces` | Manage trace capture for diagnostics and learning |

### Git Sync (Team Collaboration)

| Command | Description |
|---------|-------------|
| `db-mcp git-init [NAME]` | Enable git sync for an existing connection |
| `db-mcp sync [NAME]` | Sync connection changes with git remote |
| `db-mcp pull [NAME]` | Pull connection updates from git remote |

### Migration

| Command | Description |
|---------|-------------|
| `db-mcp migrate` | Migrate from legacy storage format to new connection structure |

## Configuration

Connection data is stored in `~/.db-mcp/`:

```
~/.db-mcp/
├── config.yaml                      # Global config, active connection
└── connections/{name}/
    ├── .env                         # Database credentials (gitignored)
    ├── state.yaml                   # Onboarding state
    ├── schema/
    │   └── descriptions.yaml        # Table/column descriptions
    ├── domain/
    │   └── model.md                 # Domain model documentation
    ├── training/
    │   ├── examples.yaml            # Query examples (NL → SQL mappings)
    │   └── instructions.yaml        # Custom SQL generation rules
    └── .git/                        # Optional git sync for team sharing
```

### Configuration Artifacts

| File | Purpose |
|------|---------|
| `config.yaml` | Global settings: active connection, preferences |
| `.env` | Database URL and credentials (never committed to git) |
| `state.yaml` | Onboarding progress (discovery → review → domain-building → complete) |
| `schema/descriptions.yaml` | Human-readable descriptions of tables and columns |
| `domain/model.md` | Business domain documentation for the LLM |
| `training/examples.yaml` | Known-good query examples to guide SQL generation |
| `training/instructions.yaml` | Custom rules and constraints for SQL generation |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Connection string (required) |
| `CONNECTION_NAME` | Override active connection |
| `CONNECTION_PATH` | Override connection directory path |
| `LOG_LEVEL` | Logging verbosity (default: INFO) |

## Development

```bash
# Clone
git clone https://github.com/apelogic-ai/db-mcp.git
cd db-mcp

# Install dependencies
uv sync

# Run locally
cd packages/core
uv run db-mcp --help

# Run tests
pytest tests/

# Lint
uv run ruff check . --fix

# Build binary
uv run python scripts/build.py
```

### Project Structure

```
db-mcp/
├── packages/
│   ├── core/                # Main application (db-mcp)
│   └── models/              # Shared Pydantic models (db-mcp-models)
├── docs/                    # Design documents
├── scripts/                 # Installation scripts
└── .github/workflows/       # CI/CD
```

## Roadmap

See `docs/` for design documents on planned features:
- **Metrics Layer** - Semantic metric definitions (DAU, revenue, etc.)
- **Desktop App** - Electron GUI with visual query builder
- **Knowledge Extraction** - Learn from query traces automatically
- **Data Gateway** - Unified access to multiple data sources

## License

MIT
