"""dbmcp CLI - Standalone CLI for db-mcp MCP server.

Commands:
    db-mcp init [NAME] [GIT_URL]  - Interactive setup wizard (or clone from git)
    dbmcp start                  - Start MCP server (stdio mode)
    dbmcp config                 - Open config in editor
    dbmcp status                 - Show current configuration
    dbmcp list                   - List all connections
    dbmcp use NAME               - Switch active connection
    db-mcp git-init [NAME] [URL]  - Enable git sync for existing connection
    dbmcp sync [NAME]            - Sync changes to git remote
    dbmcp pull [NAME]            - Pull updates from git remote
    dbmcp edit [NAME]            - Edit connection credentials (.env file)
    dbmcp rename OLD NEW         - Rename a connection
    dbmcp remove NAME            - Remove a connection

Global options:
    -c, --connection NAME  - Use specific connection (default: from config)
    all                    - Apply command to all connections (where supported)
"""

# ruff: noqa: E402
# Suppress pydantic logfire plugin warning (must be before any pydantic imports)
import warnings

warnings.filterwarnings("ignore", message=".*logfire.*", category=UserWarning)

import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from db_mcp.agents import (
    AGENTS,
    configure_multiple_agents,
    detect_installed_agents,
)

console = Console()


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

# Config paths
CONFIG_DIR = Path.home() / ".db-mcp"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CONNECTIONS_DIR = CONFIG_DIR / "connections"

# Legacy paths (for migration)
LEGACY_VAULT_DIR = CONFIG_DIR / "vault"
LEGACY_PROVIDERS_DIR = CONFIG_DIR / "providers"


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


def extract_database_url_from_claude_config(claude_config: dict) -> str | None:
    """Extract DATABASE_URL from existing Claude Desktop MCP server configs."""
    mcp_servers = claude_config.get("mcpServers", {})

    # Check db-mcp entry first
    if "db-mcp" in mcp_servers:
        env = mcp_servers["db-mcp"].get("env", {})
        if "DATABASE_URL" in env:
            return env["DATABASE_URL"]

    # Check legacy db-mcp entry
    if "db-mcp" in mcp_servers:
        env = mcp_servers["db-mcp"].get("env", {})
        if "DATABASE_URL" in env:
            return env["DATABASE_URL"]

    return None


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


# =============================================================================
# Git utilities
# =============================================================================

GIT_INSTALL_URL = "https://git-scm.com/downloads"

# Default .gitignore content for connection directories
GITIGNORE_CONTENT = """db-mcp gitignore
# Ignore all dotfiles (local state, credentials, editor files, etc.)
.*
# Exceptions: keep tracked dotfiles
!.gitignore
!.collab.yaml

# Local state (not shared)
state.yaml

# Temp/backup files
*.tmp
*.bak
*~
"""


def is_git_installed() -> bool:
    """Check if git is installed and available (native or dulwich fallback)."""
    # Always returns True now since we have dulwich fallback
    return True


def is_git_repo(path: Path) -> bool:
    """Check if a directory is a git repository."""
    from db_mcp.git_utils import git

    return git.is_repo(path)


def git_init(path: Path, remote_url: str | None = None) -> bool:
    """Initialize a git repository in the given path.

    Args:
        path: Directory to initialize
        remote_url: Optional remote URL to add as origin

    Returns:
        True if successful
    """
    from db_mcp.git_utils import git

    try:
        # Initialize repo
        git.init(path)

        # Create .gitignore
        gitignore_path = path / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(GITIGNORE_CONTENT)

        # Initial commit
        git.add(path, ["."])
        git.commit(path, "Initial db-mcp connection setup")

        # Add remote if provided
        if remote_url:
            git.remote_add(path, "origin", remote_url)

        return True
    except Exception as e:
        console.print(f"[red]Git error: {e}[/red]")
        return False


