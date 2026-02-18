"""Click command group and all CLI commands for db-mcp.

Commands stay thin — they delegate to the other cli/ modules for
business logic.
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

import click
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from db_mcp.agents import AGENTS, detect_installed_agents
from db_mcp.cli.agent_config import _configure_agents, extract_database_url_from_claude_config
from db_mcp.cli.connection import (
    _get_connection_env_path,
    _load_connection_env,
    _prompt_and_save_database_url,
    _save_connection_env,
    connection_exists,
    get_active_connection,
    get_connection_path,
    list_connections,
    set_active_connection,
)
from db_mcp.cli.discovery import _run_discovery_with_progress
from db_mcp.cli.git_ops import (
    GIT_INSTALL_URL,
    git_init,
    git_pull,
    git_sync,
    is_git_repo,
    is_git_url,
)
from db_mcp.cli.init_flow import _attach_repo, _auto_register_collaborator, _init_brownfield, _init_greenfield
from db_mcp.cli.utils import (
    CONFIG_DIR,
    CONFIG_FILE,
    CONNECTIONS_DIR,
    LEGACY_PROVIDERS_DIR,
    LEGACY_VAULT_DIR,
    _get_cli_version,
    _handle_sigint,
    console,
    is_claude_desktop_installed,
    launch_claude_desktop,
    load_claude_desktop_config,
    load_config,
    save_config,
)


@click.group()
@click.version_option(version=_get_cli_version())
def main():
    """db-mcp - Database metadata MCP server for Claude Desktop."""
    pass


@main.command()
@click.argument("name", default="default", required=False)
@click.argument("source", default=None, required=False)
def init(name: str, source: str | None):
    """Interactive setup wizard - configure database and Claude Desktop.

    NAME is the connection name (default: "default").

    SOURCE is an optional git URL to clone an existing connection config.
    This enables "brownfield" setup where you join an existing team's
    semantic layer instead of starting from scratch.

    Examples:
        db-mcp init                           # New connection "default"
        db-mcp init mydb                      # New connection "mydb"
        db-mcp init mydb git@github.com:org/db-mcp-mydb.git  # Clone from git
    """
    # Check if Claude Desktop is installed
    if not is_claude_desktop_installed():
        console.print(
            Panel.fit(
                "[bold red]Claude Desktop Not Found[/bold red]\n\n"
                "db-mcp requires Claude Desktop to be installed.\n\n"
                "Download from: [cyan]https://claude.ai/download[/cyan]",
                border_style="red",
            )
        )
        return

    # Determine if this is brownfield (git clone) or greenfield (new setup)
    is_brownfield = source and is_git_url(source)

    if is_brownfield:
        _init_brownfield(name, source)
    else:
        _init_greenfield(name)


@main.command()
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def start(connection: str | None):
    """Start the MCP server (stdio mode for Claude Desktop)."""
    if not CONFIG_FILE.exists():
        console.print("[red]No config found. Run 'db-mcp init' first.[/red]")
        sys.exit(1)

    config = load_config()

    # Determine connection name
    conn_name = connection or config.get("active_connection", "default")
    connection_path = get_connection_path(conn_name)

    # Load DATABASE_URL from connection's .env file
    conn_env = _load_connection_env(conn_name)
    database_url = conn_env.get("DATABASE_URL", "")

    # Fallback to global config for backward compatibility
    if not database_url:
        database_url = config.get("database_url", "")

    # Set environment variables
    os.environ["DATABASE_URL"] = database_url
    os.environ["CONNECTION_NAME"] = conn_name
    os.environ["CONNECTION_PATH"] = str(connection_path)
    os.environ["TOOL_MODE"] = config.get("tool_mode", "shell")
    os.environ["LOG_LEVEL"] = config.get("log_level", "INFO")
    os.environ["MCP_TRANSPORT"] = "stdio"  # Always stdio for CLI

    # Legacy env vars for backward compatibility
    os.environ["PROVIDER_ID"] = conn_name
    os.environ["CONNECTIONS_DIR"] = str(CONNECTIONS_DIR)

    # Ensure connection directory exists
    connection_path.mkdir(parents=True, exist_ok=True)

    # Run pending migrations for this connection
    from db_mcp.migrations import run_migrations

    migration_result = run_migrations(conn_name)
    if migration_result.get("applied"):
        # Log to stderr so it doesn't interfere with stdio transport
        print(
            f"Applied {len(migration_result['applied'])} migrations for {conn_name}",
            file=sys.stderr,
        )

    # Patch fakeredis path for PyInstaller bundles
    if getattr(sys, "frozen", False):
        import fakeredis.model._command_info as cmd_info

        bundle_dir = getattr(sys, "_MEIPASS", "")

        def patched_load():
            import json

            if cmd_info._COMMAND_INFO is None:
                json_path = os.path.join(bundle_dir, "fakeredis", "commands.json")
                with open(json_path, encoding="utf8") as f:
                    cmd_info._COMMAND_INFO = cmd_info._encode_obj(json.load(f))

        cmd_info._load_command_info = patched_load

    # Import and run the server
    from db_mcp.server import main as server_main

    server_main()


@main.command()
def config():
    """Open config file in editor."""
    if not CONFIG_FILE.exists():
        console.print("[yellow]No config found. Run 'db-mcp init' first.[/yellow]")
        if Confirm.ask("Run setup now?", default=True):
            ctx = click.get_current_context()
            ctx.invoke(init)
            return
        return

    editor = os.environ.get("EDITOR", "vim")
    console.print(f"[dim]Opening {CONFIG_FILE} in {editor}...[/dim]")

    try:
        subprocess.run([editor, str(CONFIG_FILE)], check=True)
        console.print("[green]✓ Config saved.[/green]")
        console.print("[dim]Restart Claude Desktop to apply changes.[/dim]")
    except FileNotFoundError:
        console.print(f"[red]Editor '{editor}' not found.[/red]")
        console.print("[dim]Set EDITOR environment variable or edit manually:[/dim]")
        console.print(f"  {CONFIG_FILE}")
    except subprocess.CalledProcessError:
        console.print("[yellow]Editor exited with error.[/yellow]")


@main.command("console")
@click.option("--port", "-p", default=8384, help="Port for console UI")
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
def console_cmd(port: int, no_browser: bool):
    """Start local trace console (view MCP server activity).

    Run this in a separate terminal, then use Claude Desktop normally.
    The MCP server will send traces here for visualization.

    Example:
        Terminal 1: db-mcp console
        Terminal 2: Use Claude Desktop (which runs dbmcp start)
    """
    from db_mcp.console import start_console

    console.print(
        Panel.fit(
            f"[bold blue]db-mcp console[/bold blue]\n\n"
            f"Trace viewer at [cyan]http://localhost:{port}[/cyan]\n\n"
            f"[dim]Waiting for traces from MCP server...[/dim]\n"
            f"Press Ctrl+C to stop.",
            border_style="blue",
        )
    )

    start_console(port=port, open_browser=not no_browser, blocking=True)


@main.command()
@click.option("-c", "--connection", default=None, help="Show status for specific connection")
def status(connection: str | None):
    """Show current configuration status."""
    console.print(
        Panel.fit(
            "[bold blue]db-mcp Status[/bold blue]",
            border_style="blue",
        )
    )

    # Config status
    console.print("\n[bold]Configuration[/bold]")
    if CONFIG_FILE.exists():
        config = load_config()
        console.print(f"  Config file: [green]{CONFIG_FILE}[/green]")
        console.print(f"  Tool mode:   {config.get('tool_mode', 'N/A')}")
    else:
        console.print(f"  [yellow]No config found at {CONFIG_FILE}[/yellow]")
        console.print("  [dim]Run 'db-mcp init' to configure.[/dim]")

    # Connections status
    console.print("\n[bold]Connections[/bold]")
    connections = list_connections()
    active = get_active_connection()

    if connection and connection not in connections:
        console.print(f"[red]Connection '{connection}' not found.[/red]")
        sys.exit(1)

    if connections:
        for conn in connections:
            if connection and conn != connection:
                continue
            conn_path = get_connection_path(conn)
            is_active = conn == active
            marker = "[green]●[/green]" if is_active else "[dim]○[/dim]"
            active_label = " [green](active)[/green]" if is_active else ""

            # Check for key files
            has_schema = (conn_path / "schema" / "descriptions.yaml").exists()
            has_domain = (conn_path / "domain" / "model.md").exists()
            has_env = (conn_path / ".env").exists()

            status_parts = []
            if has_schema:
                status_parts.append("schema")
            if has_domain:
                status_parts.append("domain")
            if has_env:
                status_parts.append("credentials")

            status_str = f"[dim]({', '.join(status_parts)})[/dim]" if status_parts else ""
            console.print(f"  {marker} [cyan]{conn}[/cyan]{active_label} {status_str}")

            # Show masked database URL for active connection
            if is_active:
                conn_env = _load_connection_env(conn)
                db_url = conn_env.get("DATABASE_URL", "")
                if db_url:
                    # Mask password
                    if "@" in db_url and ":" in db_url.split("@")[0]:
                        parts = db_url.split("@")
                        prefix = parts[0]
                        scheme_user = prefix.rsplit(":", 1)[0]
                        db_url = f"{scheme_user}:****@{parts[1]}"
                    truncated = f"{db_url[:50]}..." if len(db_url) > 50 else db_url
                    console.print(f"      [dim]Database: {truncated}[/dim]")
                elif not has_env:
                    console.print(
                        "      [yellow]No .env file - run 'db-mcp init' to configure[/yellow]"
                    )
    else:
        console.print("  [dim]No connections configured.[/dim]")
        console.print("  [dim]Run 'db-mcp init' to create one.[/dim]")

    # Claude Desktop status
    console.print("\n[bold]Claude Desktop[/bold]")
    claude_config, claude_config_path = load_claude_desktop_config()
    if claude_config:
        mcp_servers = claude_config.get("mcpServers", {})
        if "db-mcp" in mcp_servers:
            console.print("  [green]✓ db-mcp configured[/green]")
            cmd = mcp_servers["db-mcp"].get("command", "N/A")
            console.print(f"  Command: {cmd}")
        elif "dbmeta" in mcp_servers:
            console.print("  [yellow]⚠ Legacy 'dbmeta' entry found[/yellow]")
            console.print("  [dim]Run 'db-mcp migrate' to upgrade.[/dim]")
        else:
            console.print("  [yellow]db-mcp not configured[/yellow]")
            console.print("  [dim]Run 'db-mcp init' to configure.[/dim]")

        # Show other servers (exclude db-mcp and legacy dbmeta)
        other_servers = [k for k in mcp_servers.keys() if k not in ("db-mcp", "dbmeta")]
        if other_servers:
            console.print(f"  Other servers: {', '.join(other_servers)}")
    else:
        console.print(f"  [dim]No config at {claude_config_path}[/dim]")

    # Legacy structure warning
    from db_mcp.vault.migrate import detect_legacy_namespace, is_namespace_migrated

    legacy_namespace = detect_legacy_namespace()
    needs_namespace_migration = legacy_namespace and not is_namespace_migrated()

    # Check if there are connections without .version (not yet migrated to v2)
    needs_structure_migration = False
    if connections:
        for conn in connections:
            conn_path = get_connection_path(conn)
            if conn_path.exists() and not (conn_path / ".version").exists():
                needs_structure_migration = True
                break

    if needs_namespace_migration or needs_structure_migration:
        console.print("\n[yellow]⚠ Legacy data detected[/yellow]")
        if needs_namespace_migration:
            console.print(f"  Found: {legacy_namespace}")
        console.print("  [bold]Run 'db-mcp migrate' to migrate to new structure.[/bold]")


def _get_git_remote_url(path: Path) -> str | None:
    """Get the git remote origin URL for a repository."""
    from db_mcp.git_utils import git

    try:
        return git.remote_get_url(path, "origin")
    except (NotImplementedError, Exception):
        return None


def _get_git_status_indicator(path: Path) -> str:
    """Get a short git status indicator for a connection."""
    from db_mcp.git_utils import git

    if not git.is_repo(path):
        return "[dim]-[/dim]"

    remote_url = _get_git_remote_url(path)

    # Check for uncommitted changes
    try:
        changes = git.status(path)
        has_changes = bool(changes)
    except Exception:
        has_changes = False

    if remote_url:
        if has_changes:
            return "[yellow]●[/yellow]"  # Has remote, uncommitted changes
        return "[green]✓[/green]"  # Has remote, clean
    else:
        if has_changes:
            return "[yellow]○[/yellow]"  # Local only, uncommitted changes
        return "[dim]○[/dim]"  # Local only, clean


@main.command("list")
def list_cmd():
    """List all configured connections."""
    connections = list_connections()
    active = get_active_connection()

    if not connections:
        console.print("[dim]No connections configured.[/dim]")
        console.print("[dim]Run 'db-mcp init <name>' to create one.[/dim]")
        return

    table = Table(title="Connections", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Active", justify="center")
    table.add_column("Schema", justify="center")
    table.add_column("Domain", justify="center")
    table.add_column("Git", justify="center")
    table.add_column("Remote")

    for conn in connections:
        conn_path = get_connection_path(conn)
        is_active = conn == active

        has_schema = (conn_path / "schema" / "descriptions.yaml").exists()
        has_domain = (conn_path / "domain" / "model.md").exists()

        git_status = _get_git_status_indicator(conn_path)
        git_remote = ""
        if is_git_repo(conn_path):
            remote_url = _get_git_remote_url(conn_path)
            if remote_url:
                # Shorten the URL for display
                if remote_url.startswith("git@github.com:"):
                    git_remote = remote_url.replace("git@github.com:", "gh:")
                elif remote_url.startswith("https://github.com/"):
                    git_remote = remote_url.replace("https://github.com/", "gh:")
                else:
                    git_remote = remote_url
                # Trim .git suffix
                if git_remote.endswith(".git"):
                    git_remote = git_remote[:-4]

        table.add_row(
            conn,
            "[green]●[/green]" if is_active else "",
            "[green]✓[/green]" if has_schema else "[dim]-[/dim]",
            "[green]✓[/green]" if has_domain else "[dim]-[/dim]",
            git_status,
            f"[dim]{git_remote}[/dim]" if git_remote else "",
        )

    console.print(table)

    # Legend
    console.print("\n[dim]Git: ✓ synced, ● uncommitted changes, ○ local only, - not enabled[/dim]")


@main.command()
@click.argument("name")
def use(name: str):
    """Switch to a different connection.

    NAME is the connection name to switch to.
    """
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        console.print("[dim]Run 'db-mcp list' to see available connections.[/dim]")
        sys.exit(1)

    set_active_connection(name)
    console.print(f"[green]✓ Switched to connection '{name}'[/green]")
    console.print("[dim]Restart Claude Desktop to apply changes.[/dim]")


@main.command()
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


@main.command()
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


@main.command("git-init")
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


@main.command()
@click.argument("name", default=None, required=False)
def edit(name: str | None):
    """Edit connection credentials (.env file).

    NAME is the connection name to edit (default: active connection).

    Opens the connection's .env file in your editor (vim by default).
    Set EDITOR environment variable to change the editor.

    The .env file contains:
    - DATABASE_URL - Connection string for the database

    To edit other connection files (schema, domain, etc.),
    open the connection directory directly:
        $EDITOR ~/.dbmcp/connections/<name>/
    """
    # Default to active connection
    if not name:
        name = get_active_connection()

    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        console.print("[dim]Run 'db-mcp list' to see available connections.[/dim]")
        sys.exit(1)

    env_path = _get_connection_env_path(name)

    # Create .env file if it doesn't exist
    if not env_path.exists():
        console.print(f"[yellow]No .env file found for '{name}'.[/yellow]")
        if Confirm.ask("Create one now?", default=True):
            _save_connection_env(name, {"DATABASE_URL": ""})
            console.print(f"[green]✓ Created {env_path}[/green]")
        else:
            return

    editor = os.environ.get("EDITOR", "vim")

    console.print(f"[dim]Opening {env_path} in {editor}...[/dim]")

    try:
        subprocess.run([editor, str(env_path)], check=True)
        console.print("[green]✓ Credentials updated.[/green]")
        console.print("[dim]Restart Claude Desktop to apply changes.[/dim]")
    except FileNotFoundError:
        console.print(f"[red]Editor '{editor}' not found.[/red]")
        console.print("[dim]Set EDITOR environment variable or edit manually:[/dim]")
        console.print(f"  {env_path}")
    except subprocess.CalledProcessError:
        console.print("[yellow]Editor exited with error.[/yellow]")


@main.command()
@click.argument("old_name")
@click.argument("new_name")
def rename(old_name: str, new_name: str):
    """Rename a connection.

    OLD_NAME is the current connection name.
    NEW_NAME is the new name for the connection.

    This renames the connection directory and updates the active
    connection if needed.
    """
    import re

    if not connection_exists(old_name):
        console.print(f"[red]Connection '{old_name}' not found.[/red]")
        console.print("[dim]Run 'db-mcp list' to see available connections.[/dim]")
        sys.exit(1)

    if connection_exists(new_name):
        console.print(f"[red]Connection '{new_name}' already exists.[/red]")
        sys.exit(1)

    # Validate new name (simple alphanumeric + dash/underscore)
    if not re.match(r"^[a-zA-Z0-9_-]+$", new_name):
        console.print("[red]Invalid name. Use only letters, numbers, dashes, underscores.[/red]")
        sys.exit(1)

    old_path = get_connection_path(old_name)
    new_path = get_connection_path(new_name)

    # Rename directory
    old_path.rename(new_path)
    console.print(f"[green]✓ Renamed '{old_name}' to '{new_name}'[/green]")

    # Update active connection if needed
    if get_active_connection() == old_name:
        set_active_connection(new_name)
        console.print(f"[dim]Active connection updated to '{new_name}'.[/dim]")

    console.print("[dim]Restart Claude Desktop to apply changes.[/dim]")


@main.command()
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def remove(name: str, force: bool):
    """Remove a connection.

    NAME is the connection name to remove.
    This deletes all data associated with the connection.
    """
    import shutil

    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    if not force:
        console.print(f"[yellow]Warning: This will delete all data in {conn_path}[/yellow]")
        if not Confirm.ask(f"Remove connection '{name}'?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    shutil.rmtree(conn_path)
    console.print(f"[green]✓ Connection '{name}' removed[/green]")

    # If this was the active connection, suggest switching
    if get_active_connection() == name:
        remaining = list_connections()
        if remaining:
            console.print(f"[yellow]'{name}' was the active connection.[/yellow]")
            console.print(f"[dim]Run 'db-mcp use {remaining[0]}' to switch.[/dim]")


@main.command()
@click.argument("command", type=click.Choice(["status", "migrate"]))
def all(command: str):
    """Run a command for all connections.

    Supported commands:
    - status: Show status for all connections
    - migrate: Run migration for all connections (legacy)
    """
    connections = list_connections()

    if not connections:
        console.print("[dim]No connections found.[/dim]")
        return

    if command == "status":
        for conn in connections:
            console.print(f"\n[bold cyan]Connection: {conn}[/bold cyan]")
            conn_path = get_connection_path(conn)

            # Quick status
            has_schema = (conn_path / "schema" / "descriptions.yaml").exists()
            has_domain = (conn_path / "domain" / "model.md").exists()
            has_state = (conn_path / "state.yaml").exists()
            has_version = (conn_path / ".version").exists()

            console.print(f"  Path:    {conn_path}")
            console.print(f"  Schema:  {'[green]✓[/green]' if has_schema else '[dim]-[/dim]'}")
            console.print(f"  Domain:  {'[green]✓[/green]' if has_domain else '[dim]-[/dim]'}")
            console.print(f"  State:   {'[green]✓[/green]' if has_state else '[dim]-[/dim]'}")
            console.print(
                f"  Version: {'[green]v2[/green]' if has_version else '[yellow]v1[/yellow]'}"
            )

    elif command == "migrate":
        from db_mcp.vault.migrate import migrate_to_connection_structure

        for conn in connections:
            console.print(f"\n[bold]Migrating: {conn}[/bold]")
            try:
                stats = migrate_to_connection_structure(conn)
                if stats.get("skipped"):
                    console.print(f"  [dim]Skipped: {stats.get('reason')}[/dim]")
                else:
                    console.print("  [green]✓ Migrated[/green]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")


# =============================================================================
# Agents command
# =============================================================================


@main.command()
@click.option("--list", "-l", "list_only", is_flag=True, help="List detected agents")
@click.option("--all", "-a", is_flag=True, help="Configure all detected agents")
@click.option(
    "--agent",
    "-A",
    multiple=True,
    help="Configure specific agent(s) by ID (e.g., claude-desktop, claude-code, codex)",
)
def agents(list_only: bool, all: bool, agent: tuple[str, ...]):
    """Configure MCP agents for db-mcp.

    Detects installed MCP-compatible agents (Claude Desktop, Claude Code, OpenAI Codex)
    and configures them to use db-mcp as an MCP server.

    Examples:
        db-mcp agents                    # Interactive selection
        db-mcp agents --list             # Show detected agents
        db-mcp agents --all              # Configure all detected
        db-mcp agents -A claude-desktop  # Configure only Claude Desktop
        db-mcp agents -A claude-code -A codex  # Configure multiple specific agents
    """
    # List mode
    if list_only:
        installed = detect_installed_agents()
        if not installed:
            console.print("[yellow]No MCP agents detected on this system.[/yellow]")
            console.print("\n[dim]Supported agents:[/dim]")
            for agent_id, agent_info in AGENTS.items():
                console.print(f"  • {agent_info.name} ({agent_id})")
            return

        console.print("[bold]Detected MCP agents:[/bold]")
        for agent_id in installed:
            agent_info = AGENTS[agent_id]
            console.print(f"  ✓ {agent_info.name}")
            console.print(f"    [dim]Config: {agent_info.config_path}[/dim]")

        console.print("\n[dim]Run 'db-mcp agents' to configure them.[/dim]")
        return

    # Determine which agents to configure
    if agent:
        # Specific agents requested
        agent_ids = list(agent)
        # Validate agent IDs
        invalid = [a for a in agent_ids if a not in AGENTS]
        if invalid:
            console.print(f"[red]Unknown agent(s): {', '.join(invalid)}[/red]")
            console.print(f"\n[dim]Valid agent IDs: {', '.join(AGENTS.keys())}[/dim]")
            return
        _configure_agents(agent_ids)
    elif all:
        # Configure all detected
        installed = detect_installed_agents()
        if not installed:
            console.print("[yellow]No MCP agents detected on this system.[/yellow]")
            return
        _configure_agents(installed)
    else:
        # Interactive mode
        _configure_agents()


# =============================================================================
# Migration command
# =============================================================================


@main.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed migration info")
def migrate(verbose: bool):
    """Migrate from legacy dbmeta to db-mcp.

    This command handles two types of migration:

    1. Namespace migration: ~/.dbmeta -> ~/.db-mcp
       Copies all data from the old config directory to the new one.

    2. Structure migration: v1 -> v2 connection format
       Converts old provider-based structure to connection-based.

    The original data is preserved as a backup.

    Examples:
        db-mcp migrate           # Run full migration
        db-mcp migrate -v        # Run with verbose output
    """
    from db_mcp.vault.migrate import (
        detect_legacy_namespace,
        is_namespace_migrated,
        migrate_namespace,
        migrate_to_connection_structure,
        write_storage_version,
    )

    console.print(
        Panel.fit(
            "[bold]db-mcp Migration[/bold]\n\nMigrating from legacy dbmeta to db-mcp format.",
            border_style="blue",
        )
    )

    # Step 1: Namespace migration (~/.dbmeta -> ~/.db-mcp)
    console.print("\n[bold]Step 1: Namespace Migration[/bold]")
    legacy_path = detect_legacy_namespace()

    if legacy_path:
        if is_namespace_migrated():
            console.print(f"  [dim]Already migrated from {legacy_path}[/dim]")
        else:
            console.print(f"  [cyan]Found legacy directory: {legacy_path}[/cyan]")
            console.print("  [cyan]Migrating to ~/.db-mcp...[/cyan]")

            stats = migrate_namespace()
            if stats.get("skipped"):
                console.print(f"  [yellow]Skipped: {stats.get('reason')}[/yellow]")
            else:
                console.print("  [green]✓ Namespace migration complete[/green]")
                if verbose:
                    console.print(f"    Connections: {stats.get('connections', 0)}")
                    console.print(f"    Providers: {stats.get('providers', 0)}")
                    console.print(f"    Config: {'yes' if stats.get('config') else 'no'}")
                    console.print(f"    Vault: {'yes' if stats.get('vault') else 'no'}")
                console.print(f"  [dim]Original preserved at: {legacy_path}[/dim]")
    else:
        console.print("  [dim]No legacy ~/.dbmeta directory found[/dim]")

    # Step 2: Structure migration (v1 -> v2 for each connection)
    console.print("\n[bold]Step 2: Connection Structure Migration[/bold]")
    connections = list_connections()

    if not connections:
        console.print("  [dim]No connections to migrate[/dim]")
    else:
        for conn in connections:
            conn_path = get_connection_path(conn)
            has_version = (conn_path / ".version").exists()

            if has_version:
                console.print(f"  [dim]{conn}: already at v2[/dim]")
            else:
                console.print(f"  [cyan]{conn}: migrating...[/cyan]")
                try:
                    stats = migrate_to_connection_structure(conn)
                    if stats.get("skipped"):
                        reason = stats.get("reason")
                        if reason == "no_legacy_data":
                            # No legacy data but connection exists - just mark as v2
                            write_storage_version(conn_path)
                            console.print("    [green]✓ Marked as v2[/green]")
                        else:
                            console.print(f"    [dim]Skipped: {reason}[/dim]")
                    else:
                        console.print("    [green]✓ Migrated to v2[/green]")
                        if verbose:
                            console.print(f"      Schema: {stats.get('schema_descriptions')}")
                            console.print(f"      Domain: {stats.get('domain_model')}")
                            console.print(f"      Examples: {stats.get('query_examples', 0)}")
                except Exception as e:
                    console.print(f"    [red]Error: {e}[/red]")

    # Step 3: Configure Claude Desktop
    console.print("\n[bold]Step 3: Claude Desktop Configuration[/bold]")
    try:
        claude_config, claude_config_path = load_claude_desktop_config()
        mcp_servers = claude_config.get("mcpServers", {})

        if "db-mcp" in mcp_servers:
            console.print("  [dim]Already configured[/dim]")
        else:
            # Get active connection for configuration
            active = get_active_connection()
            if active:
                _configure_agents()
            else:
                console.print(
                    "  [yellow]No active connection - run 'db-mcp init' to configure[/yellow]"
                )
    except Exception as e:
        console.print(f"  [yellow]Could not configure: {e}[/yellow]")

    console.print("\n[green]✓ Migration complete[/green]")
    console.print("\n[dim]Restart Claude Desktop to apply changes.[/dim]")


# =============================================================================
# Collaboration commands
# =============================================================================


@main.group()
def collab():
    """Collaborate on a shared knowledge vault via git.

    The master sets up the vault and reviews changes.
    Collaborators join via 'db-mcp collab attach <repo-url>' and sync automatically.

    Examples:
        db-mcp collab init                # Master: set up collaboration
        db-mcp collab attach <url>        # Attach shared repo to existing connection
        db-mcp collab detach              # Remove shared repo link
        db-mcp collab join                # Register as collaborator (after attach)
        db-mcp collab sync                # Push/pull changes
        db-mcp collab merge               # Master: merge collaborator changes
        db-mcp collab status              # Show sync status
        db-mcp collab members             # List team members
        db-mcp collab daemon              # Run periodic sync in background
    """
    pass


@collab.command("init")
def collab_init():
    """Set up collaboration on the active connection (master role).

    Ensures git is initialized with a remote, creates .collab.yaml
    with you as the master, and pushes to the remote.
    """
    from db_mcp.collab.manifest import (
        CollabManifest,
        add_member,
        get_user_name_from_config,
        load_manifest,
        save_manifest,
        set_user_name_in_config,
    )
    from db_mcp.git_utils import git
    from db_mcp.traces import generate_user_id, get_user_id_from_config

    name = get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    # Ensure git is set up
    if not is_git_repo(conn_path):
        console.print("[yellow]Git not initialized. Run 'db-mcp git-init' first.[/yellow]")
        sys.exit(1)

    if not git.has_remote(conn_path):
        console.print("[yellow]No git remote configured. Add one first:[/yellow]")
        console.print(f"  cd {conn_path}")
        console.print("  git remote add origin <your-repo-url>")
        sys.exit(1)

    # Get or prompt for user_name
    user_name = get_user_name_from_config()
    if not user_name:
        user_name = click.prompt("Your name (used for branch names and attribution)")
        set_user_name_in_config(user_name)

    # Get or generate user_id
    user_id = get_user_id_from_config()
    if not user_id:
        user_id = generate_user_id()
        config = load_config()
        config["user_id"] = user_id
        save_config(config)

    # Check if manifest already exists
    manifest = load_manifest(conn_path)
    if manifest:
        console.print("[yellow]Collaboration already initialized.[/yellow]")
        console.print("[dim]Use 'db-mcp collab members' to see the team.[/dim]")
        return

    # Create manifest
    from datetime import datetime, timezone

    manifest = CollabManifest(created_at=datetime.now(timezone.utc))
    manifest = add_member(manifest, user_name, user_id, "master")
    save_manifest(conn_path, manifest)

    # Commit and push
    git.add(conn_path, [".collab.yaml"])
    git.commit(conn_path, "Initialize collaboration manifest")
    try:
        git.push(conn_path)
        console.print(f"[green]Collaboration initialized for '{name}'.[/green]")
        console.print(f"[dim]You are the master. User: {user_name} ({user_id})[/dim]")
        console.print(
            "[dim]Share the repo URL with collaborators so they can run "
            "'db-mcp init <name> <url>' to join.[/dim]"
        )
    except Exception as e:
        console.print(f"[yellow]Manifest saved locally but push failed: {e}[/yellow]")
        console.print("[dim]Push manually when ready.[/dim]")


@collab.command("attach")
@click.argument("url")
def collab_attach(url: str):
    """Attach a shared knowledge repo to the active connection.

    Use this when you already have a local connection and want to
    merge in a team's shared knowledge from a git repo.

    Your local files are preserved. The team's knowledge is merged in.
    You're automatically registered as a collaborator.

    Examples:
        db-mcp collab attach git@github.com:org/db-knowledge.git
        db-mcp collab attach https://github.com/org/db-knowledge.git
    """
    name = get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        console.print("[dim]Create one first with 'db-mcp init'.[/dim]")
        sys.exit(1)

    conn_path = get_connection_path(name)
    _attach_repo(name, conn_path, url)


@collab.command("detach")
def collab_detach():
    """Remove the shared repo link from the active connection.

    Keeps all local files intact but removes the git remote.
    Your knowledge stays, you just stop syncing with the team.
    """
    from db_mcp.git_utils import git

    name = get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    if not is_git_repo(conn_path):
        console.print("[yellow]Not a git repository. Nothing to detach.[/yellow]")
        return

    if not git.has_remote(conn_path):
        console.print("[yellow]No remote configured. Nothing to detach.[/yellow]")
        return

    # Get remote URL for display
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=conn_path,
        capture_output=True,
        text=True,
    )
    remote_url = result.stdout.strip()

    if not click.confirm(f"Detach from '{remote_url}'? (local files kept)"):
        return

    subprocess.run(
        ["git", "remote", "remove", "origin"],
        cwd=conn_path,
        check=True,
    )

    console.print(f"[green]Detached '{name}' from {remote_url}.[/green]")
    console.print("[dim]Local files preserved. Re-attach with 'db-mcp collab attach'.[/dim]")


@collab.command("join")
def collab_join():
    """Join an existing collaboration as a collaborator.

    Use this if you already have the connection cloned (via 'db-mcp init <name> <url>')
    but were not registered as a collaborator, or to re-register.

    Prompts for your name, creates a collaborator branch, and pushes.
    """
    name = get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    if not is_git_repo(conn_path):
        console.print(
            "[yellow]Not a git repository. Clone with 'db-mcp init <name> <url>' first.[/yellow]"
        )
        sys.exit(1)

    from db_mcp.collab.manifest import load_manifest

    manifest = load_manifest(conn_path)
    if manifest is None:
        console.print(
            "[yellow]No .collab.yaml found. Ask the master to run 'db-mcp collab init'.[/yellow]"
        )
        sys.exit(1)

    _auto_register_collaborator(conn_path)


@collab.command("sync")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def collab_sync(connection: str | None):
    """Sync local changes with the shared vault.

    Pulls latest from main, commits local changes, and pushes.
    Additive changes (examples, learnings) auto-merge to main.
    Shared-state changes (schema, rules) open a PR for master review.
    """
    from db_mcp.collab.manifest import (
        get_user_name_from_config,
    )
    from db_mcp.collab.sync import full_sync

    name = connection or get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    if not is_git_repo(conn_path):
        console.print("[yellow]Not a git repository. Run 'db-mcp git-init' first.[/yellow]")
        sys.exit(1)

    # Determine user
    user_name = get_user_name_from_config()
    if not user_name:
        # Fall back to user_id hash so sync never fails due to missing name
        from db_mcp.traces import get_user_id_from_config

        user_name = get_user_id_from_config()
        if not user_name:
            console.print(
                "[yellow]No user_name or user_id set. Run 'db-mcp collab join' first.[/yellow]"
            )
            sys.exit(1)
        console.print(f"[dim]No user_name set, using user_id: {user_name}[/dim]")

    console.print(f"[bold]Syncing '{name}' as {user_name}...[/bold]")
    result = full_sync(conn_path, user_name)

    if result.error:
        console.print(f"[yellow]Warning: {result.error}[/yellow]")

    if result.additive_merged:
        console.print(
            f"[green]Auto-merged {result.additive_merged} additive file(s) to main.[/green]"
        )

    if result.shared_state_files:
        n = len(result.shared_state_files)
        console.print(f"[yellow]{n} shared-state file(s) need master review:[/yellow]")
        for f in result.shared_state_files:
            console.print(f"  [dim]{f}[/dim]")

    if result.pr_opened:
        console.print(f"[green]PR opened: {result.pr_url}[/green]")
    elif result.shared_state_files:
        console.print("[dim]Branch pushed. Open a PR on GitHub for master to review.[/dim]")

    if not result.additive_merged and not result.shared_state_files:
        console.print("[dim]Nothing to sync.[/dim]")


@collab.command("merge")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def collab_merge(connection: str | None):
    """Merge collaborator changes into main (master only).

    Auto-merges additive changes (examples, learnings, traces).
    Opens PRs for shared-state changes that need review.
    """
    from db_mcp.collab.manifest import get_role
    from db_mcp.collab.merge import master_merge_all
    from db_mcp.traces import get_user_id_from_config

    name = connection or get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    # Check role
    user_id = get_user_id_from_config()
    role = get_role(conn_path, user_id) if user_id else None
    if role != "master":
        console.print("[yellow]Only the master can run merge.[/yellow]")
        console.print("[dim]Your role: " + (role or "not a member") + "[/dim]")
        sys.exit(1)

    console.print(f"[bold]Merging collaborator changes for '{name}'...[/bold]")
    result = master_merge_all(conn_path)

    if not result.collaborators:
        console.print("[dim]No collaborator branches found.[/dim]")
        return

    for c in result.collaborators:
        status_parts = []
        if c.additive_merged:
            status_parts.append(f"{c.additive_merged} auto-merged")
        if c.pr_opened:
            status_parts.append(f"PR: {c.pr_url}")
        elif c.shared_state_files:
            status_parts.append(f"{len(c.shared_state_files)} need review")
        if c.error:
            status_parts.append(f"error: {c.error}")
        status = ", ".join(status_parts) if status_parts else "no changes"
        console.print(f"  [cyan]{c.user_name}[/cyan]: {status}")

    console.print(
        f"\n[green]Total: {result.total_additive} file(s) merged, "
        f"{result.total_prs} PR(s) opened.[/green]"
    )


@collab.command("prune")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def collab_prune(connection: str | None):
    """Remove collaborator branches that have been fully merged into main.

    Cleans up remote branches to keep the repository tidy.
    """
    from db_mcp.collab.merge import prune_merged_branches
    from db_mcp.git_utils import git

    name = connection or get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    if not is_git_repo(conn_path):
        console.print("[yellow]Not a git repository.[/yellow]")
        sys.exit(1)

    # Fetch latest remote state
    git.fetch(conn_path)

    console.print(f"[bold]Pruning merged branches for '{name}'...[/bold]")
    pruned = prune_merged_branches(conn_path)

    if pruned:
        for branch in pruned:
            console.print(f"  [red]Deleted[/red] {branch}")
        console.print(f"\n[green]Pruned {len(pruned)} branch(es).[/green]")
    else:
        console.print("[dim]No merged branches to prune.[/dim]")


@collab.command("status")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def collab_status(connection: str | None):
    """Show collaboration status for the active connection."""
    from db_mcp.collab.manifest import get_member, load_manifest
    from db_mcp.git_utils import git
    from db_mcp.traces import get_user_id_from_config

    name = connection or get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    console.print(f"[bold]Collaboration: {name}[/bold]")

    # Git status
    if not is_git_repo(conn_path):
        console.print("  Git: [dim]not initialized[/dim]")
        return

    branch = git.current_branch(conn_path)
    console.print(f"  Branch: [cyan]{branch}[/cyan]")

    remote_url = git.remote_get_url(conn_path)
    if remote_url:
        console.print(f"  Remote: [dim]{remote_url}[/dim]")

    # Manifest
    manifest = load_manifest(conn_path)
    if not manifest:
        console.print("  Manifest: [dim]not found (.collab.yaml)[/dim]")
        console.print("[dim]Run 'db-mcp collab init' to set up collaboration.[/dim]")
        return

    user_id = get_user_id_from_config()
    member = get_member(manifest, user_id) if user_id else None
    if member:
        console.print(f"  Role: [green]{member.role}[/green]")
        console.print(f"  User: {member.user_name} ({member.user_id})")
    else:
        console.print("  Role: [yellow]not a member[/yellow]")

    console.print(f"  Members: {len(manifest.members)}")
    console.print(
        f"  Auto-sync: {'enabled' if manifest.sync.auto_sync else 'disabled'} "
        f"(every {manifest.sync.sync_interval_minutes}m)"
    )

    # Pending changes
    changes = git.status(conn_path)
    if changes:
        console.print(f"  Pending: [yellow]{len(changes)} uncommitted change(s)[/yellow]")
    else:
        console.print("  Pending: [dim]clean[/dim]")


@collab.command("members")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
def collab_members(connection: str | None):
    """List team members and their roles."""
    from db_mcp.collab.manifest import load_manifest

    name = connection or get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)
    manifest = load_manifest(conn_path)

    if not manifest:
        console.print("[dim]No .collab.yaml found. Run 'db-mcp collab init' first.[/dim]")
        return

    console.print(f"[bold]Team members for '{name}'[/bold]\n")
    for m in manifest.members:
        role_color = "green" if m.role == "master" else "cyan"
        joined = m.joined_at.strftime("%Y-%m-%d")
        console.print(
            f"  [{role_color}]{m.role:>12}[/{role_color}]  "
            f"{m.user_name} ({m.user_id})  [dim]joined {joined}[/dim]"
        )


@collab.command("daemon")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option(
    "--interval",
    default=None,
    type=int,
    help="Sync interval in minutes (default: from manifest or 60)",
)
def collab_daemon(connection: str | None, interval: int | None):
    """Run periodic background sync (long-running process).

    Pulls from main and pushes local changes at a regular interval.
    Useful for daemon/sidecar mode where db-mcp runs continuously.

    For session mode (Claude wakes up db-mcp then releases), the MCP
    server automatically pulls on startup and pushes on shutdown.
    """
    import asyncio as _asyncio

    from db_mcp.collab.background import CollabSyncLoop
    from db_mcp.collab.manifest import (
        get_member,
        get_user_name_from_config,
        load_manifest,
    )
    from db_mcp.traces import get_user_id_from_config

    name = connection or get_active_connection()
    if not connection_exists(name):
        console.print(f"[red]Connection '{name}' not found.[/red]")
        sys.exit(1)

    conn_path = get_connection_path(name)

    if not is_git_repo(conn_path):
        console.print("[yellow]Not a git repository. Run 'db-mcp git-init' first.[/yellow]")
        sys.exit(1)

    manifest = load_manifest(conn_path)
    if not manifest:
        console.print("[yellow]No .collab.yaml found. Run 'db-mcp collab init' first.[/yellow]")
        sys.exit(1)

    # Determine user
    user_name = get_user_name_from_config()
    user_id = get_user_id_from_config()
    if not user_id:
        console.print("[yellow]No user_id set. Run 'db-mcp collab join' first.[/yellow]")
        sys.exit(1)
    if not user_name:
        user_name = user_id
        console.print(f"[dim]No user_name set, using user_id: {user_name}[/dim]")

    member = get_member(manifest, user_id)
    if not member:
        console.print("[yellow]You are not a member of this vault.[/yellow]")
        sys.exit(1)

    sync_interval = interval or manifest.sync.sync_interval_minutes

    console.print(f"[bold]Starting collab daemon for '{name}'[/bold]")
    console.print(f"  User: {user_name} ({user_id})")
    console.print(f"  Role: {member.role}")
    console.print(f"  Interval: {sync_interval}m")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    async def _run_daemon():
        loop = CollabSyncLoop(conn_path, user_name, sync_interval)
        await loop.start()
        # Do an initial sync immediately
        import asyncio as _aio

        await _aio.to_thread(loop._run_sync)
        console.print("[green]Initial sync complete. Daemon running...[/green]")
        try:
            # Block until interrupted
            while True:
                await _aio.sleep(3600)
        except _aio.CancelledError:
            pass
        finally:
            await loop.stop()

    try:
        _asyncio.run(_run_daemon())
    except KeyboardInterrupt:
        console.print("\n[dim]Daemon stopped.[/dim]")


# =============================================================================
# Traces commands
# =============================================================================


@main.group()
def traces():
    """Manage trace capture for diagnostics and learning.

    Traces capture MCP server activity (tool calls, queries, etc.)
    and store them as JSONL files for agent analysis.

    Examples:
        db-mcp traces on       # Enable trace capture
        db-mcp traces off      # Disable trace capture
        db-mcp traces status   # Show trace settings and files
    """
    pass


@traces.command("on")
def traces_on():
    """Enable trace capture.

    When enabled, the MCP server will write traces to:
        ~/.dbmcp/connections/{name}/traces/{user_id}/YYYY-MM-DD.jsonl

    A unique user_id is generated on first enable to identify
    your traces when sharing with the team.
    """
    from db_mcp.traces import generate_user_id, get_user_id_from_config

    config = load_config()

    # Check if already enabled
    if config.get("traces_enabled"):
        console.print("[dim]Traces already enabled.[/dim]")
        user_id = config.get("user_id", "unknown")
        console.print(f"[dim]User ID: {user_id}[/dim]")
        return

    # Generate user_id if not exists
    user_id = get_user_id_from_config()
    if not user_id:
        user_id = generate_user_id()
        config["user_id"] = user_id
        console.print(f"[green]✓ Generated user ID: {user_id}[/green]")

    # Enable traces
    config["traces_enabled"] = True
    save_config(config)

    console.print("[green]✓ Traces enabled[/green]")
    console.print(f"[dim]User ID: {user_id}[/dim]")
    console.print("[dim]Restart Claude Desktop to start capturing traces.[/dim]")


@traces.command("off")
def traces_off():
    """Disable trace capture.

    Existing trace files are preserved.
    """
    config = load_config()

    if not config.get("traces_enabled"):
        console.print("[dim]Traces already disabled.[/dim]")
        return

    config["traces_enabled"] = False
    save_config(config)

    console.print("[green]✓ Traces disabled[/green]")
    console.print("[dim]Restart Claude Desktop to stop capturing traces.[/dim]")


@traces.command("status")
def traces_status():
    """Show trace capture status and file locations."""
    config = load_config()

    enabled = config.get("traces_enabled", False)
    user_id = config.get("user_id")

    console.print("[bold]Trace Capture[/bold]")
    console.print(f"  Status:  {'[green]enabled[/green]' if enabled else '[dim]disabled[/dim]'}")

    if user_id:
        console.print(f"  User ID: [cyan]{user_id}[/cyan]")
    else:
        console.print("  User ID: [dim]not set (will generate on enable)[/dim]")

    # Show trace files for active connection
    active = get_active_connection()
    if active and user_id:
        conn_path = get_connection_path(active)
        traces_dir = conn_path / "traces" / user_id

        console.print(f"\n[bold]Traces for '{active}'[/bold]")
        console.print(f"  Directory: {traces_dir}")

        if traces_dir.exists():
            trace_files = sorted(traces_dir.glob("*.jsonl"), reverse=True)
            if trace_files:
                console.print(f"  Files: {len(trace_files)}")
                # Show recent files
                for tf in trace_files[:5]:
                    size = tf.stat().st_size
                    size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
                    console.print(f"    [dim]{tf.name}[/dim] ({size_str})")
                if len(trace_files) > 5:
                    console.print(f"    [dim]... and {len(trace_files) - 5} more[/dim]")
            else:
                console.print("  [dim]No trace files yet.[/dim]")
        else:
            console.print("  [dim]No traces directory yet.[/dim]")

    if not enabled:
        console.print("\n[dim]Run 'db-mcp traces on' to enable capture.[/dim]")


# =============================================================================
# UI server command
# =============================================================================


@main.command("ui")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8080, help="Port to listen on")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option("-v", "--verbose", is_flag=True, help="Show server logs in terminal")
def ui_cmd(host: str, port: int, connection: str | None, verbose: bool):
    """Start the UI server with BICP support.

    This starts a FastAPI server that provides:
    - /bicp POST endpoint for JSON-RPC requests
    - /bicp/stream WebSocket for streaming notifications
    - /health GET endpoint for health checks
    - Static file serving for the UI build

    The UI server enables browser-based interaction with db-mcp
    using the BICP (Business Intelligence Client Protocol).

    Example:
        db-mcp ui                    # Start on default port 8080
        db-mcp ui -v                 # Start with verbose logging
        db-mcp ui -p 3001            # Start on port 3001
        db-mcp ui -c mydb -p 8080    # Use specific connection
    """
    import threading
    import urllib.request
    import webbrowser

    # Create config directory if it doesn't exist (for fresh installs)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONNECTIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Load or create default config
    if CONFIG_FILE.exists():
        config = load_config()
    else:
        config = {}

    # Determine connection name
    conn_name = connection or config.get("active_connection", "")

    # Set environment variables
    if conn_name:
        connection_path = get_connection_path(conn_name)
        conn_env = _load_connection_env(conn_name)
        database_url = conn_env.get("DATABASE_URL", "")

        # Fallback to global config for backward compatibility
        if not database_url:
            database_url = config.get("database_url", "")

        os.environ["DATABASE_URL"] = database_url
        os.environ["CONNECTION_NAME"] = conn_name
        os.environ["CONNECTION_PATH"] = str(connection_path)

        # Ensure connection directory exists
        connection_path.mkdir(parents=True, exist_ok=True)

        # Run pending migrations for this connection
        from db_mcp.migrations import run_migrations

        migration_result = run_migrations(conn_name)
        if migration_result.get("applied"):
            console.print(
                f"[dim]Applied {len(migration_result['applied'])} migrations for {conn_name}[/dim]"
            )
    else:
        os.environ["DATABASE_URL"] = ""
        os.environ["CONNECTION_NAME"] = ""
        os.environ["CONNECTION_PATH"] = ""

    # Run migrations for all connections (UI may switch between them)
    from db_mcp.migrations import run_migrations_all

    all_results = run_migrations_all()
    total_applied = sum(len(r.get("applied", [])) for r in all_results)
    if total_applied > 0:
        console.print(f"[dim]Applied {total_applied} migrations across all connections[/dim]")

    os.environ["TOOL_MODE"] = config.get("tool_mode", "shell")
    os.environ["LOG_LEVEL"] = config.get("log_level", "INFO")

    # Legacy env vars for backward compatibility
    os.environ["PROVIDER_ID"] = conn_name
    os.environ["CONNECTIONS_DIR"] = str(CONNECTIONS_DIR)

    # Determine the URL to open in browser
    browser_host = "localhost" if host == "0.0.0.0" else host
    url = f"http://{browser_host}:{port}"

    conn_display = f"[cyan]{conn_name}[/cyan]" if conn_name else "[dim]none[/dim]"
    console.print(
        Panel.fit(
            f"[bold blue]db-mcp UI Server[/bold blue]\n\n"
            f"Connection: {conn_display}\n"
            f"Server: [cyan]{url}[/cyan]\n\n"
            f"Press Ctrl+C to stop.",
            border_style="blue",
        )
    )

    # Open browser once server is ready
    def open_browser():
        import time

        # Poll until server is ready (max 10 seconds)
        for _ in range(20):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=0.5)
                webbrowser.open(url)
                return
            except Exception:
                time.sleep(0.5)

    threading.Thread(target=open_browser, daemon=True).start()

    # Restore default SIGINT handler so uvicorn can shutdown gracefully
    signal.signal(signal.SIGINT, signal.default_int_handler)

    from db_mcp.ui_server import start_ui_server

    # Set up log file path
    log_file = CONFIG_DIR / "ui-server.log" if not verbose else None

    try:
        start_ui_server(host=host, port=port, log_file=log_file)
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")


@main.command()
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


@main.group()
def playground():
    """Manage the playground connection with Chinook SQLite database.

    The playground provides a sample SQLite database (Chinook) for
    testing and learning db-mcp features without setting up your own database.

    Examples:
        db-mcp playground install    # Install playground database
        db-mcp playground status     # Check installation status
    """
    pass


@playground.command("install")
def playground_install():
    """Install the playground connection.

    Downloads and installs the Chinook SQLite database as a sample connection
    called 'playground'. This gives you a working database to test db-mcp features.
    """
    from db_mcp.playground import install_playground

    try:
        result = install_playground()

        if result["success"]:
            if result.get("already_installed"):
                console.print("[dim]Playground already installed.[/dim]")
                console.print("Connection: [cyan]playground[/cyan]")
                console.print(f"Database: [dim]{result['database_url']}[/dim]")
            else:
                console.print(f"[green]✓ Playground installed: {result['database_url']}[/green]")
        else:
            error_msg = result.get("error", "Unknown error")
            console.print(f"[red]Failed to install playground: {error_msg}[/red]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error installing playground: {e}[/red]")
        sys.exit(1)


@playground.command("status")
def playground_status():
    """Check if playground is installed and show connection details."""
    from db_mcp.playground import PLAYGROUND_CONNECTION_NAME, is_playground_installed

    if is_playground_installed():
        console.print("Playground: [green]installed[/green]")
        console.print(f"Connection: [cyan]{PLAYGROUND_CONNECTION_NAME}[/cyan]")

        # Try to read the database URL from the connector
        try:
            import yaml as _yaml

            connections_dir = Path.home() / ".db-mcp" / "connections"
            playground_dir = connections_dir / PLAYGROUND_CONNECTION_NAME
            connector_path = playground_dir / "connector.yaml"

            if connector_path.exists():
                with open(connector_path) as f:
                    cfg = _yaml.safe_load(f) or {}
                    db_url = cfg.get("database_url", "")
                    if db_url:
                        console.print(f"Database: [dim]{db_url}[/dim]")
                    else:
                        console.print("Database: [yellow]not configured[/yellow]")
            else:
                console.print("Database: [yellow]connector.yaml not found[/yellow]")
        except Exception as e:
            console.print(f"Database: [yellow]error reading config: {e}[/yellow]")
    else:
        console.print("Playground: [dim]not installed[/dim]")
        console.print("[dim]Run 'db-mcp playground install' to install.[/dim]")


if __name__ == "__main__":
    main()
