"""Discover command: schema discovery for database connections."""

import sys

import click

from db_mcp.cli.connection import (
    _load_connection_env,
    get_active_connection,
    get_connection_path,
)
from db_mcp.cli.discovery import _run_discovery_with_progress
from db_mcp.cli.utils import console


@click.command()
@click.option("--url", "-u", help="Database connection URL")
@click.option("--output", "-o", help="Output file path (default: stdout)")
@click.option("--connection", "-c", "conn_name", help="Use existing connection by name")
@click.option(
    "--schema",
    "schemas",
    multiple=True,
    help="Limit discovery to one or more schemas (repeatable).",
)
@click.option(
    "--timeout",
    "timeout_s",
    type=int,
    default=300,
    show_default=True,
    help="Abort discovery if it takes longer than this many seconds (best-effort).",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format",
)
def discover(url, output, conn_name, schemas, timeout_s, fmt):
    """Discover database schema (catalogs, schemas, tables, columns).

    Connects to a database and discovers its full schema structure.
    Outputs the result as YAML or JSON.

    Examples:
        db-mcp discover --url postgres://user:pass@host/db
        db-mcp discover --connection mydb --output schema.yaml
        db-mcp discover --url postgres://... --format json
    """
    import json as _json
    from pathlib import Path

    import yaml as _yaml

    from db_mcp.connectors import Connector
    from db_mcp.connectors.sql import SQLConnector, SQLConnectorConfig

    if url and conn_name:
        console.print("[red]Use either --url or --connection, not both.[/red]")
        sys.exit(1)

    if timeout_s is None:
        timeout_s = 300
    if timeout_s < 0:
        console.print("[red]--timeout must be >= 0[/red]")
        sys.exit(1)

    # Resolve connector
    connector: Connector | None = None

    if url:
        # Direct URL: create a SQL connector with per-statement timeout where supported.
        config = SQLConnectorConfig(
            database_url=url,
            capabilities={
                "connect_args": {"options": "-c statement_timeout=10000"},
            },
        )
        connector = SQLConnector(config)
    elif conn_name:
        # Named connection
        conn_path = get_connection_path(conn_name)
        if not conn_path.exists():
            console.print(f"[red]Connection '{conn_name}' not found.[/red]")
            sys.exit(1)
        from db_mcp.connectors import get_connector

        connector = get_connector(str(conn_path))
    else:
        # Try active connection
        active = get_active_connection()
        conn_path = get_connection_path(active)
        if not conn_path.exists():
            console.print(
                "[red]No connection specified. Use --url or --connection, "
                "or set up a connection with 'db-mcp init'.[/red]"
            )
            sys.exit(1)

        # We have a connection directory, but it may not have a DB URL configured.
        # Avoid surfacing an internal message like "No database URL configured".
        conn_env = _load_connection_env(active)
        database_url = conn_env.get("DATABASE_URL")
        if not database_url:
            console.print(
                "[red]No connection specified. Use --url or --connection, "
                "or set up a connection with 'db-mcp init'.[/red]"
            )
            sys.exit(1)

        from db_mcp.connectors import get_connector

        try:
            connector = get_connector(str(conn_path))
        except Exception:
            console.print(
                "[red]No connection specified. Use --url or --connection, "
                "or set up a connection with 'db-mcp init'.[/red]"
            )
            sys.exit(1)

    # Run discovery
    result = _run_discovery_with_progress(
        connector,
        conn_name=conn_name or "cli-discover",
        timeout_s=timeout_s,
        schemas=list(schemas) if schemas else None,
    )
    if result is None:
        sys.exit(1)

    schema_dict = result["schema"].model_dump(mode="json", by_alias=True)

    # Serialize
    if fmt == "json":
        output_str = _json.dumps(schema_dict, indent=2, ensure_ascii=False)
    else:
        output_str = _yaml.dump(
            schema_dict, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    # Output
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(output_str)
        from rich.console import Console as _Console

        _Console(stderr=True).print(f"[green]Schema written to {output}[/green]")
    else:
        click.echo(output_str)


def register_commands(main_group: click.Group) -> None:
    """Register the discover command with the main group."""
    main_group.add_command(discover)
