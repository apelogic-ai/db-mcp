"""Playground handlers."""

from __future__ import annotations

from typing import Any


async def handle_playground_install(params: dict[str, Any]) -> dict[str, Any]:
    from db_mcp.playground import install_playground

    return install_playground()


async def handle_playground_status(params: dict[str, Any]) -> dict[str, Any]:
    from db_mcp.playground import is_playground_installed

    return {"installed": is_playground_installed()}
