"""Tests for execution policy helpers and protocol acknowledgment flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from db_mcp_data.execution.policy import (
    check_protocol_ack_gate,
    evaluate_sql_execution_policy,
    has_fresh_protocol_ack,
    record_protocol_ack,
)

from db_mcp.tools.shell import _protocol


def test_evaluate_sql_policy_requires_validation_when_enabled():
    payload, statement_type, is_write = evaluate_sql_execution_policy(
        sql="SELECT 1",
        capabilities={"supports_validate_sql": True},
        confirmed=False,
        require_validate_first=True,
    )
    assert payload is not None
    assert payload["status"] == "error"
    assert "validate_sql" in payload["error"]
    assert statement_type == "UNKNOWN"
    assert is_write is False


def test_evaluate_sql_policy_requires_write_confirmation():
    payload, statement_type, is_write = evaluate_sql_execution_policy(
        sql="INSERT INTO users(id) VALUES (1)",
        capabilities={
            "allow_sql_writes": True,
            "allowed_write_statements": ["INSERT"],
            "require_write_confirmation": True,
        },
        confirmed=False,
        require_validate_first=False,
        query_id="q-1",
    )
    assert payload is not None
    assert payload["status"] == "confirm_required"
    assert payload["query_id"] == "q-1"
    assert statement_type == "INSERT"
    assert is_write is True


def test_protocol_ack_gate_requires_recent_ack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("DB_MCP_REQUIRE_PROTOCOL_ACK", "1")
    conn_path = tmp_path / "conn"
    conn_path.mkdir(parents=True, exist_ok=True)

    blocked = check_protocol_ack_gate(connection="demo", connection_path=conn_path)
    assert blocked is not None
    assert blocked["status"] == "error"
    assert blocked["error_code"] == "POLICY"

    record_protocol_ack(conn_path, source="test")
    assert has_fresh_protocol_ack(conn_path) is True
    allowed = check_protocol_ack_gate(connection="demo", connection_path=conn_path)
    assert allowed is None


@pytest.mark.asyncio
async def test_protocol_tool_records_ack(tmp_path: Path):
    protocol_path = tmp_path / "PROTOCOL.md"
    protocol_path.write_text("rules", encoding="utf-8")

    with patch("db_mcp.tools.utils._resolve_connection_path", return_value=str(tmp_path)):
        content = await _protocol(connection="demo")

    assert content == "rules"
    assert has_fresh_protocol_ack(tmp_path) is True
