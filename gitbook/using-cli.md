# Using the CLI

The `db-mcp` CLI is the primary way to create connections, run services, and manage collaboration flows.

## Core lifecycle

```bash
db-mcp init mydb
db-mcp status
db-mcp start
```

## Common commands

### Connection management

- `db-mcp list`
- `db-mcp use NAME`
- `db-mcp edit [NAME]`
- `db-mcp rename OLD NEW`
- `db-mcp remove NAME`
- `db-mcp all COMMAND`

### Service commands

- `db-mcp start`
- `db-mcp ui`
- `db-mcp console`
- `db-mcp playground install`
- `db-mcp playground status`

### Agent integration

- `db-mcp agents`
- `db-mcp agents --list`
- `db-mcp agents --all`
- `db-mcp agents -A claude-desktop -A codex`

### Discovery and diagnostics

- `db-mcp discover --connection NAME`
- `db-mcp discover --url <database_url>`
- `db-mcp traces on`
- `db-mcp traces off`
- `db-mcp traces status`

### Git and team sync

- `db-mcp git-init [NAME] [REMOTE_URL]`
- `db-mcp pull [NAME]`
- `db-mcp sync [NAME]`

### Collaboration group

- `db-mcp collab init`
- `db-mcp collab attach <repo-url>`
- `db-mcp collab join`
- `db-mcp collab sync`
- `db-mcp collab merge`
- `db-mcp collab status`
- `db-mcp collab members`

## Typical daily workflow

```bash
# Start your day
db-mcp pull analytics
db-mcp use analytics
db-mcp status

# Work with your agent
# ...ask queries in agent...

# Capture and share updates
db-mcp traces status
db-mcp sync analytics
```

## Help and command introspection

```bash
db-mcp --help
db-mcp <command> --help
db-mcp collab --help
db-mcp traces --help
```
