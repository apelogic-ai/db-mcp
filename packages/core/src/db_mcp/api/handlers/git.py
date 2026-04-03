"""Git history handlers."""

from __future__ import annotations

from typing import Any

import db_mcp.services.git as git_service
from db_mcp.api.helpers import _connections_dir


async def handle_git_history(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    limit = params.get("limit", 50)

    if not connection or not path:
        return {"success": False, "error": "connection and path are required"}

    return git_service.get_git_history(
        _connections_dir() / connection, path, limit=limit
    )


async def handle_git_show(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    commit = params.get("commit")

    if not connection or not path or not commit:
        return {"success": False, "error": "connection, path, and commit are required"}

    return git_service.get_git_content(
        _connections_dir() / connection, path, commit
    )


async def handle_git_revert(params: dict[str, Any]) -> dict[str, Any]:
    connection = params.get("connection")
    path = params.get("path")
    commit = params.get("commit")

    if not connection or not path or not commit:
        return {"success": False, "error": "connection, path, and commit are required"}

    return git_service.revert_git_file(
        _connections_dir() / connection, path, commit
    )
