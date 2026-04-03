"""Tests for db-mcp gaps CLI commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from db_mcp_cli.main import main


@patch("db_mcp_cli.commands.gaps_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.gaps_cmd.get_connection_path")
@patch("db_mcp_knowledge.gaps.store.load_gaps")
def test_gaps_list_empty(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    gaps = MagicMock()
    gaps.gaps = []
    mock_load.return_value = gaps

    runner = CliRunner()
    result = runner.invoke(main, ["gaps", "list"])
    assert result.exit_code == 0
    assert "No open knowledge gaps" in result.output


@patch("db_mcp_cli.commands.gaps_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.gaps_cmd.get_connection_path")
@patch("db_mcp_knowledge.gaps.store.load_gaps")
def test_gaps_list_shows_open(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    gap = MagicMock()
    gap.id = "g1"
    gap.gap_type = "missing_description"
    gap.description = "Table users has no description"
    gap.source.value = "scan"
    gap.status.value = "open"
    gaps = MagicMock()
    gaps.gaps = [gap]
    mock_load.return_value = gaps

    runner = CliRunner()
    result = runner.invoke(main, ["gaps", "list"])
    assert result.exit_code == 0
    assert "g1" in result.output
    assert "missing_description" in result.output


@patch("db_mcp_cli.commands.gaps_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.gaps_cmd.get_connection_path")
@patch("db_mcp_knowledge.gaps.store.dismiss_gap")
def test_gaps_dismiss_success(mock_dismiss, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_dismiss.return_value = {"dismissed": True, "gap_id": "g1", "count": 1}

    runner = CliRunner()
    result = runner.invoke(main, ["gaps", "dismiss", "g1"])
    assert result.exit_code == 0
    assert "dismissed" in result.output.lower()


@patch("db_mcp_cli.commands.gaps_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.gaps_cmd.get_connection_path")
@patch("db_mcp_knowledge.gaps.store.dismiss_gap")
def test_gaps_dismiss_not_found(mock_dismiss, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_dismiss.return_value = {"dismissed": False, "error": "Gap not found"}

    runner = CliRunner()
    result = runner.invoke(main, ["gaps", "dismiss", "nope"])
    assert result.exit_code != 0
