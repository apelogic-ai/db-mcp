"""Tests for db-mcp domain CLI commands."""

from unittest.mock import patch

from click.testing import CliRunner

from db_mcp_cli.main import main


@patch("db_mcp.registry.ConnectionRegistry.get_active_connection_name", return_value="test")
@patch("db_mcp.registry.ConnectionRegistry.get_connection_path")
def test_domain_show_no_model(mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")

    runner = CliRunner()
    result = runner.invoke(main, ["domain", "show"])
    assert result.exit_code == 0
    assert "No domain model found" in result.output


@patch("db_mcp.registry.ConnectionRegistry.get_active_connection_name", return_value="test")
@patch("db_mcp.registry.ConnectionRegistry.get_connection_path")
def test_domain_show_with_model(mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    model_dir = tmp_path / "domain"
    model_dir.mkdir()
    (model_dir / "model.md").write_text("# My Domain\n\nEntities and relationships.")

    runner = CliRunner()
    result = runner.invoke(main, ["domain", "show"])
    assert result.exit_code == 0
    assert "My Domain" in result.output
