# Tools Reference

db-mcp exposes MCP tools dynamically based on tool mode and connector capabilities.

## Tool exposure rules

- `TOOL_MODE=detailed`: full tool surface.
- `TOOL_MODE=shell`: shell-first workflow plus execution helpers.
- Connector capabilities control SQL/API tool availability (for example `supports_sql`, `supports_validate_sql`).

## Connection routing

Most tools accept `connection` to target a specific connection:

```json
{"connection": "analytics"}
```

Best practice:

- Always pass `connection` in multi-connection sessions.
- Keep `connection` consistent across validate/execute flows.

## Core tools

- `ping`: server health check
- `get_config`: non-sensitive runtime config
- `list_connections`: available connections
- `shell`: controlled shell access in connection vault
- `protocol`: read `PROTOCOL.md`

## SQL and database tools

- `test_connection`
- `detect_dialect`
- `list_catalogs`
- `list_schemas`
- `list_tables`
- `describe_table`
- `sample_table`
- `validate_sql`
- `run_sql`
- `get_result`
- `export_results`
- `get_data`

## API connector tools

- `api_discover`
- `api_query`
- `api_mutate`
- `api_describe_endpoint`
- `api_execute_sql` (only when API connector supports SQL)

## Onboarding and domain tools

- `mcp_setup_status`
- `mcp_setup_start`
- `mcp_setup_discover`
- `mcp_setup_discover_status`
- `mcp_setup_next`
- `mcp_setup_approve`
- `mcp_setup_bulk_approve`
- `mcp_setup_skip`
- `mcp_setup_reset`
- `mcp_setup_add_ignore_pattern`
- `mcp_setup_remove_ignore_pattern`
- `mcp_setup_import_ignore_patterns`
- `mcp_setup_import_descriptions`
- `mcp_domain_status`
- `mcp_domain_generate`
- `mcp_domain_approve`
- `mcp_domain_skip`

## Training and rules tools

- `query_status`
- `query_generate`
- `query_approve`
- `query_feedback`
- `query_add_rule`
- `query_list_examples`
- `query_list_rules`
- `import_examples`
- `import_instructions`

## Metrics and gaps tools

- `metrics_discover`
- `metrics_list`
- `metrics_approve`
- `metrics_add`
- `metrics_remove`
- `get_knowledge_gaps`
- `dismiss_knowledge_gap`

## Insights and compatibility tools

- `dismiss_insight`
- `mark_insights_processed`
- `mcp_list_improvements`
- `mcp_suggest_improvement`
- `mcp_approve_improvement`

## Testing helper tools

- `test_elicitation`
- `test_sampling`

## Resources

In addition to tools, db-mcp provides MCP resources such as:

- `db-mcp://connections`
- `db-mcp://schema/{connection}`
- `db-mcp://ground-rules`
- `db-mcp://sql-rules`
- `db-mcp://insights/pending`
