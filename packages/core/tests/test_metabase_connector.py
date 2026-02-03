"""TDD tests for MetabaseConnector — written before implementation."""

from unittest.mock import MagicMock, patch

import pytest

from db_mcp.connectors import Connector


@pytest.fixture
def env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("MB_USERNAME=demo@example.com\nMB_PASSWORD=supersecret\n")
    return env


@pytest.fixture
def metabase_config():
    from db_mcp.connectors.metabase import MetabaseAuthConfig, MetabaseConnectorConfig

    return MetabaseConnectorConfig(
        base_url="https://metabase.example.com",
        database_id=12,
        database_name="analytics",
        auth=MetabaseAuthConfig(username_env="MB_USERNAME", password_env="MB_PASSWORD"),
    )


@pytest.fixture
def metabase_connector(metabase_config, env_file, tmp_path):
    from db_mcp.connectors.metabase import MetabaseConnector

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return MetabaseConnector(metabase_config, env_path=str(env_file))


class TestMetabaseConfig:
    def test_type_is_metabase(self, metabase_config):
        assert metabase_config.type == "metabase"

    def test_has_base_url(self, metabase_config):
        assert metabase_config.base_url == "https://metabase.example.com"

    def test_has_database_id(self, metabase_config):
        assert metabase_config.database_id == 12


class TestMetabaseProtocol:
    def test_satisfies_connector_protocol(self, metabase_connector):
        assert isinstance(metabase_connector, Connector)


class TestMetabaseAuth:
    def test_missing_env_raises(self, metabase_config, tmp_path):
        from db_mcp.connectors.metabase import MetabaseConnector

        env = tmp_path / ".env"
        env.write_text("MB_USERNAME=demo@example.com\n")

        conn = MetabaseConnector(metabase_config, env_path=str(env))
        with pytest.raises(ValueError, match="not found"):
            conn._resolve_credentials()


class TestMetabaseConnection:
    def test_test_connection_success(self, metabase_connector):
        session_resp = MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "sess_123"}

        user_resp = MagicMock()
        user_resp.status_code = 200
        user_resp.json.return_value = {"id": 1, "email": "demo@example.com"}

        with (
            patch("db_mcp.connectors.metabase.requests.post", return_value=session_resp),
            patch("db_mcp.connectors.metabase.requests.get", return_value=user_resp),
        ):
            result = metabase_connector.test_connection()

        assert result["connected"] is True
        assert result["dialect"] == "metabase"

    def test_test_connection_failure(self, metabase_connector):
        session_resp = MagicMock()
        session_resp.status_code = 401
        session_resp.raise_for_status.side_effect = Exception("401 Unauthorized")

        with patch("db_mcp.connectors.metabase.requests.post", return_value=session_resp):
            result = metabase_connector.test_connection()

        assert result["connected"] is False
        assert result["error"] is not None


class TestMetabaseSchema:
    def _schema_response(self):
        return [
            {
                "schema": "public",
                "name": "users",
                "fields": [
                    {"name": "id", "base_type": "type/Integer"},
                    {"name": "email", "base_type": "type/Text"},
                ],
            },
            {
                "schema": "analytics",
                "name": "events",
                "fields": [
                    {"name": "id", "base_type": "type/Integer"},
                    {"name": "event_name", "base_type": "type/Text"},
                ],
            },
        ]

    def test_get_schemas(self, metabase_connector):
        session_resp = MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "sess_123"}

        schema_resp = MagicMock()
        schema_resp.status_code = 200
        schema_resp.json.return_value = self._schema_response()

        with (
            patch("db_mcp.connectors.metabase.requests.post", return_value=session_resp),
            patch("db_mcp.connectors.metabase.requests.get", return_value=schema_resp),
        ):
            schemas = metabase_connector.get_schemas()

        assert schemas == ["analytics", "public"]

    def test_get_tables(self, metabase_connector):
        session_resp = MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "sess_123"}

        schema_resp = MagicMock()
        schema_resp.status_code = 200
        schema_resp.json.return_value = self._schema_response()

        with (
            patch("db_mcp.connectors.metabase.requests.post", return_value=session_resp),
            patch("db_mcp.connectors.metabase.requests.get", return_value=schema_resp),
        ):
            tables = metabase_connector.get_tables(schema="public")

        assert len(tables) == 1
        assert tables[0]["name"] == "users"
        assert tables[0]["schema"] == "public"
        assert tables[0]["catalog"] == "analytics"
        assert tables[0]["full_name"] == "public.users"

    def test_get_columns(self, metabase_connector):
        session_resp = MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "sess_123"}

        schema_resp = MagicMock()
        schema_resp.status_code = 200
        schema_resp.json.return_value = self._schema_response()

        with (
            patch("db_mcp.connectors.metabase.requests.post", return_value=session_resp),
            patch("db_mcp.connectors.metabase.requests.get", return_value=schema_resp),
        ):
            cols = metabase_connector.get_columns("users", schema="public")

        names = {c["name"] for c in cols}
        assert names == {"id", "email"}


class TestMetabaseQuery:
    def test_execute_sql(self, metabase_connector):
        session_resp = MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "sess_123"}

        dataset_resp = MagicMock()
        dataset_resp.status_code = 200
        dataset_resp.json.return_value = {
            "data": {"cols": [{"name": "id"}, {"name": "name"}], "rows": [[1, "A"]]}
        }

        with patch(
            "db_mcp.connectors.metabase.requests.post",
            side_effect=[session_resp, dataset_resp],
        ):
            rows = metabase_connector.execute_sql("SELECT 1")

        assert rows == [{"id": 1, "name": "A"}]
