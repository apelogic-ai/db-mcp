"""Tests for db-mcp query and ask CLI commands."""

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from db_mcp_cli.main import main


@patch("db_mcp_cli.commands.query_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.query_cmd.get_connection_path")
@patch("db_mcp.services.query.run_sql", new_callable=AsyncMock)
def test_query_run_table_output(mock_run, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_run.return_value = {
        "columns": ["id", "name"],
        "rows": [[1, "Alice"], [2, "Bob"]],
    }

    runner = CliRunner()
    result = runner.invoke(main, ["query", "run", "SELECT * FROM users"])
    assert result.exit_code == 0
    assert "Alice" in result.output


@patch("db_mcp_cli.commands.query_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.query_cmd.get_connection_path")
@patch("db_mcp.services.query.run_sql", new_callable=AsyncMock)
def test_query_run_csv_export(mock_run, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_run.return_value = {
        "columns": ["id", "name"],
        "rows": [[1, "Alice"]],
    }

    runner = CliRunner()
    result = runner.invoke(
        main, ["query", "run", "--export", "csv", "SELECT * FROM users"]
    )
    assert result.exit_code == 0
    assert "id,name" in result.output
    assert "1,Alice" in result.output


@patch("db_mcp_cli.commands.query_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.query_cmd.get_connection_path")
@patch("db_mcp.services.query.run_sql", new_callable=AsyncMock)
def test_query_run_json_export(mock_run, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_run.return_value = {
        "columns": ["id", "name"],
        "rows": [[1, "Alice"]],
    }

    runner = CliRunner()
    result = runner.invoke(
        main, ["query", "run", "--export", "json", "SELECT * FROM users"]
    )
    assert result.exit_code == 0
    assert '"id"' in result.output
    assert '"Alice"' in result.output


@patch("db_mcp_cli.commands.query_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.query_cmd.get_connection_path")
@patch("db_mcp.services.query.run_sql", new_callable=AsyncMock)
def test_query_run_error(mock_run, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_run.return_value = {"error": "Connection failed"}

    runner = CliRunner()
    result = runner.invoke(main, ["query", "run", "SELECT 1"])
    assert result.exit_code != 0


@patch("db_mcp_cli.commands.query_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.query_cmd.get_connection_path")
@patch("db_mcp.services.query.validate_sql", new_callable=AsyncMock)
def test_query_validate_success(mock_validate, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_validate.return_value = {"query_id": "q123"}

    runner = CliRunner()
    result = runner.invoke(main, ["query", "validate", "SELECT 1"])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()
    assert "q123" in result.output


@patch("db_mcp_cli.commands.query_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.query_cmd.get_connection_path")
@patch("db_mcp.orchestrator.engine.answer_intent", new_callable=AsyncMock)
def test_ask_success(mock_answer, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_answer.return_value = {
        "sql": "SELECT COUNT(*) FROM users",
        "columns": ["count"],
        "rows": [[42]],
    }

    runner = CliRunner()
    result = runner.invoke(main, ["ask", "how many users"])
    assert result.exit_code == 0
    assert "42" in result.output


@patch("db_mcp_cli.commands.query_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.query_cmd.get_connection_path")
@patch("db_mcp.orchestrator.engine.answer_intent", new_callable=AsyncMock)
def test_ask_error(mock_answer, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_answer.return_value = {"error": "No metrics found"}

    runner = CliRunner()
    result = runner.invoke(main, ["ask", "unknown metric"])
    assert result.exit_code != 0
