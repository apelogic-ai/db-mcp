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

## Commands

| Command | Description |
|---------|-------------|
| `dbmcp init [NAME]` | Configure a new database connection |
| `dbmcp start` | Start MCP server (used by Claude Desktop) |
| `dbmcp status` | Show current configuration |
| `dbmcp list` | List all connections |
| `dbmcp use NAME` | Switch active connection |
| `dbmcp console` | Open trace viewer UI |

## How It Works

dbmcp is an MCP (Model Context Protocol) server that:

1. Introspects your database schema
2. Builds a semantic understanding of your data
3. Generates and validates SQL from natural language
4. Returns results to Claude Desktop

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

# Build binary
uv run python scripts/build.py
```

## License

MIT
