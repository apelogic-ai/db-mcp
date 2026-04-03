"""Single-tool exec mode implementation."""

from __future__ import annotations

import asyncio
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any as Context,  # noqa: UP006 — Context was fastmcp.Context; moved to mcp-server in Phase 3
)

from db_mcp.exec_runtime import (
    ExecRuntimeError,
    ExecSandboxSpec,
    derive_allowed_endpoint,
    get_exec_session_manager,
)
from db_mcp.tools.utils import require_connection, resolve_connection


@dataclass
class _ProtocolAck:
    command: str
    fingerprint: tuple[int, int]


_protocol_acks: dict[tuple[str, str], _ProtocolAck] = {}


def _load_connection_env(connection_path: Path) -> dict[str, str]:
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


def _build_exec_environment(
    connection_name: str,
    connection_path: Path,
    connector: object,
) -> dict[str, str]:
    config = getattr(connector, "config", None)
    api_config = getattr(connector, "api_config", None)

    database_url = getattr(config, "database_url", "") or ""
    base_url = getattr(config, "base_url", "") or getattr(api_config, "base_url", "") or ""
    capabilities = getattr(config, "capabilities", {}) or {}

    env = _load_connection_env(connection_path)
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


def _build_exec_spec(connection: str, *, session_id: str) -> ExecSandboxSpec:
    connector, connection_name, connection_path = resolve_connection(
        require_connection(connection)
    )
    config = getattr(connector, "config", None)
    api_config = getattr(connector, "api_config", None)

    database_url = getattr(config, "database_url", "") or ""
    base_url = getattr(config, "base_url", "") or getattr(api_config, "base_url", "") or ""

    return ExecSandboxSpec(
        session_id=session_id,
        connection=connection_name,
        connection_path=Path(connection_path),
        allowed_endpoint=derive_allowed_endpoint(database_url, base_url=base_url),
        environment=_build_exec_environment(connection_name, Path(connection_path), connector),
    )


def _protocol_fingerprint(connection_path: Path) -> tuple[int, int]:
    protocol_path = connection_path / "PROTOCOL.md"
    stat = protocol_path.stat()
    return (stat.st_mtime_ns, stat.st_size)


def _is_protocol_read_command(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False

    if len(parts) != 2:
        return False
    return parts[0] in {"cat", "head"} and parts[1] == "PROTOCOL.md"


def _protocol_gate_result() -> dict[str, object]:
    return {
        "stdout": "",
        "stderr": (
            "Read PROTOCOL.md first with "
            "exec(connection=..., command='cat PROTOCOL.md')"
        ),
        "exit_code": 1,
        "duration_ms": 0.0,
        "truncated": False,
    }


def _check_protocol_ack(
    session_id: str,
    connection: str,
    command: str,
    connection_path: Path,
) -> bool:
    key = (session_id, connection)
    current_fingerprint = _protocol_fingerprint(connection_path)
    ack = _protocol_acks.get(key)
    if ack is not None and ack.fingerprint != current_fingerprint:
        _protocol_acks.pop(key, None)
        ack = None

    if ack is not None:
        return True

    return _is_protocol_read_command(command)


def _record_protocol_ack(
    *,
    session_id: str,
    connection: str,
    command: str,
    connection_path: Path,
    result: dict[str, object],
) -> None:
    if not _is_protocol_read_command(command):
        return
    if int(result.get("exit_code", 1)) != 0:
        return
    _protocol_acks[(session_id, connection)] = _ProtocolAck(
        command=command,
        fingerprint=_protocol_fingerprint(connection_path),
    )


async def _exec(
    command: str,
    connection: str,
    timeout_seconds: int = 30,
    ctx: Context | None = None,
) -> dict[str, object]:
    """Run a command inside the sandboxed connection workspace."""
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1")
    if timeout_seconds > 600:
        raise ValueError("timeout_seconds must be at most 600")

    session_id = getattr(ctx, "session_id", None) or "stateless"
    spec = _build_exec_spec(connection, session_id=session_id)
    if not _check_protocol_ack(session_id, spec.connection, command, spec.connection_path):
        return _protocol_gate_result()

    manager = get_exec_session_manager()
    try:
        result = await asyncio.to_thread(
            manager.execute,
            session_id=session_id,
            spec=spec,
            command=command,
            timeout_seconds=timeout_seconds,
        )
        _record_protocol_ack(
            session_id=session_id,
            connection=spec.connection,
            command=command,
            connection_path=spec.connection_path,
            result=result,
        )
        return result
    except ExecRuntimeError as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "exit_code": 1,
            "duration_ms": 0.0,
            "truncated": False,
        }