def git_clone(url: str, dest: Path) -> bool:
    """Clone a git repository.

    Args:
        url: Git URL to clone
        dest: Destination path

    Returns:
        True if successful
    """
    from db_mcp.git_utils import git

    try:
        git.clone(url, dest)
        return True
    except NotImplementedError:
        console.print("[red]Clone requires native git to be installed.[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Git clone failed: {e}[/red]")
        return False


def git_sync(path: Path) -> bool:
    """Sync local changes to remote (add, commit, pull --rebase, push).

    Args:
        path: Git repository path

    Returns:
        True if successful
    """
    from datetime import datetime

    from db_mcp.git_utils import git

    try:
        # Check for changes
        changes = git.status(path)
        has_changes = bool(changes)

        if has_changes:
            # Add all changes
            git.add(path, ["."])

            # Commit with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            git.commit(path, f"dbmcp sync {timestamp}")
            console.print("[green]✓ Changes committed[/green]")
        else:
            console.print("[dim]No local changes to commit.[/dim]")

        # Check if remote exists
        if not git.has_remote(path):
            console.print(
                "[yellow]No remote configured. Use 'git remote add origin <url>'[/yellow]"
            )
            return True

        # Pull with rebase to get remote changes
        console.print("[dim]Pulling remote changes...[/dim]")
        try:
            git.pull(path, rebase=True)
        except Exception as e:
            error_msg = str(e).lower()
            if "conflict" in error_msg:
                console.print("[yellow]Merge conflict detected.[/yellow]")
                console.print("[dim]Resolve conflicts manually, then run:[/dim]")
                console.print(f"  cd {path}")
                console.print("  git add .")
                console.print("  git rebase --continue")
                console.print("  dbmcp sync")
                return False
            elif "couldn't find remote ref" in error_msg:
                # Remote branch doesn't exist yet, that's ok
                pass
            else:
                console.print(f"[yellow]Pull warning: {e}[/yellow]")

        # Push changes
        console.print("[dim]Pushing to remote...[/dim]")
        try:
            git.push(path)
        except Exception as e:
            error_msg = str(e).lower()
            if "rejected" in error_msg:
                console.print("[yellow]Push rejected. Try 'dbmcp pull' first.[/yellow]")
                return False
            else:
                console.print(f"[red]Push failed: {e}[/red]")
                return False

        console.print("[green]✓ Synced with remote[/green]")
        return True

    except Exception as e:
        console.print(f"[red]Git error: {e}[/red]")
        return False


def git_pull(path: Path) -> bool:
    """Pull changes from remote.

    Args:
        path: Git repository path

    Returns:
        True if successful
    """
    from db_mcp.git_utils import git

    try:
        # Check for uncommitted changes
        changes = git.status(path)
        stashed = False

        if changes:
            console.print("[yellow]You have uncommitted changes.[/yellow]")
            console.print("[dim]Stashing changes before pull...[/dim]")
            try:
                git.stash(path)
                stashed = True
            except NotImplementedError:
                console.print(
                    "[yellow]Stash requires native git. Commit your changes first.[/yellow]"
                )
                return False

        # Pull
        try:
            git.pull(path, rebase=True)
        except Exception as e:
            error_msg = str(e).lower()
            if "conflict" in error_msg:
                console.print("[yellow]Merge conflict detected.[/yellow]")
                console.print(f"[dim]Resolve conflicts in {path}[/dim]")
                return False
            elif "couldn't find remote ref" in error_msg:
                console.print("[dim]Remote branch not found (may not exist yet).[/dim]")
            else:
                console.print(f"[yellow]Pull warning: {e}[/yellow]")

        # Pop stash if we stashed
        if stashed:
            try:
                git.stash_pop(path)
                console.print("[dim]Restored local changes.[/dim]")
            except Exception:
                console.print("[yellow]Conflict applying stashed changes.[/yellow]")
                console.print("[dim]Resolve conflicts manually.[/dim]")
                return False

        console.print("[green]✓ Pulled from remote[/green]")
        return True

    except Exception as e:
        console.print(f"[red]Git error: {e}[/red]")
        return False


