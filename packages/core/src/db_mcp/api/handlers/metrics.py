"""Metrics handlers."""

from __future__ import annotations

import logging
from typing import Any

from db_mcp_knowledge.vault.paths import DIMENSIONS_FILE, METRICS_CATALOG_FILE

import db_mcp.services.metrics as metrics_service
import db_mcp.services.vault as vault_service
from db_mcp.api.helpers import _connections_dir

logger = logging.getLogger(__name__)


async def handle_metrics_list(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    if not connection:
        return {"success": False, "error": "connection is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}
    return {
        "success": True,
        **metrics_service.list_approved_metrics(connection, connection_path=conn_path),
    }


async def handle_metrics_add(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    item_type = params.get("type", "metric")
    data = params.get("data", {})

    if not connection:
        return {"success": False, "error": "connection is required"}
    if not data or not data.get("name"):
        return {"success": False, "error": "data with name is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if item_type == "dimension":
            result = metrics_service.add_dimension_definition(connection=connection, data=data)
            if result.get("success"):
                vault_service.try_git_commit(
                    conn_path, f"Add dimension: {data['name']}", [DIMENSIONS_FILE]
                )
            return result

        result = metrics_service.add_metric_definition(connection=connection, data=data)
        if result.get("success"):
            vault_service.try_git_commit(
                conn_path, f"Add metric: {data['name']}", [METRICS_CATALOG_FILE]
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_metrics_update(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    item_type = params.get("type", "metric")
    name = params.get("name")
    data = params.get("data", {})

    if not connection or not name:
        return {"success": False, "error": "connection and name are required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if item_type == "dimension":
            result = metrics_service.update_dimension_definition(
                connection=connection, name=name, data=data
            )
            if result.get("success"):
                vault_service.try_git_commit(
                    conn_path,
                    f"Update dimension: {result['name']}",
                    [DIMENSIONS_FILE],
                )
            return result

        result = metrics_service.update_metric_definition(
            connection=connection, name=name, data=data
        )
        if result.get("success"):
            vault_service.try_git_commit(
                conn_path, f"Update metric: {result['name']}", [METRICS_CATALOG_FILE]
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_metrics_delete(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    item_type = params.get("type", "metric")
    name = params.get("name")

    if not connection or not name:
        return {"success": False, "error": "connection and name are required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if item_type == "dimension":
            result = metrics_service.delete_dimension_definition(connection, name)
            if result.get("success"):
                vault_service.try_git_commit(
                    conn_path, f"Delete dimension: {name}", [DIMENSIONS_FILE]
                )
            return result

        result = metrics_service.delete_metric_definition(connection, name)
        if result.get("success"):
            vault_service.try_git_commit(
                conn_path, f"Delete metric: {name}", [METRICS_CATALOG_FILE]
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_metrics_candidates(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    if not connection:
        return {"success": False, "error": "connection is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        result = await metrics_service.discover_metric_candidates(connection, conn_path)
        return {"success": True, **result}
    except Exception as e:
        logger.exception("Mining failed: %s", e)
        return {"success": False, "error": str(e)}


async def handle_metrics_approve(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    item_type = params.get("type", "metric")
    data = params.get("data", {})

    if not connection:
        return {"success": False, "error": "connection is required"}
    if not data or not data.get("name"):
        return {"success": False, "error": "data with name is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if item_type == "dimension":
            result = metrics_service.approve_dimension_candidate(
                connection=connection, data=data
            )
            if result.get("success"):
                vault_service.try_git_commit(
                    conn_path,
                    f"Add dimension: {data['name']}",
                    [DIMENSIONS_FILE],
                )
            return result

        result = metrics_service.approve_metric_candidate(connection=connection, data=data)
        if result.get("success"):
            vault_service.try_git_commit(
                conn_path, f"Add metric: {data['name']}", [METRICS_CATALOG_FILE]
            )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}
