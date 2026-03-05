# Tools Reference

db-mcp exposes MCP tools dynamically based on tool mode and connector capabilities.

## Tool exposure rules

- `TOOL_MODE=detailed`: exposes introspection, query-training, metrics, and helper tools.
- `TOOL_MODE=shell`: shell-first workflow with execution helpers.
- Connector capabilities control SQL/API tool availability (for example `supports_sql`, `supports_validate_sql`, `supports_async_jobs`).

## Availability matrix

| Tool group | Availability |
|---|---|
| `ping`, `get_config`, `list_connections`, `shell`, `protocol` | Always exposed |
| `mcp_setup_*`, `mcp_domain_*`, `import_examples`, `import_instructions` | Always exposed |
| `dismiss_insight`, `mark_insights_processed`, `mcp_*improvement*` | Always exposed |
| `run_sql` | Only when selected connection type supports SQL |
| `validate_sql` | Only when SQL + `supports_validate_sql=true` |
| `get_result` | Only when SQL + `supports_async_jobs=true` |
| `export_results` | Only when SQL is supported |
| `api_*` tools | Only when at least one API connection exists |
| `api_execute_sql` | Only for API connectors with SQL capability |
| `test_connection`, `list_*`, `describe_table`, `query_*`, `metrics_*`, `get_data`, `test_*` helpers | Detailed mode only |

## Connection routing

Most tools accept `connection` to target a specific connection:

```json
{"connection": "analytics"}
```

Best practice:

- Always pass `connection` in multi-connection sessions.
- Keep `connection` consistent across validate/execute flows.
- If `connection` is omitted and multiple candidates exist, the tool errors and asks for explicit selection.

## Core tools

- `ping`: server health check
- `get_config`: non-sensitive runtime config
- `list_connections`: available connections
- `shell`: controlled shell access in connection vault
- `protocol`: read `PROTOCOL.md`

## SQL and database tools

- `test_connection` (detailed mode)
- `detect_dialect` (detailed mode)
- `get_dialect_rules` (detailed mode) — returns SQL dialect rules for the connection's database type
- `get_connection_dialect` (detailed mode) — returns the detected dialect name for the active connection
- `list_catalogs` (detailed mode)
- `list_schemas` (detailed mode)
- `list_tables` (detailed mode)
- `describe_table` (detailed mode)
- `sample_table` (detailed mode)
- `validate_sql` (when `supports_validate_sql=true`)
- `run_sql` (when SQL execution is supported)
- `get_result` (when async jobs are supported)
- `export_results` (when SQL execution is supported)
- `get_data` (detailed mode)

Example (`validate_sql` + `run_sql` flow):

```json
{"connection":"analytics","sql":"SELECT * FROM public.users LIMIT 10"}
```

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

- `query_status` (detailed mode)
- `query_generate` (detailed mode)
- `query_approve` (detailed mode)
- `query_feedback` (detailed mode)
- `query_add_rule` (detailed mode)
- `query_list_examples` (detailed mode)
- `query_list_rules` (detailed mode)
- `import_examples`
- `import_instructions`

## Metrics and gaps tools

- `metrics_discover` (detailed mode)
- `metrics_list` (detailed mode)
- `metrics_approve` (detailed mode)
- `metrics_add` (detailed mode)
- `metrics_remove` (detailed mode)
- `get_knowledge_gaps` (detailed mode)
- `dismiss_knowledge_gap` (detailed mode)

## Insights and compatibility tools

- `dismiss_insight`
- `mark_insights_processed`
- `mcp_list_improvements`
- `mcp_suggest_improvement`
- `mcp_approve_improvement`

## Testing helper tools

- `test_elicitation` (detailed mode)
- `test_sampling` (detailed mode)

## Resources

In addition to tools, db-mcp provides MCP resources such as:

- `db-mcp://connections`
- `db-mcp://schema/{connection}`
- `db-mcp://ground-rules`
- `db-mcp://sql-rules`
- `db-mcp://insights/pending`

## Prompts

db-mcp also exposes prompts:

- `review-insights`: workflow prompt for reviewing and resolving pending insights.
