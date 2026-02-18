"""Agent and migration commands: agents, migrate."""

import click

from db_mcp.agents import AGENTS, detect_installed_agents
from db_mcp.cli.agent_config import _configure_agents
from db_mcp.cli.connection import (
    get_active_connection,
    get_connection_path,
    list_connections,
)
from db_mcp.cli.utils import console, load_claude_desktop_config


@click.command()
@click.option("--list", "-l", "list_only", is_flag=True, help="List detected agents")
@click.option("--all", "-a", is_flag=True, help="Configure all detected agents")
@click.option(
    "--agent",
    "-A",
    multiple=True,
    help="Configure specific agent(s) by ID (e.g., claude-desktop, claude-code, codex)",
)
def agents(list_only: bool, all: bool, agent: tuple[str, ...]):
    """Configure MCP agents for db-mcp.

    Detects installed MCP-compatible agents (Claude Desktop, Claude Code, OpenAI Codex)
    and configures them to use db-mcp as an MCP server.

    Examples:
        db-mcp agents                    # Interactive selection
        db-mcp agents --list             # Show detected agents
        db-mcp agents --all              # Configure all detected
        db-mcp agents -A claude-desktop  # Configure only Claude Desktop
        db-mcp agents -A claude-code -A codex  # Configure multiple specific agents
    """
    # List mode
    if list_only:
        installed = detect_installed_agents()
        if not installed:
            console.print("[yellow]No MCP agents detected on this system.[/yellow]")
            console.print("\n[dim]Supported agents:[/dim]")
            for agent_id, agent_info in AGENTS.items():
                console.print(f"  • {agent_info.name} ({agent_id})")
            return

        console.print("[bold]Detected MCP agents:[/bold]")
        for agent_id in installed:
            agent_info = AGENTS[agent_id]
            console.print(f"  ✓ {agent_info.name}")
            console.print(f"    [dim]Config: {agent_info.config_path}[/dim]")

        console.print("\n[dim]Run 'db-mcp agents' to configure them.[/dim]")
        return

    # Determine which agents to configure
    if agent:
        # Specific agents requested
        agent_ids = list(agent)
        # Validate agent IDs
        invalid = [a for a in agent_ids if a not in AGENTS]
        if invalid:
            console.print(f"[red]Unknown agent(s): {', '.join(invalid)}[/red]")
            console.print(f"\n[dim]Valid agent IDs: {', '.join(AGENTS.keys())}[/dim]")
            return
        _configure_agents(agent_ids)
    elif all:
        # Configure all detected
        installed = detect_installed_agents()
        if not installed:
            console.print("[yellow]No MCP agents detected on this system.[/yellow]")
            return
        _configure_agents(installed)
    else:
        # Interactive mode
        _configure_agents()


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed migration info")
def migrate(verbose: bool):
    """Migrate from legacy dbmeta to db-mcp.

    This command handles two types of migration:

    1. Namespace migration: ~/.dbmeta -> ~/.db-mcp
       Copies all data from the old config directory to the new one.

    2. Structure migration: v1 -> v2 connection format
       Converts old provider-based structure to connection-based.

    The original data is preserved as a backup.

    Examples:
        db-mcp migrate           # Run full migration
        db-mcp migrate -v        # Run with verbose output
    """
    from rich.panel import Panel

    from db_mcp.vault.migrate import (
        detect_legacy_namespace,
        is_namespace_migrated,
        migrate_namespace,
        migrate_to_connection_structure,
        write_storage_version,
    )

    console.print(
        Panel.fit(
            "[bold]db-mcp Migration[/bold]\n\nMigrating from legacy dbmeta to db-mcp format.",
            border_style="blue",
        )
    )

    # Step 1: Namespace migration (~/.dbmeta -> ~/.db-mcp)
    console.print("\n[bold]Step 1: Namespace Migration[/bold]")
    legacy_path = detect_legacy_namespace()

    if legacy_path:
        if is_namespace_migrated():
            console.print(f"  [dim]Already migrated from {legacy_path}[/dim]")
        else:
            console.print(f"  [cyan]Found legacy directory: {legacy_path}[/cyan]")
            console.print("  [cyan]Migrating to ~/.db-mcp...[/cyan]")

            stats = migrate_namespace()
            if stats.get("skipped"):
                console.print(f"  [yellow]Skipped: {stats.get('reason')}[/yellow]")
            else:
                console.print("  [green]✓ Namespace migration complete[/green]")
                if verbose:
                    console.print(f"    Connections: {stats.get('connections', 0)}")
                    console.print(f"    Providers: {stats.get('providers', 0)}")
                    console.print(f"    Config: {'yes' if stats.get('config') else 'no'}")
                    console.print(f"    Vault: {'yes' if stats.get('vault') else 'no'}")
                console.print(f"  [dim]Original preserved at: {legacy_path}[/dim]")
    else:
        console.print("  [dim]No legacy ~/.dbmeta directory found[/dim]")

    # Step 2: Structure migration (v1 -> v2 for each connection)
    console.print("\n[bold]Step 2: Connection Structure Migration[/bold]")
    connections = list_connections()

    if not connections:
        console.print("  [dim]No connections to migrate[/dim]")
    else:
        for conn in connections:
            conn_path = get_connection_path(conn)
            has_version = (conn_path / ".version").exists()

            if has_version:
                console.print(f"  [dim]{conn}: already at v2[/dim]")
            else:
                console.print(f"  [cyan]{conn}: migrating...[/cyan]")
                try:
                    stats = migrate_to_connection_structure(conn)
                    if stats.get("skipped"):
                        reason = stats.get("reason")
                        if reason == "no_legacy_data":
                            # No legacy data but connection exists - just mark as v2
                            write_storage_version(conn_path)
                            console.print("    [green]✓ Marked as v2[/green]")
                        else:
                            console.print(f"    [dim]Skipped: {reason}[/dim]")
                    else:
                        console.print("    [green]✓ Migrated to v2[/green]")
                        if verbose:
                            console.print(f"      Schema: {stats.get('schema_descriptions')}")
                            console.print(f"      Domain: {stats.get('domain_model')}")
                            console.print(f"      Examples: {stats.get('query_examples', 0)}")
                except Exception as e:
                    console.print(f"    [red]Error: {e}[/red]")

    # Step 3: Configure Claude Desktop
    console.print("\n[bold]Step 3: Claude Desktop Configuration[/bold]")
    try:
        claude_config, claude_config_path = load_claude_desktop_config()
        mcp_servers = claude_config.get("mcpServers", {})

        if "db-mcp" in mcp_servers:
            console.print("  [dim]Already configured[/dim]")
        else:
            # Get active connection for configuration
            active = get_active_connection()
            if active:
                _configure_agents()
            else:
                console.print(
                    "  [yellow]No active connection - run 'db-mcp init' to configure[/yellow]"
                )
    except Exception as e:
        console.print(f"  [yellow]Could not configure: {e}[/yellow]")

    console.print("\n[green]✓ Migration complete[/green]")
    console.print("\n[dim]Restart Claude Desktop to apply changes.[/dim]")


def register_commands(main_group: click.Group) -> None:
    """Register agents and migrate commands with the main group."""
    main_group.add_command(agents)
    main_group.add_command(migrate)
