"""CLI commands for domain model inspection."""

from pathlib import Path

import click

from db_mcp_cli.connection import get_active_connection, get_connection_path
from db_mcp_cli.utils import console


def _resolve_connection(connection: str | None) -> tuple[str, Path]:

    name = connection or get_active_connection()
    path = get_connection_path(name)
    if not path.exists():
        raise click.ClickException(f"Connection '{name}' not found")
    return name, path


@click.group("domain")
def domain_group():
    """View the semantic domain model."""
    pass


@domain_group.command("show")
@click.option("-c", "--connection", default=None, help="Connection name")
def domain_show(connection: str | None):
    """Show the domain model markdown."""
    _, path = _resolve_connection(connection)
    model_path = path / "domain" / "model.md"
    if not model_path.exists():
        console.print("[dim]No domain model found.[/dim]")
        return
    console.print(model_path.read_text(encoding="utf-8"))


def register_commands(cli):
    """Register domain commands."""
    cli.add_command(domain_group)