def is_git_url(s: str) -> bool:
    """Check if a string looks like a git URL."""
    if not s:
        return False
    # Common git URL patterns
    return (
        s.startswith("git@")
        or s.startswith("https://github.com/")
        or s.startswith("https://gitlab.com/")
        or s.startswith("https://bitbucket.org/")
        or s.endswith(".git")
        or "github.com" in s
        or "gitlab.com" in s
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


def _attach_repo(name: str, connection_path: Path, git_url: str):
    """Attach a shared repo to an existing local connection.

    Merges the master's knowledge into the local connection without
    clobbering local files. Registers as collaborator afterward.
    """
    from db_mcp.collab.classify import classify_files
    from db_mcp.collab.manifest import (
        get_user_name_from_config,
        set_user_name_in_config,
    )
    from db_mcp.git_utils import git

    console.print(
        Panel.fit(
            f"[bold blue]Attach Shared Knowledge[/bold blue]\n\n"
            f"Connection: [cyan]{name}[/cyan]\n"
            f"Repo: [dim]{git_url}[/dim]\n\n"
            "This will merge the team's knowledge into your "
            "existing connection.",
            border_style="blue",
        )
    )

    # Ensure git
    if not is_git_installed():
        console.print("[red]Git is required.[/red]")
        return

    # Init git if not already a repo
    if not is_git_repo(connection_path):
        git.init(connection_path)
        # Commit existing local files so merge has a clean base
        git.add(connection_path, ["."])
        try:
            git.commit(
                connection_path,
                "Initial commit: local connection state",
            )
        except Exception:
            pass  # Nothing to commit (empty dir)
        console.print("[dim]Initialized git repo for existing files.[/dim]")

    # Add remote
    if git.has_remote(connection_path):
        # Check if it's the same URL
        import subprocess

        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=connection_path,
            capture_output=True,
            text=True,
        )
        existing_url = result.stdout.strip()
        if existing_url == git_url:
            console.print("[dim]Remote already set to this URL.[/dim]")
        else:
            console.print(f"[yellow]Remote already set to {existing_url}[/yellow]")
            console.print("[yellow]Remove it first: git remote remove origin[/yellow]")
            return
    else:
        import subprocess

        subprocess.run(
            ["git", "remote", "add", "origin", git_url],
            cwd=connection_path,
            check=True,
        )

    # Fetch remote
    console.print("[dim]Fetching shared knowledge...[/dim]")
    try:
        git.fetch(connection_path)
    except Exception as e:
        console.print(f"[red]Fetch failed: {e}[/red]")
        return

    # Merge with allow-unrelated-histories
    console.print("[dim]Merging team knowledge...[/dim]")
    import subprocess

    merge_result = subprocess.run(
        [
            "git",
            "merge",
            "origin/main",
            "--allow-unrelated-histories",
            "--no-edit",
            "-m",
            "Merge shared knowledge from team repo",
        ],
        cwd=connection_path,
        capture_output=True,
        text=True,
    )

    if merge_result.returncode != 0:
        stderr = merge_result.stderr.strip()
        if "CONFLICT" in merge_result.stdout or "CONFLICT" in stderr:
            # Show conflicts and let user resolve
            console.print(
                "[yellow]Merge conflicts detected. "
                "Your local files conflict with the team repo.[/yellow]"
            )
            console.print("[dim]Resolve conflicts, then run:[/dim]")
            console.print(f"  cd {connection_path}")
            console.print("  git add . && git commit")
            console.print("  db-mcp collab join")
            return
        else:
            console.print(f"[red]Merge failed: {stderr}[/red]")
            return

    # Count what was merged
    try:
        diff_output = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=connection_path,
            capture_output=True,
            text=True,
        )
        merged_files = [f for f in diff_output.stdout.strip().split("\n") if f]
        additive, shared = classify_files(merged_files)
        console.print(
            f"[green]Merged {len(additive)} example/learning files "
            f"and {len(shared)} shared-state files.[/green]"
        )
    except Exception:
        console.print("[green]Merge complete.[/green]")

    # Prompt for user name if needed
    if not get_user_name_from_config():
        user_name = click.prompt("\nYour name (used for branch names and attribution)")
        set_user_name_in_config(user_name)

    # Register as collaborator
    _auto_register_collaborator(connection_path)

    # Push main so the remote has the merged state
    try:
        git.push(connection_path)
    except Exception:
        pass  # Collaborator may not have push to main

    console.print(f"\n[green]Done! '{name}' is now connected to the team repo.[/green]")
    console.print("[dim]Use 'db-mcp collab sync' to stay in sync.[/dim]")


