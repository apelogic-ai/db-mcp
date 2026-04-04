"""CLI commands for API connector queries."""

import json

import click

from db_mcp_cli.connection import get_active_connection, get_connection_path
from db_mcp_cli.utils import console


def _resolve_api_connector(connection: str | None):
    """Resolve an API connector by connection name."""
    from db_mcp_data.connectors import APIConnector

    name = connection or get_active_connection()
    path = get_connection_path(name)
    if not path.exists():
        raise click.ClickException(f"Connection '{name}' not found")

    from db_mcp.tools.utils import resolve_connection

    connector, _, _ = resolve_connection(name, require_type="api")
    if not isinstance(connector, APIConnector):
        raise click.ClickException(f"Connection '{name}' is not an API connector.")
    return connector


def _parse_param(raw: str) -> tuple[str, object]:
    """Parse 'key=value' param, attempting JSON decode for the value."""
    if "=" not in raw:
        raise click.BadParameter(f"Expected key=value, got: {raw}")
    key, value = raw.split("=", 1)
    try:
        return key, json.loads(value)
    except json.JSONDecodeError:
        return key, value


def _render_rows(data: list[dict], export_fmt: str | None):
    """Render list[dict] rows as table, JSON, or CSV."""
    if not data:
        console.print("[dim]No data returned.[/dim]")
        return

    columns = list(data[0].keys())

    if export_fmt == "json":
        click.echo(json.dumps(data, indent=2, default=str))
    elif export_fmt == "csv":
        import csv
        import sys

        writer = csv.writer(sys.stdout)
        writer.writerow(columns)
        for row in data:
            writer.writerow([row.get(c) for c in columns])
    else:
        from rich.table import Table

        table = Table()
        for col in columns:
            table.add_column(str(col))
        for row in data:
            table.add_row(*[str(row.get(c, "")) for c in columns])
        console.print(table)


@click.group("api")
def api_group():
    """Query REST and RPC API connectors."""


@api_group.command("query")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--export", "export_fmt", default=None, type=click.Choice(["csv", "json"]))
@click.option("-p", "--param", "raw_params", multiple=True, help="key=value (repeatable)")
@click.option("--max-pages", default=1, help="Max pages to fetch")
@click.option("--id", "record_id", default=None, help="Record ID for detail endpoints")
@click.argument("endpoint")
def api_query(connection, export_fmt, raw_params, max_pages, record_id, endpoint):
    """Query an API endpoint."""
    connector = _resolve_api_connector(connection)

    params = {}
    for raw in raw_params:
        key, value = _parse_param(raw)
        params[key] = value

    result = connector.query_endpoint(
        endpoint, params or None, max_pages, id=record_id
    )

    if result.get("error"):
        raise click.ClickException(result["error"])

    data = result.get("data", [])
    # Normalize non-list responses (response_mode=raw returns a dict or scalar)
    if isinstance(data, dict):
        data = [data]
    elif not isinstance(data, list):
        data = [{"value": data}]

    _render_rows(data, export_fmt)


@api_group.command("describe")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.argument("endpoint", required=False, default=None)
def api_describe(connection, endpoint):
    """List available endpoints, or describe a specific endpoint's parameters."""
    connector = _resolve_api_connector(connection)

    if endpoint is None:
        # List all endpoints
        from rich.table import Table

        table = Table(title="Endpoints")
        table.add_column("Name")
        table.add_column("Method")
        table.add_column("Path")
        table.add_column("Mode")
        for ep in connector.api_config.endpoints:
            mode = ep.body_mode if ep.body_mode != "query" else ""
            table.add_row(ep.name, ep.method, ep.path, mode)
        console.print(table)
    else:
        # Describe a specific endpoint
        for ep in connector.api_config.endpoints:
            if ep.name == endpoint:
                console.print(f"[bold]{ep.name}[/bold]  {ep.method} {ep.path}")
                if getattr(ep, "body_mode", "query") != "query":
                    console.print(f"  body_mode: {ep.body_mode}")
                if getattr(ep, "rpc_method", ""):
                    console.print(f"  rpc_method: {ep.rpc_method}")
                if getattr(ep, "response_mode", "data") != "data":
                    console.print(f"  response_mode: {ep.response_mode}")
                if ep.query_params:
                    console.print("  [bold]Parameters:[/bold]")
                    for qp in ep.query_params:
                        req = " (required)" if qp.required else ""
                        console.print(f"    {qp.name}: {qp.type}{req}")
                        if qp.description:
                            console.print(f"      {qp.description}")
                return
        raise click.ClickException(f"Unknown endpoint: {endpoint}")


@api_group.command("sql")
@click.option("-c", "--connection", default=None, help="Connection name")
@click.option("--export", "export_fmt", default=None, type=click.Choice(["csv", "json"]))
@click.argument("sql")
def api_sql(connection, export_fmt, sql):
    """Execute SQL on a SQL-like API connector (Dune, etc.)."""
    from db_mcp_data.connectors import get_connector_capabilities  # noqa: F811

    connector = _resolve_api_connector(connection)

    caps = get_connector_capabilities(connector)
    if not caps.get("supports_sql"):
        raise click.ClickException(
            "This API connector does not support SQL execution. Use `api query` instead."
        )

    try:
        rows = connector.execute_sql(sql)
    except Exception as exc:
        raise click.ClickException(str(exc))

    if not isinstance(rows, list):
        rows = [rows] if rows else []

    _render_rows(rows, export_fmt)


def register_commands(cli):
    """Register api commands."""
    cli.add_command(api_group)
