"""CLI commands for metrics management."""

import click
from rich.table import Table

from db_mcp_cli.connection import resolve_connection as _resolve_connection
from db_mcp_cli.utils import console


@click.group("metrics")
def metrics_group():
    """Manage business metric definitions."""
    pass


@metrics_group.command("list")
@click.option("-c", "--connection", default=None, help="Connection name")
def metrics_list(connection: str | None):
    """List all metrics in the catalog."""
    from db_mcp_knowledge.metrics.store import load_metrics

    name, path = _resolve_connection(connection)
    catalog = load_metrics(name, connection_path=path)
    if not catalog.metrics:
        console.print("[dim]No metrics defined.[/dim]")
        return

    table = Table(title=f"Metrics ({name})")
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Status")
    table.add_column("Tags")
    for m in catalog.metrics:
        table.add_row(m.name, m.description, m.status, ", ".join(m.tags))
    console.print(table)


@metrics_group.command("add")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--name", required=True, help="Metric identifier")
@click.option("--description", required=True, help="What the metric measures")
@click.option("--sql", required=True, help="SQL expression")
@click.option("--tags", default=None, help="Comma-separated tags")
def metrics_add(connection: str | None, name: str, description: str, sql: str, tags: str | None):
    """Add a metric to the catalog."""
    from db_mcp_knowledge.metrics.store import add_metric

    conn_name, path = _resolve_connection(connection)
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    result = add_metric(
        conn_name, name, description, sql, connection_path=path, tags=tag_list
    )
    if result.get("added"):
        console.print(f"[green]Metric '{name}' added.[/green]")
    else:
        raise click.ClickException(result.get("error", "Failed to add metric"))


@metrics_group.command("remove")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.argument("name")
def metrics_remove(connection: str | None, name: str):
    """Remove a metric from the catalog."""
    from db_mcp_knowledge.metrics.store import delete_metric

    conn_name, path = _resolve_connection(connection)
    result = delete_metric(conn_name, name, connection_path=path)
    if result.get("deleted"):
        console.print(f"[green]Metric '{name}' removed.[/green]")
    else:
        raise click.ClickException(result.get("error", "Metric not found"))


@metrics_group.command("discover")
@click.option("-c", "--connection", default=None, help="Connection name")
def metrics_discover(connection: str | None):
    """Discover metric candidates from vault material."""
    import asyncio

    from db_mcp_knowledge.metrics.mining import mine_metrics_and_dimensions

    _, path = _resolve_connection(connection)
    result = asyncio.run(mine_metrics_and_dimensions(path))
    mc = result.get("metrics_added", 0)
    dc = result.get("dimensions_added", 0)
    console.print(f"Discovered {mc} metric candidate(s) and {dc} dimension candidate(s).")


def register_commands(cli):
    """Register metrics commands."""
    cli.add_command(metrics_group)
