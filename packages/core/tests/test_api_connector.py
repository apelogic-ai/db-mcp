"""TDD tests for APIConnector — written before implementation."""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib
import yaml

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


# ---------------------------------------------------------------------------
# Ad-hoc querying (query_endpoint)
# ---------------------------------------------------------------------------


class TestAPIConnectorAdHocQuery:
    """Tests for direct ad-hoc API querying via query_endpoint()."""

    def test_query_endpoint_returns_data(self, data_dir, env_file):
        """query_endpoint should return {data, rows_returned} shape with raw data."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="users", path="/users")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp):
            result = conn.query_endpoint("users")

        assert "data" in result
        assert "rows_returned" in result
        assert result["rows_returned"] == 2
        assert len(result["data"]) == 2
        assert result["data"][0]["name"] == "Alice"

    def test_query_endpoint_passes_user_params(self, data_dir, env_file):
        """User params should appear in the HTTP request."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="events", path="/events")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": 1}]

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp) as mock_get:
            conn.query_endpoint("events", params={"active": "true", "order": "startDate"})

        call_kwargs = mock_get.call_args
        passed_params = call_kwargs.kwargs.get("params", {})
        assert passed_params["active"] == "true"
        assert passed_params["order"] == "startDate"

    def test_query_endpoint_merges_auth_params(self, data_dir, env_file):
        """Auth params should be merged alongside user params."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="query_param", token_env="TEST_API_KEY", param_name="key"),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": 1}]

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp) as mock_get:
            conn.query_endpoint("items", params={"color": "red"})

        passed_params = mock_get.call_args.kwargs.get("params", {})
        assert passed_params["key"] == "sk-test-12345"
        assert passed_params["color"] == "red"

    def test_query_endpoint_unknown_endpoint_errors(self, api_connector):
        """Should return error for unknown endpoint name."""
        result = api_connector.query_endpoint("nonexistent")
        assert "error" in result

    def test_query_endpoint_preserves_nested_data(self, data_dir, env_file):
        """Nested JSON should be returned as-is without flattening."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="users", path="/users")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 1, "address": {"city": "NYC", "zip": "10001"}, "tags": ["admin", "active"]},
        ]

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp):
            result = conn.query_endpoint("users")

        row = result["data"][0]
        # Nested dict preserved
        assert row["address"] == {"city": "NYC", "zip": "10001"}
        # Nested list preserved
        assert row["tags"] == ["admin", "active"]

    def test_query_endpoint_fetch_by_single_id(self, data_dir, env_file):
        """Fetching by a single ID should call /{id} and return that record."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="events", path="/events")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "42", "title": "Event 42", "details": {"foo": 1}}

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp) as mock_get:
            result = conn.query_endpoint("events", id="42")

        # Should call /events/42
        called_url = mock_get.call_args.args[0]
        assert called_url.endswith("/events/42")
        assert result["rows_returned"] == 1
        assert result["data"][0]["title"] == "Event 42"
        # Nested data preserved
        assert result["data"][0]["details"] == {"foo": 1}

    def test_query_endpoint_fetch_by_multiple_ids(self, data_dir, env_file):
        """Fetching by multiple IDs should call /{id} for each and collect results."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="events", path="/events")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {"id": "1", "title": "First"}
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {"id": "2", "title": "Second"}

        with patch("db_mcp.connectors.api.requests.get", side_effect=[resp1, resp2]) as mock_get:
            result = conn.query_endpoint("events", id=["1", "2"])

        assert mock_get.call_count == 2
        assert result["rows_returned"] == 2
        assert result["data"][0]["title"] == "First"
        assert result["data"][1]["title"] == "Second"

    def test_query_endpoint_single_page_default(self, data_dir, env_file):
        """With max_pages=1 (default), only one HTTP call should be made."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
            APIPaginationConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
            pagination=APIPaginationConfig(
                type="cursor",
                data_field="data",
                page_size=2,
            ),
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": 1}, {"id": 2}], "has_more": True}

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp) as mock_get:
            result = conn.query_endpoint("items")

        assert mock_get.call_count == 1
        assert result["rows_returned"] == 2

    def test_query_endpoint_multi_page(self, data_dir, env_file):
        """With max_pages > 1, should follow pagination up to the limit."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
            APIPaginationConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
            pagination=APIPaginationConfig(
                type="cursor",
                cursor_param="after",
                cursor_field="data[-1].id",
                data_field="data",
                page_size=2,
            ),
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {"data": [{"id": "a"}, {"id": "b"}], "has_more": True}
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {"data": [{"id": "c"}], "has_more": False}

        with patch("db_mcp.connectors.api.requests.get", side_effect=[page1, page2]):
            result = conn.query_endpoint("items", max_pages=3)

        assert result["rows_returned"] == 3

    def test_query_endpoint_respects_data_field(self, data_dir, env_file):
        """Should extract rows from data_field wrapper."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
            APIPaginationConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
            pagination=APIPaginationConfig(data_field="results"),
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"id": 1}, {"id": 2}], "total": 2}

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp):
            result = conn.query_endpoint("items")

        assert result["rows_returned"] == 2
        assert result["data"][0]["id"] == 1


class TestAPIConnectorPathParams:
    def test_query_endpoint_path_param_substitution(self, data_dir, env_file):
        """query_endpoint should substitute {param} in endpoint path."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="query_results", path="/query/{query_id}/results")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp) as mock_get:
            conn.query_endpoint("query_results", params={"query_id": "123", "limit": "1"})

        called_url = mock_get.call_args.args[0]
        called_params = mock_get.call_args.kwargs["params"]
        assert called_url.endswith("/query/123/results")
        assert "query_id" not in called_params
        assert called_params["limit"] == "1"


