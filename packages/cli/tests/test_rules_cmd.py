"""Tests for db-mcp rules CLI commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from db_mcp_cli.main import main


@patch("db_mcp_cli.commands.rules_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.rules_cmd.get_connection_path")
@patch("db_mcp_knowledge.training.store.load_instructions")
def test_rules_list_empty(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    inst = MagicMock()
    inst.rules = []
    mock_load.return_value = inst

    runner = CliRunner()
    result = runner.invoke(main, ["rules", "list"])
    assert result.exit_code == 0
    assert "No rules defined" in result.output


@patch("db_mcp_cli.commands.rules_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.rules_cmd.get_connection_path")
@patch("db_mcp_knowledge.training.store.load_instructions")
def test_rules_list_shows_rules(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    inst = MagicMock()
    inst.rules = ["Always use UTC", "Limit to 1000 rows"]
    mock_load.return_value = inst

    runner = CliRunner()
    result = runner.invoke(main, ["rules", "list"])
    assert result.exit_code == 0
    assert "Always use UTC" in result.output
    assert "Limit to 1000 rows" in result.output


@patch("db_mcp_cli.commands.rules_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.rules_cmd.get_connection_path")
@patch("db_mcp_knowledge.training.store.add_rule")
def test_rules_add_success(mock_add, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_add.return_value = {"added": True, "total_rules": 3}

    runner = CliRunner()
    result = runner.invoke(main, ["rules", "add", "--rule", "1 GB = 1073741824 bytes"])
    assert result.exit_code == 0
    assert "3 total" in result.output
