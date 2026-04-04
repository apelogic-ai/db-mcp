"""CLI commands for query execution and validation."""

import asyncio

import click

from db_mcp_cli.connection import resolve_connection as _resolve_connection
from db_mcp_cli.utils import console


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

    data = result.get("data", result.get("rows", []))
    columns = result.get("columns", [])

    # run_sql returns data as list[dict]; normalize to list[list] for uniform rendering
    if data and isinstance(data[0], dict):
        if not columns:
            columns = list(data[0].keys())
        rows = [list(row.values()) for row in data]
    else:
        rows = data

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


_SQL_KEYWORD_RE = __import__("re").compile(
    r"^\s*(select|with|show|describe|explain)\b", __import__("re").IGNORECASE
)


@click.command("ask")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.argument("intent")
def ask_command(connection: str | None, intent: str):
    """Answer a natural language question about your data."""
    if _SQL_KEYWORD_RE.match(intent):
        raise click.UsageError(
            "Intent looks like SQL. Use `db-mcp query run` to execute SQL directly."
        )

    from db_mcp.orchestrator.engine import answer_intent

    name, _ = _resolve_connection(connection)
    result = asyncio.run(answer_intent(intent=intent, connection=name))
    if result.get("error"):
        error_msg = result["error"]
        warnings = result.get("warnings", [])
        if warnings:
            error_msg += "\n  " + "\n  ".join(warnings)
        raise click.ClickException(error_msg)

    if result.get("answer"):
        console.print(result["answer"])

    records = result.get("records", [])
    if records:
        from rich.table import Table

        columns = list(records[0].keys())
        table = Table()
        for col in columns:
            table.add_column(str(col))
        for record in records:
            table.add_row(*[str(v) for v in record.values()])
        console.print(table)


def register_commands(cli):
    """Register query and ask commands."""
    cli.add_command(query_group)
    cli.add_command(ask_command)
