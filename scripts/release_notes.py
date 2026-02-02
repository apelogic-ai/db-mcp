#!/usr/bin/env python3
"""Release notes helper for db-mcp.

Workflow (recommended):
1) Create/maintain a per-release file: releases/vX.Y.Z.md
2) Run: scripts/release_notes.py prepare X.Y.Z
   - creates a stub if missing (and exits non-zero so you fill it)
   - validates basic structure
   - prepends the release notes into CHANGELOG.md

This keeps the per-release notes as the source-of-truth while generating
an always-up-to-date CHANGELOG.md for users.
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REL_DIR = REPO / "releases"
CHANGELOG = REPO / "CHANGELOG.md"

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

TEMPLATE = """# db-mcp v{ver}

## Highlights
- 

## Breaking changes
- None

## Features
- 

## Fixes
- 

## Security
- None

## Upgrade notes
- None

## Known issues
- None
"""


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def validate_version(ver: str) -> None:
    if not SEMVER_RE.match(ver):
        die(f"Invalid version '{ver}'. Expected semver like 0.4.36")


def release_file(ver: str) -> Path:
    return REL_DIR / f"v{ver}.md"


def normalize_notes(md: str) -> str:
    md = md.strip() + "\n"
    return md


def ensure_release_file(ver: str) -> Path:
    p = release_file(ver)
    if not p.exists():
        write_text(p, TEMPLATE.format(ver=ver))
        die(
            f"Created stub release notes at {p}.\n"
            "Fill it out, then re-run: scripts/release_notes.py prepare <version>",
            2,
        )
    return p


def extract_body(md: str) -> str:
    """Return md without the first H1 if present (for changelog embedding)."""
    lines = md.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        # drop leading blank line
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip() + "\n"


def update_changelog(ver: str, notes_md: str) -> None:
    if not CHANGELOG.exists():
        die("CHANGELOG.md not found (expected at repo root)")

    today = _dt.date.today().isoformat()
    header = f"## [{ver}] - {today}\n\n"
    body = extract_body(notes_md)
    entry = header + body + "\n"

    ch = read_text(CHANGELOG)

    # Don't duplicate
    if f"## [{ver}]" in ch:
        return

    # Insert after Unreleased section.
    marker = "## [Unreleased]"
    idx = ch.find(marker)
    if idx == -1:
        die("CHANGELOG.md missing '## [Unreleased]' section")

    # Find end of Unreleased section: next '## [' header after marker.
    after = ch.find("\n## [", idx + len(marker))
    if after == -1:
        # append to end
        new_ch = ch.rstrip() + "\n\n" + entry
    else:
        new_ch = ch[:after] + "\n" + entry + ch[after:]

    write_text(CHANGELOG, new_ch)


def basic_validate_notes(notes_md: str) -> None:
    # lightweight sanity checks
    if not notes_md.strip().startswith("#"):
        die("Release notes should start with a '# ' header")
    if "## Highlights" not in notes_md:
        die("Release notes must include a '## Highlights' section")


def cmd_prepare(ver: str) -> None:
    validate_version(ver)
    p = ensure_release_file(ver)
    notes = normalize_notes(read_text(p))
    basic_validate_notes(notes)
    update_changelog(ver, notes)
    print(f"OK: prepared notes for v{ver}")
    print(f"- release notes: {p}")
    print(f"- changelog updated: {CHANGELOG}")


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        die(
            "Usage:\n"
            "  scripts/release_notes.py prepare <version>\n",
            0,
        )

    cmd = argv[1]
    if cmd == "prepare":
        if len(argv) != 3:
            die("Usage: scripts/release_notes.py prepare <version>")
        cmd_prepare(argv[2])
    else:
        die(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main(sys.argv)
