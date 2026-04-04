"""Tests for db-mcp query and ask CLI commands."""

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from db_mcp_cli.main import main


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp.services.query.run_sql", new_callable=AsyncMock)
def test_query_run_table_output(mock_run, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    # run_sql returns list[dict] under "data" key
    mock_run.return_value = {
        "data": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        "columns": ["id", "name"],
    }

    runner = CliRunner()
    result = runner.invoke(main, ["query", "run", "SELECT * FROM users"])
    assert result.exit_code == 0
    assert "Alice" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp.services.query.run_sql", new_callable=AsyncMock)
def test_query_run_csv_export(mock_run, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_run.return_value = {
        "data": [{"id": 1, "name": "Alice"}],
        "columns": ["id", "name"],
    }

    runner = CliRunner()
    result = runner.invoke(
        main, ["query", "run", "--export", "csv", "SELECT * FROM users"]
    )
    assert result.exit_code == 0
    assert "id,name" in result.output
    assert "1,Alice" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp.services.query.run_sql", new_callable=AsyncMock)
def test_query_run_json_export(mock_run, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_run.return_value = {
        "data": [{"id": 1, "name": "Alice"}],
        "columns": ["id", "name"],
    }

    runner = CliRunner()
    result = runner.invoke(
        main, ["query", "run", "--export", "json", "SELECT * FROM users"]
    )
    assert result.exit_code == 0
    assert '"id"' in result.output
    assert '"Alice"' in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp.services.query.run_sql", new_callable=AsyncMock)
def test_query_run_error(mock_run, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_run.return_value = {"error": "Connection failed"}

    runner = CliRunner()
    result = runner.invoke(main, ["query", "run", "SELECT 1"])
    assert result.exit_code != 0


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
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


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp.orchestrator.engine.answer_intent", new_callable=AsyncMock)
def test_ask_success(mock_answer, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    # answer_intent returns AnswerIntentResponse.model_dump() with "records" (list[dict])
    mock_answer.return_value = {
        "status": "success",
        "answer": "Executed metric 'user_count' on connection 'test' and returned 1 row.",
        "records": [{"count": 42}],
    }

    runner = CliRunner()
    result = runner.invoke(main, ["ask", "how many users"])
    assert result.exit_code == 0
    assert "42" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp.orchestrator.engine.answer_intent", new_callable=AsyncMock)
def test_ask_error(mock_answer, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_answer.return_value = {"error": "No metrics found"}

    runner = CliRunner()
    result = runner.invoke(main, ["ask", "unknown metric"])
    assert result.exit_code != 0


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
def test_ask_sql_input_rejected(mock_path, mock_active, tmp_path):
    """SQL-looking input should be redirected to query run instead."""
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")

    runner = CliRunner()
    result = runner.invoke(main, ["ask", "SELECT 1"])
    assert result.exit_code != 0
    assert "query run" in result.output.lower()


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp.orchestrator.engine.answer_intent", new_callable=AsyncMock)
def test_ask_error_with_warnings(mock_answer, mock_path, mock_active, tmp_path):
    """Warnings from answer_intent should appear alongside the error."""
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_answer.return_value = {
        "error": "No approved metric matched the intent.",
        "warnings": ["Available metrics: dau, revenue"],
    }

    runner = CliRunner()
    result = runner.invoke(main, ["ask", "how many widgets"])
    assert result.exit_code != 0
    assert "dau" in result.output
