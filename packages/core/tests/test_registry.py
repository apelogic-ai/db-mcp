"""Tests for ConnectionRegistry."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from db_mcp.config import Settings
from db_mcp.registry import ConnectionInfo, ConnectionRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset singleton between tests."""
    ConnectionRegistry.reset()
    yield
    ConnectionRegistry.reset()


@pytest.fixture
def connections_dir(tmp_path: Path) -> Path:
    """Create a mock connections directory with sample connections."""
    # Connection 1: SQL
    sql_dir = tmp_path / "my-postgres"
    sql_dir.mkdir()
    (sql_dir / "connector.yaml").write_text(
        yaml.dump({"type": "sql", "dialect": "postgresql", "description": "Main Postgres DB"})
    )
    (sql_dir / ".env").write_text("DATABASE_URL=postgresql://localhost/mydb\n")

    # Connection 2: API
    api_dir = tmp_path / "stripe-api"
    api_dir.mkdir()
    (api_dir / "connector.yaml").write_text(
        yaml.dump({"type": "api", "description": "Stripe API"})
    )

    # Connection 3: no connector.yaml (should be skipped)
    empty_dir = tmp_path / "broken"
    empty_dir.mkdir()

    # A regular file (should be skipped)
    (tmp_path / "not-a-dir.txt").write_text("ignore me")

    return tmp_path


@pytest.fixture
def settings(connections_dir: Path) -> Settings:
    return Settings(
        connections_dir=str(connections_dir),
        connection_name="my-postgres",
    )


@pytest.fixture
def registry(settings: Settings) -> ConnectionRegistry:
    return ConnectionRegistry(settings)


class TestDiscovery:
    def test_discover_finds_valid_connections(self, registry: ConnectionRegistry):
        result = registry.discover()
        assert set(result.keys()) == {"my-postgres", "stripe-api"}

    def test_discover_skips_dirs_without_yaml(self, registry: ConnectionRegistry):
        result = registry.discover()
        assert "broken" not in result

    def test_discover_reads_metadata(self, registry: ConnectionRegistry):
        result = registry.discover()
        pg = result["my-postgres"]
        assert pg.type == "sql"
        assert pg.dialect == "postgresql"
        assert pg.description == "Main Postgres DB"

    def test_discover_marks_default(self, registry: ConnectionRegistry):
        result = registry.discover()
        assert result["my-postgres"].is_default is True
        assert result["stripe-api"].is_default is False

    def test_discover_empty_dir(self, tmp_path: Path):
        s = Settings(connections_dir=str(tmp_path / "nonexistent"), connection_name="x")
        r = ConnectionRegistry(s)
        assert r.discover() == {}

    def test_discover_malformed_yaml(self, connections_dir: Path):
        bad = connections_dir / "bad-yaml"
        bad.mkdir()
        (bad / "connector.yaml").write_text(": : invalid yaml [")
        s = Settings(connections_dir=str(connections_dir), connection_name="default")
        r = ConnectionRegistry(s)
        result = r.discover()
        # Should still discover it with defaults
        assert "bad-yaml" in result
        assert result["bad-yaml"].type == "sql"


class TestListConnections:
    def test_list_returns_dicts(self, registry: ConnectionRegistry):
        items = registry.list_connections()
        assert len(items) == 2
        names = {item["name"] for item in items}
        assert names == {"my-postgres", "stripe-api"}

    def test_list_auto_discovers(self, registry: ConnectionRegistry):
        # Don't call discover() first
        items = registry.list_connections()
        assert len(items) == 2

    def test_list_dict_fields(self, registry: ConnectionRegistry):
        items = registry.list_connections()
        pg = next(i for i in items if i["name"] == "my-postgres")
        assert pg == {
            "name": "my-postgres",
            "type": "sql",
            "dialect": "postgresql",
            "description": "Main Postgres DB",
            "is_default": True,
        }


class TestGetConnectionPath:
    def test_default_path(self, registry: ConnectionRegistry, settings: Settings):
        path = registry.get_connection_path(None)
        assert path == settings.get_effective_connection_path()

    def test_named_path(self, registry: ConnectionRegistry, connections_dir: Path):
        registry.discover()
        path = registry.get_connection_path("stripe-api")
        assert path == connections_dir / "stripe-api"

    def test_unknown_name_fallback(self, registry: ConnectionRegistry, connections_dir: Path):
        path = registry.get_connection_path("unknown")
        assert path == connections_dir / "unknown"


class TestGetConnector:
    @patch("db_mcp.registry.get_connector")
    def test_lazy_loads_connector(self, mock_get: MagicMock, registry: ConnectionRegistry):
        mock_connector = MagicMock()
        mock_get.return_value = mock_connector

        result = registry.get_connector("my-postgres")
        assert result is mock_connector
        mock_get.assert_called_once()

    @patch("db_mcp.registry.get_connector")
    def test_caches_connector(self, mock_get: MagicMock, registry: ConnectionRegistry):
        mock_get.return_value = MagicMock()

        c1 = registry.get_connector("my-postgres")
        c2 = registry.get_connector("my-postgres")
        assert c1 is c2
        assert mock_get.call_count == 1

    @patch("db_mcp.registry.get_connector")
    def test_default_connector(self, mock_get: MagicMock, registry: ConnectionRegistry):
        mock_get.return_value = MagicMock()
        registry.get_connector(None)
        mock_get.assert_called_once()


class TestSingleton:
    def test_get_instance_returns_same(self, settings: Settings):
        r1 = ConnectionRegistry.get_instance(settings)
        r2 = ConnectionRegistry.get_instance(settings)
        assert r1 is r2

    def test_reset_clears_instance(self, settings: Settings):
        r1 = ConnectionRegistry.get_instance(settings)
        ConnectionRegistry.reset()
        r2 = ConnectionRegistry.get_instance(settings)
        assert r1 is not r2


class TestConnectionInfo:
    def test_to_dict(self):
        info = ConnectionInfo(
            name="test", path=Path("/tmp/test"), type="api", description="Test"
        )
        d = info.to_dict()
        assert d == {
            "name": "test",
            "type": "api",
            "dialect": "",
            "description": "Test",
            "is_default": False,
        }
