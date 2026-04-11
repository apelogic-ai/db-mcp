---
name: query
description: Query any db-mcp database connection — auto-resolves connections, validates SQL, retries with budget. Use for any data question.
autoContext: true
paths: "**"
---

# Data Query Skill

Answer data questions using db-mcp. Works with any configured connection
(SQL databases, APIs, file connectors).

## Step 1 — Identify the right connection

**DO NOT guess or cycle through connections.** Determine the correct
connection FIRST using this decision tree:

1. If the user specified a connection name → use it
2. If the question mentions a known domain → use the mapping below
3. If unsure → run `list_connections` and pick based on the question context
4. If still unsure → ASK the user which connection to use

### Connection discovery

Run this ONCE at the start of the session (skip if you've already done it):

```
list_connections()
```

Then for each connection that looks relevant, check what's in it:

```
shell(command="ls ~/.db-mcp/connections/<name>/schema/")
```

### Common patterns

- **If the user asks about a specific table name** → grep for it across connections:
  `shell(command="grep -rl '<table_name>' ~/.db-mcp/connections/*/schema/")`
- **If the user mentions "playground" or "sample"** → use `playground`
- **If the user mentions an API service (Solana, Dune, Jira)** → use the matching API connection
- **If the user says "use X"** → use connection X

## Step 2 — Read the knowledge vault

Before writing ANY SQL, check what's already known:

```
shell(command="cat ~/.db-mcp/connections/<connection>/PROTOCOL.md")
shell(command="grep -ri '<keyword>' ~/.db-mcp/connections/<connection>/examples/")
shell(command="cat ~/.db-mcp/connections/<connection>/instructions/business_rules.yaml")
```

If there's a matching example → use it directly. Don't reinvent SQL that's already been validated.

## Step 3 — Understand the schema

For SQL databases:
```
list_tables(connection="<name>")
describe_table(connection="<name>", table="<table>")
```

For 3-level hierarchy databases (Trino, Snowflake, etc.):
```
list_catalogs(connection="<name>")
list_schemas(connection="<name>", catalog="<catalog>")
list_tables(connection="<name>", catalog="<catalog>", schema="<schema>")
```

**NEVER skip the catalog level for Trino connections.** Going straight to
`list_tables` without specifying catalog causes "table not found" errors.

For API connections:
```
api_describe_endpoint(connection="<name>")
```

## Step 4 — Write, validate, execute

```
validate_sql(connection="<name>", sql="<your SQL>")
run_sql(connection="<name>", query_id="<from validate>")
```

If validate_sql is not supported (SQLite, API connectors):
```
run_sql(connection="<name>", sql="<your SQL>")
```

For API endpoints:
```
api_query(connection="<name>", endpoint="<endpoint>", params={...})
```

## Step 5 — Present results

- Format numbers with commas (1,234,567 not 1234567)
- Show row counts: "Returned 42 rows"
- For large results: summarize key findings first, then offer full data
- If the user asked a yes/no question → answer yes/no first, then show evidence

## Retry budget

**Maximum 3 attempts per approach.** If the same query or tool call fails
3 times:

1. Stop
2. Summarize what you tried and what failed
3. Ask the user for guidance

Do NOT make 10+ blind attempts. Do NOT cycle through connections hoping
one works.

## After success

Save the query as an example for future use:
```
query_approve(connection="<name>", sql="<the SQL>", intent="<what the user asked>")
```

This helps future sessions skip straight to the answer.
