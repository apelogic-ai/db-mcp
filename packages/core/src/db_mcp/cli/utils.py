"""Utility functions for the db-mcp CLI.

Shared helpers: config I/O, paths, version, signal handling,
Claude Desktop detection/launch.
"""

# ruff: noqa: E402
# Suppress pydantic logfire plugin warning (must be before any pydantic imports)
import warnings

warnings.filterwarnings("ignore", message=".*logfire.*", category=UserWarning)

import json
import os
import platform
import signal
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import yaml
from rich.console import Console

console = Console()

# Config paths
CONFIG_DIR = Path.home() / ".db-mcp"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CONNECTIONS_DIR = CONFIG_DIR / "connections"

# Legacy paths (for migration)
LEGACY_VAULT_DIR = CONFIG_DIR / "vault"
LEGACY_PROVIDERS_DIR = CONFIG_DIR / "providers"


def _get_cli_version() -> str:
    """Get installed package version.

    Falls back to "unknown" when package metadata isn't available
    (e.g. running from a source checkout without installation).
    """
    try:
        return version("db-mcp")
    except PackageNotFoundError:
        return "unknown"


def _handle_sigint(signum, frame):
    """Handle Ctrl-C gracefully."""
    console.print("\n[dim]Cancelled.[/dim]")
    sys.exit(130)


# Register signal handler early to catch Ctrl-C before Click processes it
signal.signal(signal.SIGINT, _handle_sigint)


def load_config() -> dict:
    """Load config from file."""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict) -> None:
    """Save config to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def get_claude_desktop_config_path() -> Path:
    """Get Claude Desktop config path for current OS."""
    system = platform.system()
    if system == "Darwin":  # macOS
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    else:  # Linux
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_db_mcp_binary_path() -> str:
    """db-mcp binary (or script in dev mode).

    Re-exported from agents module for backward compatibility.
    """
    from db_mcp.agents import get_db_mcp_binary_path as _get_binary_path

    return _get_binary_path()


def load_claude_desktop_config() -> tuple[dict, Path]:
    """Load Claude Desktop config.

    Returns (config_dict, config_path).
    """
    config_path = get_claude_desktop_config_path()

    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f), config_path
        except json.JSONDecodeError:
            console.print(f"[red]Invalid JSON in {config_path}[/red]")
            return {}, config_path

    return {}, config_path


def save_claude_desktop_config(config: dict, config_path: Path) -> None:
    """Save Claude Desktop config."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def is_claude_desktop_installed() -> bool:
    """Check if Claude Desktop is installed."""
    system = platform.system()

    if system == "Darwin":  # macOS
        app_path = Path("/Applications/Claude.app")
        return app_path.exists()
    elif system == "Windows":
        # Check common install locations
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            claude_path = Path(local_app_data) / "Programs" / "Claude" / "Claude.exe"
            if claude_path.exists():
                return True
        program_files = os.environ.get("PROGRAMFILES", "")
        if program_files:
            claude_path = Path(program_files) / "Claude" / "Claude.exe"
            if claude_path.exists():
                return True
        return False
    else:  # Linux
        # Check common locations
        for path in [
            "/usr/bin/claude",
            "/usr/local/bin/claude",
            Path.home() / ".local" / "bin" / "claude",
        ]:
            if Path(path).exists():
                return True
        return False


def launch_claude_desktop() -> None:
    """Launch Claude Desktop application."""
    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["open", "-a", "Claude"], check=True)
            console.print("[green]✓ Claude Desktop launched[/green]")
        elif system == "Windows":
            # Try common install locations
            subprocess.run(["start", "claude"], shell=True, check=True)
            console.print("[green]✓ Claude Desktop launched[/green]")
        else:
            console.print("[dim]Please launch Claude Desktop manually.[/dim]")
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[dim]Could not auto-launch. Please start Claude Desktop manually.[/dim]")
