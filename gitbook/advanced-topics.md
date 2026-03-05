# Advanced Topics

This section covers operational and architecture-level workflows after initial setup.

## Knowledge management lifecycle

Each connection has a local knowledge vault that evolves over time:

- schema descriptions
- domain model
- examples (`NL -> SQL`)
- rules/instructions
- learnings from failures and refinements

Recommended loop:

1. Seed schema/domain via onboarding tools.
2. Approve and curate examples/rules during real usage.
3. Review gaps and insights regularly.
4. Keep connection artifacts versioned with git.

## Insights and trace-driven improvement

Enable traces to feed learning and diagnostics:

```bash
db-mcp traces on
db-mcp traces status
```

Then use:

- UI `/insights` for operational trends
- `db-mcp://insights/pending` resource for actionable items
- `dismiss_insight` / `mark_insights_processed` for workflow control

Visualization:

![Insights — semantic layer gaps and usage patterns](assets/ui-insights.jpg)

## Collaboration model

Team workflows are git-based, at connection scope.

Starter flow:

```bash
db-mcp git-init analytics <remote-url>
db-mcp sync analytics
```

Collaborative subgroup commands:

- `db-mcp collab init`
- `db-mcp collab attach <url>`
- `db-mcp collab detach`
- `db-mcp collab join`
- `db-mcp collab sync`
- `db-mcp collab merge`
- `db-mcp collab prune`
- `db-mcp collab status`
- `db-mcp collab members`
- `db-mcp collab daemon`

`db-mcp collab status` sample:

![Collaboration status output](assets/cli-collab-status.png)

## Connector profiles

Each connection can declare a connector profile (`sql_db`, `api_sql`, `api_openapi`, `api_probe`, `file_local`, `hybrid_bi`) that controls default capabilities and tool behavior. See [Connector Profiles](connector-profiles.md) for the full reference.

Validate your connector configuration:

```bash
db-mcp connector validate ~/.db-mcp/connections/mydb/connector.yaml
```

## Multi-connection operations

For stable behavior in mixed workloads:

- pass `connection` explicitly in tool calls
- keep `connector.yaml` present for every connection
- keep connector type/capabilities accurate
- avoid implicit defaults in long-running agent sessions

Preflight check before troubleshooting:

```bash
db-mcp doctor -c <connection>
```

## Tool mode strategy

- `detailed`: better for explicit tool orchestration and debugging.
- `shell`: better for vault-first workflows where the agent uses file context heavily.

Set in config and verify with:

```bash
db-mcp status
```

Operational guidance:

- Keep `shell` for day-to-day query sessions and faster grounding from vault files.
- Use `detailed` for onboarding, schema introspection, and structured tool debugging.

## Shell safety model

The `shell` tool is intentionally constrained:

- command allowlist (`cat`, `grep`, `find`, `ls`, `head`, `tail`, `wc`, `sort`, `uniq`, `diff`, `mkdir`, `touch`, `tee`, `echo`, `date`, `uuidgen`)
- no deletion/move/network commands
- no overwrite redirection (`>`)

This is by design to protect vault integrity and credentials.

## Protocol acknowledgment

db-mcp can require agents to read `PROTOCOL.md` before executing SQL queries. This adds a safety gate that ensures the agent has loaded the connection's context before running anything.

Configuration:

- Set `DB_MCP_REQUIRE_PROTOCOL_ACK=true` to enable
- `DB_MCP_PROTOCOL_ACK_TTL_SECONDS` controls how long an acknowledgment stays valid (default: 6 hours)
- The agent reads `PROTOCOL.md` via the `protocol` tool, which records a fresh acknowledgment
- If the acknowledgment expires or is missing, `run_sql` returns an error asking the agent to re-read the protocol

This is useful for long-running sessions where context might drift.

## Execution engine

SQL execution in db-mcp flows through an execution engine that handles both synchronous and asynchronous queries:

- **Synchronous**: the query runs and returns results immediately (standard SQL databases)
- **Asynchronous**: the query is submitted, returns an execution ID, and results are polled via `get_result` (common with SQL-like APIs such as Dune Analytics)

The execution engine automatically handles:

- Query store for tracking execution state
- Timeout and polling behavior for async providers
- Result caching for completed executions

## Migrations and compatibility

Use migration commands when upgrading legacy layouts:

```bash
db-mcp migrate
```

Migration handles:

- legacy namespace (`~/.dbmeta` -> `~/.db-mcp`)
- connection structure/version upgrades
- agent config modernization
