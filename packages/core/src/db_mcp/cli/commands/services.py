"""Service commands: console, UI, daemon, and playground group."""

import os
import signal
import sys
import threading
from pathlib import Path

import click
from rich.panel import Panel

from db_mcp.cli.commands.core import start as start_cmd
from db_mcp.cli.connection import (
    _load_connection_env,
    get_connection_path,
)
from db_mcp.cli.utils import (
    CONFIG_DIR,
    CONFIG_FILE,
    CONNECTIONS_DIR,
    console,
    load_config,
)
from db_mcp.config import reset_settings
from db_mcp.local_service import (
    build_local_service_state,
    clear_local_service_state,
    write_local_service_state,
)


def _patch_fakeredis_for_frozen() -> None:
    """Patch fakeredis data-file lookup for PyInstaller bundles."""
    if not getattr(sys, "frozen", False):
        return

    import fakeredis.model._command_info as cmd_info

    bundle_dir = getattr(sys, "_MEIPASS", "")

    def patched_load() -> None:
        import json

        if cmd_info._COMMAND_INFO is None:
            json_path = os.path.join(bundle_dir, "fakeredis", "commands.json")
            with open(json_path, encoding="utf8") as f:
                cmd_info._COMMAND_INFO = cmd_info._encode_obj(json.load(f))

    cmd_info._load_command_info = patched_load


def _configure_service_environment(
    connection: str | None,
    *,
    tool_mode_override: str | None = None,
    runtime_interface_override: str | None = None,
) -> str | None:
    """Configure process environment for a selected connection."""
    # Create config directory if it doesn't exist (for fresh installs)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONNECTIONS_DIR.mkdir(parents=True, exist_ok=True)

    config = load_config() if CONFIG_FILE.exists() else {}
    conn_name = connection or config.get("active_connection", "")

    if conn_name:
        connection_path = get_connection_path(conn_name)
        conn_env = _load_connection_env(conn_name)
        database_url = conn_env.get("DATABASE_URL", "") or config.get("database_url", "")

        os.environ["DATABASE_URL"] = database_url
        os.environ["CONNECTION_NAME"] = conn_name
        os.environ["CONNECTION_PATH"] = str(connection_path)
        connection_path.mkdir(parents=True, exist_ok=True)

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

    from db_mcp.migrations import run_migrations_all

    all_results = run_migrations_all()
    total_applied = sum(len(r.get("applied", [])) for r in all_results)
    if total_applied > 0:
        console.print(f"[dim]Applied {total_applied} migrations across all connections[/dim]")

    os.environ["PROVIDER_ID"] = conn_name or ""
    os.environ["CONNECTIONS_DIR"] = str(CONNECTIONS_DIR)
    os.environ["TOOL_MODE"] = tool_mode_override or config.get("tool_mode", "shell")
    os.environ["RUNTIME_INTERFACE"] = runtime_interface_override or config.get(
        "runtime_interface", "native"
    )
    os.environ["LOG_LEVEL"] = config.get("log_level", "INFO")
    return conn_name or None


def _start_ui_background_service(*, host: str, port: int, verbose: bool) -> threading.Thread:
    """Start the UI/runtime HTTP surface in a background thread."""
    _patch_fakeredis_for_frozen()
    from db_mcp.ui_server import start_ui_server

    log_file = CONFIG_DIR / "ui-server.log" if not verbose else None
    thread = threading.Thread(
        target=start_ui_server,
        kwargs={"host": host, "port": port, "log_file": log_file},
        daemon=True,
        name="db-mcp-ui",
    )
    thread.start()
    return thread


def _run_http_mcp_service(*, host: str, port: int, path: str) -> None:
    """Run the MCP server over HTTP in the foreground."""
    _patch_fakeredis_for_frozen()
    os.environ["MCP_TRANSPORT"] = "http"
    os.environ["MCP_HOST"] = host
    os.environ["MCP_PORT"] = str(port)
    os.environ["MCP_PATH"] = path
    reset_settings()
    from db_mcp.server import main as server_main

    server_main()


