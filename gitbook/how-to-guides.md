# How-To Guides

These are the most common db-mcp user journeys, with copy/paste commands and expected outcomes.

## 1. Get your first useful answer (Playground)

Use the built-in Chinook sample DB to validate your setup before touching production data.

```bash
db-mcp playground install
db-mcp playground status
db-mcp use playground
db-mcp agents --all
```

Then ask your agent:

> "Show top 10 customers by total invoice amount."

Verify activity:

```bash
db-mcp traces status
```

![Playground status output](assets/cli-playground-status.png)
![Detected MCP agents](assets/cli-agents-list.png)

Related docs: [Quickstart](quickstart.md), [Working with Agents](working-with-agents.md)

## 2. Connect your own database safely

Create a real connection, then validate before asking production questions.

```bash
db-mcp init analytics
db-mcp use analytics
db-mcp status
db-mcp doctor -c analytics
db-mcp discover -c analytics
```

Expected:

- `status` shows the active connection and credentials
- `doctor` passes resolve/auth/execute checks
- `discover` returns schemas/tables/columns

![Doctor help output](assets/cli-doctor-help.png)
![Doctor command pass output](assets/cli-doctor-dune-pass.png)

Related docs: [Install and Configuration](install-and-configuration.md), [Using the CLI](using-cli.md)

## 3. Configure agent clients for your team

Discover installed clients, then configure in one pass.

```bash
db-mcp agents --list
db-mcp agents --all
```

If you need selective setup:

```bash
db-mcp agents -A claude-desktop -A codex
```

After config, restart each client and verify via `db-mcp status`.

![Agents interactive setup](assets/cli-agents-interactive.png)
![Agents list output](assets/cli-agents-list.png)

Related docs: [Working with Agents](working-with-agents.md)

## 4. Debug connection issues quickly

Use deterministic preflight checks first, before deeper troubleshooting.

```bash
db-mcp doctor -c <connection>
db-mcp doctor -c <connection> --json
```

Use failures to localize the issue:

- `resolve_connection` or `load_connector`: config/layout issue
- `auth`: credential/secrets issue
- `execute_test` or `poll_test`: connector/runtime issue

![Doctor command pass output](assets/cli-doctor-dune-pass.png)

Related docs: [Using the CLI](using-cli.md), [Tools Reference](tools-reference.md)

## 5. Improve answer quality over time (knowledge loop)

Run with traces enabled, then capture missing business context in vault files.

```bash
db-mcp traces on
db-mcp ui
```

Workflow:

1. Ask real questions from your agent.
2. Review `/insights` for unmapped terms and query patterns.
3. Add business rules/examples in `/context`.
4. Re-run key prompts and confirm improved SQL quality.

![Insights — semantic layer gaps and usage patterns](assets/ui-insights.jpg)
![Context viewer — browse schema, domain, examples, and rules](assets/ui-context.jpg)

Related docs: [Using the Web UI](using-web-ui.md), [Advanced Topics](advanced-topics.md)

## 6. Collaborate on a shared knowledge vault

For shared ownership of context/rules/examples, use collaboration commands per connection.

```bash
db-mcp collab init
db-mcp collab status
db-mcp collab members
```

Collaborator flow:

```bash
db-mcp collab attach <repo-url>
db-mcp collab join
db-mcp collab status
```

Master review flow:

```bash
db-mcp collab merge
db-mcp collab prune
```

![Collab status output](assets/cli-collab-status.png)

Related docs: [Using the CLI](using-cli.md), [Advanced Topics](advanced-topics.md)
