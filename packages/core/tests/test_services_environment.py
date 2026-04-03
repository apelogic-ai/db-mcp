"""TDD tests for services.environment — shared sandbox environment helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from db_mcp.services.environment import build_sandbox_environment, load_connection_env


class TestLoadConnectionEnv:
    """Tests for load_connection_env."""

    def test_missing_env_file(self, tmp_path: Path) -> None:
        assert load_connection_env(tmp_path) == {}

    def test_basic_key_value(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("FOO=bar\n")
        assert load_connection_env(tmp_path) == {"FOO": "bar"}

    def test_strips_quotes(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text('KEY="hello"\nKEY2=\'world\'\n')
        result = load_connection_env(tmp_path)
        assert result["KEY"] == "hello"
        assert result["KEY2"] == "world"

    def test_skips_comments_and_blank_lines(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("# comment\n\nA=1\n  \n")
        result = load_connection_env(tmp_path)
        assert result == {"A": "1"}

    def test_skips_lines_without_equals(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("NOEQUALS\nOK=yes\n")
        assert load_connection_env(tmp_path) == {"OK": "yes"}

    def test_value_with_equals_sign(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("URL=postgres://host:5432/db?sslmode=require\n")
        result = load_connection_env(tmp_path)
        assert result["URL"] == "postgres://host:5432/db?sslmode=require"


class TestBuildSandboxEnvironment:
    """Tests for build_sandbox_environment."""

    def _make_connector(
        self,
        database_url: str = "",
        base_url: str = "",
        capabilities: dict | None = None,
    ) -> MagicMock:
        config = MagicMock()
        config.database_url = database_url
        config.base_url = base_url
        config.capabilities = capabilities or {}
        connector = MagicMock()
        connector.config = config
        connector.api_config = None
        return connector

    def test_basic_env_keys(self, tmp_path: Path) -> None:
        connector = self._make_connector()
        env = build_sandbox_environment("myconn", tmp_path, connector)
        assert env["CONNECTION_NAME"] == "myconn"
        assert env["CONNECTION_PATH"] == "/workspace"
        assert env["VAULT_PATH"] == "/workspace"
        assert env["HOME"] == "/workspace"
        assert env["PYTHONUNBUFFERED"] == "1"

    def test_database_url_set(self, tmp_path: Path) -> None:
        connector = self._make_connector(database_url="postgres://localhost/db")
        env = build_sandbox_environment("c", tmp_path, connector)
        assert env["DATABASE_URL"] == "postgres://localhost/db"

    def test_database_url_empty_not_set(self, tmp_path: Path) -> None:
        connector = self._make_connector(database_url="")
        env = build_sandbox_environment("c", tmp_path, connector)
        assert "DATABASE_URL" not in env

    def test_base_url_from_config(self, tmp_path: Path) -> None:
        connector = self._make_connector(base_url="https://api.example.com")
        env = build_sandbox_environment("c", tmp_path, connector)
        assert env["BASE_URL"] == "https://api.example.com"

    def test_base_url_from_api_config(self, tmp_path: Path) -> None:
        connector = MagicMock()
        connector.config = MagicMock()
        connector.config.database_url = ""
        connector.config.base_url = ""
        connector.config.capabilities = {}
        api_config = MagicMock()
        api_config.base_url = "https://api2.example.com"
        connector.api_config = api_config
        env = build_sandbox_environment("c", tmp_path, connector)
        assert env["BASE_URL"] == "https://api2.example.com"

    def test_connect_args_serialized(self, tmp_path: Path) -> None:
        import json

        connector = self._make_connector(
            capabilities={"connect_args": {"sslmode": "require"}}
        )
        env = build_sandbox_environment("c", tmp_path, connector)
        assert json.loads(env["DB_MCP_CONNECT_ARGS_JSON"]) == {"sslmode": "require"}

    def test_merges_dot_env(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("CUSTOM_VAR=hello\n")
        connector = self._make_connector()
        env = build_sandbox_environment("c", tmp_path, connector)
        assert env["CUSTOM_VAR"] == "hello"

    def test_connector_attrs_override_dot_env(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("DATABASE_URL=from_env\n")
        connector = self._make_connector(database_url="from_connector")
        env = build_sandbox_environment("c", tmp_path, connector)
        assert env["DATABASE_URL"] == "from_connector"
