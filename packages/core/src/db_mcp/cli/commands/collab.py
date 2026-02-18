"""Collaboration commands: collab subgroup with all sub-commands."""

import subprocess
import sys

import click

from db_mcp.cli.connection import (
    connection_exists,
    get_active_connection,
    get_connection_path,
)
from db_mcp.cli.git_ops import is_git_repo
from db_mcp.cli.init_flow import _attach_repo, _auto_register_collaborator
from db_mcp.cli.utils import console, load_config, save_config


@click.group()
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


def register_commands(main_group: click.Group) -> None:
    """Register the collab group with the main group."""
    main_group.add_command(collab)
