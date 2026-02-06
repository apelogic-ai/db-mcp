"""Master merge logic.

Provides tools for the master to auto-merge additive changes from
collaborator branches and flag shared-state changes for PR review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from db_mcp.collab.classify import classify_files
from db_mcp.collab.github import gh_available, open_pr
from db_mcp.git_utils import git

logger = logging.getLogger(__name__)


@dataclass
class CollaboratorMergeResult:
    """Merge result for a single collaborator."""

    user_name: str
    additive_merged: int = 0
    shared_state_files: list[str] = field(default_factory=list)
    pr_opened: bool = False
    pr_url: str | None = None
    error: str | None = None


@dataclass
class MergeResult:
    """Aggregate merge result across all collaborators."""

    collaborators: list[CollaboratorMergeResult] = field(default_factory=list)

    @property
    def total_additive(self) -> int:
        return sum(c.additive_merged for c in self.collaborators)

    @property
    def total_prs(self) -> int:
        return sum(1 for c in self.collaborators if c.pr_opened)


def _list_remote_collaborator_branches(connection_path: Path) -> list[str]:
    """List remote collaborator/* branch names."""
    try:
        result = git._run(
            ["branch", "-r", "--list", "origin/collaborator/*"],
            cwd=connection_path,
        )
    except Exception:
        return []
    branches = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line and line.startswith("origin/collaborator/"):
            # Strip the "origin/" prefix for local reference
            branches.append(line)
    return branches


def master_merge_all(connection_path: Path) -> MergeResult:
    """Fetch all collaborator branches and process their changes.

    For each collaborator branch:
    1. Diff against main
    2. Classify files
    3. If only additive: merge into main
    4. If shared-state: open PR (or log for manual review)
    """
    result = MergeResult()

    # Ensure we're on main
    current = git.current_branch(connection_path)
    if current != "main":
        git.checkout(connection_path, "main")

    # Fetch all remote branches
    git.fetch(connection_path)

    # Find collaborator branches
    remote_branches = _list_remote_collaborator_branches(connection_path)
    if not remote_branches:
        logger.info("No remote collaborator branches found")
        return result

    for remote_branch in remote_branches:
        # Extract user_name from "origin/collaborator/{name}"
        user_name = remote_branch.split("origin/collaborator/", 1)[-1]
        collab_result = CollaboratorMergeResult(user_name=user_name)

        try:
            # Diff remote branch against main
            diff_files = git.diff_names(connection_path, "main", remote_branch)
            if not diff_files:
                continue

            additive, shared = classify_files(diff_files)
            collab_result.additive_merged = len(additive)
            collab_result.shared_state_files = shared

            if not shared:
                # All additive — safe to merge directly
                git.merge(connection_path, remote_branch)
                logger.info(
                    "Auto-merged %d additive files from %s",
                    len(additive),
                    user_name,
                )
            else:
                # Shared-state changes — open PR or log
                local_branch = f"collaborator/{user_name}"
                if gh_available():
                    title = f"[db-mcp] Changes from {user_name}"
                    body_lines = ["## Changes\n"]
                    if additive:
                        body_lines.append("### Auto-mergeable (additive)")
                        for f in additive:
                            body_lines.append(f"- `{f}`")
                    body_lines.append("\n### Needs review (shared-state)")
                    for f in shared:
                        body_lines.append(f"- `{f}`")
                    body = "\n".join(body_lines)
                    pr_url = open_pr(connection_path, local_branch, title, body)
                    if pr_url:
                        collab_result.pr_opened = True
                        collab_result.pr_url = pr_url
                else:
                    logger.info(
                        "Shared-state changes from %s on branch '%s' — "
                        "review and merge manually on GitHub.",
                        user_name,
                        local_branch,
                    )
        except Exception as e:
            collab_result.error = str(e)
            logger.warning("Error processing branch for %s: %s", user_name, e)

        result.collaborators.append(collab_result)

    # Push main if we merged anything
    if result.total_additive > 0:
        try:
            git.push(connection_path)
        except Exception as e:
            logger.warning("Push main failed: %s", e)

    return result
