"""Shared sandbox environment helpers.

Provides :func:`load_connection_env` (parse a connection ``.env`` file) and
:func:`build_sandbox_environment` (assemble the env-var dict passed to exec /
code-mode containers).
"""

from __future__ import annotations

import json
from pathlib import Path


def load_connection_env(connection_path: Path) -> dict[str, str]:
    """Parse key=value pairs from ``<connection_path>/.env``.

    Skips blank lines, comments, and lines without ``=``.
    Strips surrounding single/double quotes from values.
    """
    env_path = connection_path / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip("\"'")
    return values


def build_sandbox_environment(
    connection_name: str,
    connection_path: Path,
    connector: object,
) -> dict[str, str]:
    """Build the environment dict for exec / code-mode sandbox containers."""
    config = getattr(connector, "config", None)
    api_config = getattr(connector, "api_config", None)

    database_url = getattr(config, "database_url", "") or ""
    base_url = getattr(config, "base_url", "") or getattr(api_config, "base_url", "") or ""
    capabilities = getattr(config, "capabilities", {}) or {}

    env = load_connection_env(connection_path)
    if database_url:
        env["DATABASE_URL"] = database_url
    if base_url:
        env["BASE_URL"] = base_url
    if isinstance(capabilities.get("connect_args"), dict):
        env["DB_MCP_CONNECT_ARGS_JSON"] = json.dumps(capabilities["connect_args"])

    env["CONNECTION_NAME"] = connection_name
    env["CONNECTION_PATH"] = "/workspace"
    env["VAULT_PATH"] = "/workspace"
    env["HOME"] = "/workspace"
    env["PYTHONUNBUFFERED"] = "1"
    return env
