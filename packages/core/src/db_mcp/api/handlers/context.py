"""Context / vault handlers."""

from __future__ import annotations

import logging
from typing import Any

import yaml
from db_mcp_knowledge.vault.paths import BUSINESS_RULES_FILE

import db_mcp.services.vault as vault_service
from db_mcp.api.helpers import _config_file, _connections_dir, _is_git_enabled

logger = logging.getLogger(__name__)


async def handle_context_tree(params: dict[str, Any]) -> dict[str, Any]:
    connections_dir = _connections_dir()

    active_connection = None
    cfg = _config_file()
    if cfg.exists():
        with open(cfg) as f:
            config = yaml.safe_load(f) or {}
            active_connection = config.get("active_connection")

    return vault_service.list_context_tree(
        connections_dir=connections_dir,
        active_connection=active_connection,
        is_git_enabled=_is_git_enabled,
    )


async def handle_context_read(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}
    return vault_service.read_context_file(
        connection_path=_connections_dir() / str(connection),
        path=str(path),
    )


async def handle_context_write(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    content = params.get("content")

    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}
    if content is None:
        return {"success": False, "error": "content is required"}

    conn_path = _connections_dir() / str(connection)

    try:
        write_result = vault_service.write_context_file(
            connection_path=conn_path, path=str(path), content=str(content)
        )
        if not write_result["success"]:
            return write_result

        git_commit = vault_service.try_git_commit(conn_path, f"Update {path}", [path])
        logger.info("Wrote file: %s/%s", connection, path)
        return {"success": True, "gitCommit": git_commit}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_context_create(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    content = params.get("content", "")

    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}

    conn_path = _connections_dir() / str(connection)

    try:
        create_result = vault_service.create_context_file(
            connection_path=conn_path, path=str(path), content=str(content)
        )
        if not create_result["success"]:
            return create_result

        git_commit = vault_service.try_git_commit(conn_path, f"Create {path}", [path])
        logger.info("Created file: %s/%s", connection, path)
        return {"success": True, "gitCommit": git_commit}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_context_delete(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")

    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}

    if ".." in path or path.startswith("/"):
        return {"success": False, "error": "Invalid path"}

    conn_path = _connections_dir() / connection

    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        if _is_git_enabled(conn_path):
            from db_mcp_knowledge.git_utils import git

            git.rm(conn_path, path)
            git.commit(conn_path, f"Delete {path}")
            logger.info("Git rm: %s/%s", connection, path)
            return {"success": True, "gitCommit": True}

        result = vault_service.delete_context_file(
            connection_path=conn_path, path=str(path)
        )
        if result.get("success"):
            logger.info("Trashed: %s/%s -> %s", connection, path, result.get("trashedTo"))
        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_context_add_rule(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    rule = params.get("rule")
    gap_id = params.get("gapId")

    if not connection or not rule:
        return {"success": False, "error": "connection and rule are required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}

    try:
        result = vault_service.add_business_rule(
            connection_path=conn_path,
            connection_name=str(connection),
            rule=str(rule),
        )
        if not result["success"]:
            return {"success": False, "error": result["error"]}
        if result.get("duplicate"):
            return {"success": True, "duplicate": True}

        vault_service.try_git_commit(conn_path, "Add business rule", [BUSINESS_RULES_FILE])

        if gap_id:
            try:
                from db_mcp_knowledge.gaps.store import resolve_gap

                resolve_gap(connection, gap_id, "business_rules")
            except Exception as e:
                logger.warning("Failed to resolve gap %s: %s", gap_id, e)

        logger.info("Added business rule to %s: %s", connection, str(rule)[:60])
        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def handle_context_usage(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    days = params.get("days", 7)

    if not connection:
        return {"success": False, "error": "connection is required"}

    conn_path = _connections_dir() / connection
    if not conn_path.exists():
        return {"success": False, "error": f"Connection '{connection}' not found"}
    return vault_service.get_context_usage(conn_path, days=days)
