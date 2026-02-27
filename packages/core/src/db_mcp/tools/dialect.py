"""SQL dialect MCP tools."""

from db_mcp.dialect import load_dialect_rules


async def _get_dialect_rules(dialect: str) -> dict:
    """Get SQL dialect rules for a specific dialect.

    Args:
        dialect: Dialect name (trino, postgresql, clickhouse)

    Returns:
        Dialect rules and metadata
    """
    return load_dialect_rules(dialect)


async def _get_connection_dialect(connection: str) -> dict:
    """Detect dialect from configured database and load rules.

    Args:
        connection: Connection name for multi-connection support.

    Returns:
        Detected dialect and rules for the configured database
    """
    from db_mcp.registry import ConnectionRegistry

    registry = ConnectionRegistry.get_instance()
    conn_info = registry.discover().get(connection)
    if conn_info and conn_info.dialect:
        return load_dialect_rules(conn_info.dialect)

    # Fall back to getting connector and calling get_dialect()
    try:
        connector = registry.get_connector(connection)
        dialect = connector.get_dialect()
        return load_dialect_rules(dialect)
    except Exception as e:
        return {
            "detected": False,
            "dialect": None,
            "rules": [],
            "error": f"Could not detect dialect for connection '{connection}': {e}",
        }
