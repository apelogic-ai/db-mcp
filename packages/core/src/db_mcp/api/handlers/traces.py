"""Trace viewer handlers."""

from __future__ import annotations

from typing import Any

import db_mcp.services.traces as traces_service
from db_mcp.api.helpers import _config_file, _connections_dir
from db_mcp.services.connection import get_active_connection_path


async def handle_traces_list(params: dict[str, Any]) -> dict[str, Any]:
    active = get_active_connection_path(
        config_file=_config_file(), connections_dir=_connections_dir()
    )
    return traces_service.list_traces(
        source=params.get("source", "live"),
        connection_path=active,
        date_str=params.get("date"),
        limit=params.get("limit"),
    )


async def handle_traces_clear(params: dict[str, Any]) -> dict[str, Any]:
    return traces_service.clear_traces()


async def handle_traces_dates(params: dict[str, Any]) -> dict[str, Any]:
    active = get_active_connection_path(
        config_file=_config_file(), connections_dir=_connections_dir()
    )
    return traces_service.get_trace_dates(connection_path=active)
