"""CLI commands for business rule management."""

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


@click.group("rules")
def rules_group():
    """Manage business rules for SQL generation."""
    pass


@rules_group.command("list")
@click.option("-c", "--connection", default=None, help="Connection name")
def rules_list(connection: str | None):
    """List all business rules."""
    from db_mcp_knowledge.training.store import load_instructions

    name, _ = _resolve_connection(connection)
    instructions = load_instructions(name)
    if not instructions.rules:
        console.print("[dim]No rules defined.[/dim]")
        return

    table = Table(title=f"Business Rules ({name})")
    table.add_column("#", justify="right")
    table.add_column("Rule")
    for i, rule in enumerate(instructions.rules, 1):
        table.add_row(str(i), rule)
    console.print(table)


@rules_group.command("add")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--rule", required=True, help="Business rule text")
def rules_add(connection: str | None, rule: str):
    """Add a business rule."""
    from db_mcp_knowledge.training.store import add_rule

    name, _ = _resolve_connection(connection)
    result = add_rule(name, rule)
    if result.get("added"):
        console.print(
            f"[green]Rule added ({result['total_rules']} total).[/green]"
        )
    else:
        raise click.ClickException(result.get("error", "Failed to add rule"))


def register_commands(cli):
    """Register rules commands."""
    cli.add_command(rules_group)
