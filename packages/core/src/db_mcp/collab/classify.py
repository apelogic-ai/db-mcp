"""File classification for collaborative sync.

Classifies changed files as either "additive" (safe to auto-merge) or
"shared-state" (requires PR review by master).
"""

from __future__ import annotations

from fnmatch import fnmatch as _fnmatch_segment

# Patterns for additive (append-only, conflict-free) files.
# Anything NOT matching these patterns is considered shared-state.
ADDITIVE_PATTERNS = [
    "examples/*.yaml",
    "learnings/failures/*.yaml",
    "learnings/*.md",
    "traces/*",
    "traces/**/*",
]

# Files that are safe to auto-merge even though they are technically shared-state.
# Member additions to .collab.yaml are append-only and handled well by git merge.
AUTO_MERGEABLE_SHARED_FILES = [".collab.yaml"]


def _match_pattern(path: str, pattern: str) -> bool:
    """Match a path against a pattern respecting directory depth.

    Unlike fnmatch, '*' does NOT match across '/' separators.
    '**' matches any number of directories.
    """
    path_parts = path.split("/")
    pattern_parts = pattern.split("/")

    return _match_parts(path_parts, pattern_parts)


def _match_parts(path_parts: list[str], pattern_parts: list[str]) -> bool:
    """Recursively match path segments against pattern segments."""
    if not pattern_parts and not path_parts:
        return True
    if not pattern_parts:
        return False
    if not path_parts:
        # Only match if remaining patterns are all '**'
        return all(p == "**" for p in pattern_parts)

    if pattern_parts[0] == "**":
        # '**' matches zero or more directories
        # Try matching rest of pattern against current and subsequent path positions
        for i in range(len(path_parts)):
            if _match_parts(path_parts[i:], pattern_parts[1:]):
                return True
        # Also try matching zero directories
        return _match_parts(path_parts, pattern_parts[1:])

    # Single segment: use fnmatch for glob matching within one segment (no '/')
    if _fnmatch_segment(path_parts[0], pattern_parts[0]):
        return _match_parts(path_parts[1:], pattern_parts[1:])

    return False


def is_additive(path: str) -> bool:
    """Check if a file path matches an additive pattern."""
    for pattern in ADDITIVE_PATTERNS:
        if _match_pattern(path, pattern):
            return True
    return False


def is_auto_mergeable_shared(files: list[str]) -> bool:
    """Check if a list of shared-state files are all safe to auto-merge.

    Currently, this returns True when the only shared file is .collab.yaml,
    since member additions are append-only and git handles them well.
    """
    return all(f in AUTO_MERGEABLE_SHARED_FILES for f in files)


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
