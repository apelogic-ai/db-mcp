"""Tests for db_mcp.cli.connection module.

Tests list_connections, get_connection_path, connection_exists
using a mocked filesystem (no real disk I/O to ~/.db-mcp).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db_mcp.cli.connection import (
    _get_connection_env_path,
    _load_connection_env,
    _save_connection_env,
    connection_exists,
    get_active_connection,
    get_connection_path,
    list_connections,
    set_active_connection,
)


class TestGetConnectionPath:
    def test_returns_path_under_connections_dir(self):
        """get_connection_path joins CONNECTIONS_DIR with the name."""
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", Path("/fake/.db-mcp/connections")):
            result = get_connection_path("mydb")
        assert result == Path("/fake/.db-mcp/connections/mydb")

    def test_different_names(self):
        """Each name produces a distinct path."""
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", Path("/x/connections")):
            assert get_connection_path("a") != get_connection_path("b")


class TestListConnections:
    def test_returns_empty_when_dir_missing(self):
        """Returns [] when connections directory doesn't exist."""
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            result = list_connections()
        assert result == []

    def test_returns_sorted_directory_names(self, tmp_path):
        """Returns sorted list of subdirectory names."""
        (tmp_path / "zebra").mkdir()
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        # Add a file (not a directory) — should be excluded
        (tmp_path / "notadir.txt").write_text("ignored")

        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            result = list_connections()

        assert result == ["alpha", "beta", "zebra"]

    def test_excludes_files(self, tmp_path):
        """Only directories are returned, not files."""
        (tmp_path / "conn1").mkdir()
        (tmp_path / "file.yaml").write_text("not a connection")

        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            result = list_connections()

        assert result == ["conn1"]


class TestConnectionExists:
    def test_returns_true_when_dir_exists(self, tmp_path):
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            (tmp_path / "myconn").mkdir()
            assert connection_exists("myconn") is True

    def test_returns_false_when_dir_missing(self, tmp_path):
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            assert connection_exists("nonexistent") is False


class TestGetActiveConnection:
    def test_returns_default_when_no_config(self):
        with patch("db_mcp.cli.connection.load_config", return_value={}):
            result = get_active_connection()
        assert result == "default"

    def test_returns_configured_active_connection(self):
        with patch(
            "db_mcp.cli.connection.load_config",
            return_value={"active_connection": "production"},
        ):
            result = get_active_connection()
        assert result == "production"


class TestSetActiveConnection:
    def test_updates_config_with_new_active(self):
        saved = {}

        def mock_save(cfg):
            saved.update(cfg)

        with (
            patch("db_mcp.cli.connection.load_config", return_value={"other_key": "val"}),
            patch("db_mcp.cli.connection.save_config", side_effect=mock_save),
        ):
            set_active_connection("staging")

        assert saved["active_connection"] == "staging"
        assert saved["other_key"] == "val"  # existing keys preserved


class TestConnectionEnvPath:
    def test_env_path_is_dotenv_in_connection_dir(self, tmp_path):
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            result = _get_connection_env_path("myconn")
        assert result == tmp_path / "myconn" / ".env"


class TestLoadConnectionEnv:
    def test_returns_empty_when_no_env_file(self, tmp_path):
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            result = _load_connection_env("nonexistent")
        assert result == {}

    def test_parses_key_value_pairs(self, tmp_path):
        conn_dir = tmp_path / "myconn"
        conn_dir.mkdir()
        env_file = conn_dir / ".env"
        env_file.write_text(
            '# comment\nDATABASE_URL="postgresql://u:p@h/db"\nFOO=bar\n'
        )

        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            result = _load_connection_env("myconn")

        assert result["DATABASE_URL"] == "postgresql://u:p@h/db"
        assert result["FOO"] == "bar"
        assert len(result) == 2

    def test_strips_surrounding_quotes(self, tmp_path):
        conn_dir = tmp_path / "myconn"
        conn_dir.mkdir()
        (conn_dir / ".env").write_text('KEY="quoted"\nKEY2=\'single\'\n')

        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            result = _load_connection_env("myconn")

        assert result["KEY"] == "quoted"
        assert result["KEY2"] == "single"

    def test_skips_comment_lines(self, tmp_path):
        conn_dir = tmp_path / "myconn"
        conn_dir.mkdir()
        (conn_dir / ".env").write_text("# this is a comment\nREAL_KEY=value\n")

        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            result = _load_connection_env("myconn")

        assert "REAL_KEY" in result
        assert len(result) == 1


class TestSaveConnectionEnv:
    def test_creates_env_file_with_credentials(self, tmp_path):
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            _save_connection_env("myconn", {"DATABASE_URL": "postgres://localhost/db"})

        env_file = tmp_path / "myconn" / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert "DATABASE_URL" in content
        assert "postgres://localhost/db" in content

    def test_creates_connection_directory_if_missing(self, tmp_path):
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            _save_connection_env("newconn", {"KEY": "val"})

        assert (tmp_path / "newconn").is_dir()

    def test_multiple_env_vars_written(self, tmp_path):
        with patch("db_mcp.cli.connection.CONNECTIONS_DIR", tmp_path):
            _save_connection_env("myconn", {"A": "1", "B": "2"})

        content = (tmp_path / "myconn" / ".env").read_text()
        assert "A=" in content
        assert "B=" in content
