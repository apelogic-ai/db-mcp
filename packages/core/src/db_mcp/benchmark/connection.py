"""Connection helpers for the benchmark app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from db_mcp.connectors import get_connector
from db_mcp.connectors.sql import SQLConnector
from db_mcp.registry import ConnectionRegistry


@dataclass
class SQLConnectionAccess:
    """Resolved SQL connection inputs for a benchmark run."""

    connection_name: str
    connection_path: Path
    connector: SQLConnector
    database_url: str
    connect_args: dict[str, Any] | None


def resolve_sql_connection_access(connection_name: str) -> SQLConnectionAccess:
    """Resolve a configured connection to benchmark-ready SQL access."""
    registry = ConnectionRegistry.get_instance()
    info = registry.discover().get(connection_name)
    if info is None:
        raise ValueError(f"Connection '{connection_name}' not found.")
    if info.type != "sql":
        raise ValueError(
            f"Connection '{connection_name}' has type '{info.type}'. Only SQL is supported."
        )

    connection_path = registry.get_connection_path(connection_name)
    connector = get_connector(connection_path=str(connection_path))
    if not isinstance(connector, SQLConnector):
        raise ValueError(
            f"Connection '{connection_name}' is not backed by SQLConnector. Only SQL is supported."
        )

    database_url = connector.config.database_url
    if not database_url:
        raise ValueError(f"Connection '{connection_name}' has no database_url configured.")

    connect_args = connector.config.capabilities.get("connect_args")
    if not isinstance(connect_args, dict):
        connect_args = None

    return SQLConnectionAccess(
        connection_name=connection_name,
        connection_path=connection_path,
        connector=connector,
        database_url=database_url,
        connect_args=connect_args,
    )
