"""Agent configuration helpers for the db-mcp CLI.

Handles interactive agent selection, Claude Desktop configuration,
and extracting existing database URLs from Claude configs.
"""

from db_mcp.agents import (
    AGENTS,
    configure_multiple_agents,
    detect_installed_agents,
)
from rich.prompt import Confirm

from db_mcp_cli.utils import console, get_db_mcp_binary_path


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


def _print_configure_later_hint() -> None:
    """Show how to configure MCP clients after init."""
    console.print("\n[dim]You can configure MCP clients later with:[/dim]")
    console.print("  [cyan]db-mcp agents[/cyan]  [dim](interactive CLI setup)[/dim]")
    console.print("  [cyan]db-mcp ui[/cyan]      [dim](open setup in the web UI)[/dim]")


def _configure_agents_interactive(preselect_installed: bool = True) -> list[str]:
    """Interactive agent selection.

    Args:
        preselect_installed: If True, pre-select detected agents

    Returns:
        List of agent IDs to configure
    """
    # Detect installed agents
    installed = detect_installed_agents()

    # Show detected agents as simple list
    console.print("\n[bold]Detected MCP agents:[/bold]")
    if installed:
        for agent_id in installed:
            agent = AGENTS[agent_id]
            console.print(f"  [green]●[/green] {agent.name}")
    else:
        console.print("  [dim]none[/dim]")

    not_installed = [aid for aid in AGENTS if aid not in installed]
    if not_installed:
        console.print("\n[dim]Not detected:[/dim]")
        for agent_id in not_installed:
            agent = AGENTS[agent_id]
            console.print(f"  [dim]○ {agent.name}[/dim]")

    if not installed:
        console.print(
            "\n[yellow]No MCP agents detected.[/yellow]"
        )
        _print_configure_later_hint()
        return []

    # Simple action prompt
    from rich.prompt import Prompt

    console.print("")
    if len(installed) == 1:
        agent = AGENTS[installed[0]]
        if Confirm.ask(f"Configure {agent.name}?", default=True):
            return installed
        _print_configure_later_hint()
        return []

    console.print("[bold]Configure db-mcp for:[/bold]")
    for i, agent_id in enumerate(installed, 1):
        console.print(f"  [{i}] {AGENTS[agent_id].name}")
    console.print(f"  [a] All detected ({len(installed)})")
    console.print("  [s] Skip")

    valid = [str(i) for i in range(1, len(installed) + 1)] + ["a", "s"]
    choice = Prompt.ask("Choice", choices=valid, default="a")

    if choice == "s":
        _print_configure_later_hint()
        return []
    elif choice == "a":
        return installed
    else:
        idx = int(choice) - 1
        return [installed[idx]]


def _configure_agents(agent_ids: list[str] | None = None) -> None:
    """Configure MCP agents for db-mcp.

    Args:
        agent_ids: List of agent IDs to configure. If None, uses interactive selection.
    """
    if agent_ids is None:
        agent_ids = _configure_agents_interactive()

    if not agent_ids:
        console.print("[dim]No agents selected for configuration.[/dim]")
        _print_configure_later_hint()
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
