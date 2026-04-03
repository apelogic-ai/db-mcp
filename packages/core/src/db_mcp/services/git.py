"""Git history, revert, and auto-commit services.

Provides service functions for retrieving file commit history, reading file
content at a specific commit, reverting a file to a prior commit, and a
standalone git-commit helper used by vault/metrics services.
The BICP agent delegates to these functions instead of embedding the logic
inline.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers — easy to mock in tests.
# ---------------------------------------------------------------------------


def _get_git():
    from db_mcp_knowledge.git_utils import git

    return git


def _is_conn_path_valid(conn_path: Path) -> bool:
    return conn_path.exists()


def _is_git_enabled(conn_path: Path) -> bool:
    return (conn_path / ".git").exists()


def _validate_path(path: str) -> str | None:
    """Return an error message if *path* is unsafe, else None."""
    if ".." in path or path.startswith("/"):
        return "Invalid path"
    return None


def _validate_commit(commit: str) -> str | None:
    """Return an error message if *commit* looks unsafe, else None."""
    if not commit.replace("-", "").isalnum():
        return "Invalid commit hash"
    return None


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------


def try_git_commit(conn_path: Path, message: str, files: list[str]) -> bool:
    """Commit *files* inside *conn_path* if a .git directory is present.

    Returns True when a commit was made, False when git is not enabled or
    when there is nothing to commit.  Swallows all exceptions.
    """
    if not _is_git_enabled(conn_path):
        return False
    git = _get_git()
    try:
        git.add(conn_path, files)
        result = git.commit(conn_path, message)
        return bool(result)
    except Exception as exc:
        logger.warning("Git commit failed: %s", exc)
        return False


def get_git_history(conn_path: Path, path: str, limit: int = 50) -> dict:
    """Return the commit history for *path* inside *conn_path*.

    Args:
        conn_path: Resolved connection directory (e.g. ``~/.db-mcp/myconn``).
        path: Relative path within *conn_path*.
        limit: Maximum number of commits to return.

    Returns:
        ``{"success": True, "commits": [...]}`` on success, or
        ``{"success": False, "error": str}`` on failure.

        Each commit dict has keys: ``hash``, ``fullHash``, ``message``,
        ``date`` (ISO-8601), ``author``.
    """
    if path_err := _validate_path(path):
        return {"success": False, "commits": [], "error": path_err}

    if not _is_conn_path_valid(conn_path):
        return {"success": False, "commits": [], "error": f"Connection '{conn_path.name}' not found"}  # noqa: E501

    if not _is_git_enabled(conn_path):
        return {"success": False, "commits": [], "error": "Git is not enabled for this connection"}

    file_path = conn_path / path
    if not file_path.exists():
        return {"success": False, "commits": [], "error": f"File not found: {path}"}

    try:
        git = _get_git()
        commits_list = git.log(conn_path, path, limit=limit)
        commits = [
            {
                "hash": c.hash,
                "fullHash": c.full_hash,
                "message": c.message,
                "date": c.date.isoformat(),
                "author": c.author,
            }
            for c in commits_list
        ]
        return {"success": True, "commits": commits}
    except Exception as e:
        return {"success": False, "commits": [], "error": f"Git error: {e}"}


def get_git_content(conn_path: Path, path: str, commit: str) -> dict:
    """Return the content of *path* at *commit* inside *conn_path*.

    Args:
        conn_path: Resolved connection directory.
        path: Relative path within *conn_path*.
        commit: Commit hash (short or full).

    Returns:
        ``{"success": True, "content": str, "commit": str}`` on success, or
        ``{"success": False, "error": str}`` on failure.
    """
    if path_err := _validate_path(path):
        return {"success": False, "error": path_err}

    if commit_err := _validate_commit(commit):
        return {"success": False, "error": commit_err}

    if not _is_conn_path_valid(conn_path):
        return {"success": False, "error": f"Connection '{conn_path.name}' not found"}

    if not _is_git_enabled(conn_path):
        return {"success": False, "error": "Git is not enabled for this connection"}

    try:
        git = _get_git()
        content = git.show(conn_path, path, commit)
        return {"success": True, "content": content, "commit": commit}
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Git error: {e}"}


def revert_git_file(conn_path: Path, path: str, commit: str) -> dict:
    """Revert *path* inside *conn_path* to its content at *commit*.

    Retrieves the file content at *commit*, writes it back to disk, then
    creates a new git commit recording the revert.

    Args:
        conn_path: Resolved connection directory.
        path: Relative path within *conn_path*.
        commit: Commit hash to revert to.

    Returns:
        ``{"success": True, "message": str}`` on success, or
        ``{"success": False, "error": str}`` on failure.
    """
    if path_err := _validate_path(path):
        return {"success": False, "error": path_err}

    if commit_err := _validate_commit(commit):
        return {"success": False, "error": commit_err}

    if not _is_conn_path_valid(conn_path):
        return {"success": False, "error": f"Connection '{conn_path.name}' not found"}

    if not _is_git_enabled(conn_path):
        return {"success": False, "error": "Git is not enabled for this connection"}

    try:
        git = _get_git()
        content = git.show(conn_path, path, commit)

        file_path = conn_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        git.add(conn_path, [path])
        git.commit(conn_path, f"Revert {path} to {commit[:7]}")

        return {"success": True, "message": f"Reverted {path} to commit {commit[:7]}"}
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Git revert error: {e}"}
