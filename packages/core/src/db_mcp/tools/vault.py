"""MCP tool wrappers for vault artifact operations."""

import db_mcp.services.vault as vault_service
from db_mcp.tools.utils import resolve_connection


async def _save_artifact(
    connection: str,
    artifact_type: str,
    content: str,
    name: str | None = None,
) -> dict:
    """Save a typed artifact into the resolved connection vault."""
    _, _, connection_path = resolve_connection(connection)
    return vault_service.save_artifact(
        connection_path=connection_path,
        artifact_type=artifact_type,
        content=content,
        name=name,
    )
