"""Tests for `db-mcp init` command behavior."""

from click.testing import CliRunner

from db_mcp.cli.main import main


def test_init_continues_when_no_mcp_clients_detected(monkeypatch):
    """Init should continue even when no supported MCP clients are detected."""

    monkeypatch.setattr(
        "db_mcp.cli.commands.core.detect_installed_agents",
        lambda: [],
    )

    called: dict[str, str] = {}

    def _fake_greenfield(name: str) -> None:
        called["name"] = name

    monkeypatch.setattr(
        "db_mcp.cli.commands.core._init_greenfield",
        _fake_greenfield,
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init", "demo"])

    assert result.exit_code == 0
    assert called["name"] == "demo"
    assert "No MCP Clients Auto-Detected" in result.output
    assert "db-mcp agents" in result.output
    assert "db-mcp ui" in result.output
