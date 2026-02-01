"""TDD tests for APIConnector — written before implementation."""

import json
from unittest.mock import MagicMock, patch

import pytest

from db_mcp.connectors import Connector

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path):
    """Empty data directory for synced JSONL files."""
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def env_file(tmp_path):
    """Create a .env file with a test API key."""
    env = tmp_path / ".env"
    env.write_text("TEST_API_KEY=sk-test-12345\n")
    return env


@pytest.fixture
def api_config():
    """Minimal API connector config."""
    from db_mcp.connectors.api import APIAuthConfig, APIConnectorConfig, APIEndpointConfig

    return APIConnectorConfig(
        base_url="https://api.example.com/v1",
        auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
        endpoints=[
            APIEndpointConfig(name="users", path="/users"),
            APIEndpointConfig(name="orders", path="/orders"),
        ],
    )


@pytest.fixture
def api_connector(api_config, data_dir, env_file):
    """APIConnector instance with test config."""
    from db_mcp.connectors.api import APIConnector

    return APIConnector(api_config, data_dir=str(data_dir), env_path=str(env_file))


@pytest.fixture
def synced_data_dir(data_dir):
    """Data directory pre-populated with JSONL files (simulates post-sync)."""
    users = data_dir / "users.jsonl"
    users.write_text(
        "\n".join(
            [
                json.dumps({"id": 1, "name": "Alice", "email": "alice@example.com"}),
                json.dumps({"id": 2, "name": "Bob", "email": "bob@example.com"}),
                json.dumps({"id": 3, "name": "Charlie", "email": "charlie@example.com"}),
            ]
        )
        + "\n"
    )
    orders = data_dir / "orders.jsonl"
    orders.write_text(
        "\n".join(
            [
                json.dumps({"id": 101, "user_id": 1, "amount": 9.99, "status": "paid"}),
                json.dumps({"id": 102, "user_id": 2, "amount": 24.50, "status": "pending"}),
            ]
        )
        + "\n"
    )
    return data_dir


@pytest.fixture
def synced_connector(api_config, synced_data_dir, env_file):
    """APIConnector with pre-synced data (ready to query)."""
    from db_mcp.connectors.api import APIConnector

    return APIConnector(api_config, data_dir=str(synced_data_dir), env_path=str(env_file))


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestAPIConnectorConfig:
    def test_type_is_api(self, api_config):
        assert api_config.type == "api"

    def test_has_base_url(self, api_config):
        assert api_config.base_url == "https://api.example.com/v1"

    def test_has_endpoints(self, api_config):
        assert len(api_config.endpoints) == 2
        assert api_config.endpoints[0].name == "users"
        assert api_config.endpoints[0].path == "/users"

    def test_has_auth(self, api_config):
        assert api_config.auth.type == "bearer"
        assert api_config.auth.token_env == "TEST_API_KEY"

    def test_default_pagination(self):
        from db_mcp.connectors.api import APIConnectorConfig

        config = APIConnectorConfig(base_url="https://api.example.com")
        assert config.pagination.type == "none"
        assert config.pagination.page_size == 100

    def test_default_rate_limit(self):
        from db_mcp.connectors.api import APIConnectorConfig

        config = APIConnectorConfig(base_url="https://api.example.com")
        assert config.rate_limit_rps == 10.0


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestAPIConnectorProtocol:
    def test_satisfies_connector_protocol(self, synced_connector):
        assert isinstance(synced_connector, Connector)

    def test_has_all_protocol_methods(self, synced_connector):
        for method in [
            "test_connection",
            "get_dialect",
            "get_catalogs",
            "get_schemas",
            "get_tables",
            "get_columns",
            "get_table_sample",
            "execute_sql",
        ]:
            assert hasattr(synced_connector, method), f"Missing: {method}"


# ---------------------------------------------------------------------------
# Auth resolution
# ---------------------------------------------------------------------------


class TestAPIConnectorAuth:
    def test_resolve_bearer_auth(self, api_connector):
        headers = api_connector._resolve_auth_headers()
        assert headers["Authorization"] == "Bearer sk-test-12345"

    def test_resolve_header_auth(self, data_dir, env_file):
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="header", token_env="TEST_API_KEY", header_name="X-Api-Key"),
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))
        headers = conn._resolve_auth_headers()
        assert headers["X-Api-Key"] == "sk-test-12345"

    def test_missing_env_var_raises(self, data_dir, env_file):
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="NONEXISTENT_KEY"),
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))
        with pytest.raises(ValueError, match="not found"):
            conn._resolve_auth_headers()


# ---------------------------------------------------------------------------
# Test connection
# ---------------------------------------------------------------------------


