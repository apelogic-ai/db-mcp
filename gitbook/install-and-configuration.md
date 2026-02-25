# Install and Configuration

## Installation

```bash
curl -fsSL https://download.apelogic.ai/db-mcp/install.sh | sh
```

Then verify:

```bash
db-mcp --version
db-mcp --help
```

## Configuration model

db-mcp stores global and per-connection state in `~/.db-mcp`.

```text
~/.db-mcp/
├── config.yaml
└── connections/{name}/
    ├── connector.yaml
    ├── .env
    ├── state.yaml
    ├── schema/
    ├── domain/
    ├── training/
    ├── learnings/
    └── traces/
```

## `connector.yaml` vs `.env`

Use both:

- `connector.yaml` describes connector type and behavior (`sql`, `api`, `file`, `metabase`, capabilities, metadata).
- `.env` stores secrets and credentials (for SQL usually `DATABASE_URL`).

Notes:

- `connector.yaml` is the canonical connector manifest for db-mcp.
- For plain SQL, db-mcp can fall back without `connector.yaml`, but adding it is recommended for consistent multi-connection behavior.

Minimal SQL example:

```yaml
type: sql
dialect: postgresql
description: Primary analytics warehouse
```

Minimal API example:

```yaml
type: api
base_url: https://api.example.com
auth:
  type: bearer
  token_env: API_TOKEN
```

## Create and manage connections

```bash
db-mcp init mydb
db-mcp list
db-mcp use mydb
db-mcp edit mydb
db-mcp remove mydb
```

## Important environment variables

- `DATABASE_URL`: database connection URL (usually from connection `.env`)
- `CONNECTION_NAME`: active connection name
- `CONNECTION_PATH`: active connection directory
- `CONNECTIONS_DIR`: base directory for all connections
- `LOG_LEVEL`: runtime logging level
- `TOOL_MODE`: MCP tool exposure mode (`detailed` or `shell`)

## Validate setup

```bash
db-mcp status
db-mcp discover --connection mydb --format yaml
```

If setup looks good, continue to [Using the CLI](using-cli.md) and [Working with Agents](working-with-agents.md).
