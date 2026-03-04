"""Tests for `db-mcp connector` commands."""

from __future__ import annotations

from click.testing import CliRunner

from db_mcp.cli.main import main


def test_connector_help():
    runner = CliRunner()
    result = runner.invoke(main, ["connector", "--help"])
    assert result.exit_code == 0
    assert "validate" in result.output


def test_connector_validate_passes_with_valid_yaml(tmp_path):
    yaml_path = tmp_path / "connector.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "spec_version: 1.0.0",
                "type: api",
                "profile: api_openapi",
                "base_url: https://api.example.com",
                "",
            ]
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["connector", "validate", str(yaml_path)])
    assert result.exit_code == 0, result.output
    assert "valid" in result.output.lower()


def test_connector_validate_fails_with_invalid_yaml(tmp_path):
    yaml_path = tmp_path / "connector.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "spec_version: 2.0.0",
                "type: api",
                "profile: api_openapi",
                "base_url: https://api.example.com",
                "",
            ]
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["connector", "validate", str(yaml_path)])
    assert result.exit_code == 1
    assert "invalid" in result.output.lower()
    assert "major version" in result.output.lower()

