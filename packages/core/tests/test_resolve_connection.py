"""Tests for resolve_connection() helper and multi-connection architecture."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db_mcp.tools.utils import get_resolved_provider_id, resolve_connection

# ============================================================================
# Helpers
# ============================================================================


def _make_mock_sql_connector():
    from db_mcp.connectors import SQLConnector

    mock = MagicMock(spec=SQLConnector)
    return mock


def _make_mock_api_connector():
    from db_mcp.connectors import APIConnector

    mock = MagicMock(spec=APIConnector)
    return mock


def _make_connection_info(name, path="/tmp/conn", conn_type="sql", dialect="trino"):
    from db_mcp.registry import ConnectionInfo

    return ConnectionInfo(
        name=name,
        path=Path(path),
        type=conn_type,
        dialect=dialect,
        description="",
        is_default=False,
    )


# ============================================================================
# resolve_connection tests
# ============================================================================


class TestResolveConnectionLegacyFallback:
    """Tests for legacy / no-connections-discovered mode."""

    def test_no_connections_uses_legacy_connector(self):
        """When no connections discovered, falls back to get_connector()."""
        mock_connector = _make_mock_sql_connector()

        mock_settings = MagicMock()
        mock_settings.get_effective_provider_id.return_value = "default"
        mock_settings.get_effective_connection_path.return_value = Path("/tmp/legacy")
        mock_settings.connection_name = "default"
        mock_settings.connections_dir = ""

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {}

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            patch("db_mcp.tools.utils.get_connector", return_value=mock_connector),
            patch("db_mcp.tools.utils.get_settings", return_value=mock_settings),
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            connector, name, path = resolve_connection(None)

        assert connector is mock_connector
        assert name == "default"
        assert path == Path("/tmp/legacy")

    def test_no_connections_named_connection_raises(self):
        """When no connections discovered and named connection given, raises ValueError."""
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {}

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            pytest.raises(ValueError, match="not found"),
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            resolve_connection("nonexistent")


class TestResolveConnectionSingle:
    """Tests for single-connection mode."""

    def test_single_connection_no_param(self):
        """Single connection + no param → use that connection."""
        mock_connector = _make_mock_sql_connector()
        conn_info = _make_connection_info("my-db", "/tmp/my-db", "sql")

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"my-db": conn_info}
        mock_registry.get_connector.return_value = mock_connector

        with patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls:
            mock_cr_cls.get_instance.return_value = mock_registry
            connector, name, path = resolve_connection(None)

        assert connector is mock_connector
        assert name == "my-db"
        assert path == Path("/tmp/my-db")

    def test_single_connection_named_param(self):
        """Single connection + explicit name → use named connection."""
        mock_connector = _make_mock_sql_connector()
        conn_info = _make_connection_info("my-db", "/tmp/my-db", "sql")

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"my-db": conn_info}
        mock_registry.get_connector.return_value = mock_connector

        with patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls:
            mock_cr_cls.get_instance.return_value = mock_registry
            connector, name, path = resolve_connection("my-db")

        assert connector is mock_connector
        assert name == "my-db"

    def test_single_connection_wrong_name_raises(self):
        """Named connection not in registry → helpful ValueError."""
        conn_info = _make_connection_info("my-db")
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"my-db": conn_info}

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            pytest.raises(ValueError, match="my-db"),
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            resolve_connection("wrong-db")


class TestResolveConnectionMultiple:
    """Tests for multi-connection mode."""

    def test_multiple_connections_no_param_errors(self):
        """Multiple connections + no param → error listing available."""
        sql1 = _make_connection_info("trino-prod", conn_type="sql")
        sql2 = _make_connection_info("duckdb-local", conn_type="sql")

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {
            "trino-prod": sql1,
            "duckdb-local": sql2,
        }

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            pytest.raises(ValueError) as exc_info,
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            resolve_connection(None)

        error_msg = str(exc_info.value)
        assert "trino-prod" in error_msg or "duckdb-local" in error_msg

    def test_multiple_connections_require_type_single_match(self):
        """Multiple connections, require_type, only one matches → use it."""
        sql_conn = _make_connection_info("trino-prod", conn_type="sql")
        api_conn = _make_connection_info("superset-api", conn_type="api")
        mock_connector = _make_mock_sql_connector()

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {
            "trino-prod": sql_conn,
            "superset-api": api_conn,
        }
        mock_registry.get_connector.return_value = mock_connector

        with patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls:
            mock_cr_cls.get_instance.return_value = mock_registry
            connector, name, path = resolve_connection(None, require_type="sql")

        assert name == "trino-prod"
        assert connector is mock_connector

    def test_multiple_connections_require_type_multiple_matches_errors(self):
        """Multiple connections, require_type, multiple match → error."""
        sql1 = _make_connection_info("trino-prod", conn_type="sql")
        sql2 = _make_connection_info("pg-dev", conn_type="sql")

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {
            "trino-prod": sql1,
            "pg-dev": sql2,
        }

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            pytest.raises(ValueError) as exc_info,
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            resolve_connection(None, require_type="sql")

        error_msg = str(exc_info.value)
        assert "trino-prod" in error_msg or "pg-dev" in error_msg
        assert "connection=" in error_msg

    def test_multiple_connections_named_selects_correct(self):
        """Multiple connections, explicit name → use named connection."""
        sql1 = _make_connection_info("trino-prod", "/tmp/trino-prod", "sql")
        sql2 = _make_connection_info("duckdb-local", "/tmp/duckdb-local", "sql")
        mock_connector = _make_mock_sql_connector()

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {
            "trino-prod": sql1,
            "duckdb-local": sql2,
        }
        mock_registry.get_connector.return_value = mock_connector

        with patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls:
            mock_cr_cls.get_instance.return_value = mock_registry
            connector, name, path = resolve_connection("duckdb-local")

        assert name == "duckdb-local"
        assert path == Path("/tmp/duckdb-local")


class TestResolveConnectionTypeValidation:
    """Tests for type validation in resolve_connection."""

    def test_type_mismatch_raises(self):
        """Named connection with wrong type → helpful error."""
        sql_conn = _make_connection_info("my-sql", conn_type="sql")
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"my-sql": sql_conn}

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            pytest.raises(ValueError, match="type 'sql'"),
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            resolve_connection("my-sql", require_type="api")

    def test_no_api_connections_raises(self):
        """No API connections when require_type='api' → helpful error."""
        sql_conn = _make_connection_info("my-sql", conn_type="sql")
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"my-sql": sql_conn}

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            pytest.raises(ValueError, match="api"),
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            resolve_connection(None, require_type="api")


class TestResolveConnectionCapabilityValidation:
    """Tests for capability validation in resolve_connection."""

    def test_capability_check_passes(self):
        """Connection with required capability → no error."""

        conn_info = _make_connection_info("my-sql", conn_type="sql")
        mock_connector = _make_mock_sql_connector()

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"my-sql": conn_info}
        mock_registry.get_connector.return_value = mock_connector

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            patch(
                "db_mcp.tools.utils.get_connector_capabilities",
                return_value={"supports_sql": True},
            ),
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            connector, name, path = resolve_connection(
                "my-sql", require_capability="supports_sql"
            )

        assert name == "my-sql"

    def test_capability_check_fails(self):
        """Connection without required capability → ValueError."""
        conn_info = _make_connection_info("my-api", conn_type="api")
        mock_connector = _make_mock_api_connector()

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"my-api": conn_info}
        mock_registry.get_connector.return_value = mock_connector

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            patch(
                "db_mcp.tools.utils.get_connector_capabilities",
                return_value={"supports_sql": False},
            ),
            pytest.raises(ValueError, match="supports_sql"),
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            resolve_connection("my-api", require_capability="supports_sql")


# ============================================================================
# get_resolved_provider_id tests
# ============================================================================


class TestGetResolvedProviderId:
    """Tests for get_resolved_provider_id() helper."""

    def test_with_connection_returns_connection_name(self):
        """When connection is given, returns it as provider_id."""
        result = get_resolved_provider_id("wifimetrics")
        assert result == "wifimetrics"

    def test_none_returns_settings_provider(self):
        """When connection is None, returns settings provider_id."""
        mock_settings = MagicMock()
        mock_settings.get_effective_provider_id.return_value = "default-conn"

        with patch("db_mcp.tools.utils.get_settings", return_value=mock_settings):
            result = get_resolved_provider_id(None)

        assert result == "default-conn"

    def test_get_resolved_provider_id_none_returns_active(self):
        """get_resolved_provider_id(None) returns active connection name (duplicate of above)."""
        mock_settings = MagicMock()
        mock_settings.get_effective_provider_id.return_value = "my-connection"

        with patch("db_mcp.tools.utils.get_settings", return_value=mock_settings):
            result = get_resolved_provider_id(None)

        assert result == "my-connection"


# ============================================================================
# Query store connection tracking tests
# ============================================================================


class TestQueryStoreConnectionTracking:
    """Tests for connection field in QueryStore."""

    def test_query_has_connection_field(self):
        """Query dataclass has connection field."""
        from db_mcp.tasks.store import Query

        q = Query(query_id="test-id", sql="SELECT 1", connection="trino-prod")
        assert q.connection == "trino-prod"

    def test_query_connection_defaults_to_none(self):
        """Query connection defaults to None for backward compat."""
        from db_mcp.tasks.store import Query

        q = Query(query_id="test-id", sql="SELECT 1")
        assert q.connection is None

    def test_register_validated_stores_connection(self):
        """register_validated() stores connection name in Query."""
        import asyncio

        from db_mcp.tasks.store import QueryStore

        store = QueryStore()

        async def _run():
            q = await store.register_validated(
                sql="SELECT 1",
                connection="trino-prod",
            )
            return q

        q = asyncio.run(_run())
        assert q.connection == "trino-prod"

    def test_register_validated_no_connection_defaults_none(self):
        """register_validated() without connection defaults to None."""
        import asyncio

        from db_mcp.tasks.store import QueryStore

        store = QueryStore()

        async def _run():
            q = await store.register_validated(sql="SELECT 1")
            return q

        q = asyncio.run(_run())
        assert q.connection is None


# ============================================================================
# Server registration multi-connection tests
# ============================================================================


class TestServerMultiConnectionRegistration:
    """Tests for server tool registration with multiple connections."""

    def test_registry_discover_aggregates_capabilities(self, tmp_path):
        """Registry discover scans all connections and aggregates capabilities."""
        import yaml

        from db_mcp.registry import ConnectionRegistry

        # Create two connections: one SQL, one API
        sql_dir = tmp_path / "my-sql"
        sql_dir.mkdir()
        (sql_dir / "connector.yaml").write_text(
            yaml.dump({"type": "sql", "dialect": "trino"})
        )

        api_dir = tmp_path / "my-api"
        api_dir.mkdir()
        (api_dir / "connector.yaml").write_text(
            yaml.dump({"type": "api", "dialect": ""})
        )

        mock_settings = MagicMock()
        mock_settings.connections_dir = str(tmp_path)
        mock_settings.connection_name = "my-sql"
        mock_settings.provider_id = "my-sql"

        registry = ConnectionRegistry(settings=mock_settings)
        connections = registry.discover()

        assert len(connections) == 2
        assert "my-sql" in connections
        assert "my-api" in connections
        assert connections["my-sql"].type == "sql"
        assert connections["my-api"].type == "api"

    def test_registry_get_default_name(self):
        """get_default_name() returns settings.connection_name."""
        from db_mcp.registry import ConnectionRegistry

        mock_settings = MagicMock()
        mock_settings.connection_name = "trino-prod"
        mock_settings.provider_id = "default"

        registry = ConnectionRegistry(settings=mock_settings)
        assert registry.get_default_name() == "trino-prod"

    def test_registry_get_connections_by_type(self, tmp_path):
        """get_connections_by_type() filters by type correctly."""
        import yaml

        from db_mcp.registry import ConnectionRegistry

        for name, conn_type in [("sql1", "sql"), ("sql2", "sql"), ("api1", "api")]:
            d = tmp_path / name
            d.mkdir()
            (d / "connector.yaml").write_text(yaml.dump({"type": conn_type}))

        mock_settings = MagicMock()
        mock_settings.connections_dir = str(tmp_path)
        mock_settings.connection_name = "sql1"

        registry = ConnectionRegistry(settings=mock_settings)
        registry.discover()

        sql_conns = registry.get_connections_by_type("sql")
        api_conns = registry.get_connections_by_type("api")

        assert len(sql_conns) == 2
        assert all(c.type == "sql" for c in sql_conns)
        assert len(api_conns) == 1
        assert api_conns[0].type == "api"


# ============================================================================
# API tool dispatch with connection param tests
# ============================================================================


class TestAPIToolConnectionDispatch:
    """Tests for API tools using connection param for dispatch."""

    def test_api_query_dispatches_to_correct_connection(self):
        """api_query with connection param uses that connection's connector."""
        from pathlib import Path

        mock_api_connector = _make_mock_api_connector()
        mock_api_connector.query_endpoint.return_value = {"data": [], "rows_returned": 0}

        with patch(
            "db_mcp.tools.api.resolve_connection",
            return_value=(mock_api_connector, "my-api", Path("/tmp/my-api")),
        ) as mock_resolve:
            asyncio.run(
                __import__("db_mcp.tools.api", fromlist=["_api_query"])._api_query(
                    endpoint="users",
                    connection="my-api",
                )
            )

        mock_resolve.assert_called_once_with("my-api", require_type="api")
        mock_api_connector.query_endpoint.assert_called_once()

    def test_api_query_without_connection_auto_resolves(self):
        """api_query without connection auto-resolves when single API exists."""
        from pathlib import Path

        mock_api_connector = _make_mock_api_connector()
        mock_api_connector.query_endpoint.return_value = {"data": [], "rows_returned": 0}

        with patch(
            "db_mcp.tools.api.resolve_connection",
            return_value=(mock_api_connector, "my-api", Path("/tmp/my-api")),
        ) as mock_resolve:
            asyncio.run(
                __import__("db_mcp.tools.api", fromlist=["_api_query"])._api_query(
                    endpoint="users",
                )
            )

        mock_resolve.assert_called_once_with(None, require_type="api")

    def test_api_query_multiple_api_connections_no_param_errors(self):
        """api_query without connection param when multiple APIs exist → error."""
        with patch(
            "db_mcp.tools.api.resolve_connection",
            side_effect=ValueError(
                "Multiple api connections available: api1, api2. "
                "Specify connection=<name> to select one."
            ),
        ):
            result = asyncio.run(
                __import__("db_mcp.tools.api", fromlist=["_api_query"])._api_query(
                    endpoint="users",
                )
            )

        assert "error" in result
        assert "api1" in result["error"] or "api2" in result["error"]


