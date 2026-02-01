"""Tests for the Connector protocol and SQLConnector implementation."""

from unittest.mock import MagicMock, patch

import pytest

from db_mcp.connectors import (
    Connector,
    ConnectorConfig,
    FileConnector,
    FileConnectorConfig,
    SQLConnector,
    SQLConnectorConfig,
)


class TestConnectorProtocol:
    """Test that the Connector protocol defines the expected interface."""

    def test_connector_is_protocol(self):
        """Connector should be a typing.Protocol."""

        # Protocol should be runtime-checkable
        assert hasattr(Connector, "__protocol_attrs__") or hasattr(
            Connector, "__abstractmethods__"
        )

    def test_sql_connector_satisfies_protocol(self):
        """SQLConnector should satisfy the Connector protocol."""
        # Just verify that SQLConnector has all the methods defined by the protocol
        required_methods = [
            "test_connection",
            "get_dialect",
            "get_catalogs",
            "get_schemas",
            "get_tables",
            "get_columns",
            "get_table_sample",
            "execute_sql",
        ]
        for method in required_methods:
            assert hasattr(SQLConnector, method), f"SQLConnector missing method: {method}"


class TestConnectorConfig:
    """Test connector configuration models."""

    def test_sql_config_from_dict(self):
        """SQLConnectorConfig can be created from a dict."""
        config = SQLConnectorConfig(database_url="postgresql://user:pass@host:5432/db")
        assert config.type == "sql"
        assert config.database_url == "postgresql://user:pass@host:5432/db"

    def test_sql_config_type_is_sql(self):
        """SQLConnectorConfig always has type='sql'."""
        config = SQLConnectorConfig(database_url="trino://host/catalog")
        assert config.type == "sql"

    def test_connector_config_from_yaml(self, tmp_path):
        """ConnectorConfig.from_yaml loads the right config type."""
        yaml_file = tmp_path / "connector.yaml"
        yaml_file.write_text("type: sql\n")

        config = ConnectorConfig.from_yaml(yaml_file)
        assert config.type == "sql"

    def test_connector_config_from_yaml_unknown_type(self, tmp_path):
        """ConnectorConfig.from_yaml raises for unknown type."""
        yaml_file = tmp_path / "connector.yaml"
        yaml_file.write_text("type: unknown_source\n")

        with pytest.raises(ValueError, match="Unknown connector type"):
            ConnectorConfig.from_yaml(yaml_file)

    def test_connector_config_defaults_to_sql(self, tmp_path):
        """ConnectorConfig.from_yaml defaults to sql when type is missing."""
        yaml_file = tmp_path / "connector.yaml"
        yaml_file.write_text("{}\n")

        config = ConnectorConfig.from_yaml(yaml_file)
        assert config.type == "sql"

    def test_connector_config_missing_file_returns_sql(self, tmp_path):
        """ConnectorConfig.from_yaml returns sql config when file doesn't exist."""
        yaml_file = tmp_path / "connector.yaml"
        config = ConnectorConfig.from_yaml(yaml_file)
        assert config.type == "sql"


