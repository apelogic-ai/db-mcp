# db-mcp

Database MCP server for Claude Desktop. Query your databases using natural language.

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/apelogic-ai/db-mcp/main/scripts/install.sh | sh
```

## Quick Start

```bash
# Configure your database and Claude Desktop
dbmcp init

# Check configuration
dbmcp status
```

## Supported Databases

- PostgreSQL
- ClickHouse
- Trino
- MySQL
- SQL Server

## How It Works

dbmcp is an MCP (Model Context Protocol) server that:

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

| Command | Description |
|---------|-------------|
| `dbmcp init [NAME]` | Configure a new database connection |
| `dbmcp start` | Start MCP server (used by Claude Desktop) |
| `dbmcp status` | Show current configuration |
| `dbmcp list` | List all connections |
| `dbmcp use NAME` | Switch active connection |
| `dbmcp config` | Open config in editor |
| `dbmcp console` | Open trace viewer UI |
| `dbmcp edit [NAME]` | Edit connection credentials |
| `dbmcp git-init [NAME]` | Enable git sync for connection |
| `dbmcp sync [NAME]` | Sync changes with git remote |
| `dbmcp pull [NAME]` | Pull updates from git |
| `dbmcp rename OLD NEW` | Rename a connection |
| `dbmcp remove NAME` | Remove a connection |

## Configuration

Connection data is stored in `~/.dbmcp/`:

```
~/.dbmcp/
├── config.yaml                      # Global config, active connection
└── connections/{name}/
    ├── .env                         # Database credentials (gitignored)
    ├── schema/descriptions.yaml     # Table/column descriptions
    ├── domain/model.md              # Domain model documentation
    ├── training/                    # Query examples
    └── state.yaml                   # Onboarding state
```

## Development

```bash
# Clone
git clone https://github.com/apelogic-ai/db-mcp.git
cd db-mcp

# Install dependencies
uv sync

# Run locally
cd packages/core
uv run dbmcp --help

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
│   ├── core/                # Main application (dbmcp)
│   └── models/              # Shared Pydantic models (dbmcp-models)
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
