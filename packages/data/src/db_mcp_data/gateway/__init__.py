"""Gateway public API.

The gateway is the single typed boundary between services/tools and
the physical connectors. All data retrieval goes through here.

Public surface:
    create(request)               -> ValidatedQuery
    execute(query_id, options)    -> ExecutionResult
    run(request, options)         -> ExecutionResult   (create + execute)
    introspect(connection, scope) -> dict
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from db_mcp_models.gateway import DataRequest, DataResponse, RunOptions, ValidatedQuery

__all__ = [
    "capabilities",
    "create",
    "execute",
    "get_query",
    "introspect",
    "mark_complete",
    "mark_error",
    "mark_running",
    "run",
    "start_query_execution",
]


async def create(
    request: DataRequest,
    *,
    connection_path: Path | None = None,
    cost_tier: str = "unknown",
    estimated_rows: int | None = None,
    estimated_cost: float | None = None,
    explanation: list | None = None,
) -> ValidatedQuery:
    """Validate a DataRequest, persist it, and return a ValidatedQuery.

    Stores the query in QueryStore so it can be executed by query_id via
    gateway.execute().  Pre-computed cost metadata (cost_tier, estimated_rows,
    estimated_cost, explanation) from validate_sql's EXPLAIN step is forwarded
    so the stored Query reflects the actual cost tier rather than 'unknown'.
    """
    from datetime import UTC, datetime

    from db_mcp_models.gateway import EndpointQuery, SQLQuery

    from db_mcp_data.execution.query_store import get_query_store

    if isinstance(request.query, SQLQuery):
        query_type = "sql"
        sql_text = request.query.sql
        endpoint_name = None
        store_sql = sql_text
    elif isinstance(request.query, EndpointQuery):
        import json as _json
        query_type = "endpoint"
        sql_text = None
        endpoint_name = request.query.endpoint
        # Serialize the full EndpointQuery so execute() can reconstruct it losslessly.
        store_sql = "endpoint_json:" + _json.dumps({
            "endpoint": request.query.endpoint,
            "params": dict(request.query.params),
            "method": request.query.method,
            "max_pages": request.query.max_pages,
        })
    else:
        raise TypeError(f"Unsupported query type: {type(request.query).__name__}")

    store = get_query_store()
    query = await store.register_validated(
        sql=store_sql,
        cost_tier=cost_tier,
        estimated_rows=estimated_rows,
        estimated_cost=estimated_cost,
        explanation=explanation or [],
        connection=request.connection,
    )

    return ValidatedQuery(
        query_id=query.query_id,
        connection=request.connection,
        query_type=query_type,
        request=request,
        cost_tier=cost_tier,
        validated_at=datetime.now(UTC),
        sql=sql_text,
        endpoint=endpoint_name,
    )


async def execute(
    query_id: str,
    *,
    connection_path: Path | None = None,
    options: RunOptions | None = None,
) -> DataResponse:
    """Execute a previously validated query by query_id.

    Looks up the query in QueryStore, resolves the connector via connection_path,
    dispatches to the appropriate adapter, and returns a DataResponse.
    """
    from db_mcp_models.gateway import EndpointQuery, SQLQuery

    from db_mcp_data.execution.query_store import get_query_store
    from db_mcp_data.gateway.dispatcher import get_adapter, get_connector

    store = get_query_store()
    query = await store.get(query_id)

    if query is None:
        return DataResponse(
            status="error",
            data=[],
            columns=[],
            rows_returned=0,
            error=f"Query '{query_id}' not found. Use gateway.create() first.",
        )

    # Cost-gate check: cost_tier="reject" is blocked unless confirmed.
    confirmed = options.confirmed if options is not None else False
    if query.cost_tier == "reject" and not confirmed:
        return DataResponse(
            status="error",
            data=[],
            columns=[],
            rows_returned=0,
            error=(
                f"Query '{query_id}' has cost_tier='reject' and cannot run without explicit "
                "confirmation. Pass RunOptions(confirmed=True) to override."
            ),
        )

    resolved_path = connection_path or Path(".")
    connection = query.connection or ""

    # Reconstruct the request from the stored SQL / endpoint payload.
    if query.sql and query.sql.startswith("endpoint_json:"):
        import json as _json
        payload = _json.loads(query.sql[len("endpoint_json:"):])
        data_query: SQLQuery | EndpointQuery = EndpointQuery(
            endpoint=payload["endpoint"],
            params=payload.get("params") or {},
            method=payload.get("method", "GET"),
            max_pages=payload.get("max_pages", 1),
        )
    elif query.sql and query.sql.startswith("endpoint:"):
        # Legacy placeholder (no params) — kept for backward compat.
        endpoint_name = query.sql[len("endpoint:"):]
        data_query = EndpointQuery(endpoint=endpoint_name)
    else:
        data_query = SQLQuery(sql=query.sql or "")

    from db_mcp_models.gateway import DataRequest
    request = DataRequest(connection=connection, query=data_query)

    try:
        connector = get_connector(connection_path=str(resolved_path))
        adapter = get_adapter(connector)
    except ValueError as exc:
        return DataResponse(
            status="error", data=[], columns=[], rows_returned=0, error=str(exc)
        )

    return adapter.execute(connector, request, connection_path=resolved_path)


async def run(
    request: DataRequest,
    *,
    connection_path: Path | None = None,
    options: RunOptions | None = None,
) -> DataResponse:
    """Convenience: create() then execute() in one call.

    Persists the validated query in QueryStore and executes it immediately.
    Returns a typed DataResponse.
    """
    vq = await create(request, connection_path=connection_path)
    return await execute(vq.query_id, connection_path=connection_path, options=options)


def introspect(
    connection: str,
    scope: str,
    *,
    connection_path: Path | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    table: str | None = None,
) -> dict[str, Any]:
    """Introspect schema objects on a connection.

    scope: "catalogs" | "schemas" | "tables" | "columns"
    Resolves the connector from connection_path, picks the right adapter,
    and delegates to adapter.introspect().
    """
    from db_mcp_data.gateway.dispatcher import resolve_and_introspect

    resolved_path = connection_path or Path(".")
    return resolve_and_introspect(
        connection,
        scope,
        connection_path=resolved_path,
        catalog=catalog,
        schema=schema,
        table=table,
    )


def capabilities(
    connection_path: Path,
) -> dict[str, Any]:
    """Return connector capabilities for a connection path.

    Resolves the connector via the gateway dispatcher and returns its
    capability dict.  Services call this instead of importing get_connector() +
    get_connector_capabilities() directly, keeping the gateway as the single
    point of entry for all connector access.
    """
    from db_mcp_data.connectors import get_connector_capabilities
    from db_mcp_data.gateway.dispatcher import get_connector as _get_connector

    connector = _get_connector(connection_path=str(connection_path))
    return get_connector_capabilities(connector)


# ---------------------------------------------------------------------------
# Query lifecycle — single boundary for QueryStore access
# ---------------------------------------------------------------------------

async def get_query(query_id: str) -> Any:
    """Return the Query record for *query_id*, or None if not found.

    Services call this instead of importing QueryStore directly, so all
    query-record access is visible at the gateway boundary.
    """
    from db_mcp_data.execution.query_store import get_query_store
    return await get_query_store().get(query_id)


async def mark_running(query_id: str) -> None:
    """Transition a query to RUNNING state."""
    from db_mcp_data.execution.query_store import QueryStatus, get_query_store
    await get_query_store().update_status(query_id, QueryStatus.RUNNING)


async def mark_complete(
    query_id: str,
    *,
    rows_returned: int,
) -> None:
    """Transition a query to COMPLETE state. Results are stored in ExecutionStore."""
    from db_mcp_data.execution.query_store import QueryStatus, get_query_store
    await get_query_store().update_status(
        query_id,
        QueryStatus.COMPLETE,
        rows_returned=rows_returned,
    )


async def mark_error(query_id: str, *, error: str) -> None:
    """Transition a query to ERROR state."""
    from db_mcp_data.execution.query_store import QueryStatus, get_query_store
    await get_query_store().update_status(query_id, QueryStatus.ERROR, error=error)


async def start_query_execution(query_id: str) -> Any:
    """Mark a query as having started background execution.

    Returns the result of QueryStore.start_execution() (truthy on success).
    """
    from db_mcp_data.execution.query_store import get_query_store
    return await get_query_store().start_execution(query_id)
