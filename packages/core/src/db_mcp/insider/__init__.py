"""Insider-agent runtime entry points."""

from __future__ import annotations

from pathlib import Path

from db_mcp.insider.config import InsiderConfig, load_insider_config
from db_mcp.insider.services import InsiderService
from db_mcp.insider.supervisor import InsiderSupervisor

_SERVICE: InsiderService | None = None
_SUPERVISOR: InsiderSupervisor | None = None


def get_insider_service() -> InsiderService:
    """Return the shared insider service."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = InsiderService()
    return _SERVICE


def get_insider_supervisor() -> InsiderSupervisor | None:
    """Return the global insider supervisor, if started."""
    return _SUPERVISOR


async def start_insider_supervisor(
    connection_path: Path | None = None,
) -> InsiderSupervisor | None:
    """Start the singleton insider supervisor if enabled."""
    global _SERVICE, _SUPERVISOR
    config = load_insider_config(connection_path)
    if not config.enabled:
        return None
    if _SERVICE is None:
        _SERVICE = InsiderService()
    service = _SERVICE
    if _SUPERVISOR is None:
        _SUPERVISOR = InsiderSupervisor(config=config, service=service)
        await _SUPERVISOR.start()
    return _SUPERVISOR


async def stop_insider_supervisor() -> None:
    """Stop the singleton insider supervisor."""
    global _SERVICE, _SUPERVISOR
    if _SUPERVISOR is not None:
        await _SUPERVISOR.stop()
        _SUPERVISOR = None
    _SERVICE = None


__all__ = [
    "InsiderConfig",
    "get_insider_service",
    "get_insider_supervisor",
    "load_insider_config",
    "start_insider_supervisor",
    "stop_insider_supervisor",
]
