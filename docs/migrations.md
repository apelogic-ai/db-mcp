# Migrations System

**Status**: Implemented  
**Created**: 2025-01-26

## Overview

db-mcp includes a database-style migration system for evolving connection data formats over time. Migrations run exactly once per connection and are tracked globally to ensure idempotency.

## How It Works

### Migration Tracking

Migrations are tracked in `~/.db-mcp/migrations.yaml`:

```yaml
migrations:
  m_20260126_001_examples_to_folder:
    run_at: "2025-01-26T10:30:00Z"
    connections:
      - my-connection
      - another-connection
```

Each migration records:
- When it was run
- Which connections it was applied to

### When Migrations Run

Migrations run automatically at CLI startup:
- `db-mcp start` - runs migrations for the active connection
- `db-mcp ui` - runs migrations for the active connection

Migrations are idempotent - they check if already applied before running.

## Writing Migrations

### Migration Structure

Migrations live in `packages/core/src/db_mcp/migrations/` with filenames like:
- `m_YYYYMMDD_NNN_description.py`

Example: `m_20260126_001_examples_to_folder.py`

### Registration Decorator

```python
from db_mcp.migrations import register_migration

@register_migration(
    id="m_20260126_001_examples_to_folder",
    description="Convert query_examples.yaml to examples/ folder format"
)
def migrate_examples_to_folder(connection_name: str, connection_path: Path) -> None:
    """Migration logic here."""
    old_file = connection_path / "training" / "query_examples.yaml"
    
    if not old_file.exists():
        return  # Nothing to migrate
    
    # ... perform migration ...
```

### Migration Function Signature

```python
def migration_function(connection_name: str, connection_path: Path) -> None:
    """
    Args:
        connection_name: Name of the connection being migrated
        connection_path: Full path to the connection directory
    
    Raises:
        Exception: If migration fails (will be caught and logged)
    """
    pass
```

### Best Practices

1. **Check preconditions first** - Return early if nothing to migrate
2. **Preserve old data** - Rename files with `.migrated` suffix instead of deleting
3. **Log progress** - Use Python logging for visibility
4. **Be idempotent** - Migration should be safe to run multiple times (though framework prevents this)
5. **Handle partial state** - Consider what happens if migration was interrupted

## Existing Migrations

### m_20260126_001_examples_to_folder

Converts the old single-file example storage format to the new folder format.

**Before:**
```
training/
└── query_examples.yaml    # All examples in one file
```

**After:**
```
training/
├── examples/
│   ├── {uuid1}.yaml      # One file per example
│   └── {uuid2}.yaml
└── query_examples.yaml.migrated  # Backup of old file
```

### m_20260126_002_instructions_to_folder

Moves business rules from root-level file to dedicated instructions folder.

**Before:**
```
{connection}/
└── prompt_instructions.yaml    # Business rules at root
```

**After:**
```
{connection}/
├── instructions/
│   └── business_rules.yaml     # Business rules in folder
└── prompt_instructions.yaml.migrated  # Backup of old file
```

## API Reference

### Running Migrations

```python
from db_mcp.migrations import run_migrations, run_migrations_all

# Run for a specific connection
result = run_migrations("my-connection")
# Returns: {"applied": ["m_20260126_001_..."], "skipped": [], "failed": []}

# Run for all connections
results = run_migrations_all()
# Returns: {"my-connection": {...}, "other-connection": {...}}
```

### Checking Migration Status

```python
from db_mcp.migrations import get_migration_status

status = get_migration_status()
# Returns dict of all migrations and which connections they've been applied to
```

## File Locations

| Path | Purpose |
|------|---------|
| `~/.db-mcp/migrations.yaml` | Global migration tracking |
| `packages/core/src/db_mcp/migrations/` | Migration source files |
| `packages/core/src/db_mcp/migrations/__init__.py` | Migration infrastructure |