def _init_brownfield(name: str, git_url: str):
    """Initialize connection by cloning from git (brownfield setup)."""
    # Check git is installed
    if not is_git_installed():
        console.print(
            Panel.fit(
                "[bold red]Git Not Found[/bold red]\n\n"
                "Git is required for cloning connection configs.\n\n"
                f"Install from: [cyan]{GIT_INSTALL_URL}[/cyan]",
                border_style="red",
            )
        )
        return

    console.print(
        Panel.fit(
            f"[bold blue]db-mcp Setup (Brownfield)[/bold blue]\n\n"
            f"Clone connection: [cyan]{name}[/cyan]\n"
            f"From: [dim]{git_url}[/dim]",
            border_style="blue",
        )
    )

    connection_path = get_connection_path(name)

    # Connection exists + repo URL → attach (synonym for collab attach)
    if connection_path.exists():
        _attach_repo(name, connection_path, git_url)
        return

    # Clone the repository
    console.print("\n[dim]Cloning repository...[/dim]")
    if not git_clone(git_url, connection_path):
        return

    console.print(f"[green]✓ Cloned to {connection_path}[/green]")

    # Show what was cloned
    console.print("\n[bold]Cloned files:[/bold]")
    for item in sorted(connection_path.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            console.print(f"  [cyan]{item.name}/[/cyan]")
        else:
            console.print(f"  {item.name}")

    # Prompt for user_name early so collaborator registration works smoothly
    from db_mcp.collab.manifest import (
        get_user_name_from_config,
        set_user_name_in_config,
    )

    if not get_user_name_from_config():
        user_name = click.prompt("\nYour name (used for branch names and attribution)")
        set_user_name_in_config(user_name)

    # Now prompt for DATABASE_URL (credentials are not in git)
    _prompt_and_save_database_url(name)

    # Recover onboarding state from cloned files
    _recover_onboarding_state(name, connection_path)

    # Auto-register as collaborator if manifest exists
    _auto_register_collaborator(connection_path)

    # Configure MCP agents
    _configure_agents()

    console.print()
    console.print(
        Panel.fit(
            "[bold green]Setup Complete![/bold green]\n\n"
            "Connection cloned from git.\n"
            "Claude Desktop needs to restart to load the new config.\n\n"
            "[dim]Use 'dbmcp pull' to get updates from the team.[/dim]\n"
            "[dim]Use 'dbmcp sync' to share your changes.[/dim]",
            border_style="green",
        )
    )

    # Offer to launch Claude Desktop
    console.print()
    if Confirm.ask("Launch Claude Desktop now?", default=True):
        launch_claude_desktop()
    else:
        console.print("[dim]Please restart Claude Desktop manually.[/dim]")


def _init_greenfield(name: str):
    """Initialize a new connection from scratch (greenfield setup)."""
    console.print(
        Panel.fit(
            f"[bold blue]db-mcp Setup[/bold blue]\n\nConfigure connection: [cyan]{name}[/cyan]",
            border_style="blue",
        )
    )

    # Load existing Claude Desktop config
    claude_config, claude_config_path = load_claude_desktop_config()
    mcp_servers = claude_config.get("mcpServers", {})

    # Check for existing db-mcp entry
    existing_url = extract_database_url_from_claude_config(claude_config)
    has_db_mcp = "db-mcp" in mcp_servers
    has_legacy = "db-mcp" in mcp_servers

    # Also check ~/.dbmcp/config.yaml for existing URL
    if not existing_url:
        db_mcp_config = load_config()
        existing_url = db_mcp_config.get("database_url")

    # Check if connection already exists
    connection_path = get_connection_path(name)
    if connection_path.exists():
        console.print(f"\n[yellow]Connection '{name}' already exists.[/yellow]")
        if not Confirm.ask("Update configuration?", default=True):
            console.print("[dim]Setup cancelled.[/dim]")
            return
    elif has_db_mcp or has_legacy:
        console.print("\n[yellow]Existing configuration found:[/yellow]")
        if has_db_mcp:
            console.print("  Entry: [cyan]db-mcp[/cyan]")
        if has_legacy:
            console.print("  Entry: [cyan]db-mcp[/cyan] (legacy)")
        if existing_url:
            # Mask password in URL for display
            display_url = existing_url
            if "@" in display_url:
                # Simple password masking
                parts = display_url.split("@")
                prefix = parts[0]
                if ":" in prefix:
                    scheme_user = prefix.rsplit(":", 1)[0]
                    display_url = f"{scheme_user}:****@{parts[1]}"
            console.print(f"  Database: [cyan]{display_url}[/cyan]")
        console.print()
    else:
        console.print(f"\n[dim]Claude Desktop config: {claude_config_path}[/dim]")
        if not claude_config_path.exists():
            console.print("[dim]Will create new config file.[/dim]")

    # Prompt for DATABASE_URL
    database_url = _prompt_and_save_database_url(name, existing_url)
    if not database_url:
        return

    # Create connection directory
    connection_path.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓ Connection directory created: {connection_path}[/green]")

    # Configure MCP agents
    _configure_agents()

    # Run migration if legacy data exists
    if LEGACY_VAULT_DIR.exists() or LEGACY_PROVIDERS_DIR.exists():
        console.print("\n[yellow]Legacy data detected. Running migration...[/yellow]")
        try:
            from db_mcp.vault.migrate import migrate_to_connection_structure

            stats = migrate_to_connection_structure(name)
            if not stats.get("skipped"):
                console.print("[green]✓ Legacy data migrated[/green]")
        except Exception as e:
            console.print(f"[yellow]Migration warning: {e}[/yellow]")

    # Offer git sync setup (only for greenfield, if git is available)
    _offer_git_setup(name, connection_path)

    # Run schema discovery
    console.print()
    if Confirm.ask("Run schema discovery now?", default=True):
        try:
            from db_mcp.connectors import get_connector

            connector = get_connector(str(connection_path))
            result = _run_discovery_with_progress(connector, conn_name=name, save=True)
            if result:
                console.print(
                    f"[green]✓ Discovered {len(result['tables'])} tables "
                    f"with {result['total_columns']} columns[/green]"
                )
        except Exception as e:
            console.print(f"[yellow]Discovery failed: {e}[/yellow]")
            console.print("[dim]You can run discovery later with 'db-mcp discover'[/dim]")

    console.print()
    console.print(
        Panel.fit(
            "[bold green]Setup Complete![/bold green]\n\n"
            "Claude Desktop needs to restart to load the new config.",
            border_style="green",
        )
    )

    # Offer to launch Claude Desktop
    console.print()
    if Confirm.ask("Launch Claude Desktop now?", default=True):
        launch_claude_desktop()
    else:
        console.print("[dim]Please restart Claude Desktop manually.[/dim]")


def _run_discovery_with_progress(
    connector,
    conn_name: str = "cli-discover",
    save: bool = False,
    timeout_s: int = 300,
    schemas: list[str] | None = None,
) -> dict | None:
    """Run schema discovery with Rich progress indicators.

    Args:
        connector: Database connector instance
        conn_name: Connection name (used for schema file if saving)
        save: If True, save schema_descriptions.yaml to the connection dir

    Returns:
        Dict with discovered tables info, or None on failure
    """
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

    from db_mcp.onboarding.schema_store import create_initial_schema

    err_console = Console(stderr=True)
    all_tables: list[dict] = []
    dialect: str | None = None

    # NOTE: SIGALRM cannot reliably interrupt blocking DBAPI calls (e.g., psycopg2),
    # so we run the whole discovery in a daemon thread with a hard deadline.

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=err_console,
        transient=True,
    ) as progress:
        # Start spinner immediately so the user sees *something* before any blocking calls.
        task = progress.add_task("Starting discovery...", total=None)
        progress.refresh()

        result: list[dict | None] = [None]
        error: list[Exception | None] = [None]

        def run() -> None:
            try:
                # Phase 1: Connect
                progress.update(task, description="Connecting...", total=None)
                test_result = connector.test_connection()
                if not test_result.get("connected"):
                    error[0] = RuntimeError(test_result.get("error", "unknown"))
                    return

                nonlocal dialect
                dialect = test_result.get("dialect")
                progress.update(task, description="Connected ✓", completed=1, total=1)

                # Phase 2: Catalogs
                progress.update(
                    task, description="Discovering catalogs...", completed=0, total=None
                )
                try:
                    catalogs = connector.get_catalogs()
                except Exception:
                    catalogs = [None]
                progress.update(
                    task,
                    description=f"Found {len([c for c in catalogs if c])} catalogs ✓",
                    completed=1,
                    total=1,
                )

                # Phase 3: Schemas
                progress.update(
                    task, description="Discovering schemas...", completed=0, total=None
                )
                all_schemas: list[dict] = []
                for catalog in catalogs:
                    try:
                        found = connector.get_schemas(catalog=catalog)
                    except Exception:
                        found = []

                    for schema in found:
                        if schemas and schema not in schemas:
                            continue
                        all_schemas.append({"catalog": catalog, "schema": schema})

                progress.update(
                    task,
                    description=f"Found {len(all_schemas)} schemas ✓",
                    completed=1,
                    total=1,
                )

                # Phase 4: Tables + columns (progress per table)
                progress.remove_task(task)
                table_task = progress.add_task("Scanning tables...", total=1)

                total_tables = 0
                for schema_info in all_schemas:
                    catalog = schema_info["catalog"]
                    schema = schema_info["schema"]
                    label = f"{catalog}.{schema}" if catalog else (schema or "default")
                    progress.update(
                        table_task,
                        description=f"Listing tables in {label}...",
                        total=None,
                    )

                    try:
                        tables = connector.get_tables(schema=schema, catalog=catalog)
                    except Exception:
                        tables = []

                    # update total now that we know table count for this schema
                    total_tables += len(tables)
                    progress.update(table_task, total=max(total_tables, 1))

                    for t in tables:
                        progress.update(
                            table_task,
                            description=f"Scanning {t.get('full_name') or t.get('name')}...",
                        )
                        try:
                            columns = connector.get_columns(
                                t["name"], schema=schema, catalog=catalog
                            )
                        except Exception:
                            columns = []
                        all_tables.append(
                            {
                                "name": t["name"],
                                "schema": schema,
                                "catalog": catalog,
                                "full_name": t.get("full_name") or t["name"],
                                "columns": columns,
                            }
                        )
                        progress.advance(table_task)

                result[0] = {
                    "tables": all_tables,
                    "total_columns": sum(len(t["columns"]) for t in all_tables),
                    "dialect": dialect,
                }
            except Exception as e:
                error[0] = e

        import threading

        t = threading.Thread(target=run, daemon=True)
        t.start()
        if timeout_s > 0:
            t.join(timeout=timeout_s)
        else:
            t.join()

        if t.is_alive():
            console.print(f"[red]Discovery timed out after {timeout_s}s[/red]")
            return None

        if error[0] is not None:
            console.print(f"[red]Discovery failed: {error[0]}[/red]")
            return None

        if result[0] is None:
            console.print("[red]Discovery failed: unknown error[/red]")
            return None

    total_columns = sum(len(t["columns"]) for t in all_tables)
    err_console.print(
        f"[green]Done![/green] Found [bold]{len(all_tables)}[/bold] tables "
        f"with [bold]{total_columns}[/bold] columns."
    )

    # Build schema object
    schema_obj = create_initial_schema(
        provider_id=conn_name,
        dialect=dialect,
        tables=all_tables,
    )

    # Optionally save to connection directory
    if save:
        from db_mcp.onboarding.schema_store import save_schema_descriptions

        schema_obj.provider_id = conn_name
        save_result = save_schema_descriptions(schema_obj)
        if save_result.get("saved"):
            err_console.print(f"[green]✓ Schema saved to {save_result.get('file_path')}[/green]")

    return {
        "tables": all_tables,
        "total_columns": total_columns,
        "dialect": dialect,
        "schema": schema_obj,
    }


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


