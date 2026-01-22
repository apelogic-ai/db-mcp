"""Migration from legacy storage formats to connection-based structure.

Storage format versions:
- v1: ~/.db-mcp/vault/ + ~/.db-mcp/providers/{id}/ (separate directories)
- v2: ~/.db-mcp/connections/{name}/ (self-contained connection directory)

Namespace migration:
- ~/.dbmeta -> ~/.db-mcp (old namespace to new)

Handles migration of:
- schema_descriptions.yaml -> schema/descriptions.yaml
- domain_model.md -> domain/model.md
- onboarding_state.yaml -> state.yaml
- query_examples.yaml -> examples/*.yaml (split into individual files)
- feedback_log.yaml -> learnings/failures/*.yaml (split, filter failures only)
- instructions/domain.md -> domain/model.md (if domain_model.md missing)
"""

import logging
import shutil
from pathlib import Path

import yaml

from db_mcp.config import STORAGE_VERSION, get_settings

logger = logging.getLogger(__name__)

VERSION_FILE = ".version"
NAMESPACE_MIGRATED_FILE = ".migrated_from_dbmeta"
LEGACY_NAMESPACE_DIR = ".dbmeta"
NEW_NAMESPACE_DIR = ".db-mcp"


def get_storage_version(path: Path) -> int:
    """Get the storage format version from a directory.

    Args:
        path: Directory to check for version file

    Returns:
        Version number (0 if no version file, format unknown)
    """
    version_file = path / VERSION_FILE
    if version_file.exists():
        try:
            content = version_file.read_text().strip()
            return int(content)
        except (ValueError, OSError):
            return 0
    return 0


def write_storage_version(path: Path, version: int = STORAGE_VERSION) -> None:
    """Write the storage format version to a directory.

    Args:
        path: Directory to write version file to
        version: Version number to write
    """
    version_file = path / VERSION_FILE
    version_file.write_text(str(version))
    logger.debug(f"Wrote version {version} to {version_file}")


def detect_legacy_namespace() -> Path | None:
    """Detect if legacy ~/.dbmeta directory exists.

    Returns:
        Path to legacy directory if found, None otherwise
    """
    legacy_path = Path.home() / LEGACY_NAMESPACE_DIR
    if legacy_path.exists() and legacy_path.is_dir():
        return legacy_path
    return None


def is_namespace_migrated() -> bool:
    """Check if namespace migration has already been completed.

    Returns:
        True if migration marker file exists in new namespace
    """
    new_path = Path.home() / NEW_NAMESPACE_DIR
    marker_file = new_path / NAMESPACE_MIGRATED_FILE
    return marker_file.exists()


