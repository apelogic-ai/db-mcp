"""File classification for collaborative sync.

Classifies changed files as either "additive" (safe to auto-merge) or
"shared-state" (requires PR review by master).
"""

from __future__ import annotations

from fnmatch import fnmatch

# Patterns for additive (append-only, conflict-free) files.
# Anything NOT matching these patterns is considered shared-state.
ADDITIVE_PATTERNS = [
    "examples/*.yaml",
    "learnings/failures/*.yaml",
    "learnings/*.md",
    "traces/*",
    "traces/**/*",
]


def is_additive(path: str) -> bool:
    """Check if a file path matches an additive pattern."""
    for pattern in ADDITIVE_PATTERNS:
        if fnmatch(path, pattern):
            return True
    return False


def classify_files(changed_files: list[str]) -> tuple[list[str], list[str]]:
    """Classify a list of changed file paths.

    Returns:
        Tuple of (additive_files, shared_state_files).
    """
    additive: list[str] = []
    shared: list[str] = []
    for f in changed_files:
        if is_additive(f):
            additive.append(f)
        else:
            shared.append(f)
    return additive, shared
