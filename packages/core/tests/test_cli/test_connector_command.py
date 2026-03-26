"""Tests for `db-mcp connector` commands."""

from __future__ import annotations

from click.testing import CliRunner

from db_mcp.cli.main import main


def test_connector_help():
    runner = CliRunner()
    result = runner.invoke(main, ["connector", "--help"])
    assert result.exit_code == 0
    assert "validate" in result.output
    assert "templates" in result.output


def test_connector_templates_lists_builtins():
    runner = CliRunner()
    result = runner.invoke(main, ["connector", "templates"])

    assert result.exit_code == 0, result.output
    assert "jira" in result.output
    assert "dune" in result.output
    assert "superset" in result.output


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


def test_connector_validate_passes_with_valid_template_yaml(tmp_path):
    yaml_path = tmp_path / "jira.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "id: jira",
                "title: Jira Cloud",
                "description: Jira API template",
                "env:",
                "  - name: JIRA_EMAIL",
                "    prompt: Jira email",
                "    secret: false",
                "connector:",
                "  spec_version: 1.0.0",
                "  type: api",
                "  profile: api_openapi",
                "  base_url: https://example.atlassian.net",
                "",
            ]
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["connector", "validate", str(yaml_path)])
    assert result.exit_code == 0, result.output
    assert "template" in result.output.lower()
    assert "jira" in result.output


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
