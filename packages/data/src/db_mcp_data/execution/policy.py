"""Execution policy helpers for deterministic SQL tool behavior."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from db_mcp_data.validation.explain import get_write_policy, validate_sql_permissions

PROTOCOL_ACK_ENV = "DB_MCP_REQUIRE_PROTOCOL_ACK"
PROTOCOL_ACK_TTL_ENV = "DB_MCP_PROTOCOL_ACK_TTL_SECONDS"
PROTOCOL_ACK_FILENAME = "protocol_ack.json"
DEFAULT_PROTOCOL_ACK_TTL_SECONDS = 6 * 60 * 60


def _is_env_true(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def protocol_ack_path(connection_path: Path) -> Path:
    """Return location of protocol acknowledgment marker for a connection."""
    return connection_path / "state" / PROTOCOL_ACK_FILENAME


def record_protocol_ack(connection_path: Path, source: str = "protocol") -> None:
    """Record that the agent/user explicitly read protocol instructions."""
    ack_path = protocol_ack_path(connection_path)
    ack_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "acknowledged_at": datetime.now(UTC).isoformat(),
        "source": source,
    }
    ack_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _protocol_ack_ttl_seconds() -> int:
    raw = os.getenv(PROTOCOL_ACK_TTL_ENV)
    if raw is None:
        return DEFAULT_PROTOCOL_ACK_TTL_SECONDS
    try:
        ttl = int(raw)
    except ValueError:
        return DEFAULT_PROTOCOL_ACK_TTL_SECONDS
    return max(ttl, 0)


def protocol_ack_required() -> bool:
    """Whether execution should require a recent protocol acknowledgment."""
    return _is_env_true(os.getenv(PROTOCOL_ACK_ENV))


def has_fresh_protocol_ack(connection_path: Path) -> bool:
    """Check if protocol acknowledgment marker exists and is still fresh."""
    ack_path = protocol_ack_path(connection_path)
    if not ack_path.exists():
        return False

    try:
        payload = json.loads(ack_path.read_text(encoding="utf-8"))
        ts_raw = payload.get("acknowledged_at")
        if not isinstance(ts_raw, str):
            return False
        ts = datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
    except Exception:
        return False

    ttl = _protocol_ack_ttl_seconds()
    if ttl == 0:
        return True

    return datetime.now(UTC) <= ts + timedelta(seconds=ttl)


def protocol_ack_gate_error(connection: str) -> dict[str, Any]:
    """Return deterministic policy error payload for missing protocol ack."""
    ttl = _protocol_ack_ttl_seconds()
    ttl_hint = "no expiry" if ttl == 0 else f"{ttl} seconds"
    return {
        "status": "error",
        "error_code": "POLICY",
        "error": (
            "Execution policy requires protocol acknowledgment before running SQL. "
            "Call protocol(connection=...) or read PROTOCOL.md via shell first."
        ),
        "connection": connection,
        "guidance": {
            "next_steps": [
                f"Call protocol(connection='{connection}')",
                "Then retry run_sql(...)",
            ],
            "policy": {"required": "protocol_ack", "ttl": ttl_hint},
        },
    }


def check_protocol_ack_gate(connection: str, connection_path: Path) -> dict[str, Any] | None:
    """Return policy error payload when protocol ack is required but missing/stale."""
    if not protocol_ack_required():
        return None
    if has_fresh_protocol_ack(connection_path):
        return None
    return protocol_ack_gate_error(connection)


def evaluate_sql_execution_policy(
    *,
    sql: str,
    capabilities: dict[str, Any],
    confirmed: bool,
    require_validate_first: bool,
    query_id: str | None = None,
) -> tuple[dict[str, Any] | None, str, bool]:
    """Apply deterministic SQL execution checks and return status payload if blocked."""
    if require_validate_first and capabilities.get("supports_validate_sql", True):
        return (
            {
                "status": "error",
                "error": "Validation required. Use validate_sql first.",
                "guidance": {
                    "next_steps": [
                        "Call validate_sql(sql=...) to get a query_id",
                        "Then call run_sql(query_id=..., connection=...)",
                    ]
                },
            },
            "UNKNOWN",
            False,
        )

    is_allowed, error, statement_type, is_write = validate_sql_permissions(
        sql, capabilities=capabilities
    )
    if not is_allowed:
        payload: dict[str, Any] = {
            "status": "error",
            "error": error,
            "sql": sql,
            "statement_type": statement_type,
            "is_write": is_write,
        }
        if query_id is not None:
            payload["query_id"] = query_id
        return payload, statement_type, is_write

    _, _, require_write_confirmation = get_write_policy(capabilities)
    if is_write and require_write_confirmation and not confirmed:
        payload = {
            "status": "confirm_required",
            "sql": sql,
            "statement_type": statement_type,
            "is_write": True,
            "message": (
                "Write statement requires confirmation. "
                "Re-run with confirmed=true to execute."
            ),
        }
        if query_id is not None:
            payload["query_id"] = query_id
        return payload, statement_type, is_write

    return None, statement_type, is_write
