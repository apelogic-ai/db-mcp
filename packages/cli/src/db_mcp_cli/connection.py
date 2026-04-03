"""Connection management utilities for the db-mcp CLI.

Handles listing, reading, writing, and activating connections stored in
~/.db-mcp/connections/.
"""

from pathlib import Path

import yaml
from db_mcp_data.connector_templates import get_connector_template
from db_mcp_data.contracts.connector_contracts import CONNECTOR_SPEC_VERSION
from rich.prompt import Prompt

from db_mcp_cli.utils import (
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


def _prompt_and_save_api_connection(name: str, template_name: str | None = None) -> bool:
    """Prompt for API connector settings and persist connector.yaml + .env."""
    template = get_connector_template(template_name) if template_name else None
    if template_name and template is None:
        console.print(f"[red]Unknown connector template: {template_name}[/red]")
        return False

    if template is not None:
        console.print("\n[bold]API Connection[/bold]")
        console.print(f"[dim]Using built-in template: {template.title}[/dim]\n")

        connector_yaml = yaml.safe_load(yaml.safe_dump(template.connector))
        base_url = Prompt.ask(
            template.base_url_prompt or "API Base URL",
            default=str(connector_yaml.get("base_url", "")),
        )
        if not base_url:
            console.print("[red]API Base URL is required.[/red]")
            return False
        connector_yaml["base_url"] = base_url

        env_vars: dict[str, str] = {}
        for env_var in template.env:
            value = Prompt.ask(env_var.prompt, default="", password=env_var.secret)
            if not value:
                console.print(f"[red]{env_var.name} is required.[/red]")
                return False
            env_vars[env_var.name] = value

        connector_path = get_connection_path(name)
        connector_path.mkdir(parents=True, exist_ok=True)
        connector_yaml_path = connector_path / "connector.yaml"
        with open(connector_yaml_path, "w") as f:
            yaml.dump(connector_yaml, f, default_flow_style=False, sort_keys=False)

        _save_connection_env(name, env_vars)
        console.print(f"\n[green]✓ API connector saved to {connector_yaml_path}[/green]")
        console.print(f"[green]✓ Credentials saved to {_get_connection_env_path(name)}[/green]")

        config = load_config()
        config.update(
            {
                "active_connection": name,
                "tool_mode": "shell",
                "log_level": "INFO",
            }
        )
        config.pop("database_url", None)
        save_config(config)
        console.print(f"[green]✓ Config saved to {CONFIG_FILE}[/green]")
        return True

    console.print("\n[bold]API Connection[/bold]")
    console.print("[dim]Example base URL: https://api.example.com/v1[/dim]\n")

    base_url = Prompt.ask("API Base URL", default="")
    if not base_url:
        console.print("[red]API Base URL is required.[/red]")
        return False

    auth_type = Prompt.ask("Auth type", choices=["header", "bearer", "basic"], default="header")

    auth_config: dict[str, object] = {"type": auth_type}
    env_vars: dict[str, str] = {}

    if auth_type == "basic":
        username_env = Prompt.ask("Username/email env var name", default="API_USERNAME")
        username_value = Prompt.ask(f"Value for {username_env}", default="", password=False)
        password_env = Prompt.ask("Password/token env var name", default="API_PASSWORD")
        password_value = Prompt.ask(f"Value for {password_env}", default="", password=True)
        if not username_value or not password_value:
            console.print("[red]Both username/email and password/token values are required.[/red]")
            return False

        auth_config.update(
            {
                "username_env": username_env,
                "password_env": password_env,
            }
        )
        env_vars = {
            username_env: username_value,
            password_env: password_value,
        }
    else:
        token_env = Prompt.ask("API key env var name", default="API_KEY")
        token_value = Prompt.ask(f"Value for {token_env}", default="", password=True)
        if not token_value:
            console.print("[red]API key value is required.[/red]")
            return False

        auth_config.update(
            {
                "token_env": token_env,
                **(
                    {"header_name": Prompt.ask("Auth header name", default="X-API-KEY")}
                    if auth_type == "header"
                    else {}
                ),
            }
        )
        env_vars = {token_env: token_value}

    connector_path = get_connection_path(name)
    connector_path.mkdir(parents=True, exist_ok=True)

    sql_support = Prompt.ask(
        "Does this API support SQL queries?",
        choices=["yes", "no"],
        default="yes",
    )

    connector_yaml: dict[str, object] = {
        "spec_version": CONNECTOR_SPEC_VERSION,
        "type": "api",
        "profile": "api_openapi",
        "base_url": base_url,
        "auth": auth_config,
        "endpoints": [],
        "capabilities": {
            "sql": False,
            "supports_validate_sql": False,
            "supports_async_jobs": False,
        },
    }

    if sql_support == "yes":
        connector_yaml["profile"] = "api_sql"
        sql_mode = Prompt.ask("SQL mode", choices=["api_async", "api_sync"], default="api_async")
        execute_path = Prompt.ask("SQL execute path", default="/sql/execute")
        status_path = Prompt.ask(
            "Execution status path",
            default="/execution/{execution_id}/status",
        )
        results_path = Prompt.ask(
            "Execution results path",
            default="/execution/{execution_id}/results",
        )

        connector_yaml["endpoints"] = [
            {"name": "execute_sql", "path": execute_path, "method": "POST", "body_mode": "json"},
            {"name": "get_execution_status", "path": status_path, "method": "GET"},
            {"name": "get_execution_results", "path": results_path, "method": "GET"},
        ]
        connector_yaml["capabilities"] = {
            "sql": True,
            "supports_validate_sql": False,
            "supports_async_jobs": sql_mode == "api_async",
            "sql_mode": sql_mode,
        }

    connector_yaml_path = connector_path / "connector.yaml"
    with open(connector_yaml_path, "w") as f:
        yaml.dump(connector_yaml, f, default_flow_style=False, sort_keys=False)

    _save_connection_env(name, env_vars)
    console.print(f"\n[green]✓ API connector saved to {connector_yaml_path}[/green]")
    console.print(f"[green]✓ Credentials saved to {_get_connection_env_path(name)}[/green]")

    config = load_config()
    config.update(
        {
            "active_connection": name,
            "tool_mode": "shell",
            "log_level": "INFO",
        }
    )
    config.pop("database_url", None)
    save_config(config)
    console.print(f"[green]✓ Config saved to {CONFIG_FILE}[/green]")
    return True
