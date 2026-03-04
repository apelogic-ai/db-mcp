"""Tests for BICP connection handlers."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_connections_test_uses_connector_for_named_connection(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        conn_path = Path(tmpdir) / ".db-mcp" / "connections" / "top-ledger"
        conn_path.mkdir(parents=True)

        (conn_path / ".env").write_text('DATABASE_URL="trino://user@host:8443/catalog"\n')
        (conn_path / "connector.yaml").write_text(
            "type: sql\ncapabilities:\n  connect_args:\n    http_scheme: http\n"
        )

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "trino"

        mock_connector = MagicMock()
        mock_connector.test_connection.return_value = {"connected": True, "dialect": "trino"}

        with patch("db_mcp.connectors.get_connector", return_value=mock_connector) as mock_get:
            result = await agent._handle_connections_test({"name": "top-ledger"})

        assert result["success"] is True
        mock_get.assert_called_once()
        mock_connector.test_connection.assert_called_once()


@pytest.mark.asyncio
async def test_connections_test_database_url_passes_connect_args():
    from db_mcp.bicp.agent import DBMCPAgent

    agent = DBMCPAgent.__new__(DBMCPAgent)
    agent._method_handlers = {}
    agent._settings = None
    agent._dialect = "trino"

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (1,)
    mock_conn.execute.return_value = mock_result
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.connect.return_value.__exit__.return_value = False

    with patch("db_mcp.db.connection.get_engine", return_value=mock_engine) as mock_get:
        result = await agent._handle_connections_test(
            {
                "databaseUrl": "trino://user@host:8443/catalog",
                "connectArgs": {"http_scheme": "http", "verify": False},
            }
        )

    assert result["success"] is True
    mock_get.assert_called_once_with(
        "trino://user@host:8443/catalog",
        connect_args={"http_scheme": "http", "verify": False},
    )


@pytest.mark.asyncio
async def test_connections_test_database_url_parses_connect_args_from_url():
    from db_mcp.bicp.agent import DBMCPAgent

    agent = DBMCPAgent.__new__(DBMCPAgent)
    agent._method_handlers = {}
    agent._settings = None
    agent._dialect = "trino"

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (1,)
    mock_conn.execute.return_value = mock_result
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.connect.return_value.__exit__.return_value = False

    url = "trino://user@host:8443/catalog?http_scheme=http&verify=false"

    with patch("db_mcp.db.connection.get_engine", return_value=mock_engine) as mock_get:
        result = await agent._handle_connections_test({"databaseUrl": url})

    assert result["success"] is True
    mock_get.assert_called_once_with(
        "trino://user@host:8443/catalog",
        connect_args={"http_scheme": "http", "verify": False},
    )


@pytest.mark.asyncio
async def test_connections_list_falls_back_to_connection_name_env(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        monkeypatch.setenv("CONNECTION_NAME", "playground")

        conn_path = Path(tmpdir) / ".db-mcp" / "connections" / "playground"
        conn_path.mkdir(parents=True)

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "sqlite"

        result = await agent._handle_connections_list({})

    assert result["activeConnection"] == "playground"
    assert result["connections"][0]["name"] == "playground"
    assert result["connections"][0]["isActive"] is True


@pytest.mark.asyncio
async def test_connections_list_prefers_config_over_connection_name_env(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        monkeypatch.setenv("CONNECTION_NAME", "playground")

        db_mcp_dir = Path(tmpdir) / ".db-mcp"
        connections_dir = db_mcp_dir / "connections"
        connections_dir.mkdir(parents=True)
        (connections_dir / "playground").mkdir()
        (connections_dir / "prod").mkdir()
        (db_mcp_dir / "config.yaml").write_text("active_connection: prod\n")

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "sqlite"

        result = await agent._handle_connections_list({})

    assert result["activeConnection"] == "prod"
    assert [c["name"] for c in result["connections"]] == ["playground", "prod"]
    assert result["connections"][0]["isActive"] is False
    assert result["connections"][1]["isActive"] is True


def test_get_active_connection_path_falls_back_to_connection_name_env(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        monkeypatch.setenv("CONNECTION_NAME", "playground")

        agent = DBMCPAgent.__new__(DBMCPAgent)
        path = agent._get_active_connection_path()

    assert path == Path(tmpdir) / ".db-mcp" / "connections" / "playground"


def test_get_active_connection_path_prefers_config_over_connection_name_env(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        monkeypatch.setenv("CONNECTION_NAME", "playground")

        db_mcp_dir = Path(tmpdir) / ".db-mcp"
        db_mcp_dir.mkdir(parents=True)
        (db_mcp_dir / "config.yaml").write_text("active_connection: prod\n")

        agent = DBMCPAgent.__new__(DBMCPAgent)
        path = agent._get_active_connection_path()

    assert path == Path(tmpdir) / ".db-mcp" / "connections" / "prod"
