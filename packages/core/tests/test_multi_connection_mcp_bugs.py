"""Tests for multi-connection MCP bugs.

Tests specifically for the bugs found in v0.5.21:
1. discover() skips connections without connector.yaml
2. SQLConnectorConfig crashes on 'description' field
3. Better error for invalid connection names (verification)
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from db_mcp.config import Settings
from db_mcp.connectors import _load_api_config, _load_file_config, _load_sql_config
from db_mcp.connectors.api import APIConnectorConfig
from db_mcp.connectors.file import FileConnectorConfig
from db_mcp.connectors.sql import SQLConnectorConfig
from db_mcp.registry import ConnectionRegistry
from db_mcp.tools.utils import resolve_connection


class TestDiscoverWithoutConnectorYaml:
    """Test Bug 1: discover() skips connections without connector.yaml"""

    def test_discover_finds_connection_with_only_state_yaml(self):
        """discover() should find connections that only have state.yaml (no connector.yaml)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            connections_dir = Path(tmpdir)

            # Create a connection with only state.yaml (no connector.yaml)
            conn_dir = connections_dir / "rna-research"
            conn_dir.mkdir()

            # Create state.yaml to indicate this is a real connection
            state_yaml = conn_dir / "state.yaml"
            state_yaml.write_text(yaml.dump({
                "phase": "schema",
                "created_at": "2024-01-01T00:00:00Z"
            }))

            # Create .env file with DATABASE_URL
            env_file = conn_dir / ".env"
            env_file.write_text("DATABASE_URL=postgresql://user:pass@localhost:5432/rna\n")

            # Create some knowledge vault files to make it look realistic
            schema_dir = conn_dir / "schema"
            schema_dir.mkdir()
            (schema_dir / "descriptions.yaml").write_text("tables: {}")

            settings = Settings(connections_dir=str(connections_dir))
            registry = ConnectionRegistry(settings)

            connections = registry.discover()

            # Should find the connection even without connector.yaml
            assert "rna-research" in connections

            conn_info = connections["rna-research"]
            assert conn_info.name == "rna-research"
            assert conn_info.type == "sql"  # default type
            assert conn_info.dialect == "postgresql"  # detected from DATABASE_URL
            assert conn_info.description == ""  # default description

    def test_discover_connection_without_state_yaml_skipped(self):
        """discover() should skip directories that don't have state.yaml (stray dirs)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            connections_dir = Path(tmpdir)

            # Create a directory that looks like a connection but has no state.yaml
            stray_dir = connections_dir / "random-folder"
            stray_dir.mkdir()
            # Just create some random file
            (stray_dir / "notes.txt").write_text("random notes")

            settings = Settings(connections_dir=str(connections_dir))
            registry = ConnectionRegistry(settings)

            connections = registry.discover()

            # Should not find the stray directory
            assert "random-folder" not in connections

    def test_discover_prefers_connector_yaml_over_env_detection(self):
        """If both connector.yaml and .env exist, connector.yaml takes precedence"""
        with tempfile.TemporaryDirectory() as tmpdir:
            connections_dir = Path(tmpdir)

            conn_dir = connections_dir / "test-conn"
            conn_dir.mkdir()

            # Create state.yaml
            (conn_dir / "state.yaml").write_text(yaml.dump({"phase": "complete"}))

            # Create .env with postgres URL
            (conn_dir / ".env").write_text("DATABASE_URL=postgresql://user@localhost/db\n")

            # Create connector.yaml with different dialect and description
            connector_yaml = conn_dir / "connector.yaml"
            connector_yaml.write_text(yaml.dump({
                "type": "sql",
                "database_url": "sqlite:///test.db",
                "dialect": "sqlite",
                "description": "Test connection with explicit config"
            }))

            settings = Settings(connections_dir=str(connections_dir))
            registry = ConnectionRegistry(settings)

            connections = registry.discover()

            assert "test-conn" in connections
            conn_info = connections["test-conn"]

            # Should use values from connector.yaml, not detected from .env
            assert conn_info.dialect == "sqlite"
            assert conn_info.description == "Test connection with explicit config"

    def test_discover_dialect_detection_from_database_url(self):
        """Test that dialect detection works for various database URLs"""
        test_cases = [
            ("postgresql://user@localhost/db", "postgresql"),
            ("mysql://user@localhost/db", "mysql"),
            ("sqlite:///path/to/db.sqlite", "sqlite"),
            ("clickhouse://localhost:8123/db", "clickhouse"),
            ("trino://localhost:8080/catalog", "trino"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            connections_dir = Path(tmpdir)

            for i, (db_url, expected_dialect) in enumerate(test_cases):
                conn_dir = connections_dir / f"conn-{i}"
                conn_dir.mkdir()

                (conn_dir / "state.yaml").write_text(yaml.dump({"phase": "schema"}))
                (conn_dir / ".env").write_text(f"DATABASE_URL={db_url}\n")

            settings = Settings(connections_dir=str(connections_dir))
            registry = ConnectionRegistry(settings)

            connections = registry.discover()

            for i, (db_url, expected_dialect) in enumerate(test_cases):
                conn_name = f"conn-{i}"
                assert conn_name in connections
                assert connections[conn_name].dialect == expected_dialect


class TestSQLConnectorConfigDescriptionField:
    """Test Bug 2: SQLConnectorConfig crashes on 'description' field"""

    def test_load_sql_config_with_description_field(self):
        """_load_sql_config should handle 'description' field without crashing"""
        config_data = {
            "type": "sql",
            "database_url": "sqlite:///test.db",
            "description": "Copy of Chinook for multi-connection testing",
            "capabilities": {"supports_validate_sql": False}
        }

        # This should not crash
        config = _load_sql_config(config_data)

        assert isinstance(config, SQLConnectorConfig)
        assert config.database_url == "sqlite:///test.db"
        assert config.description == "Copy of Chinook for multi-connection testing"
        assert config.capabilities == {"supports_validate_sql": False}

    def test_load_sql_config_with_unknown_fields_does_not_crash(self):
        """_load_sql_config should handle unknown fields gracefully"""
        config_data = {
            "type": "sql",
            "database_url": "postgresql://localhost/db",
            "description": "Test database",
            "unknown_field": "some value",
            "another_unknown": 42,
            "capabilities": {}
        }

        # Should not crash and should filter out unknown fields
        config = _load_sql_config(config_data)

        assert isinstance(config, SQLConnectorConfig)
        assert config.database_url == "postgresql://localhost/db"
        assert config.description == "Test database"
        assert config.capabilities == {}
        # Unknown fields should be filtered out (not accessible via config)

    def test_sql_connector_config_description_field_exists(self):
        """SQLConnectorConfig should have a description field"""
        config = SQLConnectorConfig(
            database_url="sqlite:///test.db",
            description="Test description",
            capabilities={}
        )

        assert config.description == "Test description"
        assert config.database_url == "sqlite:///test.db"

    def test_sql_connector_config_description_defaults_to_empty(self):
        """SQLConnectorConfig description should default to empty string"""
        config = SQLConnectorConfig(database_url="sqlite:///test.db")

        assert config.description == ""

    def test_load_file_config_with_description_field(self):
        """_load_file_config should handle description field if added"""
        config_data = {
            "type": "file",
            "directory": "/path/to/files",
            "description": "File connector description",
            "sources": [],
            "capabilities": {}
        }

        # Should work after we add description field to FileConnectorConfig
        config = _load_file_config(config_data)

        assert isinstance(config, FileConnectorConfig)
        assert config.directory == "/path/to/files"
        # Description should be handled (either in the config or filtered out safely)

    def test_load_api_config_handles_description_already(self):
        """APIConnectorConfig already has api_description field"""
        config_data = {
            "type": "api",
            "base_url": "https://api.example.com",
            "api_description": "Example API for testing",
            "endpoints": [],
            "auth": {},
            "pagination": {},
            "rate_limit_rps": 10.0,
            "capabilities": {}
        }

        config = _load_api_config(config_data)

        assert isinstance(config, APIConnectorConfig)
        assert config.base_url == "https://api.example.com"
        assert config.api_description == "Example API for testing"


class TestInvalidConnectionNameError:
    """Test Bug 3: Better error for invalid connection names"""

    def test_resolve_connection_invalid_name_shows_available(self):
        """resolve_connection with invalid name should show available connections"""
        with tempfile.TemporaryDirectory() as tmpdir:
            connections_dir = Path(tmpdir)

            # Create some valid connections
            for name in ["playground", "chinook-copy"]:
                conn_dir = connections_dir / name
                conn_dir.mkdir()
                (conn_dir / "state.yaml").write_text(yaml.dump({"phase": "complete"}))
                (conn_dir / "connector.yaml").write_text(yaml.dump({
                    "type": "sql",
                    "database_url": "sqlite:///test.db"
                }))

            try:
                # Reset singleton and create instance with test settings
                ConnectionRegistry.reset()
                settings = Settings(connections_dir=str(connections_dir))
                registry = ConnectionRegistry.get_instance(settings)
                registry.discover()

                with pytest.raises(ValueError) as exc_info:
                    resolve_connection("nonexistent")

                error_msg = str(exc_info.value)
                assert "Connection 'nonexistent' not found" in error_msg
                assert "Available connections:" in error_msg
                assert "playground" in error_msg
                assert "chinook-copy" in error_msg
            finally:
                # Clean up singleton for other tests
                ConnectionRegistry.reset()

    def test_resolve_connection_works_after_discover_fix(self):
        """resolve_connection should work with connections that have no connector.yaml"""
        with tempfile.TemporaryDirectory() as tmpdir:
            connections_dir = Path(tmpdir)

            # Create connection with only state.yaml (no connector.yaml)
            conn_dir = connections_dir / "rna-research"
            conn_dir.mkdir()
            (conn_dir / "state.yaml").write_text(yaml.dump({"phase": "schema"}))
            (conn_dir / ".env").write_text("DATABASE_URL=postgresql://localhost/rna\n")

            try:
                # Reset singleton and create instance with test settings
                ConnectionRegistry.reset()
                settings = Settings(connections_dir=str(connections_dir))
                registry = ConnectionRegistry.get_instance(settings)
                registry.discover()

                # After fix, this should work
                connector, conn_name, conn_path = resolve_connection("rna-research")

                assert conn_name == "rna-research"
                assert conn_path == conn_dir
                assert connector is not None
            finally:
                # Clean up singleton for other tests
                ConnectionRegistry.reset()
