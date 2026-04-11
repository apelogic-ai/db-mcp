---
name: onboard
description: Set up a new db-mcp database connection — walks through configuration, schema discovery, and initial knowledge vault setup.
---

# Connection Onboarding

Set up a new db-mcp database connection interactively.

## Step 1 — Determine connection type

Ask the user:

> What kind of data source are you connecting?
> 1. **SQL database** (PostgreSQL, MySQL, ClickHouse, Trino, SQLite)
> 2. **API** (REST, JSON-RPC — e.g. Dune, Solana RPC, Jira)
> 3. **File** (CSV, Parquet, JSONL on local disk)

## Step 2 — Create the connection

For SQL databases:
```
db-mcp init <connection-name>
```
This will prompt for the DATABASE_URL. Help the user construct it:
- PostgreSQL: `postgresql://user:password@host:5432/database`
- MySQL: `mysql://user:password@host:3306/database`
- ClickHouse: `clickhouse://user:password@host:8443/database`
- Trino: `trino://user@host:8443/catalog/schema`
- SQLite: `sqlite:////absolute/path/to/file.db`

For API connections:
```
db-mcp init <connection-name> --type api
```
Then help configure `connector.yaml` with base_url, auth, and endpoints.

For file connections:
```
db-mcp init <connection-name> --type file
```
Point to the directory containing data files.

## Step 3 — Test the connection

```
db-mcp query validate -c <connection-name> "SELECT 1"
```

If it fails, help debug:
- Wrong credentials → check .env file
- Network issue → check host:port accessibility
- SSL → check if `?sslmode=require` is needed

## Step 4 — Discover the schema

```
db-mcp schema tables -c <connection-name>
```

For large databases, show the first 20 tables and ask which ones matter:

> I found 150 tables. Here are the first 20:
> ...
> Which tables are most important for your work? I'll focus on documenting those.

Then for each important table:
```
db-mcp schema describe -c <connection-name> <table>
```

## Step 5 — Set up initial knowledge

Help the user add their first business rule:
```
db-mcp rules add -c <connection-name> "rule text here"
```

Suggest rules based on what the schema reveals:
- Columns named `is_test`, `is_deleted`, `is_active` → filter rules
- Date columns → time boundary conventions
- Columns named `status` with enum values → valid values rule

## Step 6 — Run a sample query

Ask the user for their most common question about this data, then:
1. Write the SQL
2. Validate it
3. Run it
4. Save it as the first example

```
db-mcp query run -c <connection-name> "<sql>"
```

## Step 7 — Summary

Print what was set up:
- Connection name and type
- Tables discovered
- Rules added
- Example queries saved
- Next steps: "Run `/query` to ask questions about your data"
