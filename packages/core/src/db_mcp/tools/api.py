"""API connector MCP tools."""

from db_mcp.connectors import APIConnector, get_connector


async def _api_sync(endpoint: str | None = None) -> dict:
    """Sync data from API endpoints.

    Fetches latest data from configured API endpoints and stores
    as local JSONL files for querying.

    Args:
        endpoint: Optional endpoint name to sync. If not provided, syncs all endpoints.

    Returns:
        Sync results including rows fetched per endpoint and any errors.
    """
    connector = get_connector()
    if not isinstance(connector, APIConnector):
        return {"error": "Active connection is not an API connector"}
    return connector.sync(endpoint_name=endpoint)
