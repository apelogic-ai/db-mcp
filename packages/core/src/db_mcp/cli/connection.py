"""Connection management utilities for the db-mcp CLI.

Handles listing, reading, writing, and activating connections stored in
~/.db-mcp/connections/.
"""

from pathlib import Path

from rich.prompt import Prompt

from db_mcp.cli.utils import (
    CONFIG_FILE,
    CONNECTIONS_DIR,
    console,
    load_config,
    save_config,
)


def get_connection_path(name: str) -> Path:
    """Get path to a connection directory."""
    return CONNECTIONS_DIR / name


def list_connections() -> list[str]:
    """List all connection names."""
    if not CONNECTIONS_DIR.exists():
        return []
    return sorted([d.name for d in CONNECTIONS_DIR.iterdir() if d.is_dir()])


def get_active_connection() -> str:
    """Get the active connection name from config."""
    config = load_config()
    return config.get("active_connection", "default")


def set_active_connection(name: str) -> None:
    """Set the active connection in config."""
    config = load_config()
    config["active_connection"] = name
    save_config(config)


def connection_exists(name: str) -> bool:
    """Check if a connection exists."""
    return get_connection_path(name).exists()


def _get_connection_env_path(name: str) -> Path:
    """Get path to connection's .env file."""
    return get_connection_path(name) / ".env"


def _load_connection_env(name: str) -> dict:
    """Load environment variables from connection's .env file."""
    env_file = _get_connection_env_path(name)
    if not env_file.exists():
        return {}

    env_vars = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes if present
                value = value.strip().strip("\"'")
                env_vars[key] = value
    return env_vars


def _save_connection_env(name: str, env_vars: dict):
    """Save environment variables to connection's .env file."""
    conn_path = get_connection_path(name)
    conn_path.mkdir(parents=True, exist_ok=True)

    env_file = _get_connection_env_path(name)
    with open(env_file, "w") as f:
        f.write("# db-mcp connection credentials\n")
        f.write("# This file is gitignored - do not commit\n\n")
        for key, value in env_vars.items():
            f.write(f'{key}="{value}"\n')


def _prompt_and_save_database_url(name: str, existing_url: str | None = None) -> str | None:
    """Prompt for database URL and save to connection's .env file."""
    # Try to load existing URL from connection's .env
    if not existing_url:
        conn_env = _load_connection_env(name)
        existing_url = conn_env.get("DATABASE_URL")

    console.print("\n[bold]Database Connection[/bold]")
    console.print("[dim]Examples:[/dim]")
    console.print("  trino://user:pass@host:8443/catalog/schema?http_scheme=https")
    console.print("  clickhouse+native://user:pass@host:9000/database")
    console.print("  postgresql://user:pass@host:5432/database")
    console.print()

    database_url = Prompt.ask(
        "Database URL",
        default=existing_url or "",
    )

    if not database_url:
        console.print("[red]Database URL is required.[/red]")
        return None

    # Save DATABASE_URL to connection's .env file (gitignored)
    _save_connection_env(name, {"DATABASE_URL": database_url})
    console.print(f"\n[green]✓ Credentials saved to {_get_connection_env_path(name)}[/green]")

    # Save non-sensitive config to global config.yaml
    config = load_config()
    config.update(
        {
            "active_connection": name,
            "tool_mode": "shell",
            "log_level": "INFO",
        }
    )
    # Remove database_url from global config if present (migrate to per-connection)
    config.pop("database_url", None)

    save_config(config)
    console.print(f"[green]✓ Config saved to {CONFIG_FILE}[/green]")

    return database_url
