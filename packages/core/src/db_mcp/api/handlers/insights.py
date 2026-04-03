"""Insight and gap handlers."""

from __future__ import annotations

import logging
from typing import Any

import db_mcp.services.insights as insights_service
import db_mcp.services.vault as vault_service
from db_mcp.api.helpers import _config_file, _connections_dir
from db_mcp.services.connection import get_active_connection_path

logger = logging.getLogger(__name__)


async def handle_insights_analyze(params: dict[str, Any]) -> dict[str, Any]:
    days = params.get("days", 7)
    active = get_active_connection_path(
        config_file=_config_file(), connections_dir=_connections_dir()
    )
    analysis = insights_service.analyze_insights(connection_path=active, days=days)
    return {"success": True, "analysis": analysis}


async def handle_gaps_dismiss(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    gap_id = params.get("gapId")
    reason = params.get("reason")

    if not connection or not gap_id:
        return {"success": False, "error": "connection and gapId are required"}

    try:
        result = insights_service.dismiss_gap(connection, gap_id, reason)
        if result.get("success"):
            logger.info(
                "Dismissed gap %s in %s%s", gap_id, connection,
                f": {reason}" if reason else "",
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_insights_save_example(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    sql = params.get("sql")
    intent = params.get("intent")

    if not connection or not sql or not intent:
        return {"success": False, "error": "connection, sql, and intent are required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        result = insights_service.save_example(connection=connection, sql=sql, intent=intent)
        if result.get("success"):
            file_path = result.get("file_path")
            if file_path:
                vault_service.try_git_commit(
                    conn_path, "Add training example from insights", [file_path]
                )
            return {
                "success": True,
                "example_id": result["example_id"],
                "total_examples": result["total_examples"],
            }
        return {"success": False, "error": result.get("error", "Failed to save example")}
    except Exception as e:
        return {"success": False, "error": str(e)}