class TestSQLConnector:
    """Test SQLConnector wrapping existing db/ functions."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        engine.url.host = "localhost"
        engine.url.database = "testdb"
        return engine

    @pytest.fixture
    def connector(self):
        """Create a SQLConnector with a test URL."""
        config = SQLConnectorConfig(database_url="postgresql://user:pass@localhost:5432/testdb")
        return SQLConnector(config)

    def test_get_dialect(self, connector):
        """SQLConnector.get_dialect returns dialect from URL."""
        assert connector.get_dialect() == "postgresql"

    def test_get_dialect_trino(self):
        """SQLConnector.get_dialect returns 'trino' for trino URLs."""
        config = SQLConnectorConfig(database_url="trino://user:pass@host:8080/catalog")
        conn = SQLConnector(config)
        assert conn.get_dialect() == "trino"

    def test_test_connection_delegates(self, connector, mock_engine):
        """SQLConnector.test_connection delegates to db.connection.test_connection."""
        with patch("db_mcp.connectors.sql.db_test_connection") as mock_test:
            mock_test.return_value = {
                "connected": True,
                "dialect": "postgresql",
                "url_host": "localhost",
                "url_database": "testdb",
                "error": None,
            }
            result = connector.test_connection()
            assert result["connected"] is True
            mock_test.assert_called_once_with(connector.config.database_url)

    def test_get_catalogs_delegates(self, connector):
        """SQLConnector.get_catalogs delegates to db.introspection.get_catalogs."""
        with patch("db_mcp.connectors.sql.db_get_catalogs") as mock:
            mock.return_value = ["dwh", "staging"]
            result = connector.get_catalogs()
            assert result == ["dwh", "staging"]
            mock.assert_called_once_with(connector.config.database_url)

    def test_get_schemas_delegates(self, connector):
        """SQLConnector.get_schemas delegates to db.introspection.get_schemas."""
        with patch("db_mcp.connectors.sql.db_get_schemas") as mock:
            mock.return_value = ["public", "analytics"]
            result = connector.get_schemas(catalog="dwh")
            assert result == ["public", "analytics"]
            mock.assert_called_once_with(connector.config.database_url, catalog="dwh")

    def test_get_tables_delegates(self, connector):
        """SQLConnector.get_tables delegates to db.introspection.get_tables."""
        with patch("db_mcp.connectors.sql.db_get_tables") as mock:
            mock.return_value = [
                {"name": "users", "schema": "public", "catalog": None, "full_name": "public.users"}
            ]
            result = connector.get_tables(schema="public")
            assert len(result) == 1
            assert result[0]["name"] == "users"
            mock.assert_called_once_with(
                schema="public", catalog=None, database_url=connector.config.database_url
            )

    def test_get_columns_delegates(self, connector):
        """SQLConnector.get_columns delegates to db.introspection.get_columns."""
        with patch("db_mcp.connectors.sql.db_get_columns") as mock:
            mock.return_value = [
                {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True}
            ]
            result = connector.get_columns("users", schema="public")
            assert len(result) == 1
            assert result[0]["name"] == "id"
            mock.assert_called_once_with(
                "users", schema="public", catalog=None, database_url=connector.config.database_url
            )

    def test_get_table_sample_delegates(self, connector):
        """SQLConnector.get_table_sample delegates to db.introspection.get_table_sample."""
        with patch("db_mcp.connectors.sql.db_get_table_sample") as mock:
            mock.return_value = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
            result = connector.get_table_sample("users", schema="public", limit=2)
            assert len(result) == 2
            mock.assert_called_once_with(
                "users",
                schema="public",
                catalog=None,
                limit=2,
                database_url=connector.config.database_url,
            )

    def test_execute_sql_delegates(self, connector, mock_engine):
        """SQLConnector.execute_sql executes SQL via SQLAlchemy engine."""
        with patch("db_mcp.connectors.sql.get_engine", return_value=mock_engine):
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id", "name"]
            mock_result.__iter__ = MagicMock(return_value=iter([(1, "Alice"), (2, "Bob")]))
            mock_conn.execute.return_value = mock_result
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

            rows = connector.execute_sql("SELECT * FROM users")
            assert len(rows) == 2
            assert rows[0] == {"id": 1, "name": "Alice"}


class TestGetConnector:
    """Test the get_connector factory function."""

    def test_get_connector_returns_sql_by_default(self):
        """get_connector returns SQLConnector when no connector.yaml exists."""
        from db_mcp.connectors import get_connector

        with patch("db_mcp.connectors.get_settings") as mock_settings:
            mock_settings.return_value.database_url = "postgresql://host/db"
            mock_settings.return_value.get_effective_connection_path.return_value = "/tmp/fake"

            connector = get_connector()
            assert isinstance(connector, SQLConnector)

    def test_get_connector_reads_connector_yaml(self, tmp_path):
        """get_connector reads connector.yaml from connection path."""
        from db_mcp.connectors import get_connector

        yaml_file = tmp_path / "connector.yaml"
        yaml_file.write_text("type: sql\n")

        with patch("db_mcp.connectors.get_settings") as mock_settings:
            mock_settings.return_value.database_url = "postgresql://host/db"
            mock_settings.return_value.get_effective_connection_path.return_value = str(tmp_path)

            connector = get_connector()
            assert isinstance(connector, SQLConnector)


class TestFileConnectorFactory:
    """Test factory/config integration for file connector type."""

    def test_config_from_yaml_file_type(self, tmp_path):
        """ConnectorConfig.from_yaml returns FileConnectorConfig for type: file."""
        yaml_file = tmp_path / "connector.yaml"
        yaml_file.write_text("type: file\nsources:\n  - name: sales\n    path: /data/sales.csv\n")
        config = ConnectorConfig.from_yaml(yaml_file)
        assert isinstance(config, FileConnectorConfig)
        assert config.type == "file"
        assert len(config.sources) == 1
        assert config.sources[0].name == "sales"
        assert config.sources[0].path == "/data/sales.csv"

    def test_config_from_yaml_file_multiple_sources(self, tmp_path):
        """ConnectorConfig.from_yaml parses multiple file sources."""
        yaml_file = tmp_path / "connector.yaml"
        yaml_file.write_text(
            "type: file\n"
            "sources:\n"
            "  - name: sales\n"
            "    path: /data/sales.csv\n"
            "  - name: events\n"
            "    path: /data/events/*.parquet\n"
        )
        config = ConnectorConfig.from_yaml(yaml_file)
        assert isinstance(config, FileConnectorConfig)
        assert len(config.sources) == 2

    def test_get_connector_file_type(self, tmp_path):
        """get_connector returns FileConnector for type: file."""
        from db_mcp.connectors import get_connector

        yaml_file = tmp_path / "connector.yaml"
        yaml_file.write_text("type: file\nsources:\n  - name: test\n    path: /data/test.csv\n")

        with patch("db_mcp.connectors.get_settings") as mock_settings:
            mock_settings.return_value.get_effective_connection_path.return_value = str(tmp_path)
            connector = get_connector()
            assert isinstance(connector, FileConnector)
