# Quickstart

Get from zero to your first db-mcp-backed agent query in a few minutes, using the built-in Playground (Chinook SQLite) database.

## 1. Install

```bash
curl -fsSL https://download.apelogic.ai/db-mcp/install.sh | sh
```

## 2. Install the built-in Playground connection

```bash
db-mcp playground install
db-mcp playground status
```

You should see:

- `Playground: installed`
- `Connection: playground`
- a local SQLite path (Chinook sample DB)

![Playground status output](assets/cli-playground-status.png)

## 3. Make Playground active and verify

```bash
db-mcp use playground
db-mcp status
```

You should see:

- `playground` as active connection
- agent setup status

## 4. Configure agent integration

```bash
db-mcp agents
```

If you want non-interactive setup:

```bash
db-mcp agents --all
```

`db-mcp agents --list` sample after setup:

![Detected MCP agents](assets/cli-agents-list.png)

## 5. Start querying from your agent

In your agent client (for example Claude Desktop), ask a natural-language question against the Chinook sample data, such as:

> "What are the top 10 customers by total invoice amount?"

db-mcp handles schema/context lookup, SQL generation/validation, and execution through MCP tools.

Tip:

- New connections default to `TOOL_MODE=shell`, so the agent will follow a vault-first workflow (`PROTOCOL.md`, `schema/descriptions.yaml`, `examples/*.yaml`).

## 6. Optional: inspect Playground schema

```bash
db-mcp discover -c playground
```

![Discover output for playground](assets/cli-discover-playground.png)

## 7. Optional: run server or UI manually

```bash
db-mcp start     # MCP stdio server (normally launched by the client)
db-mcp ui        # Web UI
db-mcp console   # Trace console
```

## 8. Verify activity

```bash
db-mcp traces status
```

Or open the UI and inspect `/traces` and `/insights`.

![Traces — OpenTelemetry viewer for MCP operations](assets/ui-traces.jpg)

## 9. Connect your own database (when ready)

```bash
db-mcp init mydb
db-mcp use mydb
db-mcp status
```

Use Playground for first-run testing, then switch to your real connection.

Next:

- [How-To Guides](how-to-guides.md)
- [Install and Configuration](install-and-configuration.md)
- [Working with Agents](working-with-agents.md)
