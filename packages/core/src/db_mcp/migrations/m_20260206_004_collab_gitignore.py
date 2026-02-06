"""Migration: Update .gitignore to allow .collab.yaml.

Existing connections have a .gitignore that ignores all dotfiles (.*).
This migration adds an exception for .collab.yaml so the collaboration
manifest can be tracked in git.
"""

import logging
from pathlib import Path

from db_mcp.migrations import register_migration

logger = logging.getLogger(__name__)

COLLAB_EXCEPTION = "!.collab.yaml"


@register_migration(
    id="20260206_004_collab_gitignore",
    description="Allow .collab.yaml in .gitignore",
)
def collab_gitignore(connection_path: Path) -> bool:
    """Add !.collab.yaml exception to .gitignore.

    Args:
        connection_path: Path to the connection directory

    Returns:
        True if migration succeeded, False on error
    """
    from db_mcp.git_utils import git

    gitignore_path = connection_path / ".gitignore"

    # No .gitignore or not a git repo — nothing to do
    if not gitignore_path.exists() or not git.is_repo(connection_path):
        return True

    try:
        content = gitignore_path.read_text()

        # Already has the exception
        if COLLAB_EXCEPTION in content:
            logger.debug("collab exception already in .gitignore for %s", connection_path.name)
            return True

        # Add exception after !.gitignore line
        if "!.gitignore" in content:
            content = content.replace("!.gitignore", f"!.gitignore\n{COLLAB_EXCEPTION}")
        else:
            # Append to end
            content = content.rstrip() + f"\n{COLLAB_EXCEPTION}\n"

        gitignore_path.write_text(content)

        # Commit the change
        git.add(connection_path, [".gitignore"])
        git.commit(connection_path, "Allow .collab.yaml in .gitignore")

        logger.info("Updated .gitignore for %s", connection_path.name)
        return True

    except Exception as e:
        logger.error("Failed to update .gitignore for %s: %s", connection_path.name, e)
        return False
