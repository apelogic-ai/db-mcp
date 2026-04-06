"""Server commands: start (MCP stdio server) and config (open config in editor)."""

import os
import subprocess
import sys
from pathlib import Path

import click
from rich.prompt import Confirm

from db_mcp_cli.connection import (
    _load_connection_env,
    get_connection_path,
)
from db_mcp_cli.utils import (
    CONFIG_FILE,
    console,
    load_config,
)


def _resolve_preconfigured_connection_path(
    connection_name: str,
) -> tuple[Path, Path]:
    """Prefer benchmark/injected connection env over CLI-global home paths."""
    configured_path = os.environ.get("CONNECTION_PATH", "").strip()
    if configured_path:
        path = Path(configured_path).expanduser()
        if path.name == connection_name:
            return path, path.parent

    configured_dir = os.environ.get("CONNECTIONS_DIR", "").strip()
    if configured_dir:
        directory = Path(configured_dir).expanduser()
        return directory / connection_name, directory

    path = get_connection_path(connection_name)
    return path, path.parent


def _load_connection_env_from_path(connection_path: Path) -> dict[str, str]:
    """Load environment variables from a concrete connection directory."""
    env_file = connection_path / ".env"
    if not env_file.exists():
        return {}

    env_vars: dict[str, str] = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value.strip().strip("\"'")
    return env_vars


@click.command()
@click.option("-c", "--connection", default=None, help="Connection name (default: active)")
@click.option(
    "--mode",
    type=click.Choice(["detailed", "shell", "exec-only", "code"]),
    default=None,
    help="Optional tool startup mode override.",
)
def start(connection: str | None, mode: str | None):
    """Start the MCP server (stdio mode for Claude Desktop)."""
    if not CONFIG_FILE.exists():
        console.print("[red]No config found. Run 'db-mcp init' first.[/red]")
        sys.exit(1)

    config = load_config()

    # Determine connection name
    conn_name = connection or config.get("active_connection", "default")
    connection_path, connections_dir = _resolve_preconfigured_connection_path(conn_name)

    # Load DATABASE_URL from connection's .env file
    conn_env = _load_connection_env_from_path(connection_path)
    if not conn_env and connection_path == get_connection_path(conn_name):
        conn_env = _load_connection_env(conn_name)
    database_url = conn_env.get("DATABASE_URL", "")

    # Fallback to global config for backward compatibility
    if not database_url:
        database_url = config.get("database_url", "")

    # Set environment variables
    os.environ["DATABASE_URL"] = database_url
    os.environ["CONNECTION_NAME"] = conn_name
    os.environ["CONNECTION_PATH"] = str(connection_path)
    os.environ["TOOL_MODE"] = mode or config.get("tool_mode", "shell")
    os.environ["LOG_LEVEL"] = config.get("log_level", "INFO")
    os.environ["MCP_TRANSPORT"] = "stdio"  # Always stdio for CLI

    # Legacy env vars for backward compatibility
    os.environ["PROVIDER_ID"] = conn_name
    os.environ["CONNECTIONS_DIR"] = str(connections_dir)

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
    from db_mcp_server.server import main as server_main

    server_main()


@click.command()
def config():
    """Open config file in editor."""
    if not CONFIG_FILE.exists():
        console.print("[yellow]No config found. Run 'db-mcp init' first.[/yellow]")
        if Confirm.ask("Run setup now?", default=True):
            from db_mcp_cli.commands.init_cmd import init

            ctx = click.get_current_context()
            ctx.invoke(init)
            return
        return

    editor = os.environ.get("EDITOR", "vim")
    console.print(f"[dim]Opening {CONFIG_FILE} in {editor}...[/dim]")

    try:
        subprocess.run([editor, str(CONFIG_FILE)], check=True)
        console.print("[green]✓ Config saved.[/green]")
        console.print("[dim]Restart your MCP agent to apply changes.[/dim]")
    except FileNotFoundError:
        console.print(f"[red]Editor '{editor}' not found.[/red]")
        console.print("[dim]Set EDITOR environment variable or edit manually:[/dim]")
        console.print(f"  {CONFIG_FILE}")
    except subprocess.CalledProcessError:
        console.print("[yellow]Editor exited with error.[/yellow]")