class TestAPIConnectorTestConnection:
    def test_connection_success(self, api_connector):
        """test_connection with a mocked HTTP response should succeed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_response):
            result = api_connector.test_connection()
        assert result["connected"] is True
        assert result["dialect"] == "duckdb"

    def test_connection_failure(self, api_connector):
        """test_connection with HTTP error should report failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_response):
            result = api_connector.test_connection()
        assert result["connected"] is False
        assert result["error"] is not None


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class TestAPIConnectorSync:
    def test_sync_writes_jsonl_files(self, api_connector, data_dir):
        """Sync should write JSONL files to data directory."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ]
        }

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_response):
            result = api_connector.sync()

        assert "users" in result["synced"]
        users_file = data_dir / "users.jsonl"
        assert users_file.exists()
        lines = users_file.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["name"] == "Alice"

    def test_sync_single_endpoint(self, api_connector, data_dir):
        """Sync with endpoint_name should only sync that endpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": 1}]}

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_response):
            result = api_connector.sync(endpoint_name="users")

        assert "users" in result["synced"]
        assert "orders" not in result["synced"]

    def test_sync_returns_row_counts(self, api_connector, data_dir):
        """Sync should report row counts per endpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": 1}, {"id": 2}, {"id": 3}]}

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_response):
            result = api_connector.sync(endpoint_name="users")

        assert result["rows_fetched"]["users"] == 3

    def test_sync_error_reported(self, api_connector):
        """Sync should report errors per endpoint without crashing."""
        with patch(
            "db_mcp.connectors.api.requests.get",
            side_effect=Exception("Connection refused"),
        ):
            result = api_connector.sync(endpoint_name="users")

        assert len(result["errors"]) > 0
        assert "users" in result["errors"][0]


# ---------------------------------------------------------------------------
# Querying (inherits FileConnector via DuckDB)
# ---------------------------------------------------------------------------


class TestAPIConnectorQuery:
    def test_get_dialect(self, synced_connector):
        assert synced_connector.get_dialect() == "duckdb"

    def test_get_catalogs(self, synced_connector):
        assert synced_connector.get_catalogs() == [None]

    def test_get_schemas(self, synced_connector):
        assert synced_connector.get_schemas() == [None]

    def test_get_tables(self, synced_connector):
        tables = synced_connector.get_tables()
        names = {t["name"] for t in tables}
        assert "users" in names
        assert "orders" in names

    def test_get_columns(self, synced_connector):
        cols = synced_connector.get_columns("users")
        col_names = {c["name"] for c in cols}
        assert "id" in col_names
        assert "name" in col_names
        assert "email" in col_names

    def test_execute_sql(self, synced_connector):
        rows = synced_connector.execute_sql("SELECT COUNT(*) AS cnt FROM users")
        assert rows[0]["cnt"] == 3

    def test_execute_sql_join(self, synced_connector):
        rows = synced_connector.execute_sql(
            "SELECT u.name, o.amount FROM users u "
            "JOIN orders o ON u.id = o.user_id ORDER BY o.amount"
        )
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"

    def test_get_table_sample(self, synced_connector):
        sample = synced_connector.get_table_sample("users", limit=2)
        assert len(sample) == 2
        assert "name" in sample[0]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestAPIConnectorPagination:
    def test_cursor_pagination(self, data_dir, env_file):
        """Cursor pagination should follow cursor until no more data."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
            APIPaginationConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com/v1",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
            pagination=APIPaginationConfig(
                type="cursor",
                cursor_param="starting_after",
                cursor_field="data[-1].id",
                page_size_param="limit",
                page_size=2,
                data_field="data",
            ),
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        # Page 1: has_more=True, Page 2: has_more=False
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "data": [{"id": "a"}, {"id": "b"}],
            "has_more": True,
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "data": [{"id": "c"}],
            "has_more": False,
        }

        with patch("db_mcp.connectors.api.requests.get", side_effect=[page1, page2]):
            result = conn.sync(endpoint_name="items")

        assert result["rows_fetched"]["items"] == 3
        items_file = data_dir / "items.jsonl"
        lines = items_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_offset_pagination(self, data_dir, env_file):
        """Offset pagination should increment offset until empty page."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
            APIPaginationConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com/v1",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
            pagination=APIPaginationConfig(
                type="offset",
                page_size=2,
                data_field="results",
            ),
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {"results": [{"id": 1}, {"id": 2}]}
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {"results": [{"id": 3}]}
        page3 = MagicMock()
        page3.status_code = 200
        page3.json.return_value = {"results": []}

        with patch("db_mcp.connectors.api.requests.get", side_effect=[page1, page2, page3]):
            result = conn.sync(endpoint_name="items")

        assert result["rows_fetched"]["items"] == 3
