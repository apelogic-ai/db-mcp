"""Service commands: console, ui, and playground group."""

import os
import signal
import sys
from pathlib import Path

import click
from rich.panel import Panel

from db_mcp.cli.connection import (
    _load_connection_env,
    get_active_connection,
    get_connection_path,
)
from db_mcp.cli.utils import (
    CONFIG_DIR,
    CONFIG_FILE,
    CONNECTIONS_DIR,
    console,
    load_config,
)


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
    main_group.add_command(ui_cmd)
    main_group.add_command(playground)
