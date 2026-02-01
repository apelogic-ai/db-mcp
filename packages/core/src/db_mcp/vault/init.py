"""Vault initialization and directory structure management."""

import logging

from db_mcp.onboarding.state import get_connection_path

logger = logging.getLogger(__name__)

# Default PROTOCOL.md content
PROTOCOL_MD = """# Knowledge Vault Protocol

This connection directory stores query examples, learnings, business rules,
and instructions for SQL generation. Use `shell` for bash access and the
dedicated MCP tools for structured operations.

## Directory Structure

```
connection/
├── PROTOCOL.md              # This file (system-managed, overwritten on updates)
├── connector.yaml           # Connector config (sql/api/file) — absent = SQL
├── state.yaml               # Onboarding state
├── knowledge_gaps.yaml      # Tracked vocabulary gaps (auto-detected + manually added)
├── schema/
│   └── descriptions.yaml    # Cached schema with table/column descriptions
├── domain/
│   └── model.md             # Domain model (entities, relationships, terminology)
├── instructions/
│   ├── sql_rules.md         # SQL dialect rules and gotchas
│   └── business_rules.yaml  # Business rules for SQL generation (synonyms, filters, etc.)
├── examples/
│   └── {uuid}.yaml          # Saved query examples
├── learnings/
│   ├── patterns.md          # Successful query patterns
│   ├── schema_gotchas.md    # Schema quirks and pitfalls
│   ├── trace-analysis-patterns.md  # Patterns from trace analysis
│   └── failures/            # Failed query logs
│       └── {uuid}.yaml
├── metrics/
│   ├── catalog.yaml         # Business metric definitions (KPIs, aggregations)
│   └── dimensions.yaml      # Dimension definitions (axes for slicing metrics)
└── data/                    # (API/file connectors only) Synced data files
    └── {endpoint}.jsonl
```

## CRITICAL: Use Cached Schema First

**NEVER introspect the database directly if cached schema exists.**

On first run, db-mcp discovers and caches the full database schema. This cache contains:
- `schema/descriptions.yaml` - Complete table/column descriptions with semantic annotations
- `domain/model.md` - Domain model explaining relationships and business logic

**Before ANY database introspection:**
1. Check if `schema/descriptions.yaml` exists
2. If it exists, use it as your primary schema reference
3. Only call `list_catalogs()`, `list_schemas()`, `list_tables()` if cache is missing

```bash
# Check for cached schema
cat schema/descriptions.yaml 2>/dev/null | head -50
```

If the file exists and has content, USE IT instead of calling discovery tools.

## CRITICAL: Read Domain Model

**ALWAYS read the domain model before writing queries.**

The domain model (`domain/model.md`) contains:
- Business entity relationships
- Key concepts and terminology
- Important joins and aggregations
- Common query patterns

```bash
cat domain/model.md
```

This is NOT optional - it contains critical context for correct SQL generation.

## CRITICAL: Check Business Rules

**ALWAYS read business rules before generating SQL.**

Business rules (`instructions/business_rules.yaml`) contain:
- Term synonyms (e.g., "CUI" = "chargeable_user_identity")
- Required filters and conditions
- Column usage rules and gotchas
- Domain-specific SQL patterns

```bash
cat instructions/business_rules.yaml 2>/dev/null
```

These rules are accumulated from analyst feedback and trace analysis.
Ignoring them leads to incorrect queries.

## Metrics & Dimensions

The `metrics/` directory stores business metric and dimension definitions:

- **`metrics/catalog.yaml`** — Named metrics (KPIs, aggregations) with SQL expressions
  - Example: DAU, monthly revenue, churn rate
  - Each metric has: name, description, SQL expression, related tables, tags

- **`metrics/dimensions.yaml`** — Dimension definitions (axes for slicing metrics)
  - Example: country, device_type, subscription_plan
  - Each dimension has: name, column, type (categorical/temporal/geographic), related tables

**Use `metrics_list()` to check existing metrics before generating SQL.**
When a user asks about a business KPI, check the metrics catalog first — it may
already have an approved SQL definition.

To discover new metrics and dimensions from the schema, use `metrics_discover()`.
This mines the knowledge vault (schema, examples, business rules) for candidates
and groups them by semantic category (Location, Time, Device, etc.).

Approve candidates with `metrics_approve()` or manually define with `metrics_add()`.
Remove obsolete entries with `metrics_remove()`.

## Database Hierarchy

**ALWAYS start discovery at the CATALOG level, not schema level.**

Many databases use 3-level hierarchy: `catalog.schema.table`
- WRONG: `list_tables(schema="radius")` - misses the catalog
- RIGHT: `list_catalogs()` first, then drill down

Before ANY query work:
1. Check cached schema first (`schema/descriptions.yaml`)
2. Check `instructions/sql_rules.md` for hierarchy rules
3. Check business rules (`instructions/business_rules.yaml`)
4. Check domain model (`domain/model.md`)
5. Only if cache missing: use `list_catalogs()` to discover

Failing to do this will cause "table not found" errors.

## Connection Types

This connection may be one of three types (check `connector.yaml`):

### SQL Connections (default)
Standard database connections (PostgreSQL, ClickHouse, Trino, MySQL, SQL Server).
Use `run_sql` / `get_data` for queries. The database hierarchy section above applies.

### API Connections (`type: api`)
REST API connections. Data is queried directly from API endpoints.

**Workflow for API connections:**
1. Use `api_describe_endpoint(endpoint)` to see available query parameters
2. Use `api_query(endpoint, params)` to fetch data with filters

Key tools:
- `api_describe_endpoint` — Shows endpoint metadata and available query params
  (name, type, description, required, enum values)
- `api_query` — Hit an endpoint directly with query params, returns
  `{columns, data, rows_returned}`. Default: single page. Use `max_pages` for more.
- `api_discover` — Auto-discover endpoints from OpenAPI spec or probing

**Do NOT use `run_sql` for API connections** — use `api_query` instead.

### File Connections (`type: file`)
Local file connections (CSV, Parquet, JSON, JSONL) queried via DuckDB.
Use `run_sql` for queries — DuckDB reads files directly.

## IMPORTANT: User Transparency

**ALWAYS inform the user when you save or discover knowledge.**

After saving anything to the vault, add a footnote to your response:

> **Knowledge saved**: Saved this query as example `{uuid}` for future reference.

When you find and use existing knowledge, mention it:

> **Using prior knowledge**: Found similar query in `examples/{file}`.

This helps users understand what the system is learning and builds trust.

## On Session Start

1. Read this protocol:
```bash
cat PROTOCOL.md
```

2. Check for cached schema (USE THIS FIRST):
```bash
cat schema/descriptions.yaml 2>/dev/null | head -100
```

3. Read domain model (REQUIRED):
```bash
cat domain/model.md
```

4. Check database structure rules:
```bash
cat instructions/sql_rules.md
```

5. Check business rules (REQUIRED):
```bash
cat instructions/business_rules.yaml
```

6. Check knowledge gaps (recommended):
```
get_knowledge_gaps()
```
This shows unmapped business terms that previous sessions couldn't resolve.
If you can clarify any gaps during your work, use `query_add_rule` to add
the mapping and the gap will auto-resolve.

## Before Generating SQL

### 1. Use cached schema (PRIMARY SOURCE)
```bash
# Search for relevant tables/columns in cache
grep -i "keyword" schema/descriptions.yaml
```

### 2. Check business rules for the term
```bash
grep -i "keyword" instructions/business_rules.yaml
```

### 3. Search for existing examples
```bash
grep -ri "keyword1\\|keyword2" examples/
```

### 4. If match found, read it
```bash
cat examples/{matched_file}.yaml
```

### 5. Check for relevant learnings
```bash
grep -i "table_name" learnings/patterns.md
cat learnings/schema_gotchas.md
```

### 6. Reference domain model for context
The domain model should already be loaded from session start.
If not, read it now:
```bash
cat domain/model.md
```

## After Successful Query

Save as example for future use. First generate a UUID:
```bash
uuidgen
```

Then use that UUID in the filename (replace YOUR_UUID with the output):
```bash
cat >> examples/YOUR_UUID.yaml << 'EOF'
intent: "description of what user asked"
keywords:
  - keyword1
  - keyword2
sql: |
  SELECT ...
tables:
  - table1
validated: true
EOF
```

**Then tell the user**: "Saved this query as example `{uuid}` for future reference."

## After Failed Query

Record the failure for learning. First generate a UUID:
```bash
uuidgen
```

Then save the failure:
```bash
cat >> learnings/failures/YOUR_UUID.yaml << 'EOF'
intent: "what user asked"
sql: |
  SELECT ...
error: |
  error message
resolution: "what should be done instead"
EOF
```

**Then tell the user**: "Recorded this issue in `failures/{uuid}` to avoid repeating it."

## When Discovering a Pattern

Append to patterns file:
```bash
cat >> learnings/patterns.md << 'EOF'

## Pattern Name
- **Issue**: what goes wrong
- **Fix**: what to do instead
- **Example**: `code snippet`
EOF
```

**Then tell the user**: "Added pattern '{name}' to learnings for future queries."

## When Discovering a Schema Gotcha

Append to schema gotchas file:
```bash
cat >> learnings/schema_gotchas.md << 'EOF'

## Gotcha Name
- Description of the quirk
- How to work around it
EOF
```

## Adding Business Rules

When you discover term mappings, synonyms, or query constraints, add them:
```
query_add_rule(rule="CUI and chargeable_user_identity are synonyms.")
```

Or via the rules listing/management tools:
```
query_list_rules()
```

Business rules persist across sessions and are used by all future queries.

## Correcting a Mistake

Create new entry that supersedes the old. First generate a UUID:
```bash
uuidgen
```

Then create the corrected entry:
```bash
cat >> examples/YOUR_UUID.yaml << 'EOF'
supersedes: {old_uuid}
reason: "why the old one was wrong"
intent: "..."
sql: |
  SELECT ...
EOF
```

**Then tell the user**: "Corrected example `{old_uuid}` with new version `{new_uuid}`."

## MCP Tools Reference

Beyond `shell`, these tools are available for structured operations:

| Tool | Purpose |
|------|---------|
| `get_knowledge_gaps` | View open/resolved knowledge gaps |
| `dismiss_knowledge_gap` | Dismiss a gap as false positive |
| `query_add_rule` | Add a business rule |
| `query_list_rules` | List all business rules |
| `query_list_examples` | List saved query examples |
| `query_approve` | Save a validated query as example |
| `query_feedback` | Record feedback on a query |
| `validate_sql` | Validate SQL before execution |
| `run_sql` / `get_data` | Execute queries |
| `get_result` | Poll for async query results |
| `export_results` | Export data to CSV/JSON |
| `metrics_discover` | Mine knowledge vault for metric/dimension candidates |
| `metrics_list` | List approved metrics and dimensions |
| `metrics_approve` | Approve a discovered candidate into the catalog |
| `metrics_add` | Manually define a metric or dimension |
| `metrics_remove` | Remove a metric or dimension from the catalog |
| `api_query` | Query an API endpoint with params (API connectors) |
| `api_describe_endpoint` | Show endpoint metadata and available query params |
| `api_discover` | Auto-discover API endpoints from spec or probing |

## Useful Commands

```bash
# List all examples
find examples -name "*.yaml" | wc -l

# Recent examples (last 7 days)
find examples -name "*.yaml" -mtime -7

# Search across everything
grep -ri "search term" .

# Recent failures
ls -lt learnings/failures/*.yaml | head -10

# Check knowledge gaps file directly
cat knowledge_gaps.yaml 2>/dev/null
```
"""

