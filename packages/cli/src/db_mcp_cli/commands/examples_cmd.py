"""CLI commands for query example management."""

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


@click.group("examples")
def examples_group():
    """Manage query examples for few-shot learning."""
    pass


@examples_group.command("list")
@click.option("-c", "--connection", default=None, help="Connection name")
def examples_list(connection: str | None):
    """List all query examples."""
    from db_mcp_knowledge.training.store import load_examples

    name, _ = _resolve_connection(connection)
    examples = load_examples(name)
    if not examples.examples:
        console.print("[dim]No examples defined.[/dim]")
        return

    table = Table(title=f"Examples ({name})")
    table.add_column("ID")
    table.add_column("Intent")
    table.add_column("SQL", max_width=60)
    table.add_column("Tags")
    for ex in examples.examples:
        table.add_row(ex.id, ex.natural_language, ex.sql[:60], ", ".join(ex.tags))
    console.print(table)


@examples_group.command("search")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--grep", "query", required=True, help="Search term")
def examples_search(connection: str | None, query: str):
    """Search examples by intent or SQL content."""
    from db_mcp_knowledge.training.store import load_examples

    name, _ = _resolve_connection(connection)
    examples = load_examples(name)
    q = query.lower()
    matches = [
        ex
        for ex in examples.examples
        if q in ex.natural_language.lower() or q in ex.sql.lower()
    ]
    if not matches:
        console.print("[dim]No matching examples.[/dim]")
        return

    table = Table(title=f"Search results for '{query}'")
    table.add_column("ID")
    table.add_column("Intent")
    table.add_column("SQL", max_width=60)
    for ex in matches:
        table.add_row(ex.id, ex.natural_language, ex.sql[:60])
    console.print(table)


@examples_group.command("add")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--intent", required=True, help="Natural language query")
@click.option("--sql", required=True, help="Correct SQL")
@click.option("--tags", default=None, help="Comma-separated tags")
def examples_add(connection: str | None, intent: str, sql: str, tags: str | None):
    """Add a new query example."""
    from db_mcp_knowledge.training.store import add_example

    name, _ = _resolve_connection(connection)
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    result = add_example(name, intent, sql, tags=tag_list)
    if result.get("added"):
        console.print(
            f"[green]Example '{result['example_id']}' added "
            f"({result['total_examples']} total).[/green]"
        )
    else:
        raise click.ClickException(result.get("error", "Failed to add example"))


def register_commands(cli):
    """Register examples commands."""
    cli.add_command(examples_group)
