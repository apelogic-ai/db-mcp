"""Git operations for the db-mcp CLI.

Wraps dulwich/native git via db_mcp.git_utils for connection directory
version control: init, clone, sync (commit+pull+push), pull.
"""

from pathlib import Path

from db_mcp.cli.utils import console

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
            if "couldn't find remote ref" in error_msg:
                console.print("[dim]Remote branch not found (may not exist yet).[/dim]")
                return True
            console.print(f"[yellow]Pull warning: {e}[/yellow]")
            return False

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