def _configure_agents_interactive(preselect_installed: bool = True) -> list[str]:
    """Interactive agent selection.

    Args:
        preselect_installed: If True, pre-select detected agents

    Returns:
        List of agent IDs to configure
    """
    # Detect installed agents
    installed = detect_installed_agents()

    if not installed:
        console.print("[yellow]No MCP agents detected on this system.[/yellow]")
        console.print("[dim]Skipping agent configuration.[/dim]")
        return []

    # Show detected agents
    console.print("\n[bold]Detected MCP-compatible agents:[/bold]")
    for i, agent_id in enumerate(installed, 1):
        agent = AGENTS[agent_id]
        console.print(f"  [{i}] {agent.name}")

    # Prompt for selection
    console.print("\n[dim]Configure db-mcp for which agents?[/dim]")
    console.print("[1] All detected agents")
    console.print("[2] Select specific agents")
    console.print("[3] Skip agent configuration")

    choice = Prompt.ask("Choice", choices=["1", "2", "3"], default="1")

    if choice == "3":
        return []
    elif choice == "1":
        return installed
    else:
        # Individual selection
        selected = []
        for agent_id in installed:
            agent = AGENTS[agent_id]
            if Confirm.ask(f"Configure {agent.name}?", default=preselect_installed):
                selected.append(agent_id)
        return selected