# Directory structure to create inside connection
CONNECTION_DIRS = [
    "schema",
    "domain",
    "instructions",
    "examples",
    "learnings",
    "learnings/failures",
    "metrics",
]

# Files to always overwrite (system-controlled, shipped with each deploy)
CONNECTION_SYSTEM_FILES = {
    "PROTOCOL.md": PROTOCOL_MD,
}

# Initial files to create only if missing (user-editable templates)
CONNECTION_TEMPLATE_FILES = {
    "instructions/sql_rules.md": """# SQL Generation Rules

## Database Hierarchy

Check the database dialect to understand the naming hierarchy:

- **Trino/Presto**: 3-level → `catalog.schema.table` (e.g., `iceberg.radius.wifi_qm_v2`)
- **PostgreSQL**: 2-level → `schema.table` (e.g., `public.users`)
- **MySQL**: 2-level → `database.table`
- **ClickHouse**: 2-level → `database.table`

**ALWAYS verify the hierarchy before writing queries.**

Use `list_catalogs()` first if available. If it returns catalogs, you MUST include
the catalog in all table references.

## Common Mistakes

1. Using 2-level path when 3-level is required
   - WRONG: `SELECT * FROM radius.wifi_qm_v2`
   - RIGHT: `SELECT * FROM iceberg.radius.wifi_qm_v2`

2. Assuming schema names without checking
   - Always use `list_schemas(catalog="...")` to discover actual schema names

Add domain-specific SQL rules below this line.
---

""",
    "domain/model.md": "# Domain Model\n\nGenerated domain model will be saved here.\n",
    "learnings/patterns.md": "# Query Patterns\n\nDocument successful patterns here.\n",
    "learnings/schema_gotchas.md": "# Schema Gotchas\n\nDocument schema quirks here.\n",
}


