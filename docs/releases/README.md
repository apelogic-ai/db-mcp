# Release Notes

This directory contains detailed release notes for db-mcp versions.

## Workflow

The GitHub Actions release workflow (`.github/workflows/release.yml`) automatically checks for release notes in this directory:

1. When creating a release for version `X.Y.Z`, it looks for `docs/releases/vX.Y.Z.md`
2. If the file exists, it uses its contents as the GitHub release body
3. If not found, it falls back to a default template

## Creating Release Notes

For each new version:

1. Create a file named `vX.Y.Z.md` in this directory
2. Write comprehensive release notes (see existing files for format)
3. The file will automatically be used when the release is created

## Format

Release notes should include:

- Overview/Highlights
- New Features (with examples)
- Bug Fixes
- Breaking Changes (if any)
- Upgrade Instructions
- Technical Details
- Known Issues

See existing files for formatting examples.
