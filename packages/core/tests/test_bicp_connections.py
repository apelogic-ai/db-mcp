"""Tests for BICP connection handlers."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from db_mcp_models import OnboardingPhase


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
async def test_connections_get_prefers_connector_yaml_database_url_over_env(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        conn_path = Path(tmpdir) / ".db-mcp" / "connections" / "top-ledger"
        conn_path.mkdir(parents=True)

        (conn_path / ".env").write_text(
            'DATABASE_URL="trino://user@host:8443/catalog-from-env"\n'
        )
        (conn_path / "connector.yaml").write_text(
            "type: sql\n"
            "database_url: trino://user@host:8443/catalog-from-yaml\n"
            "capabilities:\n"
            "  connect_args:\n"
            "    http_scheme: http\n"
        )

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "trino"

        result = await agent._handle_connections_get({"name": "top-ledger"})

        assert result["success"] is True
        assert result["connectorType"] == "sql"
        assert result["databaseUrl"] == "trino://user@host:8443/catalog-from-yaml"


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


@pytest.mark.asyncio
async def test_sample_table_uses_named_connection(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        conn_path = Path(tmpdir) / ".db-mcp" / "connections" / "playground"
        conn_path.mkdir(parents=True)

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "sqlite"

        mock_connector = MagicMock()
        mock_connector.get_table_sample.return_value = [
            {"AlbumId": 1, "Title": "For Those About To Rock"}
        ]

        with patch("db_mcp.bicp.agent.get_connector", return_value=mock_connector) as mock_get:
            result = await agent._handle_sample_table(
                {
                    "connection": "playground",
                    "table_name": "Album",
                    "schema": "main",
                    "limit": 5,
                }
            )

    assert result["error"] is None
    assert result["row_count"] == 1
    assert result["full_name"] == "main.Album"
    mock_get.assert_called_once_with(connection_path=conn_path)
    mock_connector.get_table_sample.assert_called_once_with(
        "Album",
        schema="main",
        catalog=None,
        limit=5,
    )


@pytest.mark.asyncio
async def test_connections_save_discovery_persists_schema_and_state(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent
    from db_mcp.onboarding.schema_store import load_schema_descriptions
    from db_mcp.onboarding.state import load_state

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        conn_path = Path(tmpdir) / ".db-mcp" / "connections" / "playground-copy"
        conn_path.mkdir(parents=True)

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "sqlite"

        result = await agent._handle_connections_save_discovery(
            {
                "name": "playground-copy",
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "Album",
                        "schema": "main",
                        "catalog": None,
                        "full_name": "main.Album",
                        "columns": [
                            {"name": "AlbumId", "type": "INTEGER"},
                            {"name": "Title", "type": "VARCHAR"},
                        ],
                    },
                    {
                        "name": "Artist",
                        "schema": "main",
                        "catalog": None,
                        "full_name": "main.Artist",
                        "columns": [
                            {"name": "ArtistId", "type": "INTEGER"},
                        ],
                    },
                ],
            }
        )

        assert result["success"] is True
        assert result["tableCount"] == 2
        assert result["schemaCount"] == 1

        schema = load_schema_descriptions("playground-copy", connection_path=conn_path)
        assert schema is not None
        assert schema.provider_id == "playground-copy"
        assert schema.dialect == "sqlite"
        assert [table.full_name for table in schema.tables] == ["main.Album", "main.Artist"]
        assert [column.name for column in schema.tables[0].columns] == ["AlbumId", "Title"]

        state = load_state(connection_path=conn_path)
        assert state is not None
        assert state.phase == OnboardingPhase.DOMAIN
        assert state.connection_verified is True
        assert state.dialect_detected == "sqlite"
        assert state.schemas_discovered == ["main"]
        assert state.tables_discovered == ["main.Album", "main.Artist"]
        assert state.tables_total == 2


@pytest.mark.asyncio
async def test_connections_complete_onboarding_marks_connection_complete(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent
    from db_mcp.onboarding.state import load_state

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        conn_path = Path(tmpdir) / ".db-mcp" / "connections" / "playground-copy"
        conn_path.mkdir(parents=True)

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "sqlite"

        await agent._handle_connections_save_discovery(
            {
                "name": "playground-copy",
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "Album",
                        "schema": "main",
                        "catalog": None,
                        "full_name": "main.Album",
                        "columns": [{"name": "AlbumId", "type": "INTEGER"}],
                    }
                ],
            }
        )

        result = await agent._handle_connections_complete_onboarding(
            {
                "name": "playground-copy",
            }
        )

        assert result["success"] is True
        assert result["phase"] == "complete"

        state = load_state(connection_path=conn_path)
        assert state is not None
        assert state.phase == OnboardingPhase.COMPLETE
        assert state.tables_discovered == ["main.Album"]
        assert state.tables_total == 1


@pytest.mark.asyncio
async def test_context_create_bootstraps_draft_connection_directory(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "sqlite"

        result = await agent._handle_context_create(
            {
                "connection": "top-ledger",
                "path": "connector.yaml",
                "content": "type: sql\ndatabase_url: trino://user@host:8443/catalog\n",
            }
        )

        conn_path = Path(tmpdir) / ".db-mcp" / "connections" / "top-ledger"
        connector_path = conn_path / "connector.yaml"

        assert result["success"] is True
        assert conn_path.exists()
        assert connector_path.exists()
        assert (
            connector_path.read_text()
            == "type: sql\ndatabase_url: trino://user@host:8443/catalog\n"
        )
