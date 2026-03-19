"""Insider-agent CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from db_mcp.cli.connection import get_active_connection, get_connection_path
from db_mcp.cli.utils import console
from db_mcp.insider.services import InsiderService


def _resolve_connection(connection: str | None) -> str:
    return connection or get_active_connection()


@click.group()
def insider():
    """Operate the background insider agent."""
    pass


@insider.command("status")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def insider_status(connection: str | None) -> None:
    """Show insider-agent configuration and queue status."""
    conn_name = _resolve_connection(connection)
    service = InsiderService(connection_resolver=get_connection_path)
    status = service.get_status(conn_name)
    console.print("[bold]Insider Agent[/bold]")
    console.print(f"  Connection: [cyan]{status['connection']}[/cyan]")
    enabled_text = "[green]yes[/green]" if status["enabled"] else "[dim]no[/dim]"
    console.print(f"  Enabled:    {enabled_text}")
    console.print(f"  Provider:   {status['provider']}")
    console.print(f"  Model:      {status['model']}")
    if status.get("base_url"):
        console.print(f"  Base URL:   {status['base_url']}")
    console.print(f"  DB:         {status['db_path']}")
    console.print(f"  Events:     {status['pending_events']} pending")
    console.print(f"  Reviews:    {status['pending_reviews']} pending")


@insider.command("events")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option("--limit", default=50, show_default=True, type=int)
def insider_events(connection: str | None, limit: int) -> None:
    """List recent insider events."""
    conn_name = _resolve_connection(connection)
    rows = InsiderService(connection_resolver=get_connection_path).list_events(
        conn_name,
        limit=limit,
    )
    if not rows:
        console.print("[dim]No insider events yet.[/dim]")
        return
    for row in rows:
        console.print(
            f"[cyan]{row['event_id']}[/cyan]  "
            f"{row['event_type']}  {row['status']}  {row['created_at']}"
        )


@insider.command("runs")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option("--limit", default=50, show_default=True, type=int)
def insider_runs(connection: str | None, limit: int) -> None:
    """List recent insider runs."""
    conn_name = _resolve_connection(connection)
    rows = InsiderService(connection_resolver=get_connection_path).list_runs(
        conn_name,
        limit=limit,
    )
    if not rows:
        console.print("[dim]No insider runs yet.[/dim]")
        return
    for row in rows:
        console.print(
            f"[cyan]{row['run_id']}[/cyan]  {row['status']}  "
            f"{row['provider']}:{row['model']}  {row['started_at']}"
        )


@insider.group("review")
def insider_review() -> None:
    """Inspect and decide staged insider changes."""
    pass


@insider_review.command("list")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def insider_review_list(connection: str | None) -> None:
    """List pending review items."""
    conn_name = _resolve_connection(connection)
    rows = InsiderService(connection_resolver=get_connection_path).list_reviews(
        conn_name,
        status="pending",
    )
    if not rows:
        console.print("[dim]No pending insider reviews.[/dim]")
        return
    for row in rows:
        console.print(
            f"[cyan]{row['review_id']}[/cyan]  "
            f"{row['review_kind']}  {row['status']}  {row['created_at']}"
        )


@insider_review.command("show")
@click.argument("review_id")
def insider_review_show(review_id: str) -> None:
    """Show one review manifest and rationale."""
    service = InsiderService(connection_resolver=get_connection_path)
    row = service.get_review(review_id)
    if row is None:
        raise click.ClickException(f"Review item {review_id!r} was not found.")
    console.print(json.dumps(row, indent=2))
    console.print(Path(row["manifest_path"]).read_text())
    console.print(Path(row["reasoning_path"]).read_text())


@insider_review.command("approve")
@click.argument("review_id")
def insider_review_approve(review_id: str) -> None:
    """Approve and apply one staged review item."""
    service = InsiderService(connection_resolver=get_connection_path)
    try:
        service.approve_review(review_id)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"[green]Approved insider review {review_id}.[/green]")


@insider_review.command("reject")
@click.argument("review_id")
@click.option("--reason", default=None, help="Optional rejection reason")
def insider_review_reject(review_id: str, reason: str | None) -> None:
    """Reject one staged review item."""
    service = InsiderService(connection_resolver=get_connection_path)
    try:
        service.reject_review(review_id, reason)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"[yellow]Rejected insider review {review_id}.[/yellow]")


@insider.group("trigger")
def insider_trigger() -> None:
    """Queue insider-agent work manually."""
    pass


@insider_trigger.command("bootstrap")
@click.argument("connection")
@click.option("--force", is_flag=True, help="Create a new bootstrap event even if one exists")
def insider_trigger_bootstrap(connection: str, force: bool) -> None:
    """Queue a new-connection bootstrap observation."""
    service = InsiderService(connection_resolver=get_connection_path)
    status = service.get_status(connection)
    if not status["enabled"]:
        console.print("[yellow]Insider agent is disabled in config.[/yellow]")
        return
    event_id = service.queue_new_connection(
        connection,
        payload={"connection": connection, "source": "manual_trigger"},
        force=force,
    )
    if event_id is None:
        console.print(
            "[dim]A matching insider bootstrap event is already pending or completed.[/dim]"
        )
        return
    console.print(f"[green]Queued insider bootstrap event {event_id}.[/green]")


@insider.command("budget")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def insider_budget(connection: str | None) -> None:
    """Show insider-agent token and cost usage."""
    conn_name = _resolve_connection(connection)
    summary = InsiderService(connection_resolver=get_connection_path).get_budget_summary(
        conn_name
    )
    console.print("[bold]Insider Budget[/bold]")
    console.print(f"  Connection: {conn_name}")
    console.print(f"  Runs:       {summary['runs']}")
    console.print(f"  Input:      {summary['input_tokens']}")
    console.print(f"  Output:     {summary['output_tokens']}")
    console.print(f"  Cost:       ${summary['estimated_cost_usd']:.4f}")


def register_commands(main_group: click.Group) -> None:
    """Register the insider group with the main CLI group."""
    main_group.add_command(insider)
