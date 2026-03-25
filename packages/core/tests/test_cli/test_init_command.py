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

    def _fake_greenfield(name: str, template_name: str | None = None) -> None:
        called["name"] = name
        called["template_name"] = template_name

    monkeypatch.setattr(
        "db_mcp.cli.commands.core._init_greenfield",
        _fake_greenfield,
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init", "demo"])

    assert result.exit_code == 0
    assert called["name"] == "demo"
    assert called["template_name"] is None
    assert "No MCP Clients Auto-Detected" in result.output
    assert "db-mcp agents" in result.output
    assert "db-mcp ui" in result.output


def test_init_forwards_template_option(monkeypatch):
    monkeypatch.setattr(
        "db_mcp.cli.commands.core.detect_installed_agents",
        lambda: [],
    )

    called: dict[str, str | None] = {}

    def _fake_greenfield(name: str, template_name: str | None = None) -> None:
        called["name"] = name
        called["template_name"] = template_name

    monkeypatch.setattr(
        "db_mcp.cli.commands.core._init_greenfield",
        _fake_greenfield,
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init", "jira-demo", "--template", "jira"])

    assert result.exit_code == 0, result.output
    assert called["name"] == "jira-demo"
    assert called["template_name"] == "jira"
