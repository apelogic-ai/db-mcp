"""Traces commands: traces subgroup (on, off, status)."""

import click

from db_mcp.cli.connection import get_active_connection, get_connection_path
from db_mcp.cli.utils import console, load_config, save_config


@click.group()
def traces():
    """Manage trace capture for diagnostics and learning.

    Traces capture MCP server activity (tool calls, queries, etc.)
    and store them as JSONL files for agent analysis.

    Examples:
        db-mcp traces on       # Enable trace capture
        db-mcp traces off      # Disable trace capture
        db-mcp traces status   # Show trace settings and files
    """
    pass


@traces.command("on")
def traces_on():
    """Enable trace capture.

    When enabled, the MCP server will write traces to:
        ~/.dbmcp/connections/{name}/traces/{user_id}/YYYY-MM-DD.jsonl

    A unique user_id is generated on first enable to identify
    your traces when sharing with the team.
    """
    from db_mcp.traces import generate_user_id, get_user_id_from_config

    config = load_config()

    # Check if already enabled
    if config.get("traces_enabled"):
        console.print("[dim]Traces already enabled.[/dim]")
        user_id = config.get("user_id", "unknown")
        console.print(f"[dim]User ID: {user_id}[/dim]")
        return

    # Generate user_id if not exists
    user_id = get_user_id_from_config()
    if not user_id:
        user_id = generate_user_id()
        config["user_id"] = user_id
        console.print(f"[green]✓ Generated user ID: {user_id}[/green]")

    # Enable traces
    config["traces_enabled"] = True
    save_config(config)

    console.print("[green]✓ Traces enabled[/green]")
    console.print(f"[dim]User ID: {user_id}[/dim]")
    console.print("[dim]Restart Claude Desktop to start capturing traces.[/dim]")


@traces.command("off")
def traces_off():
    """Disable trace capture.

    Existing trace files are preserved.
    """
    config = load_config()

    if not config.get("traces_enabled"):
        console.print("[dim]Traces already disabled.[/dim]")
        return

    config["traces_enabled"] = False
    save_config(config)

    console.print("[green]✓ Traces disabled[/green]")
    console.print("[dim]Restart Claude Desktop to stop capturing traces.[/dim]")


@traces.command("status")
def traces_status():
    """Show trace capture status and file locations."""
    config = load_config()

    enabled = config.get("traces_enabled", False)
    user_id = config.get("user_id")

    console.print("[bold]Trace Capture[/bold]")
    console.print(f"  Status:  {'[green]enabled[/green]' if enabled else '[dim]disabled[/dim]'}")

    if user_id:
        console.print(f"  User ID: [cyan]{user_id}[/cyan]")
    else:
        console.print("  User ID: [dim]not set (will generate on enable)[/dim]")

    # Show trace files for active connection
    active = get_active_connection()
    if active and user_id:
        conn_path = get_connection_path(active)
        traces_dir = conn_path / "traces" / user_id

        console.print(f"\n[bold]Traces for '{active}'[/bold]")
        console.print(f"  Directory: {traces_dir}")

        if traces_dir.exists():
            trace_files = sorted(traces_dir.glob("*.jsonl"), reverse=True)
            if trace_files:
                console.print(f"  Files: {len(trace_files)}")
                # Show recent files
                for tf in trace_files[:5]:
                    size = tf.stat().st_size
                    size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
                    console.print(f"    [dim]{tf.name}[/dim] ({size_str})")
                if len(trace_files) > 5:
                    console.print(f"    [dim]... and {len(trace_files) - 5} more[/dim]")
            else:
                console.print("  [dim]No trace files yet.[/dim]")
        else:
            console.print("  [dim]No traces directory yet.[/dim]")

    if not enabled:
        console.print("\n[dim]Run 'db-mcp traces on' to enable capture.[/dim]")


def register_commands(main_group: click.Group) -> None:
    """Register the traces group with the main group."""
    main_group.add_command(traces)
