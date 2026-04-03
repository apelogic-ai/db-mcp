"""Gateway dispatcher — resolves connectors to adapters.

_ADAPTERS is ordered: APIAdapter must precede FileAdapter because
APIConnector extends FileConnector, and can_handle checks use isinstance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from db_mcp_models.gateway import DataResponse

from db_mcp_data.connectors import get_connector
from db_mcp_data.gateway.adapter import ConnectorAdapter
from db_mcp_data.gateway.api_adapter import APIAdapter
from db_mcp_data.gateway.file_adapter import FileAdapter
from db_mcp_data.gateway.sql_adapter import SQLAdapter

_ADAPTERS: list[ConnectorAdapter] = [
    APIAdapter(),   # must precede FileAdapter — APIConnector extends FileConnector
    FileAdapter(),
    SQLAdapter(),
]


def get_adapter(connector: Any) -> ConnectorAdapter:
    """Return the first adapter that can handle *connector*.

    Raises ValueError if no adapter matches.
    """
    for adapter in _ADAPTERS:
        if adapter.can_handle(connector):
            return adapter
    raise ValueError(
        f"No adapter found for connector type '{type(connector).__name__}'. "
        "Supported types: SQLConnector, APIConnector, FileConnector."
    )


def resolve_and_dispatch(
    request: Any,
    *,
    connection_path: Path,
) -> DataResponse:
    """Resolve connector from connection_path, find adapter, execute request."""
    connector = get_connector(connection_path=str(connection_path))
    try:
        adapter = get_adapter(connector)
    except ValueError as exc:
        return DataResponse(status="error", data=[], columns=[], rows_returned=0, error=str(exc))
    return adapter.execute(connector, request, connection_path=connection_path)


def resolve_and_introspect(
    connection: str,
    scope: str,
    *,
    connection_path: Path,
    catalog: str | None = None,
    schema: str | None = None,
    table: str | None = None,
) -> dict[str, Any]:
    """Resolve connector from connection_path, find adapter, introspect."""
    connector = get_connector(connection_path=str(connection_path))
    try:
        adapter = get_adapter(connector)
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}
    return adapter.introspect(
        connector,
        scope,
        catalog=catalog,
        schema=schema,
        table=table,
        connection_path=connection_path,
    )
