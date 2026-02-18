"""Core CRUD commands: init, start, config, status, list, use, edit, rename, remove, all."""

import os
import subprocess
import sys
from pathlib import Path

import click
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from db_mcp.cli.connection import (
    _get_connection_env_path,
    _load_connection_env,
    _save_connection_env,
    connection_exists,
    get_active_connection,
    get_connection_path,
    list_connections,
    set_active_connection,
)
from db_mcp.cli.git_ops import (
    GIT_INSTALL_URL,
    git_init,
    is_git_repo,
    is_git_url,
)
from db_mcp.cli.init_flow import _attach_repo, _init_brownfield, _init_greenfield
from db_mcp.cli.utils import (
    CONFIG_DIR,
    CONFIG_FILE,
    CONNECTIONS_DIR,
    console,
    is_claude_desktop_installed,
    load_claude_desktop_config,
    load_config,
    save_config,
)


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


@click.command()
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


@click.command()
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


@click.command()
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


@click.command()
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


@click.command("list")
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


@click.command()
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


@click.command()
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


@click.command()
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


@click.command()
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


@click.command()
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


def register_commands(main_group: click.Group) -> None:
    """Register all core commands with the main group."""
    main_group.add_command(init)
    main_group.add_command(start)
    main_group.add_command(config)
    main_group.add_command(status)
    main_group.add_command(list_cmd)
    main_group.add_command(use)
    main_group.add_command(edit)
    main_group.add_command(rename)
    main_group.add_command(remove)
    main_group.add_command(all)