# ============================================================================
# Backward compatibility tests
# ============================================================================


class TestBackwardCompatibility:
    """Tests ensuring single-connection mode still works exactly as before."""

    def test_resolve_connection_no_connections_no_connection_param(self):
        """With no discovered connections and connection=None, falls back gracefully."""
        mock_connector = _make_mock_sql_connector()
        mock_settings = MagicMock()
        mock_settings.get_effective_provider_id.return_value = "default"
        mock_settings.get_effective_connection_path.return_value = Path("/tmp/default")
        mock_settings.connection_name = "default"

        mock_registry = MagicMock()
        mock_registry.discover.return_value = {}

        with (
            patch("db_mcp.tools.utils.ConnectionRegistry") as mock_cr_cls,
            patch("db_mcp.tools.utils.get_connector", return_value=mock_connector),
            patch("db_mcp.tools.utils.get_settings", return_value=mock_settings),
        ):
            mock_cr_cls.get_instance.return_value = mock_registry
            connector, name, path = resolve_connection(None)

        # Should work exactly as today: use the active connector
        assert connector is mock_connector
        assert name == "default"
        assert path == Path("/tmp/default")

    def test_get_resolved_provider_id_none_returns_active(self):
        """get_resolved_provider_id(None) returns active connection name."""
        mock_settings = MagicMock()
        mock_settings.get_effective_provider_id.return_value = "my-connection"

        with patch("db_mcp.tools.utils.get_settings", return_value=mock_settings):
            result = get_resolved_provider_id(None)

        assert result == "my-connection"
