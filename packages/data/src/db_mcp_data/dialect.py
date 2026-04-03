"""Re-export shim — canonical location is db_mcp_data.connectors.dialect."""

from db_mcp_data.connectors.dialect import (  # noqa: F401
    get_dialect_file_path,
    get_dialect_for_connection,
    load_dialect_rules,
)
