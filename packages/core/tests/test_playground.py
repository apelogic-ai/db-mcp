"""Tests for playground connection installer."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from db_mcp.cli import main
from db_mcp.playground import (
    PLAYGROUND_CONNECTION_NAME,
    install_playground,
    is_playground_installed,
)


@pytest.fixture
def temp_home_dir(monkeypatch):
    """Create a temporary home directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        yield Path(tmpdir)


@pytest.fixture
def mock_data_path():
    """Mock the playground data path to avoid relying on actual bundled data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_path = Path(tmpdir)

        # Create mock chinook.db
        chinook_db = data_path / "chinook.db"
        chinook_db.write_bytes(b"mock sqlite database content")

        # Create mock playground directory
        playground_dir = data_path / "playground"
        playground_dir.mkdir()

        with patch("db_mcp.playground._get_data_path", return_value=data_path):
            yield data_path


def test_install_playground_creates_connector_with_skip_validate(temp_home_dir, mock_data_path):
    """Test that install_playground() creates connector.yaml with supports_validate_sql: false."""
    result = install_playground()

    assert result["success"] is True
    assert result["connection"] == PLAYGROUND_CONNECTION_NAME
    assert "database_url" in result
    assert result.get("already_installed") is not True

    # Check that the connector.yaml file was created
    playground_dir = temp_home_dir / ".db-mcp" / "connections" / PLAYGROUND_CONNECTION_NAME
    connector_path = playground_dir / "connector.yaml"

    assert connector_path.exists()

    # Load and verify the connector config
    with open(connector_path) as f:
        config = yaml.safe_load(f)

    assert config["type"] == "sql"
    assert config["database_url"].startswith("sqlite:///")
    assert config["capabilities"]["supports_validate_sql"] is False


def test_install_playground_already_installed_returns_existing(temp_home_dir, mock_data_path):
    """Test that install_playground() returns already_installed: true when called twice."""
    # First installation
    result1 = install_playground()
    assert result1["success"] is True
    assert result1.get("already_installed") is not True

    # Second installation should return already_installed
    result2 = install_playground()
    assert result2["success"] is True
    assert result2["already_installed"] is True
    assert result2["connection"] == PLAYGROUND_CONNECTION_NAME
    assert result2["database_url"] == result1["database_url"]


def test_is_playground_installed(temp_home_dir, mock_data_path):
    """Test is_playground_installed() function."""
    # Should return False before installation
    assert is_playground_installed() is False

    # Install playground
    install_playground()

    # Should return True after installation
    assert is_playground_installed() is True


def test_playground_install_cli_command(temp_home_dir, mock_data_path):
    """Test the 'db-mcp playground install' CLI command."""
    runner = CliRunner()

    # Test install command
    result = runner.invoke(main, ["playground", "install"])

    assert result.exit_code == 0
    assert "✓ Playground installed:" in result.output
    assert "sqlite:///" in result.output

    # Test that running install again shows already installed
    result2 = runner.invoke(main, ["playground", "install"])
    assert result2.exit_code == 0
    assert "Playground already installed." in result2.output


def test_playground_status_cli_command_not_installed(temp_home_dir):
    """Test the 'db-mcp playground status' CLI command when not installed."""
    runner = CliRunner()

    result = runner.invoke(main, ["playground", "status"])

    assert result.exit_code == 0
    assert "Playground: not installed" in result.output
    assert "Run 'db-mcp playground install' to install." in result.output


def test_playground_status_cli_command_installed(temp_home_dir, mock_data_path):
    """Test the 'db-mcp playground status' CLI command when installed."""
    runner = CliRunner()

    # Install playground first
    install_playground()

    # Test status command
    result = runner.invoke(main, ["playground", "status"])

    assert result.exit_code == 0
    assert "Playground: installed" in result.output
    assert f"Connection: {PLAYGROUND_CONNECTION_NAME}" in result.output
    assert "sqlite:///" in result.output


def test_playground_cli_commands_help():
    """Test that playground CLI commands have proper help text."""
    runner = CliRunner()

    # Test main playground help
    result = runner.invoke(main, ["playground", "--help"])
    assert result.exit_code == 0
    assert "Manage the playground connection" in result.output
    assert "install" in result.output
    assert "status" in result.output

    # Test install command help
    result = runner.invoke(main, ["playground", "install", "--help"])
    assert result.exit_code == 0
    assert "Install the playground connection" in result.output

    # Test status command help
    result = runner.invoke(main, ["playground", "status", "--help"])
    assert result.exit_code == 0
    assert "Check if playground is installed" in result.output
