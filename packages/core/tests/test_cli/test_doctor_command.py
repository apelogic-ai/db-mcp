"""Tests for `db-mcp doctor` command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from db_mcp.cli.main import main


class _FakeSQLConnector:
    def test_connection(self) -> dict:
        return {"connected": True}

    def execute_sql(self, sql: str) -> list[dict]:
        assert "SELECT 1" in sql.upper()
        return [{"db_mcp_doctor": 1}]


class _FakeAPIConnector:
    def test_connection(self) -> dict:
        return {"connected": True}


def _parse_json(output: str) -> dict:
    return json.loads(output.strip())


def test_doctor_json_passes_with_sql_execution(monkeypatch, tmp_path):
    conn_path = tmp_path / "demo"
    conn_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("db_mcp.cli.commands.core.connection_exists", lambda name: True)
    monkeypatch.setattr("db_mcp.cli.commands.core.get_connection_path", lambda name: conn_path)
    monkeypatch.setattr(
        "db_mcp.cli.commands.core.get_connector",
        lambda connection_path=None: _FakeSQLConnector(),
    )
    monkeypatch.setattr(
        "db_mcp.cli.commands.core.get_connector_capabilities",
        lambda connector: {"supports_sql": True, "supports_async_jobs": True},
    )

    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--connection", "demo", "--json"])

    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["status"] == "pass"

    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["resolve_connection"]["status"] == "pass"
    assert checks["load_connector"]["status"] == "pass"
    assert checks["auth"]["status"] == "pass"
    assert checks["execute_test"]["status"] == "pass"
    assert checks["poll_test"]["status"] == "pass"


def test_doctor_skips_execute_when_sql_not_supported(monkeypatch, tmp_path):
    conn_path = tmp_path / "demo"
    conn_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("db_mcp.cli.commands.core.connection_exists", lambda name: True)
    monkeypatch.setattr("db_mcp.cli.commands.core.get_connection_path", lambda name: conn_path)
    monkeypatch.setattr(
        "db_mcp.cli.commands.core.get_connector",
        lambda connection_path=None: _FakeAPIConnector(),
    )
    monkeypatch.setattr(
        "db_mcp.cli.commands.core.get_connector_capabilities",
        lambda connector: {"supports_sql": False, "supports_async_jobs": False},
    )

    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--connection", "demo", "--json"])

    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["status"] == "pass"

    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["execute_test"]["status"] == "skip"
    assert checks["poll_test"]["status"] == "skip"


def test_doctor_fails_for_missing_connection(monkeypatch, tmp_path):
    monkeypatch.setattr("db_mcp.cli.commands.core.connection_exists", lambda name: False)
    monkeypatch.setattr(
        "db_mcp.cli.commands.core.get_connection_path", lambda name: tmp_path / "missing"
    )

    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--connection", "missing", "--json"])

    assert result.exit_code == 1
    payload = _parse_json(result.output)
    assert payload["status"] == "fail"
    assert payload["checks"][0]["name"] == "resolve_connection"
    assert payload["checks"][0]["status"] == "fail"