def _configure_agents(agent_ids: list[str] | None = None) -> None:
    """Configure MCP agents for db-mcp.

    Args:
        agent_ids: List of agent IDs to configure. If None, uses interactive selection.
    """
    if agent_ids is None:
        agent_ids = _configure_agents_interactive()

    if not agent_ids:
        console.print("[dim]No agents selected for configuration.[/dim]")
        return

    # Get binary path
    binary_path = get_db_mcp_binary_path()

    # Configure each agent
    results = configure_multiple_agents(agent_ids, binary_path)

    # Show summary
    success_count = sum(1 for success in results.values() if success)
    console.print(f"\n[green]✓ Configured {success_count}/{len(agent_ids)} agent(s)[/green]")


def _configure_claude_desktop(name: str):
    """Configure Claude Desktop for db-mcp (legacy wrapper).

    Deprecated: Use _configure_agents instead.
    """
    binary_path = get_db_mcp_binary_path()
    from db_mcp.agents import configure_agent_for_dbmcp

    configure_agent_for_dbmcp("claude-desktop", binary_path)


def _recover_onboarding_state(name: str, connection_path: Path):
    """Recover onboarding state from cloned files.

    When cloning from git, state.yaml is not included (gitignored).
    This reconstructs the state based on existing schema/domain files.
    """
    # Set environment so state module uses correct path
    os.environ["CONNECTION_NAME"] = name
    os.environ["CONNECTIONS_DIR"] = str(CONNECTIONS_DIR)

    # Check what files exist
    schema_file = connection_path / "schema" / "descriptions.yaml"
    domain_file = connection_path / "domain" / "model.md"

    has_schema = schema_file.exists()
    has_domain = domain_file.exists()

    if not has_schema and not has_domain:
        console.print("[dim]No existing schema/domain files found.[/dim]")
        return

    # Import here to avoid circular imports and ensure env is set
    from db_mcp.onboarding.state import load_state

    # load_state will auto-recover and save if files exist but state doesn't
    state = load_state()

    if state:
        console.print(f"[green]✓ Onboarding state recovered: {state.phase.value}[/green]")
        if has_schema:
            console.print(f"  [dim]Schema: {state.tables_total} tables[/dim]")
        if has_domain:
            console.print("  [dim]Domain model: ready[/dim]")


