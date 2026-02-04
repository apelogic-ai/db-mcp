"""MCP Agent Registry - Detection and configuration for MCP-compatible agents."""

import json
import os
import platform
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rich.console import Console

console = Console()


@dataclass
class MCPAgent:
    """Represents an MCP-compatible agent/client."""

    name: str
    config_path: Path
    config_format: str  # "json" or "toml"
    config_key: str  # e.g., "mcpServers" or "mcp_servers"
    detect_fn: Callable[[], bool] | None = None  # Optional custom detection


def get_claude_desktop_config_path() -> Path:
    """Get Claude Desktop config path for current OS."""
    system = platform.system()
    if system == "Darwin":  # macOS
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    else:  # Linux
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_claude_code_config_path() -> Path:
    """Get Claude Code config path (user-level)."""
    return Path.home() / ".claude.json"


def get_codex_config_path() -> Path:
    """Get OpenAI Codex config path."""
    return Path.home() / ".codex" / "config.toml"


def detect_claude_desktop() -> bool:
    """Detect if Claude Desktop is installed."""
    config_path = get_claude_desktop_config_path()

    # Check if config exists
    if config_path.exists():
        return True

    # Check if app is installed
    system = platform.system()
    if system == "Darwin":
        app_path = Path("/Applications/Claude.app")
        return app_path.exists()
    elif system == "Windows":
        # Check common install locations
        program_files = os.environ.get("PROGRAMFILES", "C:\\Program Files")
        app_path = Path(program_files) / "Claude" / "Claude.exe"
        return app_path.exists()
    # Linux - rely on config path
    return False


def detect_claude_code() -> bool:
    """Detect if Claude Code is installed."""
    config_path = get_claude_code_config_path()

    # Check if config exists
    if config_path.exists():
        return True

    # Check if claude CLI is available
    import shutil

    return shutil.which("claude") is not None


def detect_codex() -> bool:
    """Detect if OpenAI Codex is installed."""
    config_path = get_codex_config_path()

    # Check if config directory exists
    if config_path.parent.exists():
        return True

    # Check if codex CLI is available
    import shutil

    return shutil.which("codex") is not None


# Agent registry
AGENTS: dict[str, MCPAgent] = {
    "claude-desktop": MCPAgent(
        name="Claude Desktop",
        config_path=get_claude_desktop_config_path(),
        config_format="json",
        config_key="mcpServers",
        detect_fn=detect_claude_desktop,
    ),
    "claude-code": MCPAgent(
        name="Claude Code",
        config_path=get_claude_code_config_path(),
        config_format="json",
        config_key="mcpServers",
        detect_fn=detect_claude_code,
    ),
    "codex": MCPAgent(
        name="OpenAI Codex",
        config_path=get_codex_config_path(),
        config_format="toml",
        config_key="mcp_servers",
        detect_fn=detect_codex,
    ),
}


def detect_installed_agents() -> list[str]:
    """Detect which agents are installed on the system.

    Returns list of agent IDs (keys in AGENTS dict).
    """
    installed = []
    for agent_id, agent in AGENTS.items():
        if agent.detect_fn and agent.detect_fn():
            installed.append(agent_id)
    return installed


def load_agent_config(agent: MCPAgent) -> dict:
    """Load existing config for an agent.

    Returns empty dict if config doesn't exist or is invalid.
    """
    if not agent.config_path.exists():
        return {}

    try:
        if agent.config_format == "json":
            with open(agent.config_path) as f:
                return json.load(f)
        elif agent.config_format == "toml":
            with open(agent.config_path, "rb") as f:
                return tomllib.load(f)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load {agent.name} config: {e}[/yellow]")
        return {}

    return {}