class TestAPIConnectorPostBody:
    def test_query_endpoint_post_json_body(self, data_dir, env_file):
        """POST endpoint with body_mode=json sends params as JSON body."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[
                APIEndpointConfig(
                    name="execute_sql",
                    path="/sql/execute",
                    method="POST",
                    body_mode="json",
                )
            ],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            conn.query_endpoint("execute_sql", params={"query": "SELECT 1", "limit": "1"})

        called_json = mock_req.call_args.kwargs["json"]
        called_params = mock_req.call_args.kwargs["params"]
        assert called_json == {"query": "SELECT 1", "limit": "1"}
        assert called_params == {}


class TestAPIConnectorResponseMode:
    def test_query_endpoint_raw_response_mode(self, data_dir, env_file):
        """response_mode=raw should return the full JSON body."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[
                APIEndpointConfig(
                    name="execute_sql",
                    path="/sql/execute",
                    method="POST",
                    body_mode="json",
                    response_mode="raw",
                )
            ],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"execution_id": "abc", "state": "PENDING"}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp):
            result = conn.query_endpoint("execute_sql", params={"query": "SELECT 1"})

        assert result["data"] == {"execution_id": "abc", "state": "PENDING"}


# ---------------------------------------------------------------------------
# YAML round-trip (query_params persistence)
# ---------------------------------------------------------------------------


