"""CLI commands for knowledge gap management."""

from pathlib import Path

import click
from rich.table import Table

from db_mcp_cli.connection import get_active_connection, get_connection_path
from db_mcp_cli.utils import console


def _resolve_connection(connection: str | None) -> tuple[str, Path]:

    name = connection or get_active_connection()
    path = get_connection_path(name)
    if not path.exists():
        raise click.ClickException(f"Connection '{name}' not found")
    return name, path


@click.group("gaps")
def gaps_group():
    """Manage knowledge gaps detected in the vault."""
    pass


@gaps_group.command("list")
@click.option("-c", "--connection", default=None, help="Connection name")
def gaps_list(connection: str | None):
    """List open knowledge gaps."""
    from db_mcp_knowledge.gaps.store import load_gaps

    name, _ = _resolve_connection(connection)
    gaps = load_gaps(name)
    open_gaps = [g for g in gaps.gaps if g.status.value == "open"]
    if not open_gaps:
        console.print("[dim]No open knowledge gaps.[/dim]")
        return

    table = Table(title=f"Knowledge Gaps ({name})")
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Description")
    table.add_column("Source")
    for g in open_gaps:
        table.add_row(g.id, g.gap_type, g.description, g.source.value)
    console.print(table)


@gaps_group.command("dismiss")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--reason", default=None, help="Reason for dismissal")
@click.argument("gap_id")
def gaps_dismiss(connection: str | None, gap_id: str, reason: str | None):
    """Dismiss a knowledge gap."""
    from db_mcp_knowledge.gaps.store import dismiss_gap

    name, _ = _resolve_connection(connection)
    result = dismiss_gap(name, gap_id, reason=reason)
    if result.get("dismissed"):
        console.print(f"[green]Gap '{gap_id}' dismissed ({result['count']} total).[/green]")
    else:
        raise click.ClickException(result.get("error", "Gap not found"))


def register_commands(cli):
    """Register gaps commands."""
    cli.add_command(gaps_group)
