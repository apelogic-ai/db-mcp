"""RED tests — Phase 4 step 4.02: connection_service must expose all functions
that db_mcp.bicp.agent previously implemented inline.

Each test names the function that must exist in db_mcp.services.connection and
verifies its basic contract using tmp_path fixtures (no live DB required).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# set_active_connection
# ---------------------------------------------------------------------------


def test_set_active_connection_creates_config_file(tmp_path: Path) -> None:
    """set_active_connection writes active_connection into config.yaml."""
    from db_mcp.services.connection import set_active_connection

    config_file = tmp_path / ".db-mcp" / "config.yaml"
    set_active_connection("prod", config_file)

    assert config_file.exists()
    data = yaml.safe_load(config_file.read_text())
    assert data["active_connection"] == "prod"


def test_set_active_connection_updates_existing_config(tmp_path: Path) -> None:
    """set_active_connection preserves other keys while updating active_connection."""
    from db_mcp.services.connection import set_active_connection

    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"active_connection": "old", "theme": "dark"}))

    set_active_connection("new", config_file)

    data = yaml.safe_load(config_file.read_text())
    assert data["active_connection"] == "new"
    assert data["theme"] == "dark"


# ---------------------------------------------------------------------------
# get_active_connection_path
# ---------------------------------------------------------------------------


def test_get_active_connection_path_reads_config_yaml(tmp_path: Path) -> None:
    """get_active_connection_path returns Path resolved from config.yaml."""
    from db_mcp.services.connection import get_active_connection_path

    config_file = tmp_path / "config.yaml"
    connections_dir = tmp_path / "connections"
    connections_dir.mkdir()
    (connections_dir / "prod").mkdir()
    config_file.write_text(yaml.dump({"active_connection": "prod"}))

    result = get_active_connection_path(
        config_file=config_file,
        connections_dir=connections_dir,
    )
    assert result == connections_dir / "prod"


def test_get_active_connection_path_returns_none_when_not_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_active_connection_path returns None if config is absent and env var is unset."""
    from db_mcp.services.connection import get_active_connection_path

    monkeypatch.delenv("CONNECTION_NAME", raising=False)
    result = get_active_connection_path(
        config_file=tmp_path / "missing.yaml",
        connections_dir=tmp_path / "connections",
    )
    assert result is None


