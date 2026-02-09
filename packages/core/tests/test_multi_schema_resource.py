"""Tests for multi-schema MCP resources (connections list + schema)."""

from pathlib import Path

import pytest

from db_mcp.registry import ConnectionRegistry


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset the singleton registry before each test."""
    ConnectionRegistry.reset()
    yield
    ConnectionRegistry.reset()


@pytest.fixture
def connections_dir(tmp_path: Path) -> Path:
    """Create a temporary connections directory with two connections."""
    for name, dialect, desc in [
        ("prod", "postgresql", "Production database"),
        ("staging", "clickhouse", "Staging analytics"),
    ]:
        conn_dir = tmp_path / name
        conn_dir.mkdir()
        (conn_dir / "connector.yaml").write_text(
            f"type: sql\ndialect: {dialect}\ndescription: {desc}\n"
        )
    return tmp_path


class TestConnectionsResource:
    """Tests for db-mcp://connections resource."""

    def test_list_connections_returns_valid_list(self, connections_dir: Path):
        settings = _make_settings(connections_dir)
        registry = ConnectionRegistry(settings)
        connections = registry.list_connections()

        assert len(connections) == 2
        names = {c["name"] for c in connections}
        assert names == {"prod", "staging"}
        for c in connections:
            assert "type" in c
            assert "dialect" in c
            assert "description" in c

    def test_list_connections_empty_dir(self, tmp_path: Path):
        settings = _make_settings(tmp_path)
        registry = ConnectionRegistry(settings)
        assert registry.list_connections() == []

    def test_list_connections_skips_non_connection_dirs(self, tmp_path: Path):
        # Directory without connector.yaml should be skipped
        (tmp_path / "random_dir").mkdir()
        settings = _make_settings(tmp_path)
        registry = ConnectionRegistry(settings)
        assert registry.list_connections() == []


class TestSchemaResource:
    """Tests for db-mcp://schema/{connection} resource."""

    def test_reads_schema_md(self, connections_dir: Path):
        schema_content = "# Prod Schema\n\n- users\n- orders\n"
        (connections_dir / "prod" / "schema.md").write_text(schema_content)

        settings = _make_settings(connections_dir)
        registry = ConnectionRegistry(settings)
        path = registry.get_connection_path("prod")
        schema_path = path / "schema.md"

        assert schema_path.exists()
        assert schema_path.read_text() == schema_content

    def test_falls_back_to_descriptions_yaml(self, connections_dir: Path):
        desc_content = "tables:\n  - name: users\n"
        schema_dir = connections_dir / "prod" / "schema"
        schema_dir.mkdir()
        (schema_dir / "descriptions.yaml").write_text(desc_content)

        settings = _make_settings(connections_dir)
        registry = ConnectionRegistry(settings)
        path = registry.get_connection_path("prod")

        schema_md = path / "schema.md"
        assert not schema_md.exists()
        assert (path / "schema" / "descriptions.yaml").read_text() == desc_content

    def test_missing_schema_returns_gracefully(self, connections_dir: Path):
        settings = _make_settings(connections_dir)
        registry = ConnectionRegistry(settings)
        path = registry.get_connection_path("prod")

        # Neither schema.md nor descriptions.yaml exists
        assert not (path / "schema.md").exists()
        assert not (path / "schema" / "descriptions.yaml").exists()

    def test_nonexistent_connection_path(self, connections_dir: Path):
        settings = _make_settings(connections_dir)
        registry = ConnectionRegistry(settings)
        path = registry.get_connection_path("nonexistent")

        # Should return a path (even if it doesn't exist on disk)
        assert path == connections_dir / "nonexistent"


def _make_settings(connections_dir: Path):
    """Create a minimal settings-like object for testing."""

    class FakeSettings:
        def __init__(self, cdir: Path):
            self.connections_dir = str(cdir)
            self.connection_name = "default"

        def get_effective_connection_path(self) -> Path:
            return Path(self.connections_dir) / self.connection_name

    return FakeSettings(connections_dir)