class TestAPIConnectorYAMLRoundTrip:
    """Tests for saving and loading query_params in connector.yaml."""

    def test_save_and_load_query_params(self, tmp_path, data_dir, env_file):
        """query_params should survive save → load round-trip."""
        from db_mcp.connectors import ConnectorConfig
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
            APIQueryParamConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[
                APIEndpointConfig(
                    name="events",
                    path="/events",
                    query_params=[
                        APIQueryParamConfig(
                            name="active",
                            type="boolean",
                            description="Filter by active",
                        ),
                        APIQueryParamConfig(
                            name="order",
                            type="string",
                            enum=["startDate", "volume"],
                        ),
                    ],
                ),
            ],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        yaml_path = tmp_path / "connector.yaml"
        conn.save_connector_yaml(yaml_path)

        loaded = ConnectorConfig.from_yaml(yaml_path)
        assert isinstance(loaded, APIConnectorConfig)
        assert len(loaded.endpoints) == 1
        ep = loaded.endpoints[0]
        assert len(ep.query_params) == 2
        active_qp = next(qp for qp in ep.query_params if qp.name == "active")
        assert active_qp.type == "boolean"
        assert active_qp.description == "Filter by active"
        order_qp = next(qp for qp in ep.query_params if qp.name == "order")
        assert order_qp.enum == ["startDate", "volume"]

    def test_load_yaml_without_query_params(self, tmp_path):
        """Loading connector.yaml without query_params should default to empty list."""
        from db_mcp.connectors import ConnectorConfig
        from db_mcp.connectors.api import APIConnectorConfig

        yaml_path = tmp_path / "connector.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "type": "api",
                    "base_url": "https://api.example.com",
                    "endpoints": [{"name": "items", "path": "/items"}],
                }
            )
        )

        loaded = ConnectorConfig.from_yaml(yaml_path)
        assert isinstance(loaded, APIConnectorConfig)
        assert loaded.endpoints[0].query_params == []


# ---------------------------------------------------------------------------
# SQL-like API execution (supports_sql=true, sql_mode=api_sync)
# ---------------------------------------------------------------------------


