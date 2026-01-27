"""Migration: Enable git for all existing connections.

This migration:
1. Initializes a git repo in the connection directory (if not already)
2. Creates a .gitignore for sensitive files
3. Makes an initial commit with existing files
"""

import logging
from pathlib import Path

from db_mcp.migrations import register_migration

logger = logging.getLogger(__name__)

GITIGNORE_CONTENT = """\
# Secrets - never commit credentials
.env

# Local state (not synced)
state.yaml

# Trash folder
.trash/
"""


@register_migration(
    id="20260126_003_enable_git",
    description="Enable git version control for connection",
)
def enable_git(connection_path: Path) -> bool:
    """Enable git for a connection directory.

    Args:
        connection_path: Path to the connection directory

    Returns:
        True if migration succeeded, False on error
    """
    from db_mcp.git_utils import git

    # Already has git - nothing to do
    if git.is_repo(connection_path):
        logger.debug(f"Git already enabled for {connection_path.name}")
        return True

    try:
        # Initialize git repo
        git.init(connection_path)
        logger.info(f"Initialized git repo in {connection_path.name}")

        # Create/update .gitignore
        gitignore_path = connection_path / ".gitignore"
        gitignore_path.write_text(GITIGNORE_CONTENT)

        # Stage all existing files
        git.add(connection_path, ["."])

        # Initial commit
        commit_hash = git.commit(connection_path, "Initial db-mcp connection setup")

        if commit_hash:
            logger.info(f"Created initial commit {commit_hash} for {connection_path.name}")
        else:
            logger.info(f"Git initialized for {connection_path.name} (no files to commit)")

        return True

    except Exception as e:
        logger.error(f"Failed to enable git for {connection_path.name}: {e}")
        return False
