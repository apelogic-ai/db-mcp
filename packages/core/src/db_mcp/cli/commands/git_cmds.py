"""Git-related CLI commands: sync, pull, git-init."""

import sys

import click
from rich.panel import Panel
from rich.prompt import Prompt

from db_mcp.cli.commands.core import _get_git_remote_url
from db_mcp.cli.connection import (
    connection_exists,
    get_active_connection,
    get_connection_path,
)
from db_mcp.cli.git_ops import (
    GIT_INSTALL_URL,
    git_init,
    git_pull,
    git_sync,
    is_git_repo,
)
from db_mcp.cli.utils import console


@click.command()
@click.argument("name", default=None, required=False)
def sync(name: str | None):
    """Sync connection changes with git remote.

    NAME is the connection name (default: active connection).

    This command:
    1. Commits any local changes (auto-generated commit message)
    2. Pulls remote changes (with rebase)
    3. Pushes to remote

    Use this to share your semantic layer updates with your team.
    """
    # Default to active connection
    if not name:
        name = get_active_connection()

    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    # Check if it's a git repo
    if not is_git_repo(conn_path):
        console.print(f"[yellow]Connection '{name}' is not a git repository.[/yellow]")
        console.print("[dim]Run 'db-mcp init' and enable git sync, or initialize manually:[/dim]")
        console.print(f"  cd {conn_path}")
        console.print("  git init")
        console.print("  git remote add origin <your-repo-url>")
        return

    console.print(f"[bold]Syncing connection: {name}[/bold]")
    git_sync(conn_path)


@click.command()
@click.argument("name", default=None, required=False)
def pull(name: str | None):
    """Pull connection updates from git remote.

    NAME is the connection name (default: active connection).

    This pulls the latest changes from the remote repository,
    allowing you to get updates from your team.
    """
    # Default to active connection
    if not name:
        name = get_active_connection()

    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    # Check if it's a git repo
    if not is_git_repo(conn_path):
        console.print(f"[yellow]Connection '{name}' is not a git repository.[/yellow]")
        console.print("[dim]This connection was not set up with git sync.[/dim]")
        return

    console.print(f"[bold]Pulling updates for: {name}[/bold]")
    if not git_pull(conn_path):
        sys.exit(1)


@click.command("git-init")
@click.argument("name", default=None, required=False)
@click.argument("remote_url", default=None, required=False)
def git_init_cmd(name: str | None, remote_url: str | None):
    """Enable git sync for an existing connection.

    NAME is the connection name (default: active connection).
    REMOTE_URL is the optional git remote URL.

    This initializes a git repository in the connection directory
    and optionally sets up a remote for syncing.

    Examples:
        db-mcp git-init
        db-mcp git-init mydb
        db-mcp git-init mydb git@github.com:org/db-mcp-mydb.git
    """
    # Check git is installed
    from db_mcp.cli.git_ops import is_git_installed

    if not is_git_installed():
        console.print(
            Panel.fit(
                "[bold red]Git Not Found[/bold red]\n\n"
                f"Install from: [cyan]{GIT_INSTALL_URL}[/cyan]",
                border_style="red",
            )
        )
        return

    # Default to active connection
    if not name:
        name = get_active_connection()

    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    # Check if already a git repo
    if is_git_repo(conn_path):
        console.print(f"[yellow]Connection '{name}' is already a git repository.[/yellow]")
        # Show remote info if any
        remote_url = _get_git_remote_url(conn_path)
        if remote_url:
            console.print(f"[dim]Remote 'origin': {remote_url}[/dim]")
        return

    # Prompt for remote if not provided
    if not remote_url:
        console.print(f"\n[bold]Enable git sync for: {name}[/bold]")
        console.print(
            "[dim]Enter a git remote URL to sync with (or leave empty to add later).[/dim]"
        )
        console.print("[dim]Example: git@github.com:yourorg/db-mcp-mydb.git[/dim]")
        remote_url = Prompt.ask("Git remote URL", default="")

    # Initialize git
    if git_init(conn_path, remote_url if remote_url else None):
        console.print(f"[green]✓ Git initialized for '{name}'[/green]")
        if remote_url:
            console.print(f"[dim]Remote 'origin' set to {remote_url}[/dim]")
        console.print("[dim]Use 'dbmcp sync' to push changes to the team.[/dim]")


def register_commands(main_group: click.Group) -> None:
    """Register git commands with the main group."""
    main_group.add_command(sync)
    main_group.add_command(pull)
    main_group.add_command(git_init_cmd)
