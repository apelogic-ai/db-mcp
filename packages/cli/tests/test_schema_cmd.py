"""Tests for db-mcp schema CLI commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from db_mcp_cli.main import main


@patch("db_mcp_cli.commands.schema_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.schema_cmd.get_connection_path")
@patch("db_mcp_knowledge.onboarding.schema_store.load_schema_descriptions")
def test_schema_show_empty(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_load.return_value = None

    runner = CliRunner()
    result = runner.invoke(main, ["schema", "show"])
    assert result.exit_code == 0
    assert "No schema descriptions" in result.output


@patch("db_mcp_cli.commands.schema_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.schema_cmd.get_connection_path")
@patch("db_mcp_knowledge.onboarding.schema_store.load_schema_descriptions")
def test_schema_show_with_data(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    col = MagicMock()
    col.name = "id"
    col.description = "Primary key"
    td = MagicMock()
    td.full_name = "public.users"
    td.name = "users"
    td.description = "User accounts"
    td.columns = [col]
    descs = MagicMock()
    descs.tables = [td]
    mock_load.return_value = descs

    runner = CliRunner()
    result = runner.invoke(main, ["schema", "show"])
    assert result.exit_code == 0
    assert "public.users" in result.output
    assert "id" in result.output


@patch("db_mcp_cli.commands.schema_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.schema_cmd.get_connection_path")
@patch("db_mcp_knowledge.onboarding.schema_store.load_schema_descriptions")
def test_schema_export_yaml(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    descs = MagicMock()
    descs.model_dump.return_value = {"tables": []}
    mock_load.return_value = descs

    runner = CliRunner()
    result = runner.invoke(main, ["schema", "export"])
    assert result.exit_code == 0
    assert "tables" in result.output


@patch("db_mcp_cli.commands.schema_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.schema_cmd.get_connection_path")
@patch("db_mcp_knowledge.onboarding.schema_store.load_schema_descriptions")
def test_schema_export_json(mock_load, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    descs = MagicMock()
    descs.model_dump.return_value = {"tables": []}
    mock_load.return_value = descs

    runner = CliRunner()
    result = runner.invoke(main, ["schema", "export", "--format", "json"])
    assert result.exit_code == 0
    assert '"tables"' in result.output


@patch("db_mcp_cli.commands.schema_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.schema_cmd.get_connection_path")
@patch("db_mcp.services.schema.list_catalogs")
def test_schema_catalogs(mock_list, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_list.return_value = {"catalogs": ["default", "analytics"]}

    runner = CliRunner()
    result = runner.invoke(main, ["schema", "catalogs"])
    assert result.exit_code == 0
    assert "default" in result.output
    assert "analytics" in result.output


@patch("db_mcp_cli.commands.schema_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.schema_cmd.get_connection_path")
@patch("db_mcp.services.schema.list_tables")
def test_schema_tables(mock_list, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_list.return_value = {"tables": ["users", "orders"]}

    runner = CliRunner()
    result = runner.invoke(main, ["schema", "tables"])
    assert result.exit_code == 0
    assert "users" in result.output
    assert "orders" in result.output


@patch("db_mcp_cli.commands.schema_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.schema_cmd.get_connection_path")
@patch("db_mcp.services.schema.describe_table")
def test_schema_describe(mock_desc, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_desc.return_value = {
        "columns": [
            {"name": "id", "type": "integer", "nullable": False},
            {"name": "email", "type": "varchar", "nullable": True},
        ]
    }

    runner = CliRunner()
    result = runner.invoke(main, ["schema", "describe", "users"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "email" in result.output


@patch("db_mcp_cli.commands.schema_cmd.get_active_connection", return_value="test")
@patch("db_mcp_cli.commands.schema_cmd.get_connection_path")
@patch("db_mcp.services.schema.sample_table")
def test_schema_sample(mock_sample, mock_path, mock_active, tmp_path):
    mock_path.return_value = tmp_path
    (tmp_path / "dummy").write_text("")
    mock_sample.return_value = {
        "columns": ["id", "name"],
        "rows": [[1, "Alice"], [2, "Bob"]],
    }

    runner = CliRunner()
    result = runner.invoke(main, ["schema", "sample", "users"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output
