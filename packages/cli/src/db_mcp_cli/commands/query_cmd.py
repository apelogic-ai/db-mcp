"""CLI commands for query execution and validation."""

import asyncio
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


@click.group("query")
def query_group():
    """Run and validate SQL queries."""
    pass


@query_group.command("run")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--confirmed", is_flag=True, help="Skip safety confirmation")
@click.option("--export", "export_fmt", default=None, type=click.Choice(["csv", "json"]))
@click.argument("sql")
def query_run(connection: str | None, sql: str, confirmed: bool, export_fmt: str | None):
    """Execute a SQL query."""
    from db_mcp.services.query import run_sql

    name, path = _resolve_connection(connection)
    result = asyncio.run(
        run_sql(connection=name, sql=sql, confirmed=confirmed, connection_path=path)
    )
    if result.get("error"):
        raise click.ClickException(result["error"])

    rows = result.get("rows", [])
    columns = result.get("columns", [])

    if export_fmt == "csv":
        import csv
        import sys

        writer = csv.writer(sys.stdout)
        if columns:
            writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    elif export_fmt == "json":
        import json

        records = [dict(zip(columns, row)) for row in rows] if columns else rows
        click.echo(json.dumps(records, indent=2, default=str))
    else:
        from rich.table import Table

        if not rows:
            console.print("[dim]Query returned no rows.[/dim]")
            return

        table = Table()
        for col in columns:
            table.add_column(str(col))
        for row in rows:
            table.add_row(*[str(v) for v in row])
        console.print(table)


@query_group.command("validate")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.argument("sql")
def query_validate(connection: str | None, sql: str):
    """Validate SQL without executing."""
    from db_mcp.services.query import validate_sql

    name, path = _resolve_connection(connection)
    result = asyncio.run(validate_sql(sql=sql, connection=name, connection_path=path))
    if result.get("error"):
        raise click.ClickException(result["error"])

    console.print("[green]SQL is valid.[/green]")
    if result.get("query_id"):
        console.print(f"Query ID: {result['query_id']}")


@click.command("ask")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.argument("intent")
def ask_command(connection: str | None, intent: str):
    """Answer a natural language question about your data."""
    from db_mcp.orchestrator.engine import answer_intent

    name, _ = _resolve_connection(connection)
    result = asyncio.run(answer_intent(intent=intent, connection=name))
    if result.get("error"):
        raise click.ClickException(result["error"])

    if result.get("sql"):
        console.print(f"[bold]SQL:[/bold] {result['sql']}")
    rows = result.get("rows", [])
    columns = result.get("columns", [])
    if rows:
        from rich.table import Table

        table = Table()
        for col in columns:
            table.add_column(str(col))
        for row in rows:
            table.add_row(*[str(v) for v in row])
        console.print(table)
    elif result.get("answer"):
        console.print(result["answer"])


def register_commands(cli):
    """Register query and ask commands."""
    cli.add_command(query_group)
    cli.add_command(ask_command)
