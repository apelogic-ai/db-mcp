"""Tests for db-mcp api CLI commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from db_mcp_cli.main import main

# ---------------------------------------------------------------------------
# api query
# ---------------------------------------------------------------------------


@patch("db_mcp_cli.commands.api_cmd._resolve_api_connector")
def test_api_query_table_output(mock_resolve):
    connector = MagicMock()
    connector.query_endpoint.return_value = {
        "data": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        "rows_returned": 2,
    }
    mock_resolve.return_value = connector

    runner = CliRunner()
    result = runner.invoke(main, ["api", "query", "-c", "test-api", "users"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


@patch("db_mcp_cli.commands.api_cmd._resolve_api_connector")
def test_api_query_json_export(mock_resolve):
    connector = MagicMock()
    connector.query_endpoint.return_value = {
        "data": [{"id": 1, "name": "Alice"}],
        "rows_returned": 1,
    }
    mock_resolve.return_value = connector

    runner = CliRunner()
    result = runner.invoke(
        main, ["api", "query", "-c", "test-api", "--export", "json", "users"]
    )
    assert result.exit_code == 0
    assert '"Alice"' in result.output


@patch("db_mcp_cli.commands.api_cmd._resolve_api_connector")
def test_api_query_with_params(mock_resolve):
    connector = MagicMock()
    connector.query_endpoint.return_value = {"data": [{"x": 1}], "rows_returned": 1}
    mock_resolve.return_value = connector

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["api", "query", "-c", "test-api", "getBalance",
         "--param", 'params=["addr123"]'],
    )
    assert result.exit_code == 0
    # Verify the connector was called with parsed params
    call_args = connector.query_endpoint.call_args
    assert call_args[0][0] == "getBalance"
    params = call_args[0][1]
    assert "params" in params


@patch("db_mcp_cli.commands.api_cmd._resolve_api_connector")
def test_api_query_error(mock_resolve):
    connector = MagicMock()
    connector.query_endpoint.return_value = {"error": "Unauthorized"}
    mock_resolve.return_value = connector

    runner = CliRunner()
    result = runner.invoke(main, ["api", "query", "-c", "test-api", "users"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# api describe
# ---------------------------------------------------------------------------


@patch("db_mcp_cli.commands.api_cmd._resolve_api_connector")
def test_api_describe_shows_endpoints(mock_resolve):
    from db_mcp_data.connectors.api_config import APIEndpointConfig, APIQueryParamConfig

    connector = MagicMock()
    connector.api_config.endpoints = [
        APIEndpointConfig(name="getBalance", path="/", method="POST"),
        APIEndpointConfig(
            name="users", path="/users", method="GET",
            query_params=[APIQueryParamConfig(name="limit", type="integer")],
        ),
    ]
    mock_resolve.return_value = connector

    runner = CliRunner()
    result = runner.invoke(main, ["api", "describe", "-c", "test-api"])
    assert result.exit_code == 0
    assert "getBalance" in result.output
    assert "users" in result.output


@patch("db_mcp_cli.commands.api_cmd._resolve_api_connector")
def test_api_describe_single_endpoint(mock_resolve):
    from db_mcp_data.connectors.api_config import APIEndpointConfig, APIQueryParamConfig

    connector = MagicMock()
    connector.api_config.endpoints = [
        APIEndpointConfig(
            name="users", path="/users", method="GET",
            query_params=[APIQueryParamConfig(name="limit", type="integer")],
        ),
    ]
    mock_resolve.return_value = connector

    runner = CliRunner()
    result = runner.invoke(main, ["api", "describe", "-c", "test-api", "users"])
    assert result.exit_code == 0
    assert "users" in result.output
    assert "limit" in result.output


# ---------------------------------------------------------------------------
# api sql
# ---------------------------------------------------------------------------


@patch("db_mcp_data.connectors.get_connector_capabilities", return_value={"supports_sql": True})
@patch("db_mcp_cli.commands.api_cmd._resolve_api_connector")
def test_api_sql_success(mock_resolve, mock_caps):
    connector = MagicMock()
    connector.execute_sql.return_value = [{"col1": "val1"}, {"col1": "val2"}]
    mock_resolve.return_value = connector

    runner = CliRunner()
    result = runner.invoke(
        main, ["api", "sql", "-c", "test-api", "SELECT * FROM trades LIMIT 2"]
    )
    assert result.exit_code == 0
    assert "val1" in result.output


@patch("db_mcp_data.connectors.get_connector_capabilities", return_value={"supports_sql": False})
@patch("db_mcp_cli.commands.api_cmd._resolve_api_connector")
def test_api_sql_not_supported(mock_resolve, mock_caps):
    connector = MagicMock()
    mock_resolve.return_value = connector

    runner = CliRunner()
    result = runner.invoke(
        main, ["api", "sql", "-c", "test-api", "SELECT 1"]
    )
    assert result.exit_code != 0
    assert "does not support SQL" in result.output