def migrate_namespace() -> dict:
    """Migrate from legacy ~/.dbmeta to ~/.db-mcp namespace.

    This copies all data from the old namespace to the new one, preserving
    the directory structure. The old directory is left intact as a backup.

    Returns:
        dict with migration statistics
    """
    legacy_path = detect_legacy_namespace()
    new_path = Path.home() / NEW_NAMESPACE_DIR

    # Check if already migrated
    if is_namespace_migrated():
        logger.debug("Namespace migration already completed")
        return {"skipped": True, "reason": "already_migrated"}

    # Check if legacy directory exists
    if not legacy_path:
        logger.debug("No legacy ~/.dbmeta directory found")
        return {"skipped": True, "reason": "no_legacy_namespace"}

    # Check if new directory already has substantial content
    # (user may have set up fresh without migration)
    new_connections = new_path / "connections"
    if new_connections.exists():
        existing_connections = [d for d in new_connections.iterdir() if d.is_dir()]
        if existing_connections:
            # Check if any connection has a version file (properly initialized)
            for conn in existing_connections:
                if (conn / VERSION_FILE).exists():
                    logger.info(
                        f"New namespace already has initialized connections, "
                        f"skipping namespace migration. "
                        f"Legacy data remains at {legacy_path}"
                    )
                    # Mark as migrated to avoid future checks
                    new_path.mkdir(parents=True, exist_ok=True)
                    (new_path / NAMESPACE_MIGRATED_FILE).write_text(
                        f"Skipped: new namespace already initialized\n"
                        f"Legacy data at: {legacy_path}\n"
                    )
                    return {"skipped": True, "reason": "new_namespace_exists"}

    logger.info(f"Migrating namespace: {legacy_path} -> {new_path}")

    stats = {
        "legacy_path": str(legacy_path),
        "new_path": str(new_path),
        "connections": 0,
        "config": False,
        "providers": 0,
        "vault": False,
    }

    # Ensure new directory exists
    new_path.mkdir(parents=True, exist_ok=True)

    # Migrate config.yaml
    legacy_config = legacy_path / "config.yaml"
    new_config = new_path / "config.yaml"
    if legacy_config.exists() and not new_config.exists():
        # Read and update config to fix any hardcoded paths
        try:
            import yaml

            config_data = yaml.safe_load(legacy_config.read_text())

            # Update any paths that reference the old namespace
            if config_data:
                for key in ["vault_path", "providers_dir", "connections_dir"]:
                    if key in config_data and config_data[key]:
                        old_value = config_data[key]
                        if LEGACY_NAMESPACE_DIR in old_value:
                            config_data[key] = old_value.replace(
                                LEGACY_NAMESPACE_DIR, NEW_NAMESPACE_DIR
                            )
                            logger.debug(f"Updated {key}: {old_value} -> {config_data[key]}")

                new_config.write_text(yaml.dump(config_data, default_flow_style=False))
                stats["config"] = True
                logger.info("Migrated config.yaml (with path updates)")
        except Exception as e:
            logger.warning(f"Failed to migrate config.yaml: {e}, copying as-is")
            shutil.copy2(legacy_config, new_config)
            stats["config"] = True

    # Migrate connections directory
    legacy_connections = legacy_path / "connections"
    if legacy_connections.exists():
        new_connections = new_path / "connections"
        for conn_dir in legacy_connections.iterdir():
            if conn_dir.is_dir():
                dest_conn = new_connections / conn_dir.name
                if not dest_conn.exists():
                    shutil.copytree(conn_dir, dest_conn, dirs_exist_ok=True)
                    stats["connections"] += 1
                    logger.info(f"Migrated connection: {conn_dir.name}")
                else:
                    logger.debug(f"Connection {conn_dir.name} already exists, skipping")

    # Migrate providers directory (legacy v1 structure)
    legacy_providers = legacy_path / "providers"
    if legacy_providers.exists():
        new_providers = new_path / "providers"
        for provider_dir in legacy_providers.iterdir():
            if provider_dir.is_dir():
                dest_provider = new_providers / provider_dir.name
                if not dest_provider.exists():
                    shutil.copytree(provider_dir, dest_provider, dirs_exist_ok=True)
                    stats["providers"] += 1
                    logger.info(f"Migrated provider: {provider_dir.name}")

    # Migrate vault directory (legacy v1 structure)
    legacy_vault = legacy_path / "vault"
    if legacy_vault.exists():
        new_vault = new_path / "vault"
        if not new_vault.exists():
            shutil.copytree(legacy_vault, new_vault, dirs_exist_ok=True)
            stats["vault"] = True
            logger.info("Migrated vault directory")

    # Write migration marker
    marker_file = new_path / NAMESPACE_MIGRATED_FILE
    marker_file.write_text(
        f"Migrated from: {legacy_path}\n"
        f"Migrated on: {__import__('datetime').datetime.now().isoformat()}\n"
        f"Stats: {stats}\n"
        f"\nThe original ~/.dbmeta directory has been preserved as a backup.\n"
        f"You can safely delete it after verifying the migration.\n"
    )

    logger.info(
        f"Namespace migration complete: "
        f"{stats['connections']} connections, "
        f"{stats['providers']} providers, "
        f"vault={'yes' if stats['vault'] else 'no'}"
    )
    logger.info(
        f"Original data preserved at {legacy_path} - delete manually after verifying migration"
    )

    return stats


def detect_legacy_structure() -> dict | None:
    """Detect if legacy v1 structure exists.

    Looks for the old structure:
    - ~/.dbmcp/vault/
    - ~/.dbmcp/providers/{provider_id}/

    Returns:
        dict with legacy paths if found, None otherwise
    """
    settings = get_settings()
    db_mcp_root = Path.home() / ".db-mcp"

    # Check for legacy vault path (from config or default)
    legacy_vault = None
    if settings.vault_path:
        legacy_vault = Path(settings.vault_path)
    else:
        legacy_vault = db_mcp_root / "vault"

    # Check for legacy providers path
    legacy_providers = None
    if settings.providers_dir:
        legacy_providers = Path(settings.providers_dir)
    else:
        legacy_providers = db_mcp_root / "providers"

    provider_id = settings.get_effective_provider_id()
    legacy_provider_dir = legacy_providers / provider_id if legacy_providers else None

    # Check what exists
    vault_exists = legacy_vault and legacy_vault.exists()
    provider_exists = legacy_provider_dir and legacy_provider_dir.exists()

    if not vault_exists and not provider_exists:
        return None

    # Check if it's actually legacy (no version file in connections dir)
    connections_dir = db_mcp_root / "connections"
    if connections_dir.exists():
        # If connections dir has version file, already migrated
        for conn_dir in connections_dir.iterdir():
            if conn_dir.is_dir() and (conn_dir / VERSION_FILE).exists():
                return None

    return {
        "vault_path": legacy_vault if vault_exists else None,
        "provider_path": legacy_provider_dir if provider_exists else None,
        "provider_id": provider_id,
    }


