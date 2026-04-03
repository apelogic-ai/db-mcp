"""Knowledge vault package."""

from db_mcp_knowledge.vault.init import ensure_connection_structure
from db_mcp_knowledge.vault.migrate import (
    migrate_legacy_provider_data,
    migrate_namespace,
    migrate_to_connection_structure,
)

__all__ = [
    # New connection-based functions
    "ensure_connection_structure",
    "migrate_to_connection_structure",
    "migrate_namespace",
    # Legacy aliases (deprecated)
    "migrate_legacy_provider_data",
]
