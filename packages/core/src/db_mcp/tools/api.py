"""API connector MCP tools."""

from db_mcp.config import get_settings
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


async def _api_discover() -> dict:
    """Discover API endpoints, pagination, and schema.

    Automatically discovers what endpoints are available on the configured API
    by trying OpenAPI/Swagger spec discovery, then falling back to endpoint probing.
    Updates the connection's connector.yaml with discovered endpoints.

    Returns:
        Discovery results including endpoints found, strategy used, and any errors.
    """
    connector = get_connector()
    if not isinstance(connector, APIConnector):
        return {"error": "Active connection is not an API connector"}

    result = connector.discover()

    # Persist updated config to connector.yaml
    if result.get("endpoints_found", 0) > 0:
        settings = get_settings()
        conn_path = settings.get_effective_connection_path()
        yaml_path = f"{conn_path}/connector.yaml"
        connector.save_connector_yaml(yaml_path)

    return result
