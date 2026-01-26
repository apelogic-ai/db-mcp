"""Database-style migrations for db-mcp.

Migrations run exactly once per connection. Applied migrations are tracked in
~/.db-mcp/migrations.yaml with the format:

    applied:
      nova:
        - id: "20260126_001_examples_to_folder"
          applied_at: "2026-01-26T10:30:00Z"
      boost:
        - id: "20260126_001_examples_to_folder"
          applied_at: "2026-01-26T10:31:00Z"

Usage:
    from db_mcp.migrations import run_migrations

    # Run all pending migrations for a connection
    run_migrations("nova")

    # Run all pending migrations for all connections
    run_migrations_all()
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import yaml

logger = logging.getLogger(__name__)

# Type for migration functions
MigrationFn = Callable[[Path], bool]


class Migration:
    """A single migration definition."""

    def __init__(
        self,
        id: str,
        description: str,
        up: MigrationFn,
        down: MigrationFn | None = None,
    ):
        self.id = id
        self.description = description
        self.up = up
        self.down = down


# Registry of all migrations (in order)
_MIGRATIONS: list[Migration] = []


def register_migration(
    id: str,
    description: str,
    down: MigrationFn | None = None,
) -> Callable[[MigrationFn], MigrationFn]:
    """Decorator to register a migration function.

    Usage:
        @register_migration("20260126_001_examples_to_folder", "Migrate examples to folder")
        def migrate_examples_to_folder(connection_path: Path) -> bool:
            # ... migration logic
            return True
    """

    def decorator(up_fn: MigrationFn) -> MigrationFn:
        migration = Migration(id=id, description=description, up=up_fn, down=down)
        _MIGRATIONS.append(migration)
        return up_fn

    return decorator


def get_migrations_file() -> Path:
    """Get path to migrations tracking file."""
    return Path.home() / ".db-mcp" / "migrations.yaml"


def get_connections_dir() -> Path:
    """Get path to connections directory."""
    return Path.home() / ".db-mcp" / "connections"


def load_applied_migrations() -> dict[str, list[dict]]:
    """Load the record of applied migrations.

    Returns:
        Dict mapping connection names to lists of applied migrations.
    """
    migrations_file = get_migrations_file()

    if not migrations_file.exists():
        return {}

    try:
        with open(migrations_file) as f:
            data = yaml.safe_load(f) or {}
        return data.get("applied", {})
    except Exception as e:
        logger.warning(f"Failed to load migrations file: {e}")
        return {}


def save_applied_migrations(applied: dict[str, list[dict]]) -> None:
    """Save the record of applied migrations."""
    migrations_file = get_migrations_file()
    migrations_file.parent.mkdir(parents=True, exist_ok=True)

    data = {"applied": applied}

    with open(migrations_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def mark_migration_applied(connection_name: str, migration_id: str) -> None:
    """Mark a migration as applied for a connection."""
    applied = load_applied_migrations()

    if connection_name not in applied:
        applied[connection_name] = []

    # Check if already applied
    for m in applied[connection_name]:
        if m.get("id") == migration_id:
            return  # Already marked

    applied[connection_name].append(
        {
            "id": migration_id,
            "applied_at": datetime.now(UTC).isoformat(),
        }
    )

    save_applied_migrations(applied)


def is_migration_applied(connection_name: str, migration_id: str) -> bool:
    """Check if a migration has been applied for a connection."""
    applied = load_applied_migrations()

    if connection_name not in applied:
        return False

    for m in applied[connection_name]:
        if m.get("id") == migration_id:
            return True

    return False


def get_pending_migrations(connection_name: str) -> list[Migration]:
    """Get list of migrations that haven't been applied to a connection."""
    pending = []

    for migration in _MIGRATIONS:
        if not is_migration_applied(connection_name, migration.id):
            pending.append(migration)

    return pending


def run_migrations(connection_name: str) -> dict:
    """Run all pending migrations for a connection.

    Args:
        connection_name: Name of the connection to migrate

    Returns:
        Dict with migration results
    """
    connections_dir = get_connections_dir()
    connection_path = connections_dir / connection_name

    if not connection_path.exists():
        return {
            "connection": connection_name,
            "applied": [],
            "failed": [],
            "skipped": [],
            "error": f"Connection '{connection_name}' not found",
        }

    pending = get_pending_migrations(connection_name)

    if not pending:
        logger.debug(f"No pending migrations for {connection_name}")
        return {
            "connection": connection_name,
            "applied": [],
            "failed": [],
            "skipped": [],
        }

    applied = []
    failed = []

    for migration in pending:
        logger.info(
            f"Running migration {migration.id} for {connection_name}: {migration.description}"
        )

        try:
            success = migration.up(connection_path)

            if success:
                mark_migration_applied(connection_name, migration.id)
                applied.append(migration.id)
                logger.info(f"Migration {migration.id} completed for {connection_name}")
            else:
                failed.append(migration.id)
                logger.warning(f"Migration {migration.id} returned False for {connection_name}")
                # Stop on failure - don't run subsequent migrations
                break

        except Exception as e:
            failed.append(migration.id)
            logger.error(f"Migration {migration.id} failed for {connection_name}: {e}")
            # Stop on failure
            break

    return {
        "connection": connection_name,
        "applied": applied,
        "failed": failed,
        "skipped": [m.id for m in pending if m.id not in applied and m.id not in failed],
    }


def run_migrations_all() -> list[dict]:
    """Run pending migrations for all connections.

    Returns:
        List of results for each connection
    """
    connections_dir = get_connections_dir()
    results = []

    if not connections_dir.exists():
        return results

    for connection_path in sorted(connections_dir.iterdir()):
        if not connection_path.is_dir():
            continue

        connection_name = connection_path.name
        result = run_migrations(connection_name)
        results.append(result)

        # Log summary
        if result["applied"]:
            logger.info(
                f"Connection {connection_name}: applied {len(result['applied'])} migrations"
            )

    return results


def get_all_migrations() -> list[dict]:
    """Get info about all registered migrations."""
    return [
        {"id": m.id, "description": m.description, "has_rollback": m.down is not None}
        for m in _MIGRATIONS
    ]


# Import migration modules to register them
# Each module uses @register_migration decorator
from db_mcp.migrations import (  # noqa: E402
    m_20260126_001_examples_to_folder,  # noqa: F401
    m_20260126_002_instructions_to_folder,  # noqa: F401
)