def _migrate_schema_descriptions(src_path: Path, connection_path: Path) -> bool:
    """Migrate schema_descriptions.yaml to schema/descriptions.yaml.

    Args:
        src_path: Legacy provider or vault directory
        connection_path: New connection directory

    Returns:
        True if migrated
    """
    legacy_file = src_path / "schema_descriptions.yaml"
    if not legacy_file.exists():
        return False

    dest_dir = connection_path / "schema"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "descriptions.yaml"

    if dest_file.exists():
        logger.debug("schema/descriptions.yaml already exists, skipping")
        return False

    shutil.copy2(legacy_file, dest_file)
    logger.info(f"Migrated schema_descriptions.yaml to {dest_file}")
    return True


def _migrate_domain_model(src_path: Path, connection_path: Path) -> bool:
    """Migrate domain_model.md to domain/model.md.

    Args:
        src_path: Legacy provider directory
        connection_path: New connection directory

    Returns:
        True if migrated
    """
    legacy_file = src_path / "domain_model.md"
    if not legacy_file.exists():
        # Also check instructions/domain.md (from vault)
        legacy_file = src_path / "instructions" / "domain.md"
        if not legacy_file.exists():
            return False

    dest_dir = connection_path / "domain"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "model.md"

    if dest_file.exists():
        content = dest_file.read_text()
        # Only skip if it has real content
        if content.strip() and "Generated domain model will be saved here" not in content:
            logger.debug("domain/model.md already has content, skipping")
            return False

    shutil.copy2(legacy_file, dest_file)
    logger.info(f"Migrated domain model to {dest_file}")
    return True


def _migrate_onboarding_state(src_path: Path, connection_path: Path) -> bool:
    """Migrate onboarding_state.yaml to state.yaml.

    Args:
        src_path: Legacy provider directory
        connection_path: New connection directory

    Returns:
        True if migrated
    """
    legacy_file = src_path / "onboarding_state.yaml"
    if not legacy_file.exists():
        return False

    dest_file = connection_path / "state.yaml"

    if dest_file.exists():
        logger.debug("state.yaml already exists, skipping")
        return False

    shutil.copy2(legacy_file, dest_file)
    logger.info(f"Migrated onboarding_state.yaml to {dest_file}")
    return True


def _migrate_query_examples(src_path: Path, connection_path: Path) -> int:
    """Migrate query_examples.yaml to examples/*.yaml.

    Args:
        src_path: Legacy provider directory
        connection_path: New connection directory

    Returns:
        Number of examples migrated
    """
    legacy_file = src_path / "query_examples.yaml"
    if not legacy_file.exists():
        return 0

    examples_dir = connection_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = yaml.safe_load(legacy_file.read_text())
    except Exception as e:
        logger.error(f"Failed to parse {legacy_file}: {e}")
        return 0

    examples = data.get("examples", [])
    count = 0

    for example in examples:
        example_id = example.get("id", f"migrated_{count}")

        new_example = {
            "id": example_id,
            "created": example.get("created_at", ""),
            "intent": example.get("natural_language", ""),
            "keywords": example.get("tags", []),
            "sql": example.get("sql", ""),
            "tables": example.get("tables_used", []),
            "validated": True,
            "notes": example.get("notes", ""),
            "migrated_from": "query_examples.yaml",
        }

        out_file = examples_dir / f"{example_id}.yaml"
        if not out_file.exists():
            out_file.write_text(yaml.dump(new_example, default_flow_style=False, sort_keys=False))
            count += 1

    if count > 0:
        logger.info(f"Migrated {count} query examples to examples/")
    return count


def _migrate_feedback_log(src_path: Path, connection_path: Path) -> int:
    """Migrate feedback_log.yaml to learnings/failures/*.yaml.

    Args:
        src_path: Legacy provider directory
        connection_path: New connection directory

    Returns:
        Number of failures migrated
    """
    legacy_file = src_path / "feedback_log.yaml"
    if not legacy_file.exists():
        return 0

    failures_dir = connection_path / "learnings" / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = yaml.safe_load(legacy_file.read_text())
    except Exception as e:
        logger.error(f"Failed to parse {legacy_file}: {e}")
        return 0

    feedback_list = data.get("feedback", [])
    count = 0

    for feedback in feedback_list:
        if feedback.get("feedback_type") == "approved":
            continue

        feedback_id = feedback.get("id", f"migrated_{count}")

        new_failure = {
            "id": feedback_id,
            "created": feedback.get("created_at", ""),
            "intent": feedback.get("natural_language", ""),
            "sql": feedback.get("generated_sql", ""),
            "error": feedback.get("feedback_text", ""),
            "resolution": feedback.get("corrected_sql", ""),
            "tables": feedback.get("tables_involved", []),
            "migrated_from": "feedback_log.yaml",
        }

        out_file = failures_dir / f"{feedback_id}.yaml"
        if not out_file.exists():
            out_file.write_text(yaml.dump(new_failure, default_flow_style=False, sort_keys=False))
            count += 1

    if count > 0:
        logger.info(f"Migrated {count} failures to learnings/failures/")
    return count