def _write_toml_value(value, indent=0):
    """Helper to write TOML value."""
    if isinstance(value, dict):
        # Don't write inline tables for mcp_servers entries
        return None
    elif isinstance(value, list):
        return json.dumps(value)
    elif isinstance(value, str):
        return json.dumps(value)
    elif isinstance(value, (int, float, bool)):
        return str(value).lower() if isinstance(value, bool) else str(value)
    return json.dumps(value)


def _dict_to_toml(data: dict, prefix: str = "") -> str:
    """Convert dict to TOML format string.

    Simple TOML writer for our specific use case.
    """
    lines = []

    # First pass: write non-dict values
    for key, value in data.items():
        if not isinstance(value, dict):
            toml_value = _write_toml_value(value)
            if toml_value is not None:
                lines.append(f"{key} = {toml_value}")

    # Second pass: write tables
    for key, value in data.items():
        if isinstance(value, dict):
            section = f"{prefix}.{key}" if prefix else key
            lines.append(f"\n[{section}]")
            # Write table contents
            for subkey, subvalue in value.items():
                if isinstance(subvalue, dict):
                    # Nested table
                    lines.append(f"\n[{section}.{subkey}]")
                    for k, v in subvalue.items():
                        toml_value = _write_toml_value(v)
                        if toml_value is not None:
                            lines.append(f"{k} = {toml_value}")
                else:
                    toml_value = _write_toml_value(subvalue)
                    if toml_value is not None:
                        lines.append(f"{subkey} = {toml_value}")

    return "\n".join(lines)


def save_agent_config(agent: MCPAgent, config: dict) -> None:
    """Save config for an agent.

    Creates parent directories if needed.
    """
    agent.config_path.parent.mkdir(parents=True, exist_ok=True)

    if agent.config_format == "json":
        with open(agent.config_path, "w") as f:
            json.dump(config, f, indent=2)
    elif agent.config_format == "toml":
        with open(agent.config_path, "w") as f:
            f.write(_dict_to_toml(config))


def configure_agent_for_dbmcp(agent_id: str, binary_path: str) -> bool:
    """Configure a specific agent to use db-mcp.

    Args:
        agent_id: Agent ID from AGENTS dict
        binary_path: Path to db-mcp binary

    Returns:
        True if successful, False otherwise
    """
    if agent_id not in AGENTS:
        console.print(f"[red]Unknown agent: {agent_id}[/red]")
        return False

    agent = AGENTS[agent_id]

    try:
        # Load existing config
        config = load_agent_config(agent)

        # Add/update db-mcp entry
        if agent.config_format == "json":
            # JSON format (Claude Desktop, Claude Code)
            if agent.config_key not in config:
                config[agent.config_key] = {}

            config[agent.config_key]["db-mcp"] = {
                "command": binary_path,
                "args": ["start"],
            }

            # Remove legacy dbmeta entry if exists
            if "dbmeta" in config[agent.config_key]:
                del config[agent.config_key]["dbmeta"]

        elif agent.config_format == "toml":
            # TOML format (Codex)
            if agent.config_key not in config:
                config[agent.config_key] = {}

            config[agent.config_key]["db-mcp"] = {
                "command": binary_path,
                "args": ["start"],
            }

            # Remove legacy dbmeta entry if exists
            if "dbmeta" in config[agent.config_key]:
                del config[agent.config_key]["dbmeta"]

        # Save config
        save_agent_config(agent, config)
        console.print(f"[green]✓ {agent.name} configured at {agent.config_path}[/green]")
        return True

    except Exception as e:
        console.print(f"[red]Failed to configure {agent.name}: {e}[/red]")
        return False


def configure_multiple_agents(agent_ids: list[str], binary_path: str) -> dict[str, bool]:
    """Configure multiple agents.

    Args:
        agent_ids: List of agent IDs to configure
        binary_path: Path to db-mcp binary

    Returns:
        Dict mapping agent_id -> success (bool)
    """
    results = {}
    for agent_id in agent_ids:
        results[agent_id] = configure_agent_for_dbmcp(agent_id, binary_path)
    return results
