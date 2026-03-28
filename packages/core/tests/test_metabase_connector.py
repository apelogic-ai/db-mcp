"""Tests for the supported Metabase plugin runtime path."""

from unittest.mock import MagicMock, patch

import pytest
import yaml

from db_mcp.connector_plugins.builtin.metabase import MetabasePluginConnector
from db_mcp.connector_templates import get_connector_template, materialize_connector_template
from db_mcp.connectors import Connector, get_connector


@pytest.fixture
def env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("X_API_KEY=mb-api-key-123\n")
    return env


@pytest.fixture
def metabase_connector(tmp_path, env_file):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    connector_data = materialize_connector_template(
        "metabase",
        base_url="https://metabase.example.com",
    )
    assert connector_data is not None

    from db_mcp.connectors.api import build_api_connector_config

    return MetabasePluginConnector(
        build_api_connector_config(connector_data),
        data_dir=str(data_dir),
        env_path=str(env_file),
    )


class TestMetabasePluginProtocol:
    def test_satisfies_connector_protocol(self, metabase_connector):
        assert isinstance(metabase_connector, Connector)


class TestMetabasePluginConnection:
    def test_test_connection_success(self, metabase_connector):
        user_resp = MagicMock()
        user_resp.status_code = 200
        user_resp.json.return_value = {"id": 1, "email": "demo@example.com"}

        with patch("db_mcp.connectors.api.requests.request", return_value=user_resp):
            result = metabase_connector.test_connection()

        assert result["connected"] is True


class TestMetabasePluginSchema:
    def _database_list(self):
        return [
            {"id": 12, "name": "analytics"},
            {"id": 99, "name": "sample", "is_sample": True},
        ]

    def _schema_response(self):
        return [
            {
                "schema": "public",
                "name": "users",
                "fields": [
                    {"name": "id", "base_type": "type/Integer"},
                    {"name": "email", "base_type": "type/Text"},
                ],
            }
        ]

    def test_get_schemas(self, metabase_connector):
        db_resp = MagicMock()
        db_resp.status_code = 200
        db_resp.json.return_value = self._database_list()

        schema_resp = MagicMock()
        schema_resp.status_code = 200
        schema_resp.json.return_value = self._schema_response()

        def get_side_effect(url, *args, **kwargs):
            if url.endswith("/api/database"):
                return db_resp
            if url.endswith("/api/database/12/schema"):
                return schema_resp
            raise AssertionError(f"Unexpected GET url: {url}")

        with patch("db_mcp.connectors.api.requests.get", side_effect=get_side_effect):
            assert metabase_connector.get_catalogs() == ["analytics"]
            assert metabase_connector.get_schemas(catalog="analytics") == ["public"]

    def test_get_tables_and_columns(self, metabase_connector):
        db_resp = MagicMock()
        db_resp.status_code = 200
        db_resp.json.return_value = self._database_list()

        schema_resp = MagicMock()
        schema_resp.status_code = 200
        schema_resp.json.return_value = self._schema_response()

        def get_side_effect(url, *args, **kwargs):
            if url.endswith("/api/database"):
                return db_resp
            if url.endswith("/api/database/12/schema"):
                return schema_resp
            raise AssertionError(f"Unexpected GET url: {url}")

        with patch("db_mcp.connectors.api.requests.get", side_effect=get_side_effect):
            tables = metabase_connector.get_tables(schema="public", catalog="analytics")
            columns = metabase_connector.get_columns(
                "users",
                schema="public",
                catalog="analytics",
            )

        assert tables == [
            {
                "name": "users",
                "schema": "public",
                "catalog": "analytics",
                "type": "table",
                "full_name": "analytics.public.users",
            }
        ]
        assert {column["name"] for column in columns} == {"id", "email"}


def test_metabase_template_loads():
    template = get_connector_template("metabase")
    assert template is not None
    assert template.connector["type"] == "api"


def test_get_connector_uses_metabase_plugin_runtime(tmp_path):
    connector_yaml = materialize_connector_template(
        "metabase",
        base_url="https://metabase.example.com",
    )
    assert connector_yaml is not None

    (tmp_path / "connector.yaml").write_text(yaml.safe_dump(connector_yaml, sort_keys=False))
    (tmp_path / ".env").write_text("X_API_KEY=mb-api-key-123\n")

    with patch("db_mcp.connectors.get_settings") as mock_settings:
        mock_settings.return_value.database_url = "postgresql://host/db"
        mock_settings.return_value.get_effective_connection_path.return_value = str(tmp_path)

        connector = get_connector()

    assert isinstance(connector, MetabasePluginConnector)
