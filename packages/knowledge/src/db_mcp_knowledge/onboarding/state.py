"""Onboarding state persistence."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml
from db_mcp_models import OnboardingPhase, OnboardingState

from db_mcp_knowledge.vault.paths import (
    connector_path,
    descriptions_path,
    domain_model_path,
)
from db_mcp_knowledge.vault.paths import (
    state_path as _state_path,
)

logger = logging.getLogger(__name__)


def get_provider_dir(provider_id: str) -> Path:
    """Get the directory for connection artifacts.

    Args:
        provider_id: Connection/provider identifier (required).

    Returns:
        Path to connection directory
    """
    return Path.home() / ".db-mcp" / "connections" / provider_id


def get_state_file_path(
    connection_path: Path,
    provider_id: str | None = None,
) -> Path:
    """Get path to the onboarding state file.

    Args:
        connection_path: Connection directory path (required).
        provider_id: Ignored in v2 (kept for backward compatibility).

    Returns:
        Path to state YAML file
    """
    return _state_path(connection_path)


def create_initial_state(provider_id: str) -> OnboardingState:
    """Create initial onboarding state for a provider.

    Args:
        provider_id: Provider identifier

    Returns:
        New OnboardingState instance
    """
    return OnboardingState(
        provider_id=provider_id,
        phase=OnboardingPhase.NOT_STARTED,
        started_at=datetime.now(UTC),
    )


def save_state(state: OnboardingState, connection_path: Path) -> dict:
    """Save onboarding state to YAML file.

    Args:
        state: OnboardingState to save
        connection_path: Connection directory path (required).

    Returns:
        Dict with save status
    """
    try:
        connection_path.mkdir(parents=True, exist_ok=True)

        # Update timestamp
        state.last_updated_at = datetime.now(UTC)

        # Convert to dict for YAML serialization
        state_dict = state.model_dump(mode="json")

        # Write to file
        state_file = get_state_file_path(connection_path)
        with open(state_file, "w") as f:
            yaml.dump(state_dict, f, default_flow_style=False, sort_keys=False)

        return {
            "saved": True,
            "connection": str(connection_path),
            "file_path": str(state_file),
            "error": None,
        }
    except Exception as e:
        return {
            "saved": False,
            "connection": None,
            "file_path": None,
            "error": str(e),
        }


def load_state(
    provider_id: str | None = None,
    *,
    connection_path: Path,
) -> OnboardingState | None:
    """Load onboarding state from YAML file.

    If state file doesn't exist but schema/domain files do (e.g., after
    cloning from git), automatically recovers state from existing files.

    Args:
        provider_id: Ignored in v2 (kept for backward compatibility).
        connection_path: Connection directory path (required, keyword-only).

    Returns:
        OnboardingState if found or recovered, None otherwise
    """
    state_file = get_state_file_path(connection_path)

    if not state_file.exists():
        # Try to recover state from existing files (e.g., after git clone)
        recovered = _recover_state_from_files(connection_path)
        if recovered:
            # Save the recovered state
            save_state(recovered, connection_path)
            logger.info("Recovered onboarding state from existing files")
        return recovered

    try:
        with open(state_file) as f:
            state_dict = yaml.safe_load(f)

        return OnboardingState.model_validate(state_dict)
    except Exception:
        return None


def _recover_state_from_files(
    connection_path: Path,
) -> OnboardingState | None:
    """Attempt to recover onboarding state from existing files.

    This handles the case where a connection was cloned from git
    (state.yaml is gitignored) but schema/domain files exist.

    Args:
        connection_path: Connection directory path (required).

    Returns:
        Recovered OnboardingState or None if no files found
    """
    # Check what files exist
    schema_file = descriptions_path(connection_path)
    domain_file = domain_model_path(connection_path)

    has_schema = schema_file.exists()
    has_domain = domain_file.exists()

    # If neither exists, nothing to recover
    if not has_schema and not has_domain:
        return None

    logger.info(f"Recovering state: schema={has_schema}, domain={has_domain}")

    # Extract table names from schema if it exists
    tables_discovered: list[str] = []
    tables_total = 0
    if has_schema:
        try:
            with open(schema_file) as f:
                schema_data = yaml.safe_load(f)
            if schema_data and "tables" in schema_data:
                tables = schema_data["tables"]
                # Handle both list format (v2) and dict format (legacy)
                if isinstance(tables, list):
                    tables_discovered = [t.get("full_name") or t.get("name", "") for t in tables]
                elif isinstance(tables, dict):
                    tables_discovered = list(tables.keys())
                tables_total = len(tables_discovered)
        except Exception:
            pass

    # Determine phase based on what exists
    if has_schema and has_domain:
        phase = OnboardingPhase.COMPLETE
    elif has_schema:
        phase = OnboardingPhase.DOMAIN
    else:
        phase = OnboardingPhase.SCHEMA

    # Derive provider_id from directory name
    provider_id = connection_path.name

    # Create recovered state
    return OnboardingState(
        provider_id=provider_id,
        phase=phase,
        database_url_configured=True,
        connection_verified=True,
        tables_discovered=tables_discovered,
        tables_total=tables_total,
        domain_model_generated=has_domain,
        domain_model_approved=has_domain,
        started_at=datetime.now(UTC),
        last_updated_at=datetime.now(UTC),
    )


def delete_state(
    connection_path: Path,
    provider_id: str | None = None,
    preserve_connection: bool = True,
) -> dict:
    """Delete onboarding state file, with smart preservation for discovery.

    If preserve_connection=True and the connection directory has files that allow
    state recovery (schema files, connector.yaml), the state file is deleted normally
    and recovery will work.

    If preserve_connection=True and the directory would become empty or undiscoverable,
    preserves connection facts in a reset state to prevent the connection from vanishing.

    If preserve_connection=False, always deletes the state file (legacy behavior).

    Args:
        connection_path: Connection directory path (required).
        provider_id: Ignored in v2 (kept for backward compatibility).
        preserve_connection: If True, preserve connection facts when no recovery possible

    Returns:
        Dict with delete status
    """
    state_file = get_state_file_path(connection_path)
    conn_path = connection_path

    if not state_file.exists():
        return {
            "deleted": False,
            "connection": str(conn_path),
            "error": "State file not found",
        }

    try:
        if not preserve_connection:
            # Legacy behavior: always delete the state file
            state_file.unlink()
            return {
                "deleted": True,
                "connection": str(conn_path),
                "error": None,
            }

        # New behavior: check if there are other files that would allow recovery or discovery
        connector_file = connector_path(conn_path)
        schema_file = descriptions_path(conn_path)
        domain_file = domain_model_path(conn_path)
        env_file = conn_path / ".env"

        has_recoverable_files = (
            connector_file.exists() or
            schema_file.exists() or
            domain_file.exists() or
            env_file.exists()
        )

        if has_recoverable_files:
            # Normal case: delete state file, let recovery mechanism work
            state_file.unlink()
            return {
                "deleted": True,
                "connection": str(conn_path),
                "error": None,
            }
        else:
            # Special case: no other files exist, preserve connection facts
            # Load existing state to preserve connection facts
            existing = load_state(connection_path=conn_path)

            # Create reset state preserving connection identity
            from db_mcp_models import OnboardingPhase, OnboardingState
            reset_state = OnboardingState(
                provider_id=existing.provider_id if existing else (
                    provider_id or conn_path.name
                ),
                phase=OnboardingPhase.INIT,
                database_url_configured=existing.database_url_configured if existing else False,
                connection_verified=existing.connection_verified if existing else False,
                dialect_detected=existing.dialect_detected if existing else None,
                catalogs_discovered=existing.catalogs_discovered if existing else [],
                schemas_discovered=existing.schemas_discovered if existing else [],
                tables_discovered=existing.tables_discovered if existing else [],
                started_at=datetime.now(UTC),
            )

            # Write the reset state back (preserves file existence for discover())
            save_state(reset_state, conn_path)

            return {
                "deleted": True,
                "connection": str(conn_path),
                "error": None,
            }
    except Exception as e:
        return {
            "deleted": False,
            "connection": str(conn_path),
            "error": str(e),
        }
