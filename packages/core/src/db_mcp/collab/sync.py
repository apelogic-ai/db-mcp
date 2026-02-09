"""Collaborator sync engine.

Handles the push/pull cycle for collaborators:
1. Pull latest main
2. Commit local changes to collaborator/{user_name} branch
3. Classify changes (additive vs shared-state)
4. Auto-merge additive to main, open PR for shared-state
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from db_mcp.collab.classify import classify_files, is_auto_mergeable_shared
from db_mcp.collab.github import gh_available, open_pr
from db_mcp.git_utils import git

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""

    additive_merged: int = 0
    shared_state_files: list[str] = field(default_factory=list)
    pr_opened: bool = False
    pr_url: str | None = None
    error: str | None = None


def _branch_name(user_name: str) -> str:
    """Get the collaborator branch name."""
    return f"collaborator/{user_name}"


def _ensure_branch(connection_path: Path, branch: str) -> None:
    """Switch to the collaborator branch, creating it if it doesn't exist."""
    current = git.current_branch(connection_path)
    if current == branch:
        return
    try:
        git.checkout(connection_path, branch)
    except Exception:
        # Branch doesn't exist yet — create it
        git.checkout(connection_path, branch, create=True)


def collaborator_pull(connection_path: Path, user_name: str) -> None:
    """Pull latest main into the collaborator branch.

    Fetches origin, checks out the collaborator branch, and merges
    origin/main to pick up changes from other collaborators.
    """
    branch = _branch_name(user_name)

    # Fetch latest from remote
    git.fetch(connection_path)

    # Ensure we're on our branch (create if needed)
    _ensure_branch(connection_path, branch)

    # Merge origin/main into our branch (brings in shared changes)
    try:
        git.merge(connection_path, "origin/main")
    except Exception as e:
        logger.warning("Merge from origin/main failed (may need manual resolution): %s", e)
        raise


def collaborator_push(connection_path: Path, user_name: str) -> SyncResult:
    """Commit local changes and push, auto-merging additive files.

    1. Stage and commit all changes to collaborator/{user_name}
    2. Diff against main to find what changed
    3. Classify files as additive or shared-state
    4. If only additive: merge to main and push both
    5. If shared-state: push branch and open PR
    """
    branch = _branch_name(user_name)
    result = SyncResult()

    # Ensure we're on our branch (create if needed)
    _ensure_branch(connection_path, branch)

    # Stage and commit any local changes
    changed_locally = git.status(connection_path)
    if not changed_locally:
        return result

    git.add(connection_path, ["."])
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    commit_hash = git.commit(connection_path, f"collab sync {timestamp}")
    if commit_hash is None:
        return result

    # Find what differs from main (using merge-base to only see our changes)
    try:
        try:
            base_ref = git.merge_base(connection_path, "main", branch)
        except Exception:
            base_ref = "main"
        diff_files = git.diff_names(connection_path, base_ref, branch)
    except Exception:
        try:
            base_ref = git.merge_base(connection_path, "master", branch)
        except Exception:
            base_ref = "master"
        diff_files = git.diff_names(connection_path, base_ref, branch)

    if not diff_files:
        return result

    additive, shared = classify_files(diff_files)
    result.shared_state_files = shared

    # Determine which shared files are safe to auto-merge (e.g. .collab.yaml)
    auto_shared = [f for f in shared if f in (".collab.yaml",)]
    real_shared = [f for f in shared if f not in (".collab.yaml",)]

    # Files to auto-merge: additive + auto-mergeable shared
    auto_merge_files = additive + auto_shared

    if auto_merge_files:
        if not real_shared:
            # No real shared-state — full branch merge (simpler, preserves history)
            try:
                git.checkout(connection_path, "main")
                git.merge(connection_path, branch)
                try:
                    git.push(connection_path)
                except Exception as e:
                    logger.warning("Push main failed: %s", e)
                    result.error = str(e)
                result.additive_merged = len(auto_merge_files)
                git.checkout(connection_path, branch)
            except Exception as merge_error:
                logger.warning("Auto-merge failed, falling back to PR: %s", merge_error)
                try:
                    git.merge_abort(connection_path)
                except Exception:
                    pass
                try:
                    git.checkout(connection_path, branch)
                except Exception:
                    pass
                result.additive_merged = 0
                real_shared = shared + additive
        else:
            # Mixed: selective checkout of additive files into main
            try:
                git.checkout(connection_path, "main")
                for f in auto_merge_files:
                    try:
                        git.checkout_file(connection_path, branch, f)
                    except Exception:
                        logger.warning("Could not checkout %s from branch", f)
                        continue
                git.add(connection_path, ["."])
                commit_msg = f"Auto-merge additive files from {user_name}"
                git.commit(connection_path, commit_msg)
                try:
                    git.push(connection_path)
                except Exception as e:
                    logger.warning("Push main failed: %s", e)
                    result.error = str(e)
                result.additive_merged = len(auto_merge_files)
                git.checkout(connection_path, branch)
            except Exception as e:
                logger.warning("Selective merge failed: %s", e)
                try:
                    git.checkout(connection_path, branch)
                except Exception:
                    pass
                result.additive_merged = 0

    if real_shared:
        # Shared-state changes present — push branch and open PR
        try:
            git.push_branch(connection_path, branch, force_with_lease=True)
        except Exception as e:
            logger.warning("Push branch failed: %s", e)
            result.error = str(e)
            return result

        # Try to open a PR via gh CLI
        if gh_available():
            title = f"[db-mcp] Sync from {user_name}"
            body_lines = ["## Changes\n"]
            if additive:
                body_lines.append("### Auto-mergeable (additive)")
                for f in additive:
                    body_lines.append(f"- `{f}`")
            if shared:
                body_lines.append("\n### Needs review (shared-state)")
                for f in shared:
                    body_lines.append(f"- `{f}`")
            body = "\n".join(body_lines)
            pr_url = open_pr(connection_path, branch, title, body)
            if pr_url:
                result.pr_opened = True
                result.pr_url = pr_url
        else:
            logger.info(
                "gh CLI not available — push succeeded to branch '%s', "
                "please open a PR manually on GitHub.",
                branch,
            )

    return result


def full_sync(connection_path: Path, user_name: str) -> SyncResult:
    """Full sync: pull from main, then push local changes."""
    try:
        collaborator_pull(connection_path, user_name)
    except Exception as e:
        logger.warning("Pull failed, continuing with push: %s", e)

    return collaborator_push(connection_path, user_name)
