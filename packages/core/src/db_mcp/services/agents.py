"""Agent configuration services.

Provides service functions for listing MCP agents, configuring/removing
db-mcp from their configs, reading config snippets, and writing edited
snippets back.  The BICP agent delegates to these functions instead of
embedding the logic inline.
"""

from __future__ import annotations

import json as _json
import tomllib

# ---------------------------------------------------------------------------
# Internal helpers — lazy imports, easy to mock in tests.
# ---------------------------------------------------------------------------


def _get_agents() -> dict:
    from db_mcp.agents import AGENTS

    return AGENTS


def _load_agent_config(agent) -> dict:
    from db_mcp.agents import load_agent_config

    return load_agent_config(agent)


def _save_agent_config(agent, config: dict) -> None:
    from db_mcp.agents import save_agent_config

    save_agent_config(agent, config)


def _configure_agent_for_dbmcp(agent_id: str, binary_path: str) -> bool:
    from db_mcp.agents import configure_agent_for_dbmcp

    return configure_agent_for_dbmcp(agent_id, binary_path)


def _remove_dbmcp_from_agent(agent_id: str) -> bool:
    from db_mcp.agents import remove_dbmcp_from_agent

    return remove_dbmcp_from_agent(agent_id)


def _get_binary_path() -> str:
    from db_mcp.agents import get_db_mcp_binary_path

    return get_db_mcp_binary_path()


def _dict_to_toml(data: dict) -> str:
    from db_mcp.agents import _dict_to_toml

    return _dict_to_toml(data)


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------


def list_agents() -> dict:
    """Return all configured MCP agents with their db-mcp status.

    Returns:
        ``{"agents": [...]}`` where each item has keys:
        ``id``, ``name``, ``installed``, ``configPath``, ``configExists``,
        ``configFormat``, ``dbmcpConfigured``, ``binaryPath``.
    """
    agents = _get_agents()
    agents_list = []

    for agent_id, agent in agents.items():
        installed = bool(agent.detect_fn and agent.detect_fn())
        config_exists = agent.config_path.exists()

        dbmcp_configured = False
        binary_path = None
        if config_exists:
            config = _load_agent_config(agent)
            mcp_section = config.get(agent.config_key, {})
            if "db-mcp" in mcp_section:
                dbmcp_configured = True
                binary_path = mcp_section["db-mcp"].get("command")

        agents_list.append(
            {
                "id": agent_id,
                "name": agent.name,
                "installed": installed,
                "configPath": str(agent.config_path),
                "configExists": config_exists,
                "configFormat": agent.config_format,
                "dbmcpConfigured": dbmcp_configured,
                "binaryPath": binary_path,
            }
        )

    return {"agents": agents_list}


def configure_agent(agent_id: str) -> dict:
    """Add db-mcp to an agent's MCP config.

    Args:
        agent_id: Key in the AGENTS registry.

    Returns:
        ``{"success": True, "configPath": str}`` on success, or
        ``{"success": False, "error": str}`` on failure.
    """
    agents = _get_agents()
    if agent_id not in agents:
        return {"success": False, "error": f"Unknown agent: {agent_id}"}

    try:
        binary_path = _get_binary_path()
        result = _configure_agent_for_dbmcp(agent_id, binary_path)
        if result:
            return {
                "success": True,
                "configPath": str(agents[agent_id].config_path),
            }
        return {"success": False, "error": "Configuration failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def remove_agent(agent_id: str) -> dict:
    """Remove db-mcp from an agent's MCP config.

    Args:
        agent_id: Key in the AGENTS registry.

    Returns:
        ``{"success": True}`` on success, or ``{"success": False, "error": str}``.
    """
    agents = _get_agents()
    if agent_id not in agents:
        return {"success": False, "error": f"Unknown agent: {agent_id}"}

    try:
        result = _remove_dbmcp_from_agent(agent_id)
        if result:
            return {"success": True}
        return {"success": False, "error": "Removal failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_agent_config_snippet(agent_id: str) -> dict:
    """Return the MCP servers config snippet for an agent.

    The snippet is serialised in the agent's native format (JSON or TOML).

    Args:
        agent_id: Key in the AGENTS registry.

    Returns:
        ``{"success": True, "snippet": str, "format": str, "configKey": str}``
        on success, or ``{"success": False, "error": str}`` on failure.
        An empty ``snippet`` means the agent has no MCP servers configured.
    """
    agents = _get_agents()
    if agent_id not in agents:
        return {"success": False, "error": f"Unknown agent: {agent_id}"}

    agent = agents[agent_id]
    config = _load_agent_config(agent)
    mcp_section = config.get(agent.config_key, {})

    if not mcp_section:
        return {
            "success": True,
            "snippet": "",
            "format": agent.config_format,
            "configKey": agent.config_key,
        }

    if agent.config_format == "json":
        snippet = _json.dumps(mcp_section, indent=2)
    else:
        snippet = _dict_to_toml(mcp_section)

    return {
        "success": True,
        "snippet": snippet,
        "format": agent.config_format,
        "configKey": agent.config_key,
    }


def write_agent_config(agent_id: str, snippet: str) -> dict:
    """Write an edited MCP servers config snippet back to an agent's config file.

    Validates the snippet (JSON/TOML parse + type check) before writing.
    Only replaces the MCP servers section; other config keys are preserved.

    Args:
        agent_id: Key in the AGENTS registry.
        snippet: Serialised MCP servers section in the agent's native format.

    Returns:
        ``{"success": True}`` on success, or ``{"success": False, "error": str}``.
    """
    agents = _get_agents()
    if agent_id not in agents:
        return {"success": False, "error": f"Unknown agent: {agent_id}"}

    if not snippet or not snippet.strip():
        return {"success": False, "error": "Snippet cannot be empty"}

    agent = agents[agent_id]

    if agent.config_format == "json":
        try:
            parsed = _json.loads(snippet)
        except _json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {e}"}
        if not isinstance(parsed, dict):
            return {"success": False, "error": "Snippet must be a JSON object"}
    else:
        try:
            parsed = tomllib.loads(snippet)
        except tomllib.TOMLDecodeError as e:
            return {"success": False, "error": f"Invalid TOML: {e}"}

    config = _load_agent_config(agent)
    config[agent.config_key] = parsed
    _save_agent_config(agent, config)
    return {"success": True}
