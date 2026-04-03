"""API connector MCP tools."""

from typing import Any

from db_mcp_data.connectors import APIConnector, get_connector_capabilities
from db_mcp_data.execution import check_protocol_ack_gate, evaluate_sql_execution_policy
from db_mcp_data.execution.engine import get_execution_engine
from db_mcp_data.execution.models import ExecutionRequest, ExecutionState

from db_mcp.registry import ConnectionRegistry
from db_mcp.tools.utils import require_connection, resolve_connection


def _get_api_connector(connection: str) -> tuple[APIConnector | None, dict | None]:
    """Resolve and validate an API connector.

    Returns:
        (APIConnector, None) on success, or (None, error_dict) on failure.
    """
    try:
        connection = require_connection(connection, tool_name="api tools")
        connector, conn_name, conn_path = resolve_connection(connection, require_type="api")
    except ValueError as exc:
        return None, {"error": str(exc)}

    if not isinstance(connector, APIConnector):
        return None, {"error": "Resolved connection is not an API connector"}

    return connector, None


def _is_auth_error(result: dict[str, Any]) -> bool:
    """Return True when a tool result indicates authentication/authorization failure."""
    err = result.get("error")
    if not isinstance(err, str):
        return False
    lowered = err.lower()
    return "401" in lowered or "unauthorized" in lowered


async def _api_sync(connection: str, endpoint: str | None = None) -> dict:
    """Sync data from API endpoints.

    Fetches latest data from configured API endpoints and stores
    as local JSONL files for querying.

    Args:
        connection: Connection name for multi-connection support.
        endpoint: Optional endpoint name to sync. If not provided, syncs all endpoints.

    Returns:
        Sync results including rows fetched per endpoint and any errors.
    """
    connector, err = _get_api_connector(connection)
    if err:
        return err
    return connector.sync(endpoint_name=endpoint)


async def _api_discover(connection: str) -> dict:
    """Discover API endpoints, pagination, and schema.

    Automatically discovers what endpoints are available on the configured API
    by trying OpenAPI/Swagger spec discovery, then falling back to endpoint probing.
    Updates the connection's connector.yaml with discovered endpoints.

    Args:
        connection: Connection name for multi-connection support.

    Returns:
        Discovery results including endpoints found, strategy used, and any errors.
    """
    try:
        connector, conn_name, conn_path = resolve_connection(connection, require_type="api")
    except ValueError as exc:
        return {"error": str(exc)}

    if not isinstance(connector, APIConnector):
        return {"error": "Resolved connection is not an API connector"}

    result = connector.discover()

    # Persist updated config to connector.yaml
    if result.get("endpoints_found", 0) > 0:
        yaml_path = str(conn_path / "connector.yaml")
        connector.save_connector_yaml(yaml_path)

    return result


async def _api_query(
    endpoint: str,
    connection: str,
    params: dict[str, Any] | None = None,
    max_pages: int = 1,
    id: str | list[str] | None = None,
) -> dict[str, Any]:
    """Query a REST API endpoint with parameters.

    For SQL execution on SQL-like APIs (Dune, etc.), use api_execute_sql instead.

    Returns rows from the API endpoint matching the given parameters.
    Use api_describe_endpoint to see available parameters first.

    Args:
        endpoint: Name of the endpoint to query (e.g. "markets", "events").
        connection: Connection name for multi-connection support.
        params: Endpoint parameters as key-value pairs. Values may be non-string
            types (e.g. booleans, numbers, arrays) for APIs that expect JSON payloads.
        max_pages: Maximum pages to fetch. Default 1 (single page, fast).
        id: Optional ID hint for detail endpoints. For templated endpoint paths like
            `/resource/{id}`, this substitutes the `{id}` placeholder.
            For non-templated GET endpoints, this fetches detail paths via `/{id}`.
    Returns:
        {execution_id: str, data: [...], rows_returned: int} or {error: "..."}.
    """
    try:
        connection = require_connection(connection, tool_name="api_query")
        connector, _, conn_path = resolve_connection(connection, require_type="api")
    except ValueError as exc:
        return {"error": str(exc)}

    if not isinstance(connector, APIConnector):
        return {"error": "Resolved connection is not an API connector"}

    request = ExecutionRequest(
        connection=connection,
        metadata={"endpoint": endpoint, "params": params or {}},
    )

    def _run(_payload: dict) -> dict:
        res = connector.query_endpoint(endpoint, params, max_pages, id=id)
        if _is_auth_error(res):
            ConnectionRegistry.get_instance().invalidate_connector(connection)
            refreshed, conn_err = _get_api_connector(connection)
            if conn_err:
                raise RuntimeError(conn_err.get("error", "Authentication failed"))
            res = refreshed.query_endpoint(endpoint, params, max_pages, id=id)
            if _is_auth_error(res):
                raise RuntimeError(res.get("error", "Authentication failed after retry"))
        return res

    engine = get_execution_engine(conn_path)
    handle, exec_result = engine.submit_sync(request, _run)

    if exec_result.state == ExecutionState.FAILED:
        err_msg = exec_result.error.message if exec_result.error else "Execution failed"
        return {"error": err_msg}

    return {
        "execution_id": handle.execution_id,
        "data": exec_result.data,
        "rows_returned": exec_result.rows_returned,
    }


