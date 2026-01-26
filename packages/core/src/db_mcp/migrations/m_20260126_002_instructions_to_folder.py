"""Migration: Move prompt_instructions.yaml to instructions/business_rules.yaml.

This migration:
1. Creates instructions/ directory
2. Moves prompt_instructions.yaml to instructions/business_rules.yaml
3. Leaves a .migrated marker at the old location
"""

from pathlib import Path

import yaml

from db_mcp.migrations import register_migration


@register_migration(
    id="20260126_002_instructions_to_folder",
    description="Move prompt_instructions.yaml to instructions/business_rules.yaml",
)
def migrate_instructions_to_folder(connection_path: Path) -> bool:
    """Migrate prompt_instructions.yaml to instructions/ folder.

    Args:
        connection_path: Path to the connection directory

    Returns:
        True if migration succeeded (or nothing to migrate), False on error
    """
    legacy_file = connection_path / "prompt_instructions.yaml"
    new_dir = connection_path / "instructions"
    new_file = new_dir / "business_rules.yaml"
    migrated_marker = connection_path / "prompt_instructions.yaml.migrated"

    # Already migrated marker exists
    if migrated_marker.exists():
        return True

    # New file already exists (manual migration or fresh install)
    if new_file.exists():
        # If legacy also exists, just mark it as migrated
        if legacy_file.exists():
            legacy_file.rename(migrated_marker)
        return True

    # Nothing to migrate - that's OK
    if not legacy_file.exists():
        return True

    # Create instructions directory
    new_dir.mkdir(parents=True, exist_ok=True)

    # Load legacy file
    try:
        with open(legacy_file) as f:
            data = yaml.safe_load(f)
    except Exception:
        # Can't read - mark as migrated anyway to avoid repeated failures
        legacy_file.rename(migrated_marker)
        return True

    if not data:
        # Empty file - just rename and mark done
        legacy_file.rename(migrated_marker)
        return True

    # Write to new location
    try:
        with open(new_file, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
    except Exception:
        # Failed to write - don't mark as migrated
        return False

    # Rename legacy file to mark as migrated
    legacy_file.rename(migrated_marker)

    return True