def ensure_connection_structure() -> bool:
    """Ensure connection directory structure exists.

    Creates the connection directory and subdirectories if they don't exist.
    Also creates initial template files if missing.

    Returns:
        True if connection was created/updated, False if it already existed unchanged
    """
    connection_path = get_connection_path()
    created = False

    # Create connection root
    if not connection_path.exists():
        connection_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created connection directory: {connection_path}")
        created = True

    # Create subdirectories
    for subdir in CONNECTION_DIRS:
        dir_path = connection_path / subdir
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created connection subdirectory: {subdir}")
            created = True

    # Always overwrite system-controlled files (e.g., PROTOCOL.md)
    for file_path, content in CONNECTION_SYSTEM_FILES.items():
        full_path = connection_path / file_path
        full_path.write_text(content)
        logger.info(f"Updated system file: {file_path}")
        created = True

    # Create template files only if missing (user-editable)
    for file_path, content in CONNECTION_TEMPLATE_FILES.items():
        full_path = connection_path / file_path
        if not full_path.exists():
            full_path.write_text(content)
            logger.info(f"Created template file: {file_path}")
            created = True

    if created:
        logger.info("Connection structure initialized")
    else:
        logger.debug("Connection structure already exists")

    return created


# Backward compatibility alias
def ensure_vault_structure() -> bool:
    """Deprecated: Use ensure_connection_structure instead."""
    return ensure_connection_structure()