async def _api_execute_sql(sql: str, connection: str) -> dict[str, Any]:
    """Execute SQL on a SQL-like API (Dune, Trino-based services, etc.).

    Use this for API connectors with supports_sql=true. The SQL is sent to the
    API's execute_sql endpoint, polled for completion, and results returned.

    This is the primary tool for querying SQL-like APIs like Dune Analytics.
    Do NOT use api_query for SQL - use this instead.

    Args:
        sql: SQL query to execute (e.g. "SELECT * FROM dex_solana.trades LIMIT 10")
        connection: Connection name for multi-connection support.

    Returns:
        {status: "success", data: [...], rows_returned: int} or {status: "error", error: "..."}
    """
    try:
        connection = require_connection(connection, tool_name="api_execute_sql")
        connector, _, conn_path = resolve_connection(connection, require_type="api")
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}

    if not isinstance(connector, APIConnector):
        return {"status": "error", "error": "Resolved connection is not an API connector"}

    caps = get_connector_capabilities(connector)
    if not caps.get("supports_sql"):
        return {
            "status": "error",
            "error": "This API connector does not support SQL execution. Use api_query instead.",
        }

    policy_error = check_protocol_ack_gate(connection=connection, connection_path=conn_path)
    if policy_error is not None:
        return policy_error

    policy_error, _, _ = evaluate_sql_execution_policy(
        sql=sql,
        capabilities=caps,
        confirmed=False,
        require_validate_first=False,
        query_id=None,
    )
    if policy_error is not None:
        return policy_error

    try:
        rows = connector.execute_sql(sql)
        columns = list(rows[0].keys()) if rows else []
        return {
            "status": "success",
            "data": rows,
            "columns": columns,
            "rows_returned": len(rows),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _api_describe_endpoint(endpoint: str, connection: str) -> dict[str, Any]:
    """Describe an API endpoint's available query parameters.

    Returns endpoint metadata including available filters, sorts,
    and other query parameters with their types and descriptions.

    Args:
        endpoint: Name of the endpoint to describe (e.g. "markets", "events").
        connection: Connection name for multi-connection support.

    Returns:
        Endpoint metadata including name, path, method, and query_params.
    """
    connector, err = _get_api_connector(connection)
    if err:
        return err

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


async def _api_mutate(
    endpoint: str,
    method: str,
    connection: str,
    body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create, update, or delete a resource via a REST API endpoint.

    Sends a mutating HTTP request (POST/PUT/PATCH/DELETE) to the specified
    API endpoint with an optional JSON body. Returns the raw API response.

    Use this for creating, updating, or deleting resources on REST APIs
    like Superset, Metabase, Grafana, or any CRUD API.

    Args:
        endpoint: Name of the configured endpoint to call (e.g. "charts", "dashboards").
        method: HTTP method — must be POST, PUT, PATCH, or DELETE.
        connection: Connection name for multi-connection support.
        body: JSON request body (for POST/PUT/PATCH). Optional for DELETE.
        params: Optional query string parameters.

    Returns:
        Raw API response dict, or {error: "..."} on failure.
    """
    method_upper = method.upper()
    if method_upper not in ("POST", "PUT", "PATCH", "DELETE"):
        return {
            "error": (
                f"Invalid method '{method}'. api_mutate only supports POST, PUT, PATCH, DELETE."
            )
        }

    connector, err = _get_api_connector(connection)
    if err:
        return err

    result = connector.query_endpoint(endpoint, params, body=body, method_override=method_upper)
    if _is_auth_error(result):
        ConnectionRegistry.get_instance().invalidate_connector(connection)
        connector, err = _get_api_connector(connection)
        if err:
            return err
        result = connector.query_endpoint(
            endpoint,
            params,
            body=body,
            method_override=method_upper,
        )
    return result