@click.command("console")
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


@click.command("ui")
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

    conn_name = _configure_service_environment(connection)

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

    try:
        from db_mcp.ui_server import start_ui_server

        log_file = CONFIG_DIR / "ui-server.log" if not verbose else None
        start_ui_server(host=host, port=port, log_file=log_file)
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")


@click.command("up")
@click.option("--ui-host", default="127.0.0.1", show_default=True, help="UI/runtime host")
@click.option("--ui-port", default=8789, show_default=True, type=int, help="UI/runtime port")
@click.option("--mcp-host", default="127.0.0.1", show_default=True, help="HTTP MCP host")
@click.option("--mcp-port", default=8788, show_default=True, type=int, help="HTTP MCP port")
@click.option("--mcp-path", default="/mcp", show_default=True, help="HTTP MCP path")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option("-v", "--verbose", is_flag=True, help="Show UI server logs in terminal")
def up_cmd(
    ui_host: str,
    ui_port: int,
    mcp_host: str,
    mcp_port: int,
    mcp_path: str,
    connection: str | None,
    verbose: bool,
) -> None:
    """Start the local db-mcp control plane for Claude/Desktop and the web UI."""
    conn_name = _configure_service_environment(
        connection,
        tool_mode_override="daemon",
        runtime_interface_override="native",
    )
    state = build_local_service_state(
        connection=conn_name,
        ui_host=ui_host,
        ui_port=ui_port,
        mcp_host=mcp_host,
        mcp_port=mcp_port,
        mcp_path=mcp_path,
        pid=os.getpid(),
    )
    write_local_service_state(state)

    console.print(
        Panel.fit(
            f"[bold blue]db-mcp local service[/bold blue]\n\n"
            f"Connection: [cyan]{conn_name or 'none'}[/cyan]\n"
            f"UI/runtime: [cyan]{state['ui_url']}[/cyan]\n"
            f"MCP: [cyan]{state['mcp_url']}[/cyan]\n\n"
            f"Claude/Desktop entrypoint: [cyan]db-mcp runtime[/cyan]\n"
            f"Press Ctrl+C to stop.",
            border_style="blue",
        )
    )

    _start_ui_background_service(host=ui_host, port=ui_port, verbose=verbose)

    try:
        _run_http_mcp_service(host=mcp_host, port=mcp_port, path=mcp_path)
    finally:
        clear_local_service_state()


@click.group("serve")
def serve_group() -> None:
    """Serve db-mcp over mirrored MCP and UI entry points."""


@serve_group.command("mcp")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option(
    "--mode",
    type=click.Choice(["detailed", "shell", "exec-only", "code"]),
    default=None,
    help="Optional tool startup mode override.",
)
def serve_mcp(connection: str | None, mode: str | None) -> None:
    """Start the stdio MCP server using the shared db-mcp runtime."""
    callback = start_cmd.callback
    if callback is None:  # pragma: no cover - defensive guard
        raise click.ClickException("start command is unavailable")
    callback(connection, mode)


@serve_group.command("ui")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8080, help="Port to listen on")
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option("-v", "--verbose", is_flag=True, help="Show server logs in terminal")
def serve_ui(host: str, port: int, connection: str | None, verbose: bool) -> None:
    """Start the HTTP UI server using the shared db-mcp runtime."""
    callback = ui_cmd.callback
    if callback is None:  # pragma: no cover - defensive guard
        raise click.ClickException("ui command is unavailable")
    callback(host, port, connection, verbose)


@click.group()
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


def register_commands(main_group: click.Group) -> None:
    """Register service commands with the main group."""
    main_group.add_command(console_cmd)
    main_group.add_command(serve_group)
    main_group.add_command(ui_cmd)
    main_group.add_command(up_cmd)
    main_group.add_command(playground)
