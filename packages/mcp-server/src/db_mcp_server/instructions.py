"""MCP server instruction templates (Phase 3.03).

Moved from db_mcp.server; the instruction constants and helper functions
for composing the FastMCP system prompt.
"""

from __future__ import annotations

# # Server Instructions by Mode
# =============================================================================

INSTRUCTIONS_DETAILED = """
Database metadata and query intelligence server.

## BEFORE ANY QUERY WORK

1. Read the knowledge vault protocol:
   ```
   shell(command="cat PROTOCOL.md")
   ```

2. Check SQL rules for this database:
   ```
   shell(command="cat instructions/sql_rules.md")
   ```

3. Check business metrics and dimensions:
   ```
   metrics_list()
   ```
   Use these canonical definitions when the user asks about KPIs, aggregations, or
   dimensions. Prefer metric SQL templates over generating from scratch.
   Use `metrics_discover()` to mine the vault for new candidates.

## CRITICAL: Database Hierarchy

Many databases use 3-level hierarchy: `catalog.schema.table`
- Use `list_catalogs()` FIRST if available
- Then `list_schemas(catalog="...")`
- Then `list_tables(catalog="...", schema="...")`

Do NOT skip to schema level - this causes "table not found" errors.

## After Successful Queries

Save examples and tell the user what you saved. See PROTOCOL.md for details.

## Tools Available

- Schema discovery: list_catalogs, list_schemas, list_tables, describe_table
- Query: get_data, run_sql, validate_sql, get_result, export_results
- Knowledge vault: shell (bash access to examples, learnings, instructions)
- Business rules: query_add_rule, query_list_rules
- Knowledge gaps: get_knowledge_gaps, dismiss_knowledge_gap
- Metrics: metrics_list, metrics_discover, metrics_approve, metrics_add, metrics_remove
- Metric bindings: metrics_bindings_list, metrics_bindings_validate, metrics_bindings_set
- Training: query_approve, query_feedback, query_list_examples
- Setup: vault_* and import_*

## Knowledge Gaps

Call `get_knowledge_gaps()` to see terms that previous sessions couldn't map to
schema columns. If you resolve any during your work, use `query_add_rule` to add
the mapping — the gap will auto-resolve.
"""

INSTRUCTIONS_DAEMON = """
Executor-like db-mcp daemon runtime.

Use this two-step workflow:

1. Call `prepare_task(question=..., connection=...)`
   This returns a lean structured context packet for the first attempt:
   - explicit disambiguation
   - decision hints (preferred tables, anti-patterns, unit/date rules, required filters)
   - relevant domain, business-rule, and SQL-rule context
   - relevant examples and rules
   - relevant tables, columns, and candidate joins

2. Write the SQL yourself and call:
   `execute_task(task_id=..., sql=..., confirmed=false)`

Use the `execution` payload returned by `execute_task(...)` directly.

If the first SQL attempt fails or uses the wrong table/filter, call
`prepare_task(question=..., connection=..., context=...)` again with refinement
context such as previous SQL, validation errors, tables to avoid, or filters
that must be applied. Refinement calls may return expanded raw context and fuller
schema detail when the backend detects ambiguity or a prior failed attempt.

Do not look for shell, exec, or code tools in this mode.
"""

INSTRUCTIONS_SHELL_MODE = """
Database query server - SHELL-FIRST MODE

## YOU HAVE ONE PRIMARY TOOL: shell

Use `shell` for ALL query preparation. It gives you access to a knowledge vault
containing everything you need: examples, schema, rules, learnings.

## IMMEDIATE FIRST STEP

```
shell(command="cat PROTOCOL.md")
```

This tells you exactly how to:
- Find existing query examples
- Understand the database schema
- Follow SQL rules for this database
- Save successful queries for reuse

## QUERY WORKFLOW

1. shell(command="cat PROTOCOL.md")           # Read the rules
2. shell(command="grep -ri 'keyword' examples/")  # Find similar queries
3. shell(command="cat schema/tables.yaml")    # Understand tables
4. Write SQL based on what you found
5. validate_sql(sql="...")                    # Validate before running
6. run_sql(query_id="...")                    # Execute
7. Save successful queries back to examples/

## OTHER TOOLS

- validate_sql / run_sql / get_result - Query execution (required for running SQL)
- export_results - Export data to CSV/JSON
- get_knowledge_gaps - View unmapped business terms from previous sessions
- dismiss_knowledge_gap - Dismiss a gap as false positive
- query_add_rule / query_list_rules - Manage business rules (synonyms, filters)
- metrics_list / metrics_discover / metrics_approve / metrics_add / metrics_remove
- metrics_bindings_list / metrics_bindings_validate / metrics_bindings_set
- query_approve / query_feedback - Save examples and feedback
- vault_* / import_* - Admin setup (not for regular queries)

## SQL-LIKE APIs (Dune, etc.)

For API connectors with `supports_sql: true`:
- Use `api_execute_sql(sql="SELECT ...")` to run SQL queries
- Do NOT use api_query for SQL execution - that's for REST endpoints only
- The SQL is sent to the API, polled for completion, and results returned automatically

## IMPORTANT: Business Rules and Knowledge Gaps

Before generating SQL, always check business rules:
```
shell(command="cat instructions/business_rules.yaml")
```

Call `get_knowledge_gaps()` to see terms previous sessions couldn't resolve.
If you can clarify any, use `query_add_rule` to add the mapping.

DO NOT look for other schema discovery tools. Use `shell` to explore the vault.
"""