class TestAPIConnectorSQLExecution:
    """Tests for execute_sql with SQL-like APIs (Dune, etc.)."""

    def test_execute_sql_without_supports_sql_falls_back_to_duckdb(self, api_connector, data_dir):
        """Without supports_sql, execute_sql falls back to DuckDB on local files."""
        # Sync some data first
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": 1, "name": "Alice"}]}

        with patch("db_mcp.connectors.api.requests.get", return_value=mock_resp):
            api_connector.sync("users")

        # Now execute_sql should use DuckDB on the JSONL
        result = api_connector.execute_sql("SELECT * FROM users")
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_execute_sql_with_supports_sql_calls_api(self, data_dir, env_file):
        """With supports_sql=true, execute_sql POSTs to the execute_sql endpoint."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.dune.com/api/v1",
            auth=APIAuthConfig(
                type="header", token_env="TEST_API_KEY", header_name="X-DUNE-API-KEY"
            ),
            endpoints=[
                APIEndpointConfig(
                    name="execute_sql",
                    path="/sql/execute",
                    method="POST",
                    body_mode="json",
                )
            ],
            capabilities={"supports_sql": True, "sql_mode": "api_sync"},
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        # Mock sync response (returns rows directly)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"rows": [{"token": "SOL", "volume": 1000000}]}}

        with patch("db_mcp.connectors.api.requests.post", return_value=mock_resp) as mock_post:
            result = conn.execute_sql("SELECT token, volume FROM dex_solana.trades LIMIT 1")

        # Verify the API was called correctly
        mock_post.assert_called_once()
        called_url = mock_post.call_args.args[0]
        called_json = mock_post.call_args.kwargs["json"]
        assert "/sql/execute" in called_url
        # Default sql_field is "sql" (matching Dune's API)
        assert called_json["sql"] == "SELECT token, volume FROM dex_solana.trades LIMIT 1"

        # Verify results extracted correctly
        assert len(result) == 1
        assert result[0]["token"] == "SOL"
        assert result[0]["volume"] == 1000000

    def test_execute_sql_async_polls_for_results(self, data_dir, env_file):
        """Async SQL API: polls execution_status then fetches execution_results."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.dune.com/api/v1",
            auth=APIAuthConfig(
                type="header", token_env="TEST_API_KEY", header_name="X-DUNE-API-KEY"
            ),
            endpoints=[
                APIEndpointConfig(
                    name="execute_sql", path="/sql/execute", method="POST", body_mode="json"
                ),
                APIEndpointConfig(
                    name="execution_status", path="/execution/{execution_id}/status", method="GET"
                ),
                APIEndpointConfig(
                    name="execution_results",
                    path="/execution/{execution_id}/results",
                    method="GET",
                ),
            ],
            capabilities={"supports_sql": True, "sql_mode": "api_sync"},
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        # Mock responses
        execute_resp = MagicMock()
        execute_resp.status_code = 200
        execute_resp.json.return_value = {"execution_id": "exec-123"}

        status_pending = MagicMock()
        status_pending.status_code = 200
        status_pending.json.return_value = {"state": "PENDING"}

        status_complete = MagicMock()
        status_complete.status_code = 200
        status_complete.json.return_value = {"state": "COMPLETE"}

        results_resp = MagicMock()
        results_resp.status_code = 200
        results_resp.json.return_value = {"result": {"rows": [{"id": 1, "value": "test"}]}}

        call_count = {"status": 0}

        def mock_get(url, **kwargs):
            if "status" in url:
                call_count["status"] += 1
                if call_count["status"] == 1:
                    return status_pending
                return status_complete
            elif "results" in url:
                return results_resp
            raise ValueError(f"Unexpected URL: {url}")

        with (
            patch("db_mcp.connectors.api.requests.post", return_value=execute_resp),
            patch("db_mcp.connectors.api.requests.get", side_effect=mock_get),
            patch("time.sleep"),  # Skip actual sleeping
        ):
            result = conn.execute_sql("SELECT * FROM test")

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert call_count["status"] == 2  # Called twice: pending, then complete

    def test_execute_sql_missing_endpoint_raises(self, data_dir, env_file):
        """Missing execute_sql endpoint should raise ValueError."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[],  # No execute_sql endpoint
            capabilities={"supports_sql": True},
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        with pytest.raises(ValueError, match="No 'execute_sql' endpoint configured"):
            conn.execute_sql("SELECT 1")

    def test_extract_rows_handles_various_formats(self, data_dir, env_file):
        """_extract_rows_from_response handles multiple response formats."""
        from db_mcp.connectors.api import APIConnector, APIConnectorConfig

        config = APIConnectorConfig(base_url="https://api.example.com")
        conn = APIConnector(config, data_dir=str(data_dir))

        # Format: {result: {rows: [...]}} (Dune)
        assert conn._extract_rows_from_response({"result": {"rows": [{"a": 1}]}}) == [{"a": 1}]

        # Format: {data: [...]}
        assert conn._extract_rows_from_response({"data": [{"b": 2}]}) == [{"b": 2}]

        # Format: {rows: [...]}
        assert conn._extract_rows_from_response({"rows": [{"c": 3}]}) == [{"c": 3}]

        # Format: {results: [...]}
        assert conn._extract_rows_from_response({"results": [{"d": 4}]}) == [{"d": 4}]

        # Format: direct list
        assert conn._extract_rows_from_response([{"e": 5}]) == [{"e": 5}]

        # Format: columns + rows as arrays
        assert conn._extract_rows_from_response(
            {"columns": ["x", "y"], "rows": [[1, 2], [3, 4]]}
        ) == [{"x": 1, "y": 2}, {"x": 3, "y": 4}]

        # Empty/unknown format
        assert conn._extract_rows_from_response({"unknown": "format"}) == []


# ---------------------------------------------------------------------------
# _send_request — generalized HTTP method support (v0.5.17)
# ---------------------------------------------------------------------------


class TestSendRequest:
    """Tests for the unified _send_request method."""

    def test_send_request_get(self, api_connector):
        """GET request should pass query_params, no JSON body."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            result = api_connector._send_request(
                "GET",
                "https://api.example.com/v1/users",
                {"Authorization": "Bearer tok"},
                {"limit": "10"},
            )

        mock_req.assert_called_once()
        call_kw = mock_req.call_args.kwargs
        assert call_kw["method"] == "GET"
        assert call_kw["params"] == {"limit": "10"}
        assert call_kw.get("json") is None
        assert result == {"data": []}

    def test_send_request_post_with_body(self, api_connector):
        """POST with body sends JSON body and query params separately."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "name": "New Item"}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            api_connector._send_request(
                "POST",
                "https://api.example.com/v1/items",
                {"Authorization": "Bearer tok"},
                {"format": "json"},
                body={"name": "New Item", "value": 42},
            )

        call_kw = mock_req.call_args.kwargs
        assert call_kw["method"] == "POST"
        assert call_kw["json"] == {"name": "New Item", "value": 42}
        assert call_kw["params"] == {"format": "json"}

    def test_send_request_put(self, api_connector):
        """PUT request sends body as JSON."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"updated": True}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            api_connector._send_request(
                "PUT",
                "https://api.example.com/v1/items/1",
                {},
                {},
                body={"name": "Updated"},
            )

        assert mock_req.call_args.kwargs["method"] == "PUT"
        assert mock_req.call_args.kwargs["json"] == {"name": "Updated"}

    def test_send_request_patch(self, api_connector):
        """PATCH request sends partial update body."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"patched": True}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            api_connector._send_request(
                "PATCH",
                "https://api.example.com/v1/items/1",
                {},
                {},
                body={"status": "active"},
            )

        assert mock_req.call_args.kwargs["method"] == "PATCH"
        assert mock_req.call_args.kwargs["json"] == {"status": "active"}

    def test_send_request_delete(self, api_connector):
        """DELETE request works without body."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"deleted": True}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            result = api_connector._send_request(
                "DELETE",
                "https://api.example.com/v1/items/1",
                {},
                {},
            )

        assert mock_req.call_args.kwargs["method"] == "DELETE"
        assert result == {"deleted": True}

    def test_send_request_post_no_body(self, api_connector):
        """POST without body sends params as query string only."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"triggered": True}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            api_connector._send_request(
                "POST",
                "https://api.example.com/v1/trigger",
                {},
                {"action": "run"},
            )

        call_kw = mock_req.call_args.kwargs
        assert call_kw["method"] == "POST"
        assert call_kw["params"] == {"action": "run"}


# ---------------------------------------------------------------------------
# query_endpoint with body and method_override (v0.5.17)
# ---------------------------------------------------------------------------


class TestQueryEndpointWriteSupport:
    """Tests for query_endpoint body and method_override parameters."""

    def test_query_endpoint_with_body_post(self, data_dir, env_file):
        """query_endpoint with body= sends JSON body for POST."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="create_item", path="/items", method="POST")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 99, "name": "Widget"}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            conn.query_endpoint("create_item", body={"name": "Widget", "price": 9.99})

        call_kw = mock_req.call_args.kwargs
        assert call_kw["json"] == {"name": "Widget", "price": 9.99}
        assert call_kw["method"] == "POST"

    def test_query_endpoint_with_method_override(self, data_dir, env_file):
        """method_override overrides the endpoint's default method."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="items", path="/items", method="GET")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "created": True}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            conn.query_endpoint("items", body={"name": "New"}, method_override="POST")

        assert mock_req.call_args.kwargs["method"] == "POST"
        assert mock_req.call_args.kwargs["json"] == {"name": "New"}

    def test_query_endpoint_body_with_params(self, data_dir, env_file):
        """body and params sent separately (body=JSON, params=query string)."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="items", path="/items", method="PUT")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"updated": True}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            conn.query_endpoint("items", params={"version": "2"}, body={"name": "Updated"})

        call_kw = mock_req.call_args.kwargs
        assert call_kw["params"]["version"] == "2"
        assert call_kw["json"] == {"name": "Updated"}

    def test_query_endpoint_raw_response_with_body(self, data_dir, env_file):
        """POST with response_mode=raw returns full response dict."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[
                APIEndpointConfig(
                    name="create",
                    path="/resources",
                    method="POST",
                    response_mode="raw",
                )
            ],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 42, "status": "created", "meta": {"v": 1}}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp):
            result = conn.query_endpoint("create", body={"name": "test"})

        assert result["data"] == {"id": 42, "status": "created", "meta": {"v": 1}}

    def test_query_endpoint_delete_method_override(self, data_dir, env_file):
        """DELETE via method_override works."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[APIEndpointConfig(name="items", path="/items/{item_id}", method="GET")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"deleted": True}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp) as mock_req:
            conn.query_endpoint("items", params={"item_id": "42"}, method_override="DELETE")

        assert mock_req.call_args.kwargs["method"] == "DELETE"
        assert "/items/42" in mock_req.call_args.kwargs["url"]


