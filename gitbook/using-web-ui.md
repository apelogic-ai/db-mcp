# Using the Web UI

The Web UI gives you an operator console for connections, context, metrics, insights, and traces.

## Start the UI

```bash
db-mcp ui
```

Optional flags:

```bash
db-mcp ui -p 8080
db-mcp ui -c mydb
db-mcp ui -v
```

## Main screens

## Config (`/config`)

Use this to:

- create/edit/delete connections
- test connectivity
- sync/discover API connections
- set active connection
- configure agents from UI dialogs

## Context (`/context`)

Use this to browse and edit connection knowledge artifacts:

- schema descriptions
- domain model
- examples
- instructions/rules
- learnings

This is the fastest way to inspect what db-mcp and your agents have learned.

## Insights (`/insights`)

Shows patterns derived from traces and usage:

- knowledge capture trends
- vocabulary gaps
- repeated query opportunities
- validation and quality signals

## Metrics (`/metrics`)

Manage metric and dimension catalogs:

- list approved metrics/dimensions
- discover candidates from vault artifacts
- approve/edit/remove entries

## Traces (`/traces`)

OpenTelemetry trace viewer:

- live and historical trace lists
- span drill-down for tool calls
- timing and error inspection

## Operational notes

- `db-mcp ui` starts a local FastAPI service and opens browser automatically.
- UI actions operate on the same connection state used by CLI and MCP server.
- For clean shutdown, stop with `Ctrl+C`.
