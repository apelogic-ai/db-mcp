#!/usr/bin/env python3
"""Ensure db-mcp version is consistent across release-critical files."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def fail(message: str) -> None:
    print(f"version-consistency: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def parse_init_version(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("__version__"):
            _, value = line.split("=", 1)
            return value.strip().strip("\"").strip("'")
    fail(f"Could not find __version__ in {path}")
    return ""  # unreachable


def parse_uv_lock_package_version(path: Path, package_name: str) -> str:
    data = load_toml(path)
    packages = data.get("package", [])
    if not isinstance(packages, list):
        fail(f"Unexpected uv.lock structure in {path}")

    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        if pkg.get("name") == package_name:
            version = pkg.get("version")
            if isinstance(version, str):
                return version
            fail(f"Package '{package_name}' has no string version in {path}")

    fail(f"Package '{package_name}' not found in {path}")
    return ""  # unreachable


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    core_pyproject = repo / "packages" / "core" / "pyproject.toml"
    core_init = repo / "packages" / "core" / "src" / "db_mcp" / "__init__.py"
    uv_lock = repo / "uv.lock"

    pyproject = load_toml(core_pyproject)
    project = pyproject.get("project")
    if not isinstance(project, dict):
        fail(f"Missing [project] in {core_pyproject}")

    pyproject_version = project.get("version")
    if not isinstance(pyproject_version, str):
        fail(f"Missing project.version in {core_pyproject}")

    init_version = parse_init_version(core_init)
    lock_version = parse_uv_lock_package_version(uv_lock, "db-mcp")

    mismatches: list[str] = []
    if pyproject_version != init_version:
        mismatches.append(
            f"packages/core/pyproject.toml ({pyproject_version}) != "
            f"packages/core/src/db_mcp/__init__.py ({init_version})"
        )
    if pyproject_version != lock_version:
        mismatches.append(f"packages/core/pyproject.toml ({pyproject_version}) != uv.lock ({lock_version})")

    if mismatches:
        fail("Version mismatch detected:\n- " + "\n- ".join(mismatches))

    print(
        "version-consistency: OK "
        f"(core={pyproject_version}, __init__={init_version}, uv.lock={lock_version})"
    )


if __name__ == "__main__":
    main()
