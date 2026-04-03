"""Thin MCP tool wrappers for vault artifact tools.

Calls db_mcp.services.vault directly; does not import from db_mcp.tools.vault.
"""

from __future__ import annotations

from db_mcp.services.connection import resolve_connection
from db_mcp.services.vault import (
    save_artifact,
    vault_append,
    vault_write,
)


async def _save_artifact(
    connection: str,
    artifact_type: str,
    content: str,
    name: str | None = None,
) -> dict:
    """Save a typed artifact into the resolved connection vault."""
    _, _, connection_path = resolve_connection(connection)
    return save_artifact(
        connection_path=connection_path,
        artifact_type=artifact_type,
        content=content,
        name=name,
    )


async def _vault_write(
    connection: str,
    path: str,
    content: str,
) -> dict:
    """Atomic full-file write to a whitelisted vault path.

    The path determines the Pydantic model used for validation. YAML content
    is validated against the model before being written. SQL fields are parsed
    with sqlglot.

    Allowed paths include ``schema/descriptions.yaml``,
    ``metrics/catalog.yaml``, ``instructions/business_rules.yaml``, etc.
    """
    _, _, connection_path = resolve_connection(connection)
    return vault_write(
        connection_path=connection_path,
        path=path,
        content=content,
    )


async def _vault_append(
    connection: str,
    path: str,
    content: str,
) -> dict:
    """Create a new record file or append to a markdown file in the vault.

    For ``examples/*.yaml`` paths, creates a new file (fails if it already
    exists). For ``learnings/*.md`` paths, appends content to the existing
    file or creates it.
    """
    _, _, connection_path = resolve_connection(connection)
    return vault_append(
        connection_path=connection_path,
        path=path,
        content=content,
    )
