"""GitHub PR helper using the gh CLI.

Provides a thin wrapper around `gh pr create` for opening pull requests
from collaborator branches. Falls back gracefully when gh is not installed.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def gh_available() -> bool:
    """Check if the GitHub CLI (gh) is installed."""
    return shutil.which("gh") is not None


def open_pr(
    connection_path: Path,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> str | None:
    """Open a pull request via gh CLI.

    Returns the PR URL on success, or None on failure.
    """
    if not gh_available():
        logger.info("gh CLI not found — cannot open PR automatically")
        return None

    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--head",
                branch,
                "--base",
                base,
                "--title",
                title,
                "--body",
                body,
            ],
            cwd=connection_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            logger.info("PR opened: %s", url)
            return url
        else:
            # PR may already exist
            if "already exists" in result.stderr:
                logger.info("PR already exists for branch %s", branch)
                return None
            logger.warning("gh pr create failed: %s", result.stderr.strip())
            return None
    except Exception as e:
        logger.warning("Failed to create PR: %s", e)
        return None


def list_prs(
    connection_path: Path,
    author: str | None = None,
    state: str = "open",
) -> list[dict]:
    """List pull requests via gh CLI.

    Returns list of PR dicts with keys: number, title, url, head, state.
    """
    if not gh_available():
        return []

    try:
        args = [
            "gh",
            "pr",
            "list",
            "--state",
            state,
            "--json",
            "number,title,url,headRefName,state",
        ]
        if author:
            args.extend(["--author", author])

        result = subprocess.run(
            args,
            cwd=connection_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return []
    except Exception as e:
        logger.warning("Failed to list PRs: %s", e)
        return []