# ---------------------------------------------------------------------------
# JWT login auth (v0.5.17)
# ---------------------------------------------------------------------------


class TestJWTLoginAuth:
    """Tests for jwt_login authentication type."""

    def _make_jwt_connector(self, data_dir, env_file):
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        env_file.write_text("JWT_USER=admin\nJWT_PASS=secret123\n")

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(
                type="jwt_login",
                login_endpoint="/auth/login",
                username_env="JWT_USER",
                password_env="JWT_PASS",
                token_field="access_token",
            ),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
        )
        return APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

    def test_jwt_login_fetches_token(self, data_dir, env_file):
        """First request POSTs to login endpoint and caches token."""
        conn = self._make_jwt_connector(data_dir, env_file)

        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {"access_token": "jwt-token-abc"}

        with patch("db_mcp.connectors.api.requests.post", return_value=login_resp) as mock_post:
            headers = conn._resolve_auth_headers()

        assert headers["Authorization"] == "Bearer jwt-token-abc"
        mock_post.assert_called_once()
        call_kw = mock_post.call_args
        assert call_kw.kwargs["json"]["username"] == "admin"
        assert call_kw.kwargs["json"]["password"] == "secret123"

    def test_jwt_login_caches_token(self, data_dir, env_file):
        """Second call reuses cached token without login."""
        conn = self._make_jwt_connector(data_dir, env_file)

        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {"access_token": "jwt-token-abc"}

        with patch("db_mcp.connectors.api.requests.post", return_value=login_resp) as mock_post:
            headers1 = conn._resolve_auth_headers()
            headers2 = conn._resolve_auth_headers()

        assert headers1 == headers2
        assert mock_post.call_count == 1

    def test_jwt_login_custom_token_field(self, data_dir, env_file):
        """Extracts token from configured token_field."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        env_file.write_text("JWT_USER=admin\nJWT_PASS=secret\n")

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(
                type="jwt_login",
                login_endpoint="/login",
                username_env="JWT_USER",
                password_env="JWT_PASS",
                token_field="token",
            ),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {"token": "my-custom-token"}

        with patch("db_mcp.connectors.api.requests.post", return_value=login_resp):
            headers = conn._resolve_auth_headers()

        assert headers["Authorization"] == "Bearer my-custom-token"

    def test_jwt_login_401_refresh(self, data_dir, env_file):
        """On 401, refreshes token once and retries."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        env_file.write_text("JWT_USER=admin\nJWT_PASS=secret123\n")

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(
                type="jwt_login",
                login_endpoint="/auth/login",
                username_env="JWT_USER",
                password_env="JWT_PASS",
                token_field="access_token",
            ),
            endpoints=[APIEndpointConfig(name="create_item", path="/items", method="POST")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        login_resp1 = MagicMock()
        login_resp1.status_code = 200
        login_resp1.json.return_value = {"access_token": "old-token"}

        login_resp2 = MagicMock()
        login_resp2.status_code = 200
        login_resp2.json.return_value = {"access_token": "new-token"}

        api_resp_401 = MagicMock()
        api_resp_401.status_code = 401
        api_resp_401.raise_for_status.side_effect = requests_lib.exceptions.HTTPError(
            response=api_resp_401
        )

        api_resp_ok = MagicMock()
        api_resp_ok.status_code = 200
        api_resp_ok.json.return_value = {"id": 1, "name": "Created"}

        with (
            patch(
                "db_mcp.connectors.api.requests.post",
                side_effect=[login_resp1, login_resp2],
            ),
            patch(
                "db_mcp.connectors.api.requests.request",
                side_effect=[api_resp_401, api_resp_ok],
            ),
        ):
            result = conn.query_endpoint("create_item", body={"name": "Widget"})

        assert "error" not in result
        assert result["rows_returned"] == 1

    def test_jwt_login_missing_env_raises(self, data_dir, env_file):
        """Missing username/password env vars raises ValueError."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        env_file.write_text("")

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(
                type="jwt_login",
                login_endpoint="/auth/login",
                username_env="MISSING_USER",
                password_env="MISSING_PASS",
            ),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        with pytest.raises(ValueError, match="not found"):
            conn._resolve_auth_headers()

    def test_jwt_login_alias_fields_normalized(self, data_dir, env_file):
        """login_url/username/password aliases are normalized to canonical fields."""
        from db_mcp.connectors.api import APIAuthConfig

        auth = APIAuthConfig(
            type="jwt_login",
            login_url="/auth/token",
            username="JWT_USER",
            password="JWT_PASS",
        )

        assert auth.login_endpoint == "/auth/token"
        assert auth.username_env == "JWT_USER"
        assert auth.password_env == "JWT_PASS"
        # Alias fields remain set (not cleared)
        assert auth.login_url == "/auth/token"
        assert auth.username == "JWT_USER"
        assert auth.password == "JWT_PASS"

    def test_jwt_login_alias_fields_do_not_override_canonical(self, data_dir, env_file):
        """Canonical fields take precedence when both are supplied."""
        from db_mcp.connectors.api import APIAuthConfig

        auth = APIAuthConfig(
            type="jwt_login",
            login_endpoint="/auth/login",   # canonical wins
            login_url="/should/be/ignored",
            username_env="REAL_USER",       # canonical wins
            username="IGNORED_USER",
            password_env="REAL_PASS",
            password="IGNORED_PASS",
        )

        assert auth.login_endpoint == "/auth/login"
        assert auth.username_env == "REAL_USER"
        assert auth.password_env == "REAL_PASS"

    def test_jwt_login_via_alias_fields_fetches_token(self, data_dir, env_file):
        """Full auth flow works when connector.yaml uses alias field names."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        env_file.write_text("JWT_USER=admin\nJWT_PASS=secret123\n")

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(
                type="jwt_login",
                login_url="/auth/login",   # alias
                username="JWT_USER",       # alias
                password="JWT_PASS",       # alias
            ),
            endpoints=[APIEndpointConfig(name="items", path="/items")],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {"access_token": "tok-xyz"}

        with patch("db_mcp.connectors.api.requests.post", return_value=login_resp):
            headers = conn._resolve_auth_headers()

        assert headers["Authorization"] == "Bearer tok-xyz"

    def test_load_api_config_accepts_login_url_alias(self):
        """_load_api_config round-trips a connector.yaml with login_url alias."""
        from db_mcp.connectors import _load_api_config

        data = {
            "type": "api",
            "base_url": "https://example.com",
            "auth": {
                "type": "jwt_login",
                "login_url": "/auth/token",
                "username": "JWT_USER",
                "password": "JWT_PASS",
                "token_field": "token",
            },
            "endpoints": [],
        }

        config = _load_api_config(data)
        assert config.auth.login_endpoint == "/auth/token"
        assert config.auth.username_env == "JWT_USER"
        assert config.auth.password_env == "JWT_PASS"
        assert config.auth.token_field == "token"


# ---------------------------------------------------------------------------
# Raw response mode for GET endpoints (v0.5.17)
# ---------------------------------------------------------------------------


class TestRawResponseModeGET:
    """Tests for response_mode=raw on GET endpoints."""

    def test_raw_response_get_returns_full_dict(self, data_dir, env_file):
        """GET endpoint with response_mode=raw returns full response."""
        from db_mcp.connectors.api import (
            APIAuthConfig,
            APIConnector,
            APIConnectorConfig,
            APIEndpointConfig,
        )

        config = APIConnectorConfig(
            base_url="https://api.example.com",
            auth=APIAuthConfig(type="bearer", token_env="TEST_API_KEY"),
            endpoints=[
                APIEndpointConfig(name="status", path="/status", method="GET", response_mode="raw")
            ],
        )
        conn = APIConnector(config, data_dir=str(data_dir), env_path=str(env_file))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"version": "2.1", "healthy": True, "uptime_seconds": 86400}

        with patch("db_mcp.connectors.api.requests.request", return_value=mock_resp):
            result = conn.query_endpoint("status")

        assert result["data"] == {"version": "2.1", "healthy": True, "uptime_seconds": 86400}


