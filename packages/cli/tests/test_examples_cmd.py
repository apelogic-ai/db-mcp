"""Tests for db-mcp examples CLI commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from db_mcp_cli.main import main


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.training.store.load_examples")
def test_examples_list_empty(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    examples = MagicMock()
    examples.examples = []
    mock_load.return_value = examples

    runner = CliRunner()
    result = runner.invoke(main, ["examples", "list"])
    assert result.exit_code == 0
    assert "No examples defined" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.training.store.load_examples")
def test_examples_list_shows_entries(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    ex = MagicMock()
    ex.id = "abc"
    ex.natural_language = "show users"
    ex.sql = "SELECT * FROM users"
    ex.tags = ["users"]
    examples = MagicMock()
    examples.examples = [ex]
    mock_load.return_value = examples

    runner = CliRunner()
    result = runner.invoke(main, ["examples", "list"])
    assert result.exit_code == 0
    assert "abc" in result.output
    assert "show users" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.training.store.load_examples")
def test_examples_search_matches(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    ex = MagicMock()
    ex.id = "abc"
    ex.natural_language = "show revenue"
    ex.sql = "SELECT SUM(amount) FROM orders"
    ex.tags = []
    examples = MagicMock()
    examples.examples = [ex]
    mock_load.return_value = examples

    runner = CliRunner()
    result = runner.invoke(main, ["examples", "search", "--grep", "revenue"])
    assert result.exit_code == 0
    assert "revenue" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.training.store.load_examples")
def test_examples_search_no_match(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    examples = MagicMock()
    examples.examples = []
    mock_load.return_value = examples

    runner = CliRunner()
    result = runner.invoke(main, ["examples", "search", "--grep", "xyz"])
    assert result.exit_code == 0
    assert "No matching examples" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.training.store.add_example")
def test_examples_add_success(mock_add, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_add.return_value = {"added": True, "example_id": "abc", "total_examples": 1}

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["examples", "add", "--intent", "show users", "--sql", "SELECT * FROM users"],
    )
    assert result.exit_code == 0
    assert "abc" in result.output
