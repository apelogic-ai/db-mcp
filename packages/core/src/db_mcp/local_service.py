"""Shared state helpers for the local db-mcp control plane."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def get_local_service_state_path() -> Path:
    """Return the persisted state file for the local daemon/service."""
    override = os.environ.get("DB_MCP_LOCAL_SERVICE_STATE", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".db-mcp" / "local-service.json"


def build_local_service_state(
    *,
    connection: str | None,
    ui_host: str,
    ui_port: int,
    mcp_host: str,
    mcp_port: int,
    mcp_path: str,
    pid: int | None = None,
) -> dict[str, object]:
    """Build the serializable local-service metadata payload."""
    return {
        "connection": connection,
        "ui_host": ui_host,
        "ui_port": ui_port,
        "ui_url": f"http://{ui_host}:{ui_port}",
        "runtime_url": f"http://{ui_host}:{ui_port}",
        "mcp_host": mcp_host,
        "mcp_port": mcp_port,
        "mcp_path": mcp_path,
        "mcp_health_url": f"http://{mcp_host}:{mcp_port}/health",
        "mcp_url": f"http://{mcp_host}:{mcp_port}{mcp_path}",
        "pid": pid,
    }


def write_local_service_state(state: dict[str, object]) -> Path:
    """Persist the current local-service state to disk."""
    path = get_local_service_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")
    return path


def load_local_service_state() -> dict[str, object] | None:
    """Load the persisted local-service state when present."""
    path = get_local_service_state_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def clear_local_service_state() -> None:
    """Remove the persisted local-service state file."""
    path = get_local_service_state_path()
    if path.exists():
        path.unlink()


def local_service_is_healthy(
    state: dict[str, object] | None,
    *,
    timeout_seconds: float = 1.0,
) -> bool:
    """Return True when the local daemon MCP endpoint is reachable."""
    if not state:
        return False
    health_url = str(state.get("mcp_health_url", "") or "").strip()
    if not health_url:
        return False
    try:
        with urlopen(health_url, timeout=timeout_seconds) as response:
            return response.status == 200
    except (URLError, ValueError):
        return False