INSTRUCTIONS_EXEC_ONLY = """
Database query server - EXEC-ONLY MODE

## YOU HAVE EXACTLY ONE TOOL: exec

Use `exec(connection="...", command="...")` for all work. The command runs inside
a sandboxed container whose working directory is the selected connection vault.

## IMMEDIATE FIRST STEP

```
exec(connection="...", command="cat PROTOCOL.md")
```

The mounted workspace contains the same structure as normal db-mcp connections:
- PROTOCOL.md
- schema/
- domain/
- instructions/
- examples/
- learnings/
- metrics/
- connector.yaml

Python and SQLAlchemy are installed in the container. Use local files, Python,
and shell commands to inspect the vault and query the selected data source.
For semantic metric queries, you can also run:
`db-mcp runtime intent --connection <name> --intent "show revenue" --json`
"""

INSTRUCTIONS_CODE = """
Database query server - CODE MODE

## YOU HAVE EXACTLY ONE TOOL: code

Use `code(connection="...", code="...")` for all work. The code runs as Python
inside the selected connection workspace.

## IMMEDIATE FIRST STEP

```
code(connection="...", code="print(dbmcp.read_protocol())")
```

## BUILT-IN PYTHON HELPER

Your code gets a helper object named `dbmcp`.

Use these helpers first:
- `dbmcp.read_protocol()`
- `dbmcp.connector()`
- `dbmcp.schema_descriptions()`
- `dbmcp.domain_model()`
- `dbmcp.sql_rules()`
- `dbmcp.answer_intent(intent, options=None)`
- `dbmcp.query(sql)`
- `dbmcp.scalar(sql)`
- `dbmcp.execute(sql)`

If a statement may write, re-run the tool with `confirmed=True`.
Do not rely on shell semantics in this mode.
"""


# =============================================================================
# Server Creation
# =============================================================================


def _strip_validate_sql_from_instructions(instructions: str) -> str:
    """Remove validate_sql references for connectors that don't support it."""
    replacements = {
        (
            '5. validate_sql(sql="...")                    '
            "# Validate before running\n"
            '6. run_sql(query_id="...")                    '
            "# Execute"
        ): ('5. run_sql(sql="...")                         # Execute directly'),
        ("- validate_sql / run_sql / get_result - Query execution (required for running SQL)"): (
            "- run_sql / get_result - Query execution (run_sql accepts sql= directly)"
        ),
        "- Query: get_data, run_sql, validate_sql, get_result, export_results": (
            "- Query: get_data, run_sql, get_result, export_results"
        ),
    }
    for old, new in replacements.items():
        instructions = instructions.replace(old, new)
    return instructions


def _build_connection_instructions(all_connections: dict) -> str:
    """Build instructions section listing all available connections."""
    if not all_connections:
        return ""

    lines = ["\n## Available Connections\n"]
    for name, info in all_connections.items():
        parts = [f"- **{name}**"]
        details = []
        if info.type:
            details.append(info.type)
        if info.dialect:
            details.append(info.dialect)
        if details:
            parts.append(f"({', '.join(details)})")
        if info.is_default:
            parts.append("← default")
        if info.description:
            parts.append(f"— {info.description}")
        lines.append(" ".join(parts))

    lines.append(
        '\n**Usage:** Add `connection="name"` to any tool call to target a specific connection.'
    )
    lines.append(
        "If omitted and only one connection of the required type exists, it is used automatically."
    )
    return "\n".join(lines)