def _migrate_vault_files(vault_path: Path, connection_path: Path) -> dict:
    """Migrate vault structure files (instructions, examples, learnings).

    Args:
        vault_path: Legacy vault directory
        connection_path: New connection directory

    Returns:
        dict with migration counts
    """
    stats = {"instructions": 0, "examples": 0, "learnings": 0}

    # Copy instructions (except domain.md which goes to domain/)
    src_instructions = vault_path / "instructions"
    if src_instructions.exists():
        dest_instructions = connection_path / "instructions"
        dest_instructions.mkdir(parents=True, exist_ok=True)

        for file in src_instructions.iterdir():
            if file.is_file() and file.name != "domain.md":
                dest_file = dest_instructions / file.name
                if not dest_file.exists():
                    shutil.copy2(file, dest_file)
                    stats["instructions"] += 1

    # Copy examples
    src_examples = vault_path / "examples"
    if src_examples.exists():
        dest_examples = connection_path / "examples"
        dest_examples.mkdir(parents=True, exist_ok=True)

        for file in src_examples.iterdir():
            if file.is_file():
                dest_file = dest_examples / file.name
                if not dest_file.exists():
                    shutil.copy2(file, dest_file)
                    stats["examples"] += 1

    # Copy learnings
    src_learnings = vault_path / "learnings"
    if src_learnings.exists():
        dest_learnings = connection_path / "learnings"
        shutil.copytree(src_learnings, dest_learnings, dirs_exist_ok=True)
        stats["learnings"] = sum(1 for _ in src_learnings.rglob("*") if _.is_file())

    return stats


def migrate_to_connection_structure(connection_name: str | None = None) -> dict:
    """Migrate from legacy v1 structure to v2 connection structure.

    Args:
        connection_name: Name for the new connection (defaults to provider_id)

    Returns:
        dict with migration statistics
    """
    settings = get_settings()

    if not settings.auto_migrate:
        logger.debug("Legacy migration disabled via config")
        return {"skipped": True, "reason": "disabled"}

    legacy = detect_legacy_structure()
    if not legacy:
        logger.debug("No legacy structure detected")
        return {"skipped": True, "reason": "no_legacy_data"}

    # Determine connection name and path
    if not connection_name:
        connection_name = legacy["provider_id"] or "default"

    connection_path = settings.get_effective_connection_path()

    # Check if already at v2
    if get_storage_version(connection_path) >= 2:
        logger.debug(f"Connection {connection_name} already at v2")
        return {"skipped": True, "reason": "already_migrated"}

    logger.info(f"Migrating to connection structure: {connection_path}")

    # Ensure connection directory exists
    connection_path.mkdir(parents=True, exist_ok=True)

    stats = {
        "connection_name": connection_name,
        "connection_path": str(connection_path),
        "schema_descriptions": False,
        "domain_model": False,
        "onboarding_state": False,
        "query_examples": 0,
        "failures": 0,
        "vault_files": {},
    }

    # Migrate from provider directory
    if legacy["provider_path"]:
        provider_path = legacy["provider_path"]
        stats["schema_descriptions"] = _migrate_schema_descriptions(provider_path, connection_path)
        stats["domain_model"] = _migrate_domain_model(provider_path, connection_path)
        stats["onboarding_state"] = _migrate_onboarding_state(provider_path, connection_path)
        stats["query_examples"] = _migrate_query_examples(provider_path, connection_path)
        stats["failures"] = _migrate_feedback_log(provider_path, connection_path)

    # Migrate from vault directory
    if legacy["vault_path"]:
        vault_path = legacy["vault_path"]
        # Domain model might be in vault/instructions/
        if not stats["domain_model"]:
            stats["domain_model"] = _migrate_domain_model(vault_path, connection_path)
        stats["vault_files"] = _migrate_vault_files(vault_path, connection_path)

    # Write version file
    write_storage_version(connection_path, STORAGE_VERSION)

    logger.info(f"Migration complete: {stats}")
    return stats


# Backward compatibility alias
def migrate_legacy_provider_data() -> dict:
    """Deprecated: Use migrate_to_connection_structure instead."""
    return migrate_to_connection_structure()
