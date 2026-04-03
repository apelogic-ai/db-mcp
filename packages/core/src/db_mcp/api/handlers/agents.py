"""Agent management handlers."""

from __future__ import annotations

from typing import Any

import db_mcp.services.agents as agents_service


async def handle_agents_list(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.list_agents()


async def handle_agents_configure(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.configure_agent(params.get("agentId", ""))


async def handle_agents_remove(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.remove_agent(params.get("agentId", ""))


async def handle_agents_config_snippet(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.get_agent_config_snippet(params.get("agentId", ""))


async def handle_agents_config_write(params: dict[str, Any]) -> dict[str, Any]:
    return agents_service.write_agent_config(
        params.get("agentId", ""), params.get("snippet", "")
    )
