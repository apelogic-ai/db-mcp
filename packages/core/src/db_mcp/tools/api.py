"""API connector MCP tools."""

from typing import Any

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


async def _api_query(
    endpoint: str,
    params: dict[str, str] | None = None,
    max_pages: int = 1,
    id: str | list[str] | None = None,
) -> dict[str, Any]:
    """Query a REST API endpoint with parameters.

    NOTE: This is for REST endpoints only, NOT for SQL execution.
    For SQL-like APIs (Dune, etc.) with supports_sql=true, use run_sql(sql="...") instead.

    Returns rows from the API endpoint matching the given parameters.
    Use api_describe_endpoint to see available parameters first.

    Args:
        endpoint: Name of the endpoint to query (e.g. "markets", "events").
        params: Query parameters as key-value pairs (e.g. {"active": "true"}).
        max_pages: Maximum pages to fetch. Default 1 (single page, fast).
        id: Fetch specific record(s) by ID. Hits the detail endpoint /{id}.
            Pass a single ID string or a list of ID strings.

    Returns:
        {data: [...], rows_returned: int} or {error: "..."}.
    """
    connector = get_connector()
    if not isinstance(connector, APIConnector):
        return {"error": "Active connection is not an API connector"}
    return connector.query_endpoint(endpoint, params, max_pages, id=id)


async def _api_describe_endpoint(endpoint: str) -> dict[str, Any]:
    """Describe an API endpoint's available query parameters.

    Returns endpoint metadata including available filters, sorts,
    and other query parameters with their types and descriptions.

    Args:
        endpoint: Name of the endpoint to describe (e.g. "markets", "events").

    Returns:
        Endpoint metadata including name, path, method, and query_params.
    """
    connector = get_connector()
    if not isinstance(connector, APIConnector):
        return {"error": "Active connection is not an API connector"}

    for ep in connector.api_config.endpoints:
        if ep.name == endpoint:
            return {
                "name": ep.name,
                "path": ep.path,
                "method": ep.method,
                "query_params": [
                    {
                        "name": qp.name,
                        "type": qp.type,
                        "description": qp.description,
                        "required": qp.required,
                        "enum": qp.enum,
                        "default": qp.default,
                    }
                    for qp in ep.query_params
                ],
            }

    return {"error": f"Unknown endpoint: {endpoint}"}
