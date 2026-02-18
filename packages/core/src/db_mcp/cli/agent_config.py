"""Agent configuration helpers for the db-mcp CLI.

Handles interactive agent selection, Claude Desktop configuration,
and extracting existing database URLs from Claude configs.
"""

from rich.prompt import Confirm

from db_mcp.agents import (
    AGENTS,
    configure_multiple_agents,
    detect_installed_agents,
)
from db_mcp.cli.utils import console, get_db_mcp_binary_path


def extract_database_url_from_claude_config(claude_config: dict) -> str | None:
    """Extract DATABASE_URL from existing Claude Desktop MCP server configs."""
    mcp_servers = claude_config.get("mcpServers", {})

    # Check db-mcp entry first
    if "db-mcp" in mcp_servers:
        env = mcp_servers["db-mcp"].get("env", {})
        if "DATABASE_URL" in env:
            return env["DATABASE_URL"]

    # Check legacy db-mcp entry
    if "db-mcp" in mcp_servers:
        env = mcp_servers["db-mcp"].get("env", {})
        if "DATABASE_URL" in env:
            return env["DATABASE_URL"]

    return None


def _configure_agents_interactive(preselect_installed: bool = True) -> list[str]:
    """Interactive agent selection.

    Args:
        preselect_installed: If True, pre-select detected agents

    Returns:
        List of agent IDs to configure
    """
    # Detect installed agents
    installed = detect_installed_agents()

    if not installed:
        console.print("[yellow]No MCP agents detected on this system.[/yellow]")
        console.print("[dim]Skipping agent configuration.[/dim]")
        return []

    # Show detected agents
    console.print("\n[bold]Detected MCP-compatible agents:[/bold]")
    for i, agent_id in enumerate(installed, 1):
        agent = AGENTS[agent_id]
        console.print(f"  [{i}] {agent.name}")

    # Prompt for selection
    console.print("\n[dim]Configure db-mcp for which agents?[/dim]")
    console.print("[1] All detected agents")
    console.print("[2] Select specific agents")
    console.print("[3] Skip agent configuration")

    from rich.prompt import Prompt

    choice = Prompt.ask("Choice", choices=["1", "2", "3"], default="1")

    if choice == "3":
        return []
    elif choice == "1":
        return installed
    else:
        # Individual selection
        selected = []
        for agent_id in installed:
            agent = AGENTS[agent_id]
            if Confirm.ask(f"Configure {agent.name}?", default=preselect_installed):
                selected.append(agent_id)
        return selected


def _configure_agents(agent_ids: list[str] | None = None) -> None:
    """Configure MCP agents for db-mcp.

    Args:
        agent_ids: List of agent IDs to configure. If None, uses interactive selection.
    """
    if agent_ids is None:
        agent_ids = _configure_agents_interactive()

    if not agent_ids:
        console.print("[dim]No agents selected for configuration.[/dim]")
        return

    # Get binary path
    binary_path = get_db_mcp_binary_path()

    # Configure each agent
    results = configure_multiple_agents(agent_ids, binary_path)

    # Show summary
    success_count = sum(1 for success in results.values() if success)
    console.print(f"\n[green]✓ Configured {success_count}/{len(agent_ids)} agent(s)[/green]")


def _configure_claude_desktop(name: str):
    """Configure Claude Desktop for db-mcp (legacy wrapper).

    Deprecated: Use _configure_agents instead.
    """
    binary_path = get_db_mcp_binary_path()
    from db_mcp.agents import configure_agent_for_dbmcp

    configure_agent_for_dbmcp("claude-desktop", binary_path)