def _auto_register_collaborator(connection_path: Path) -> None:
    """Auto-register as collaborator when cloning a vault with .collab.yaml.

    Called during brownfield init (db-mcp init <name> <git-url>).
    If the cloned repo has a collaboration manifest, this:
    1. Prompts for user_name if not in config
    2. Gets or generates user_id
    3. Creates collaborator/{user_name} branch
    4. Adds self to .collab.yaml and commits+pushes the branch
    """
    from db_mcp.collab.manifest import (
        add_member,
        get_member,
        get_user_name_from_config,
        load_manifest,
        save_manifest,
        set_user_name_in_config,
    )
    from db_mcp.git_utils import git
    from db_mcp.traces import generate_user_id, get_user_id_from_config

    manifest = load_manifest(connection_path)
    if manifest is None:
        return  # No collab manifest — nothing to do

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

    # Skip if already registered
    if get_member(manifest, user_id) is not None:
        console.print(f"[dim]Already registered as collaborator: {user_name}[/dim]")
        return

    # Create collaborator branch
    branch = f"collaborator/{user_name}"
    git.checkout(connection_path, branch, create=True)

    # Add self to manifest
    manifest = add_member(manifest, user_name, user_id, "collaborator")
    save_manifest(connection_path, manifest)
    git.add(connection_path, [".collab.yaml"])
    git.commit(connection_path, f"Add collaborator: {user_name}")
    try:
        git.push_branch(connection_path, branch)
        console.print(f"[green]Registered as collaborator: {user_name}[/green]")
        console.print(f"[dim]Branch: {branch} | User ID: {user_id}[/dim]")
    except Exception as e:
        console.print(
            f"[yellow]Registered locally but push failed (retry with 'collab sync'): {e}[/yellow]"
        )