def test_get_active_connection_path_falls_back_to_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When config has no active_connection, fall back to CONNECTION_NAME env var."""
    from db_mcp.services.connection import get_active_connection_path

    connections_dir = tmp_path / "connections"
    connections_dir.mkdir()
    (connections_dir / "staging").mkdir()
    monkeypatch.setenv("CONNECTION_NAME", "staging")

    result = get_active_connection_path(
        config_file=tmp_path / "config.yaml",
        connections_dir=connections_dir,
    )
    assert result == connections_dir / "staging"


# ---------------------------------------------------------------------------
# switch_active_connection
# ---------------------------------------------------------------------------


def test_switch_active_connection_updates_config(tmp_path: Path) -> None:
    """switch_active_connection writes the new name to config.yaml and returns success."""
    from db_mcp.services.connection import switch_active_connection

    connections_dir = tmp_path / "connections"
    config_file = tmp_path / "config.yaml"
    (connections_dir / "staging").mkdir(parents=True)

    result = switch_active_connection(
        "staging",
        connections_dir=connections_dir,
        config_file=config_file,
    )

    assert result["success"] is True
    assert result["activeConnection"] == "staging"
    data = yaml.safe_load(config_file.read_text())
    assert data["active_connection"] == "staging"


def test_switch_active_connection_fails_for_unknown_name(tmp_path: Path) -> None:
    """switch_active_connection returns failure when connection directory is absent."""
    from db_mcp.services.connection import switch_active_connection

    result = switch_active_connection(
        "ghost",
        connections_dir=tmp_path / "connections",
        config_file=tmp_path / "config.yaml",
    )

    assert result["success"] is False
    assert "error" in result


def test_switch_active_connection_requires_name() -> None:
    """switch_active_connection returns failure when name is falsy."""
    from db_mcp.services.connection import switch_active_connection

    result = switch_active_connection(
        "",
        connections_dir=Path("/tmp"),
        config_file=Path("/tmp/cfg.yaml"),
    )
    assert result["success"] is False


# ---------------------------------------------------------------------------
# delete_connection
# ---------------------------------------------------------------------------


def test_delete_connection_removes_directory(tmp_path: Path) -> None:
    """delete_connection removes the connection directory."""
    from db_mcp.services.connection import delete_connection

    connections_dir = tmp_path / "connections"
    (connections_dir / "old").mkdir(parents=True)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"active_connection": "other"}))

    result = delete_connection(
        "old",
        connections_dir=connections_dir,
        config_file=config_file,
    )

    assert result["success"] is True
    assert not (connections_dir / "old").exists()


def test_delete_connection_auto_switches_when_active(tmp_path: Path) -> None:
    """delete_connection auto-switches the active connection when deleting the active one."""
    from db_mcp.services.connection import delete_connection

    connections_dir = tmp_path / "connections"
    (connections_dir / "active").mkdir(parents=True)
    (connections_dir / "other").mkdir(parents=True)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"active_connection": "active"}))

    result = delete_connection(
        "active",
        connections_dir=connections_dir,
        config_file=config_file,
    )

    assert result["success"] is True
    # Should have switched to the remaining connection
    data = yaml.safe_load(config_file.read_text())
    assert data.get("active_connection") == "other"


def test_delete_connection_returns_failure_for_missing(tmp_path: Path) -> None:
    """delete_connection returns failure when connection does not exist."""
    from db_mcp.services.connection import delete_connection

    result = delete_connection(
        "nonexistent",
        connections_dir=tmp_path / "connections",
        config_file=tmp_path / "config.yaml",
    )
    assert result["success"] is False


# ---------------------------------------------------------------------------
# extract_connect_args_from_url
# ---------------------------------------------------------------------------


def test_extract_connect_args_returns_unchanged_url_when_no_query() -> None:
    """extract_connect_args_from_url returns original URL unchanged when no query params."""
    from db_mcp.services.connection import extract_connect_args_from_url

    url = "trino://host:8443/catalog"
    result_url, args = extract_connect_args_from_url(url)

    assert result_url == url
    assert args is None


def test_extract_connect_args_strips_http_scheme_and_returns_connect_args() -> None:
    """extract_connect_args_from_url removes http_scheme from URL and returns it in dict."""
    from db_mcp.services.connection import extract_connect_args_from_url

    url = "trino://host:8443/catalog?http_scheme=https"
    result_url, args = extract_connect_args_from_url(url)

    assert "http_scheme" not in result_url
    assert args is not None
    assert args["http_scheme"] == "https"


def test_extract_connect_args_handles_verify_false() -> None:
    """extract_connect_args_from_url converts verify=false to bool False."""
    from db_mcp.services.connection import extract_connect_args_from_url

    url = "trino://host:8443/catalog?verify=false"
    _, args = extract_connect_args_from_url(url)

    assert args is not None
    assert args["verify"] is False


# ---------------------------------------------------------------------------
# test_file_directory
# ---------------------------------------------------------------------------


def test_test_file_directory_success(tmp_path: Path) -> None:
    """test_file_directory returns success when FileConnector reports connected."""
    from db_mcp.services.connection import test_file_directory

    mock_connector = MagicMock()
    mock_connector.test_connection.return_value = {
        "connected": True,
        "sources": {"orders": None, "users": None},
    }

    with patch("db_mcp_data.connectors.file.FileConnector", return_value=mock_connector):
        with patch("db_mcp_data.connectors.file.FileConnectorConfig"):
            result = test_file_directory(str(tmp_path))

    assert result["success"] is True
    assert result["dialect"] == "duckdb"


def test_test_file_directory_failure(tmp_path: Path) -> None:
    """test_file_directory returns failure when FileConnector reports not connected."""
    from db_mcp.services.connection import test_file_directory

    mock_connector = MagicMock()
    mock_connector.test_connection.return_value = {
        "connected": False,
        "error": "No supported files found",
    }

    with patch("db_mcp_data.connectors.file.FileConnector", return_value=mock_connector):
        with patch("db_mcp_data.connectors.file.FileConnectorConfig"):
            result = test_file_directory(str(tmp_path))

    assert result["success"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# test_database_url
# ---------------------------------------------------------------------------


def test_test_database_url_success() -> None:
    """test_database_url returns success when SQLAlchemy connects without error."""
    from db_mcp.services.connection import test_database_url

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    with patch("db_mcp.services.connection_test.get_engine", return_value=mock_engine):
        result = test_database_url("postgresql://user:pass@host/db")

    assert result["success"] is True
    mock_engine.dispose.assert_called_once()


def test_test_database_url_failure() -> None:
    """test_database_url returns failure when SQLAlchemy raises an exception."""
    from db_mcp.services.connection import test_database_url

    with patch(
        "db_mcp.services.connection_test.get_engine",
        side_effect=Exception("connection refused"),
    ):
        result = test_database_url("postgresql://user:pass@host/db")

    assert result["success"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# create_sql_connection
# ---------------------------------------------------------------------------


def test_create_sql_connection_creates_directory_and_env_file(tmp_path: Path) -> None:
    """create_sql_connection creates the connection directory and .env file on success."""
    from db_mcp.services.connection import create_sql_connection

    connections_dir = tmp_path / "connections"
    config_file = tmp_path / "config.yaml"

    with patch(
        "db_mcp.services.connection_test.test_database_url",
        return_value={"success": True},
    ):
        result = create_sql_connection(
            "mydb",
            "postgresql://user:pass@host/db",
            connections_dir=connections_dir,
            config_file=config_file,
            set_active=False,
        )

    assert result["success"] is True
    conn_dir = connections_dir / "mydb"
    assert conn_dir.exists()
    env_file = conn_dir / ".env"
    assert env_file.exists()
    assert "postgresql://user:pass@host/db" in env_file.read_text()


def test_create_sql_connection_rejects_duplicate(tmp_path: Path) -> None:
    """create_sql_connection fails if the connection directory already exists."""
    from db_mcp.services.connection import create_sql_connection

    connections_dir = tmp_path / "connections"
    (connections_dir / "mydb").mkdir(parents=True)

    result = create_sql_connection(
        "mydb",
        "postgresql://user:pass@host/db",
        connections_dir=connections_dir,
        config_file=tmp_path / "config.yaml",
    )
    assert result["success"] is False


def test_create_sql_connection_fails_on_bad_url(tmp_path: Path) -> None:
    """create_sql_connection returns failure when database URL test fails."""
    from db_mcp.services.connection import create_sql_connection

    with patch(
        "db_mcp.services.connection.test_database_url",
        return_value={"success": False, "error": "bad creds"},
    ):
        result = create_sql_connection(
            "mydb",
            "postgresql://bad@host/db",
            connections_dir=tmp_path / "connections",
            config_file=tmp_path / "config.yaml",
        )

    assert result["success"] is False


# ---------------------------------------------------------------------------
# create_file_connection
# ---------------------------------------------------------------------------


def test_create_file_connection_creates_connector_yaml(tmp_path: Path) -> None:
    """create_file_connection writes connector.yaml for a file-type connection."""
    from db_mcp.services.connection import create_file_connection

    conn_path = tmp_path / "connections" / "files"
    config_file = tmp_path / "config.yaml"
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir)

    with patch(
        "db_mcp.services.connection.test_file_directory",
        return_value={"success": True, "message": "2 tables"},
    ):
        result = create_file_connection(
            "files",
            {"directory": data_dir},
            conn_path=conn_path,
            config_file=config_file,
            set_active=False,
        )

    assert result["success"] is True
    connector_yaml = conn_path / "connector.yaml"
    assert connector_yaml.exists()
    data = yaml.safe_load(connector_yaml.read_text())
    assert data["type"] == "file"
    assert data["directory"] == data_dir


def test_create_file_connection_fails_without_directory(tmp_path: Path) -> None:
    """create_file_connection requires directory param."""
    from db_mcp.services.connection import create_file_connection

    result = create_file_connection(
        "files",
        {},
        conn_path=tmp_path / "conn",
        config_file=tmp_path / "config.yaml",
    )
    assert result["success"] is False


# ---------------------------------------------------------------------------
# sync_api_connection
# ---------------------------------------------------------------------------


def test_sync_api_connection_returns_failure_for_missing(tmp_path: Path) -> None:
    """sync_api_connection fails when connection directory does not exist."""
    from db_mcp.services.connection import sync_api_connection

    result = sync_api_connection("ghost", connections_dir=tmp_path / "connections")
    assert result["success"] is False


def test_sync_api_connection_calls_api_connector_sync(tmp_path: Path) -> None:
    """sync_api_connection instantiates an APIConnector and calls sync()."""
    from db_mcp.services.connection import sync_api_connection

    connections_dir = tmp_path / "connections"
    conn_path = connections_dir / "feeds"
    conn_path.mkdir(parents=True)
    (conn_path / "connector.yaml").write_text(
        "type: api\nbase_url: https://example.com\nauth:\n  type: none\n"
    )

    from db_mcp_data.connectors.api import APIConnectorConfig

    mock_sync_result = {"synced": ["endpoint1"], "rows_fetched": {}, "errors": []}
    mock_connector = MagicMock()
    mock_connector.sync.return_value = mock_sync_result
    # spec=APIConnectorConfig makes isinstance() pass inside the service
    mock_config = MagicMock(spec=APIConnectorConfig)

    with (
        patch("db_mcp_data.connectors.ConnectorConfig") as mock_cc,
        patch("db_mcp_data.connectors.api.APIConnector", return_value=mock_connector),
    ):
        mock_cc.from_yaml.return_value = mock_config
        result = sync_api_connection("feeds", connections_dir=connections_dir)

    assert result["success"] is True


# ---------------------------------------------------------------------------
# build_api_template_descriptor
# ---------------------------------------------------------------------------


def test_build_api_template_descriptor_returns_none_for_unknown() -> None:
    """build_api_template_descriptor returns None for an unknown template ID."""
    from db_mcp.services.connection import build_api_template_descriptor

    with patch(
        "db_mcp.services.connection_crud.get_connector_template", return_value=None
    ):
        result = build_api_template_descriptor("nonexistent-template")

    assert result is None


def test_build_api_template_descriptor_returns_descriptor_dict() -> None:
    """build_api_template_descriptor returns a dict with expected keys for a known template."""
    from db_mcp.services.connection import build_api_template_descriptor

    mock_template = MagicMock()
    mock_template.id = "shopify"
    mock_template.title = "Shopify"
    mock_template.description = "Shopify connector"
    mock_template.base_url_prompt = "Enter your store URL"
    mock_template.connector = {
        "type": "api",
        "base_url": "https://myshop.myshopify.com",
        "auth": {"type": "bearer", "token_env": "SHOPIFY_TOKEN"},
    }
    mock_template.env = []

    with patch(
        "db_mcp.services.connection_crud.get_connector_template", return_value=mock_template
    ):
        result = build_api_template_descriptor("shopify")

    assert result is not None
    assert result["id"] == "shopify"
    assert result["title"] == "Shopify"
    assert "auth" in result
    assert "env" in result
