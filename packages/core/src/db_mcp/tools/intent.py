"""Intent-oriented orchestration tools."""

from __future__ import annotations

from typing import Any

from db_mcp.orchestrator.engine import answer_intent
from db_mcp.tools.shell import inject_protocol


async def _answer_intent(
    intent: str,
    connection: str,
    options: dict[str, Any] | None = None,
) -> dict:
    """Resolve a semantic intent and execute it through the orchestration path."""
    payload = await answer_intent(intent=intent, connection=connection, options=options)
    return inject_protocol(payload)