def _offer_git_setup(name: str, connection_path: Path):
    """Offer to set up git sync for the connection."""
    # Skip if already a git repo (e.g., from brownfield)
    if is_git_repo(connection_path):
        return

    # Check if git is installed
    if not is_git_installed():
        console.print("\n[dim]Tip: Install git to enable team sync features.[/dim]")
        console.print(f"[dim]     {GIT_INSTALL_URL}[/dim]")
        return

    console.print("\n[bold]Git Sync (Optional)[/bold]")
    console.print("[dim]Enable git to share your semantic layer with your team.[/dim]")

    if not Confirm.ask("Enable git sync for this connection?", default=False):
        return

    # Ask for remote URL (optional)
    console.print(
        "\n[dim]Enter a git remote URL to sync with (or leave empty to add later).[/dim]"
    )
    console.print("[dim]Example: git@github.com:yourorg/db-mcp-mydb.git[/dim]")
    remote_url = Prompt.ask("Git remote URL", default="")

    # Initialize git
    if git_init(connection_path, remote_url if remote_url else None):
        console.print("[green]✓ Git repository initialized[/green]")
        if remote_url:
            console.print(f"[dim]Remote 'origin' set to {remote_url}[/dim]")
            console.print("[dim]Use 'dbmcp sync' to push changes to the team.[/dim]")
        else:
            console.print("[dim]Add a remote later with: git remote add origin <url>[/dim]")
            console.print("[dim]Then use 'dbmcp sync' to push changes.[/dim]")


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
    import subprocess

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
    import threading
    import urllib.request
    import webbrowser

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
        from db_mcp.connectors import get_connector

        connector = get_connector(str(conn_path))

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
        output_str = json.dumps(schema_dict, indent=2, ensure_ascii=False)
    else:
        output_str = yaml.dump(
            schema_dict, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    # Output
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(output_str)
        Console(stderr=True).print(f"[green]Schema written to {output}[/green]")
    else:
        click.echo(output_str)


if __name__ == "__main__":
    main()