# ---------------------------------------------------------------------------
# api_mutate tool (v0.5.17)
# ---------------------------------------------------------------------------


class TestAPIMutateTool:
    """Tests for the _api_mutate MCP tool function."""

    @pytest.fixture
    def mock_api_connector(self):
        from db_mcp.connectors.api import APIConnector

        mock = MagicMock(spec=APIConnector)
        mock.query_endpoint.return_value = {
            "data": {"id": 1, "created": True},
            "rows_returned": 1,
        }
        return mock

    def test_api_mutate_post(self, mock_api_connector):
        """api_mutate POST calls query_endpoint correctly."""
        from db_mcp.tools.api import _api_mutate

        with patch(
            "db_mcp.tools.api.get_connector",
            return_value=mock_api_connector,
        ):
            asyncio.run(
                _api_mutate(
                    endpoint="items",
                    method="POST",
                    body={"name": "Widget"},
                )
            )

        mock_api_connector.query_endpoint.assert_called_once_with(
            "items", None, body={"name": "Widget"}, method_override="POST"
        )

    def test_api_mutate_rejects_get(self):
        """api_mutate rejects GET method."""
        from db_mcp.tools.api import _api_mutate

        result = asyncio.run(_api_mutate(endpoint="items", method="GET", body={}))
        assert "error" in result

    def test_api_mutate_accepts_valid_methods(self, mock_api_connector):
        """api_mutate accepts POST, PUT, PATCH, DELETE."""
        from db_mcp.tools.api import _api_mutate

        for method in ["POST", "PUT", "PATCH", "DELETE"]:
            mock_api_connector.reset_mock()
            mock_api_connector.query_endpoint.return_value = {"data": {}, "rows_returned": 0}
            with patch("db_mcp.tools.api.get_connector", return_value=mock_api_connector):
                result = asyncio.run(_api_mutate(endpoint="items", method=method, body={"x": 1}))
            assert "error" not in result

    def test_api_mutate_passes_params(self, mock_api_connector):
        """api_mutate passes optional params through."""
        from db_mcp.tools.api import _api_mutate

        with patch(
            "db_mcp.tools.api.get_connector",
            return_value=mock_api_connector,
        ):
            asyncio.run(
                _api_mutate(
                    endpoint="items",
                    method="POST",
                    body={"name": "test"},
                    params={"version": "2"},
                )
            )

        mock_api_connector.query_endpoint.assert_called_once_with(
            "items", {"version": "2"}, body={"name": "test"}, method_override="POST"
        )

    def test_api_mutate_non_api_connector_errors(self):
        """api_mutate errors if connector is not APIConnector."""
        from db_mcp.tools.api import _api_mutate

        mock_sql = MagicMock()
        mock_sql.__class__.__name__ = "SQLConnector"

        with patch("db_mcp.tools.api.get_connector", return_value=mock_sql):
            result = asyncio.run(_api_mutate(endpoint="items", method="POST", body={"x": 1}))
        assert "error" in result
