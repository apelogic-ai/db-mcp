---
name: release
description: Cut a db-mcp release — bumps version, writes release notes, runs checks, commits, tags, and pushes. Default is patch; pass "minor" or "major" for larger bumps.
---

# Release Skill

Cut a db-mcp release. Arguments: `patch` (default), `minor`, or `major`.

## Step 1 — Determine bump type and compute new version

Parse `$ARGUMENTS`. If empty or "patch" → patch bump. "minor" → minor bump. "major" → major bump.

Read current version from `packages/core/pyproject.toml` (`project.version` field).

Compute the new version by applying the bump:
- patch: X.Y.Z → X.Y.(Z+1)
- minor: X.Y.Z → X.(Y+1).0
- major: X.Y.Z → (X+1).0.0

State the bump type and new version clearly before proceeding.

## Step 2 — Verify we are on main and it is clean

```bash
git status --short
git branch --show-current
```

Abort with a clear message if:
- Not on `main`
- There are uncommitted changes unrelated to release prep

## Step 3 — Bump version in two files

Edit `packages/core/pyproject.toml`: change `version = "OLD"` → `version = "NEW"`.
Edit `packages/core/src/db_mcp/__init__.py`: change `__version__ = "OLD"` → `__version__ = "NEW"`.

## Step 4 — Write release notes

Create `docs/releases/vNEW.md` with the required sections:
1. `# Release vNEW - {Title}` — derive a short title from recent commit messages
2. `## Overview` — one-paragraph summary of what changed
3. `## Highlights` — bullet list of user-facing changes
4. `## New Features` / `## Bug Fixes` — as applicable (omit empty sections)
5. `## Files Changed` — table of key files and what changed
6. `## Testing` — test counts and lint status (get counts by running tests or reading recent output)

To understand what changed since the last release, run:
```bash
git log $(git describe --tags --abbrev=0 HEAD^)..HEAD --oneline
```

Then run:
```bash
uv run python scripts/release_notes.py prepare NEW
```

This validates the release notes structure and prepends them into `CHANGELOG.md`.

## Step 5 — Update uv.lock

```bash
uv lock
```

## Step 6 — Validate

Run all checks. Do not skip any. Do not push if any check fails — fix the issue first.

```bash
# Version consistency
uv run python scripts/check_version_consistency.py

# Lint
uv run ruff check . --fix

# Core tests (largest suite — run this, others if time allows)
cd packages/core && uv run pytest tests/ -q
```

TypeScript check if UI files changed:
```bash
cd packages/ui && bunx tsc --noEmit
```

## Step 7 — Commit

Stage only the release files:
```bash
git add packages/core/pyproject.toml \
        packages/core/src/db_mcp/__init__.py \
        docs/releases/vNEW.md \
        CHANGELOG.md \
        uv.lock
```

Commit message: `chore: release vNEW`

Co-authored-by line: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`

## Step 8 — Tag and push

```bash
git tag -a vNEW -m "Release vNEW — {one-line summary}"
git push origin main
git push origin vNEW
```

## Step 9 — Confirm

Report the tag SHA and the GitHub Actions release URL pattern:
`https://github.com/apelogic-ai/db-mcp/releases/tag/vNEW`

CI will build and publish the platform binaries automatically.

---

## Rules

- **Never edit existing release notes** in `docs/releases/`. Each version gets exactly one file, written once.
- **Never push if tests fail.** Fix first.
- **Never skip version consistency check.** It validates pyproject.toml, `__init__.py`, and uv.lock all agree.
- **Always be on `main`** before cutting a release.
- The release commit must contain only the 5 release files listed in Step 7 — no code changes.
