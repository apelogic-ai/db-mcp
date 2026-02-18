"""Tests for the `db-mcp discover` CLI command."""

import json
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from db_mcp.cli import main


def _make_mock_connector():
    """Create a mock connector with realistic discovery responses."""
    connector = MagicMock()
    connector.test_connection.return_value = {"connected": True, "dialect": "postgresql"}
    connector.get_catalogs.return_value = [None]
    connector.get_schemas.return_value = ["public", "analytics"]
    connector.get_tables.side_effect = lambda schema=None, catalog=None: (
        [{"name": "users", "full_name": f"{schema}.users"}]
        if schema == "public"
        else [{"name": "events", "full_name": f"{schema}.events"}]
    )
    connector.get_columns.side_effect = lambda table, schema=None, catalog=None: [
        {"name": "id", "type": "integer"},
        {"name": "name", "type": "varchar"},
    ]
    return connector


def _extract_yaml(output: str) -> dict:
    """Extract YAML from CLI output, skipping Rich progress lines."""
    # Find the start of YAML (first line starting with a yaml key)
    lines = output.split("\n")
    yaml_start = None
    for i, line in enumerate(lines):
        if line.startswith("version:") or line.startswith("tables:"):
            yaml_start = i
            break
    if yaml_start is None:
        raise ValueError(f"No YAML found in output: {output[:200]}")
    return yaml.safe_load("\n".join(lines[yaml_start:]))


def _extract_json(output: str) -> dict:
    """Extract JSON from CLI output, skipping Rich progress lines."""
    # Find the JSON object
    start = output.index("{")
    return json.loads(output[start:])


class TestDiscoverCommand:
    """Tests for the discover CLI command."""

    def test_discover_no_url_no_connection_no_active(self, tmp_path):
        """Should fail when no URL, connection, or active connection exists."""
        runner = CliRunner()
        with (
            patch(
                "db_mcp.cli.commands.discover_cmd.get_active_connection",
                return_value="default",
            ),
            patch(
                "db_mcp.cli.commands.discover_cmd.get_connection_path",
                return_value=tmp_path / "nonexistent",
            ),
        ):
            result = runner.invoke(main, ["discover"])
        assert result.exit_code != 0

    def test_discover_named_connection_not_found(self, tmp_path):
        """Should fail when named connection doesn't exist."""
        runner = CliRunner()
        with patch(
                "db_mcp.cli.commands.discover_cmd.get_connection_path",
                return_value=tmp_path / "nonexistent",
            ):
            result = runner.invoke(main, ["discover", "-c", "bogus"])
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("db_mcp.cli.commands.discover_cmd.get_connection_path")
    def test_discover_connection_failed(self, mock_path, tmp_path):
        """Should fail gracefully on connection error."""
        runner = CliRunner()
        mock_connector = MagicMock()
        mock_connector.test_connection.return_value = {"connected": False, "error": "refused"}

        with patch("db_mcp.connectors.sql.SQLConnector", return_value=mock_connector):
            result = runner.invoke(main, ["discover", "--url", "postgres://bad:url@host/db"])
        assert result.exit_code != 0

    def test_discover_with_url_yaml(self):
        """Should discover schema and output YAML."""
        runner = CliRunner()
        mock_connector = _make_mock_connector()

        with patch("db_mcp.connectors.sql.SQLConnector", return_value=mock_connector):
            result = runner.invoke(main, ["discover", "--url", "postgres://u:p@h/db"])

        assert result.exit_code == 0
        parsed = _extract_yaml(result.output)
        assert parsed is not None
        assert "tables" in parsed
        assert len(parsed["tables"]) == 2

    def test_discover_with_url_json(self):
        """Should discover schema and output JSON."""
        runner = CliRunner()
        mock_connector = _make_mock_connector()

        with patch("db_mcp.connectors.sql.SQLConnector", return_value=mock_connector):
            result = runner.invoke(
                main, ["discover", "--url", "postgres://u:p@h/db", "--format", "json"]
            )

        assert result.exit_code == 0
        parsed = _extract_json(result.output)
        assert "tables" in parsed
        assert len(parsed["tables"]) == 2

    def test_discover_output_file(self, tmp_path):
        """Should write to output file."""
        runner = CliRunner()
        mock_connector = _make_mock_connector()
        out_file = tmp_path / "schema.yaml"

        with patch("db_mcp.connectors.sql.SQLConnector", return_value=mock_connector):
            result = runner.invoke(
                main, ["discover", "--url", "postgres://u:p@h/db", "-o", str(out_file)]
            )

        assert result.exit_code == 0
        assert out_file.exists()
        parsed = yaml.safe_load(out_file.read_text())
        assert len(parsed["tables"]) == 2

    def test_discover_columns_included(self):
        """Should include column names and types."""
        runner = CliRunner()
        mock_connector = _make_mock_connector()

        with patch("db_mcp.connectors.sql.SQLConnector", return_value=mock_connector):
            result = runner.invoke(main, ["discover", "--url", "postgres://u:p@h/db"])

        parsed = _extract_yaml(result.output)
        table = parsed["tables"][0]
        assert len(table["columns"]) == 2
        assert table["columns"][0]["name"] == "id"
        assert table["columns"][0]["type"] == "integer"
