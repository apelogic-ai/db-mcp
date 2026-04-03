"""CLI commands for schema introspection and vault descriptions."""

import json

import click
import yaml
from rich.table import Table

from db_mcp_cli.connection import resolve_connection as _resolve_connection
from db_mcp_cli.utils import console


@click.group("schema")
def schema_group():
    """Inspect database schema and vault descriptions."""
    pass


@schema_group.command("show")
@click.option("-c", "--connection", default=None, help="Connection name")
def schema_show(connection: str | None):
    """Show stored schema descriptions from the vault."""
    from db_mcp_knowledge.onboarding.schema_store import load_schema_descriptions

    name, path = _resolve_connection(connection)
    descs = load_schema_descriptions(name, connection_path=path)
    if descs is None or not descs.tables:
        console.print("[dim]No schema descriptions stored.[/dim]")
        return

    for td in descs.tables:
        console.print(f"\n[bold]{td.full_name or td.name}[/bold]")
        if td.description:
            console.print(f"  {td.description}")
        for col in td.columns:
            desc = f" - {col.description}" if col.description else ""
            console.print(f"  [dim]{col.name}[/dim]{desc}")


@schema_group.command("export")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--format", "fmt", type=click.Choice(["yaml", "json"]), default="yaml")
def schema_export(connection: str | None, fmt: str):
    """Export schema descriptions to stdout."""
    from db_mcp_knowledge.onboarding.schema_store import load_schema_descriptions

    name, path = _resolve_connection(connection)
    descs = load_schema_descriptions(name, connection_path=path)
    if descs is None:
        raise click.ClickException("No schema descriptions found")

    data = descs.model_dump(mode="json")
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))


@schema_group.command("catalogs")
@click.option("-c", "--connection", default=None, help="Connection name")
def schema_catalogs(connection: str | None):
    """List database catalogs."""
    from db_mcp.services.schema import list_catalogs

    _, path = _resolve_connection(connection)
    result = list_catalogs(path)
    catalogs = result.get("catalogs", [])
    if not catalogs:
        console.print("[dim]No catalogs found.[/dim]")
        return
    for c in catalogs:
        console.print(c)


@schema_group.command("schemas")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--catalog", default=None, help="Filter by catalog")
def schema_schemas(connection: str | None, catalog: str | None):
    """List database schemas."""
    from db_mcp.services.schema import list_schemas

    _, path = _resolve_connection(connection)
    result = list_schemas(path, catalog=catalog)
    schemas = result.get("schemas", [])
    if not schemas:
        console.print("[dim]No schemas found.[/dim]")
        return
    for s in schemas:
        console.print(s)


@schema_group.command("tables")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--schema", "schema_name", default=None, help="Filter by schema")
@click.option("--catalog", default=None, help="Filter by catalog")
def schema_tables(connection: str | None, schema_name: str | None, catalog: str | None):
    """List database tables."""
    from db_mcp.services.schema import list_tables

    _, path = _resolve_connection(connection)
    result = list_tables(path, schema=schema_name, catalog=catalog)
    tables = result.get("tables", [])
    if not tables:
        console.print("[dim]No tables found.[/dim]")
        return

    table_view = Table(title="Tables")
    table_view.add_column("Name")
    for t in tables:
        if isinstance(t, dict):
            table_view.add_row(t.get("name", str(t)))
        else:
            table_view.add_row(str(t))
    console.print(table_view)


@schema_group.command("describe")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.argument("table_name")
def schema_describe(connection: str | None, table_name: str):
    """Describe a table's columns."""
    from db_mcp.services.schema import describe_table

    _, path = _resolve_connection(connection)
    result = describe_table(table_name, path)
    if result.get("error"):
        raise click.ClickException(result["error"])

    columns = result.get("columns", [])
    table_view = Table(title=f"Table: {table_name}")
    table_view.add_column("Column")
    table_view.add_column("Type")
    table_view.add_column("Nullable")
    for col in columns:
        if isinstance(col, dict):
            table_view.add_row(
                col.get("name", ""),
                str(col.get("type", "")),
                str(col.get("nullable", "")),
            )
    console.print(table_view)


@schema_group.command("sample")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--limit", default=5, help="Number of rows")
@click.argument("table_name")
def schema_sample(connection: str | None, table_name: str, limit: int):
    """Sample rows from a table."""
    from db_mcp.services.schema import sample_table

    _, path = _resolve_connection(connection)
    result = sample_table(table_name, path, limit=limit)
    if result.get("error"):
        raise click.ClickException(result["error"])

    rows = result.get("rows", [])
    columns = result.get("columns", [])
    if not rows:
        console.print("[dim]No rows returned.[/dim]")
        return

    table_view = Table(title=f"Sample: {table_name} (limit={limit})")
    for col in columns:
        table_view.add_column(str(col))
    for row in rows:
        table_view.add_row(*[str(v) for v in row])
    console.print(table_view)


def register_commands(cli):
    """Register schema commands."""
    cli.add_command(schema_group)
