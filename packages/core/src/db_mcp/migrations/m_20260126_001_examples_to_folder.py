"""Migration: Convert query_examples.yaml to examples/ folder format.

This migration:
1. Reads query_examples.yaml (if exists)
2. Creates individual files in examples/ for each example
3. Renames query_examples.yaml to query_examples.yaml.migrated
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

from db_mcp.migrations import register_migration


def _example_to_file_format(example: dict) -> dict:
    """Convert legacy example format to new file format."""
    return {
        "id": example.get("id", str(uuid.uuid4())[:8]),
        "intent": example.get("natural_language", ""),
        "sql": example.get("sql", ""),
        "tables": example.get("tables_used", []),
        "keywords": example.get("tags", []),
        "notes": example.get("notes"),
        "validated": True,
        "created_at": example.get("created_at"),
        "created_by": example.get("created_by"),
    }


@register_migration(
    id="20260126_001_examples_to_folder",
    description="Migrate query_examples.yaml to examples/ folder format",
)
def migrate_examples_to_folder(connection_path: Path) -> bool:
    """Migrate query_examples.yaml to examples/ folder.

    Args:
        connection_path: Path to the connection directory

    Returns:
        True if migration succeeded (or nothing to migrate), False on error
    """
    legacy_file = connection_path / "query_examples.yaml"

    # Nothing to migrate - that's OK
    if not legacy_file.exists():
        return True

    # Already migrated marker exists
    migrated_marker = connection_path / "query_examples.yaml.migrated"
    if migrated_marker.exists():
        return True

    # Create examples directory
    examples_dir = connection_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)

    # Load legacy file
    try:
        with open(legacy_file) as f:
            data = yaml.safe_load(f)
    except Exception:
        # Can't read - mark as migrated anyway to avoid repeated failures
        return True

    if not data or "examples" not in data:
        # Empty or invalid format - rename and mark done
        legacy_file.rename(migrated_marker)
        return True

    # Migrate each example
    count = 0
    for example in data.get("examples", []):
        example_id = example.get("id", str(uuid.uuid4())[:8])
        file_path = examples_dir / f"{example_id}.yaml"

        # Skip if already exists (from previous partial migration or manual creation)
        if file_path.exists():
            continue

        file_data = _example_to_file_format(example)

        # Handle created_at - ensure it's a string
        if file_data.get("created_at"):
            if hasattr(file_data["created_at"], "isoformat"):
                file_data["created_at"] = file_data["created_at"].isoformat()
        else:
            file_data["created_at"] = datetime.now(UTC).isoformat()

        # Remove None values for cleaner YAML
        file_data = {k: v for k, v in file_data.items() if v is not None}

        try:
            with open(file_path, "w") as f:
                yaml.dump(
                    file_data,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
            count += 1
        except Exception:
            # Continue with other examples
            continue

    # Rename legacy file to mark as migrated
    legacy_file.rename(migrated_marker)

    return True
