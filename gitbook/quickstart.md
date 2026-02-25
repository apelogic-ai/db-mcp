# Quickstart

Get from zero to your first db-mcp-backed agent query in a few minutes.

## 1. Install

```bash
curl -fsSL https://download.apelogic.ai/db-mcp/install.sh | sh
```

## 2. Create your first connection

```bash
db-mcp init mydb
```

The setup flow configures:

- your connection credentials
- local connection directory under `~/.db-mcp/connections/mydb`
- agent integration (or lets you configure agents later)

## 3. Check status

```bash
db-mcp status
```

You should see:

- an active connection
- credentials present (`.env`)
- agent setup status

## 4. Start querying from your agent

In your agent client (for example Claude Desktop), ask a natural-language question such as:

> "What are the top 10 customers by revenue this quarter?"

db-mcp handles schema/context lookup, SQL generation/validation, and execution through MCP tools.

## 5. Optional: run server or UI manually

```bash
db-mcp start     # MCP stdio server (normally launched by the client)
db-mcp ui        # Web UI
db-mcp console   # Trace console
```

Next:

- [Install and Configuration](install-and-configuration.md)
- [Working with Agents](working-with-agents.md)
