"""Init flow implementations for the db-mcp CLI.

Implements the three init paths:
- _init_greenfield: new connection from scratch
- _init_brownfield: clone from git URL
- _attach_repo: attach shared repo to existing connection

Also includes helpers called during init:
_recover_onboarding_state, _auto_register_collaborator, _offer_git_setup.
"""

import os
import subprocess
from pathlib import Path

import click
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from db_mcp.cli.agent_config import _configure_agents
from db_mcp.cli.connection import (
    _load_connection_env,
    _prompt_and_save_database_url,
    get_connection_path,
)
from db_mcp.cli.discovery import _run_discovery_with_progress
from db_mcp.cli.git_ops import (
    GIT_INSTALL_URL,
    git_clone,
    git_init,
    is_git_installed,
    is_git_repo,
)
from db_mcp.cli.utils import (
    CONNECTIONS_DIR,
    LEGACY_PROVIDERS_DIR,
    LEGACY_VAULT_DIR,
    console,
    launch_claude_desktop,
    load_config,
    save_config,
)


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
        from db_mcp.git_utils import git as _git

        _git.push(connection_path)
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
    from db_mcp.cli.agent_config import extract_database_url_from_claude_config
    from db_mcp.cli.utils import load_claude_desktop_config

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
