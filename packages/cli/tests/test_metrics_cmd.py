"""Tests for db-mcp metrics CLI commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from db_mcp_cli.main import main


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.metrics.store.load_metrics")
def test_metrics_list_empty(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")  # make path exist
    catalog = MagicMock()
    catalog.metrics = []
    mock_load.return_value = catalog

    runner = CliRunner()
    result = runner.invoke(main, ["metrics", "list"])
    assert result.exit_code == 0
    assert "No metrics defined" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.metrics.store.load_metrics")
def test_metrics_list_shows_table(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    m = MagicMock()
    m.name = "dau"
    m.description = "Daily active users"
    m.status = "approved"
    m.tags = ["engagement"]
    catalog = MagicMock()
    catalog.metrics = [m]
    mock_load.return_value = catalog

    runner = CliRunner()
    result = runner.invoke(main, ["metrics", "list"])
    assert result.exit_code == 0
    assert "dau" in result.output
    assert "Daily active users" in result.output


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.metrics.store.add_metric")
def test_metrics_add_success(mock_add, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_add.return_value = {"added": True}

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["metrics", "add", "--name", "revenue", "--description", "Total rev", "--sql", "SUM(amt)"],
    )
    assert result.exit_code == 0
    assert "added" in result.output.lower()
    mock_add.assert_called_once()


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.metrics.store.delete_metric")
def test_metrics_remove_success(mock_delete, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_delete.return_value = {"deleted": True}

    runner = CliRunner()
    result = runner.invoke(main, ["metrics", "remove", "revenue"])
    assert result.exit_code == 0
    assert "removed" in result.output.lower()


@patch("db_mcp_cli.connection.get_active_connection", return_value="test")
@patch("db_mcp_cli.connection.get_connection_path")
@patch("db_mcp_knowledge.metrics.store.delete_metric")
def test_metrics_remove_not_found(mock_delete, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_delete.return_value = {"deleted": False, "error": "Metric not found"}

    runner = CliRunner()
    result = runner.invoke(main, ["metrics", "remove", "nope"])
    assert result.exit_code != 0


def test_metrics_list_with_connection_flag(tmp_path):
    with patch(
        "db_mcp.registry.ConnectionRegistry.get_connection_path", return_value=tmp_path
    ), patch("db_mcp_knowledge.metrics.store.load_metrics") as mock_load:
        (tmp_path / "dummy").write_text("")
        catalog = MagicMock()
        catalog.metrics = []
        mock_load.return_value = catalog

        runner = CliRunner()
        result = runner.invoke(main, ["metrics", "list", "-c", "prod"])
        assert result.exit_code == 0
        mock_load.assert_called_once_with("prod", connection_path=tmp_path)
