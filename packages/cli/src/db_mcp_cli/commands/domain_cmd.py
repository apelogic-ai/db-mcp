"""CLI commands for domain model inspection."""

import click

from db_mcp_cli.connection import resolve_connection as _resolve_connection
from db_mcp_cli.utils import console


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
