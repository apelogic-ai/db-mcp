"""Single-tool code mode implementation."""

from __future__ import annotations

import asyncio
from typing import (
    Any as Context,  # noqa: UP006 — Context was fastmcp.Context; moved to mcp-server in Phase 3
)

from db_mcp.code_runtime import CodeRuntimeService
from db_mcp.exec_runtime import get_exec_session_manager


def _get_code_runtime_service() -> CodeRuntimeService:
    """Build the code runtime service with the active execution manager."""
    return CodeRuntimeService(manager=get_exec_session_manager())


async def _code(
    code: str,
    connection: str,
    timeout_seconds: int = 30,
    confirmed: bool = False,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Run Python code in the shared db-mcp code runtime."""
    session_id = getattr(ctx, "session_id", None) or "stateless"
    service = _get_code_runtime_service()
    result = await asyncio.to_thread(
        service.run,
        connection,
        code,
        session_id=session_id,
        timeout_seconds=timeout_seconds,
        confirmed=confirmed,
    )
    return result.to_dict()
