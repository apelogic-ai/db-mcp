"""Tests for the MCP server."""

import asyncio
import importlib
import pkgutil
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastmcp.client import Client

from db_mcp.config import reset_settings
from db_mcp.insights.detector import Insight, InsightStore, load_insights, save_insights
from db_mcp.registry import ConnectionInfo, ConnectionRegistry
from db_mcp.server import _create_server
from db_mcp.tools import daemon_tasks


def _get_tool_names(server):
    """Extract registered tool names from a FastMCP server."""
    return set(server._tool_manager._tools.keys())


def _tool_payload(result_data: dict) -> dict:
    """Return structuredContent when present, otherwise raw result data."""
    return result_data.get("structuredContent", result_data)


def _write_sql_connector(connection_dir: Path) -> None:
    connection_dir.mkdir(parents=True, exist_ok=True)
    (connection_dir / "connector.yaml").write_text(
        "\n".join(
            [
                "type: sql",
                "database_url: sqlite:///tmp/test.sqlite",
            ]
        )
        + "\n"
    )


def test_mcp_server_created():
    """Test MCP server is properly configured."""
    server = _create_server()
    assert server.name == "db-mcp"


@pytest.mark.asyncio
async def test_server_tools_registered():
    """Test that expected tools are registered on the server."""
    server = _create_server()
    # Basic sanity check - server should have tools registered
    assert server is not None


def test_server_exposes_improvement_tools(monkeypatch):
    """Backward-compat improvement tools should be exposed."""
    monkeypatch.setenv("TOOL_MODE", "detailed")
    reset_settings()
    server = _create_server()
    tools = _get_tool_names(server)
    assert "mcp_suggest_improvement" in tools
    assert "mcp_list_improvements" in tools
    assert "mcp_approve_improvement" in tools


@pytest.mark.asyncio
async def test_improvement_tools_behavior_with_pending_insights(tmp_path, monkeypatch):
    """Improvement tools should list/suggest/approve pending insights."""
    connections_dir = tmp_path / "connections"
    connection_name = "default"
    connection_path = connections_dir / connection_name
    _write_sql_connector(connection_path)

    monkeypatch.setenv("CONNECTIONS_DIR", str(connections_dir))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    store = InsightStore(
        insights=[
            Insight(
                id="info-1",
                category="knowledge",
                severity="info",
                title="Info insight",
                summary="Low-priority insight",
                detected_at=100.0,
            ),
            Insight(
                id="action-1",
                category="pattern",
                severity="action",
                title="Action insight",
                summary="High-priority insight",
                detected_at=200.0,
            ),
        ]
    )
    save_insights(connection_path, store)

    server = _create_server()
    async with Client(server) as client:
        listed = (
            await client.call_tool("mcp_list_improvements", {"connection": connection_name})
        ).data
        listed_payload = _tool_payload(listed)
        assert listed_payload["count"] == 2
        assert {i["id"] for i in listed_payload["improvements"]} == {"info-1", "action-1"}

        suggested = (
            await client.call_tool("mcp_suggest_improvement", {"connection": connection_name})
        ).data
        suggested_payload = _tool_payload(suggested)
        assert suggested_payload["status"] == "ok"
        assert suggested_payload["improvement"]["id"] == "action-1"

        approved = (
            await client.call_tool(
                "mcp_approve_improvement",
                {"improvement_id": "action-1", "connection": connection_name},
            )
        ).data
        approved_payload = _tool_payload(approved)
        assert approved_payload["status"] == "approved"
        assert approved_payload["remaining"] == 1

    # Persisted state should reflect approval (dismissed insight no longer pending).
    remaining_ids = {i.id for i in load_insights(connection_path).pending()}
    assert remaining_ids == {"info-1"}


@pytest.mark.asyncio
async def test_mcp_suggest_improvement_returns_none_when_empty(tmp_path, monkeypatch):
    """Suggest improvement should return status=none when no pending insights exist."""
    connections_dir = tmp_path / "connections"
    connection_name = "default"
    connection_path = connections_dir / connection_name
    _write_sql_connector(connection_path)

    monkeypatch.setenv("CONNECTIONS_DIR", str(connections_dir))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()
    save_insights(connection_path, InsightStore(insights=[]))

    server = _create_server()
    async with Client(server) as client:
        result = (
            await client.call_tool("mcp_suggest_improvement", {"connection": connection_name})
        ).data
        payload = _tool_payload(result)
        assert payload == {"status": "none", "improvement": None}


@pytest.mark.asyncio
async def test_improvement_tools_accept_connection_argument(tmp_path, monkeypatch):
    """Improvement tools should route by explicit connection when provided."""
    connections_dir = tmp_path / "connections"
    one_path = connections_dir / "one"
    two_path = connections_dir / "two"
    _write_sql_connector(one_path)
    _write_sql_connector(two_path)

    # Make directories discoverable as connections.
    (one_path / "state.yaml").write_text("phase: schema\n")
    (two_path / "state.yaml").write_text("phase: schema\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(connections_dir))
    monkeypatch.setenv("CONNECTION_NAME", "one")
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    save_insights(
        one_path,
        InsightStore(
            insights=[
                Insight(
                    id="one-1",
                    category="pattern",
                    severity="info",
                    title="One",
                    summary="One summary",
                    detected_at=100.0,
                )
            ]
        ),
    )
    save_insights(
        two_path,
        InsightStore(
            insights=[
                Insight(
                    id="two-1",
                    category="pattern",
                    severity="action",
                    title="Two",
                    summary="Two summary",
                    detected_at=200.0,
                )
            ]
        ),
    )

    try:
        server = _create_server()
        async with Client(server) as client:
            listed = (await client.call_tool("mcp_list_improvements", {"connection": "two"})).data
            listed_payload = _tool_payload(listed)
            assert listed_payload["count"] == 1
            assert listed_payload["improvements"][0]["id"] == "two-1"

            suggested = (
                await client.call_tool("mcp_suggest_improvement", {"connection": "two"})
            ).data
            suggested_payload = _tool_payload(suggested)
            assert suggested_payload["improvement"]["id"] == "two-1"

            approved = (
                await client.call_tool(
                    "mcp_approve_improvement",
                    {"improvement_id": "two-1", "connection": "two"},
                )
            ).data
            approved_payload = _tool_payload(approved)
            assert approved_payload["status"] == "approved"
    finally:
        ConnectionRegistry.reset()

    assert [i.id for i in load_insights(two_path).pending()] == []
    assert [i.id for i in load_insights(one_path).pending()] == ["one-1"]


@pytest.mark.asyncio
async def test_get_config_accepts_connection_argument(tmp_path):
    """get_config should accept optional connection for multi-connection clients."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_registry.get_connection_path.return_value = tmp_path
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "detailed"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "default"
        mock_settings.return_value.database_url = ""

        server = _create_server()
        async with Client(server) as client:
            result = (await client.call_tool("get_config", {"connection": "test"})).data
            payload = _tool_payload(result)

    assert payload["connection"] == "test"
    assert payload["connection_path"] == str(tmp_path)
    mock_registry.get_connection_path.assert_called_with("test")


@pytest.mark.asyncio
async def test_get_config_database_configured_from_resolved_connection(tmp_path):
    """get_config should derive database_configured from the selected connection connector."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    mock_connector = MagicMock()
    mock_connector.config.database_url = "trino://user:pass@host:8443/catalog/schema"

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_registry.get_connection_path.return_value = tmp_path
        mock_registry.get_connector.return_value = mock_connector
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "detailed"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "default"
        mock_settings.return_value.database_url = ""

        server = _create_server()
        async with Client(server) as client:
            result = (await client.call_tool("get_config", {"connection": "test"})).data
            payload = _tool_payload(result)

    assert payload["database_configured"] is True
    mock_registry.get_connector.assert_called_with("test")


@pytest.mark.asyncio
async def test_ping_database_configured_from_default_connection(tmp_path):
    """ping should derive database_configured from the default connection connector."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql"}))
    conn_info = ConnectionInfo(
        name="default", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    mock_connector = MagicMock()
    mock_connector.config.database_url = "trino://user:pass@host:8443/catalog/schema"

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"default": conn_info}
        mock_registry.get_connection_path.return_value = tmp_path
        mock_registry.get_connector.return_value = mock_connector
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "detailed"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "default"
        mock_settings.return_value.database_url = ""

        server = _create_server()
        async with Client(server) as client:
            result = (await client.call_tool("ping", {})).data
            payload = _tool_payload(result)

    assert payload["database_configured"] is True
    mock_registry.get_connector.assert_called_with("default")


class TestConnectorTypeToolGating:
    """Tools should be registered based on connector type (sql/api/file)."""

    def test_sql_connector_exposes_sql_tools(self, tmp_path):
        """Default (SQL) connector should have run_sql, validate_sql, etc."""
        connector_yaml = tmp_path / "connector.yaml"
        connector_yaml.write_text(yaml.dump({"type": "sql"}))
        conn_info = ConnectionInfo(
            name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
        )

        with (
            patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
            patch("db_mcp.server.get_settings") as mock_settings,
        ):
            mock_registry = MagicMock()
            mock_registry.discover.return_value = {"test": conn_info}
            mock_reg_cls.get_instance.return_value = mock_registry
            mock_settings.return_value.tool_mode = "detailed"
            mock_settings.return_value.auth0_enabled = False
            mock_settings.return_value.auth0_domain = ""
            server = _create_server()

        tools = _get_tool_names(server)
        assert "run_sql" in tools
        assert "validate_sql" in tools
        assert "list_tables" in tools
        assert "describe_table" in tools

    def test_sql_connector_hides_api_tools(self, tmp_path):
        """SQL connector should NOT expose api_query, api_describe_endpoint."""
        connector_yaml = tmp_path / "connector.yaml"
        connector_yaml.write_text(yaml.dump({"type": "sql"}))
        conn_info = ConnectionInfo(
            name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
        )

        with (
            patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
            patch("db_mcp.server.get_settings") as mock_settings,
        ):
            mock_registry = MagicMock()
            mock_registry.discover.return_value = {"test": conn_info}
            mock_reg_cls.get_instance.return_value = mock_registry
            mock_settings.return_value.tool_mode = "detailed"
            mock_settings.return_value.auth0_enabled = False
            mock_settings.return_value.auth0_domain = ""
            server = _create_server()

        tools = _get_tool_names(server)
        assert "api_query" not in tools
        assert "api_describe_endpoint" not in tools
        assert "api_discover" not in tools

    def test_api_connector_hides_sql_tools(self, tmp_path):
        """API connector should NOT expose run_sql, validate_sql, get_result."""
        connector_yaml = tmp_path / "connector.yaml"
        connector_yaml.write_text(yaml.dump({"type": "api", "base_url": "https://example.com"}))
        conn_info = ConnectionInfo(
            name="test", path=tmp_path, type="api", dialect="", description="", is_default=True
        )

        with (
            patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
            patch("db_mcp.server.get_settings") as mock_settings,
        ):
            mock_registry = MagicMock()
            mock_registry.discover.return_value = {"test": conn_info}
            mock_reg_cls.get_instance.return_value = mock_registry
            mock_settings.return_value.tool_mode = "detailed"
            mock_settings.return_value.auth0_enabled = False
            mock_settings.return_value.auth0_domain = ""
            server = _create_server()

        tools = _get_tool_names(server)
        # SQL-specific execution tools are hidden for pure API connectors
        assert "run_sql" not in tools
        assert "validate_sql" not in tools
        assert "get_result" not in tools

    def test_api_connector_with_sql_capabilities_exposes_run_sql(self, tmp_path):
        """SQL-like API connector should expose api_execute_sql but hide validate_sql."""
        connector_yaml = tmp_path / "connector.yaml"
        connector_yaml.write_text(
            yaml.dump(
                {
                    "type": "api",
                    "base_url": "https://example.com",
                    "capabilities": {
                        "supports_sql": True,
                        "supports_validate_sql": False,
                        "supports_async_jobs": False,
                    },
                }
            )
        )
        conn_info = ConnectionInfo(
            name="test", path=tmp_path, type="api", dialect="", description="", is_default=True
        )

        with (
            patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
            patch("db_mcp.server.get_settings") as mock_settings,
        ):
            mock_registry = MagicMock()
            mock_registry.discover.return_value = {"test": conn_info}
            mock_reg_cls.get_instance.return_value = mock_registry
            mock_settings.return_value.tool_mode = "detailed"
            mock_settings.return_value.auth0_enabled = False
            mock_settings.return_value.auth0_domain = ""
            server = _create_server()

        tools = _get_tool_names(server)
        # API+SQL connectors expose api_execute_sql (not run_sql) and hide validate_sql
        assert "api_execute_sql" in tools
        assert "run_sql" not in tools
        assert "validate_sql" not in tools
        assert "get_result" not in tools
        assert "list_tables" in tools
        assert "describe_table" in tools

    def test_api_connector_with_legacy_sql_capability_key_exposes_api_execute_sql(self, tmp_path):
        """Legacy `capabilities.sql: true` should still enable SQL-like API tooling."""
        connector_yaml = tmp_path / "connector.yaml"
        connector_yaml.write_text(
            yaml.dump(
                {
                    "type": "api",
                    "base_url": "https://example.com",
                    "capabilities": {
                        "sql": True,
                        "supports_validate_sql": False,
                    },
                }
            )
        )
        conn_info = ConnectionInfo(
            name="test", path=tmp_path, type="api", dialect="", description="", is_default=True
        )

        with (
            patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
            patch("db_mcp.server.get_settings") as mock_settings,
        ):
            mock_registry = MagicMock()
            mock_registry.discover.return_value = {"test": conn_info}
            mock_reg_cls.get_instance.return_value = mock_registry
            mock_settings.return_value.tool_mode = "detailed"
            mock_settings.return_value.auth0_enabled = False
            mock_settings.return_value.auth0_domain = ""
            server = _create_server()

        tools = _get_tool_names(server)
        assert "api_execute_sql" in tools

    def test_api_connector_exposes_api_tools(self, tmp_path):
        """API connector should expose api_query, api_describe_endpoint, api_discover."""
        connector_yaml = tmp_path / "connector.yaml"
        connector_yaml.write_text(yaml.dump({"type": "api", "base_url": "https://example.com"}))
        conn_info = ConnectionInfo(
            name="test", path=tmp_path, type="api", dialect="", description="", is_default=True
        )

        with (
            patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
            patch("db_mcp.server.get_settings") as mock_settings,
        ):
            mock_registry = MagicMock()
            mock_registry.discover.return_value = {"test": conn_info}
            mock_reg_cls.get_instance.return_value = mock_registry
            mock_settings.return_value.tool_mode = "detailed"
            mock_settings.return_value.auth0_enabled = False
            mock_settings.return_value.auth0_domain = ""
            server = _create_server()

        tools = _get_tool_names(server)
        assert "api_query" in tools
        assert "api_describe_endpoint" in tools
        assert "api_discover" in tools

    def test_api_connector_keeps_common_tools(self, tmp_path):
        """API connector should still have shell, protocol, onboarding tools."""
        connector_yaml = tmp_path / "connector.yaml"
        connector_yaml.write_text(yaml.dump({"type": "api", "base_url": "https://example.com"}))

        with patch("db_mcp.server.get_settings") as mock_settings:
            mock_settings.return_value.tool_mode = "detailed"
            mock_settings.return_value.get_effective_connection_path.return_value = tmp_path
            mock_settings.return_value.connection_name = "test"
            mock_settings.return_value.database_url = ""
            mock_settings.return_value.auth0_enabled = False
            mock_settings.return_value.auth0_domain = ""
            server = _create_server()

        tools = _get_tool_names(server)
        assert "ping" in tools
        assert "shell" in tools
        assert "protocol" in tools
        assert "mcp_setup_status" in tools
        assert "mcp_domain_generate" in tools


def test_shell_auto_profile_reduces_tool_surface(tmp_path):
    """Shell mode + auto profile should expose only query-focused tools."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql", "database_url": "sqlite:///tmp/test.db"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "shell"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "test"

        server = _create_server()

    tools = _get_tool_names(server)
    assert "shell" in tools
    assert "protocol" in tools
    assert "run_sql" in tools
    assert "validate_sql" in tools
    assert "search_tools" in tools
    assert "export_tool_sdk" in tools
    assert "mcp_setup_status" not in tools
    assert "mcp_suggest_improvement" not in tools
    assert "list_tables" not in tools


def test_detailed_query_profile_reduces_tool_surface(tmp_path):
    """Detailed mode can still force a smaller query profile."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql", "database_url": "sqlite:///tmp/test.db"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "detailed"
        mock_settings.return_value.tool_profile = "query"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "test"

        server = _create_server()

    tools = _get_tool_names(server)
    assert "run_sql" in tools
    assert "validate_sql" in tools
    assert "search_tools" in tools
    assert "export_tool_sdk" in tools
    assert "mcp_setup_status" not in tools
    assert "mcp_suggest_improvement" not in tools
    assert "list_tables" not in tools


def test_shell_full_profile_keeps_admin_tools(tmp_path):
    """Shell mode can opt back into full profile when needed."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql", "database_url": "sqlite:///tmp/test.db"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "shell"
        mock_settings.return_value.tool_profile = "full"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "test"

        server = _create_server()

    tools = _get_tool_names(server)
    assert "mcp_setup_status" in tools
    assert "mcp_suggest_improvement" in tools
    assert "search_tools" in tools
    assert "export_tool_sdk" in tools
    # Detailed-only helper tools remain off in shell mode.
    assert "list_tables" not in tools


def test_exec_only_mode_exposes_only_exec_tool(tmp_path):
    """Exec-only mode should register exactly one MCP tool."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql", "database_url": "sqlite:///tmp/test.db"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "exec-only"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "test"

        server = _create_server()

    assert _get_tool_names(server) == {"exec"}


def test_code_mode_exposes_only_code_tool(tmp_path):
    """Code mode should register exactly one MCP tool."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql", "database_url": "sqlite:///tmp/test.db"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "code"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "test"

        server = _create_server()

    assert _get_tool_names(server) == {"code"}


def test_daemon_mode_exposes_only_task_tools(tmp_path):
    """Daemon mode should expose only the executor-like task surface."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql", "database_url": "sqlite:///tmp/test.db"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_reg_cls.get_instance.return_value = mock_registry

        mock_settings.return_value.tool_mode = "daemon"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "test"

        server = _create_server()

    assert _get_tool_names(server) == {"prepare_task", "execute_task"}


@pytest.mark.asyncio
async def test_daemon_mode_prepare_and_execute_task(tmp_path, monkeypatch):
    """Daemon mode should prepare compact context and execute SQL by task id."""
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    db_path = tmp_path / "daemon.sqlite"
    _write_sql_connector(connection_path)
    (connection_path / "connector.yaml").write_text(
        yaml.dump({"type": "sql", "database_url": f"sqlite:///{db_path}"})
    )
    (connection_path / "PROTOCOL.md").write_text("Read protocol first.\n")
    (connection_path / "domain").mkdir(parents=True, exist_ok=True)
    (connection_path / "domain" / "model.md").write_text(
        "# Revenue\nCustomers live in the Customer table.\n"
    )
    (connection_path / "instructions").mkdir(parents=True, exist_ok=True)
    (connection_path / "instructions" / "business_rules.yaml").write_text(
        yaml.dump({"rules": ["Customer counts should use the Customer table."]})
    )
    (connection_path / "schema").mkdir(parents=True, exist_ok=True)
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.dump(
            {
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "Customer",
                        "schema": "main",
                        "full_name": "main.Customer",
                        "description": "Customer records",
                        "columns": [
                            {"name": "CustomerId", "type": "INTEGER"},
                            {"name": "Country", "type": "TEXT"},
                        ],
                    }
                ],
            }
        )
    )
    (connection_path / "examples").mkdir(parents=True, exist_ok=True)
    (connection_path / "examples" / "count_customers.yaml").write_text(
        yaml.dump(
            {
                "intent": "How many customers are there?",
                "sql": "SELECT COUNT(*) AS answer FROM Customer",
                "tables": ["Customer"],
                "keywords": ["count", "customers"],
            }
        )
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.setenv("TOOL_MODE", "daemon")
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    server = _create_server()
    async with Client(server) as client:
        prepared = (
            await client.call_tool(
                "prepare_task",
                {"question": "How many customers are there?", "connection": connection_name},
            )
        ).data
        prepared_payload = _tool_payload(prepared)
        assert prepared_payload["status"] == "context_ready"
        assert prepared_payload["connection"] == connection_name
        assert "suggested_sql" not in prepared_payload["context"]
        assert prepared_payload["context"]["candidate_tables"][0]["identifier"] == "main.Customer"
        assert prepared_payload["context"]["examples"][0]["sql"] == (
            "SELECT COUNT(*) AS answer FROM Customer"
        )
        assert prepared_payload["context"]["disambiguation"]["ambiguous"] is False
        assert prepared_payload["observability"]["timed_out"] is False
        assert prepared_payload["observability"]["context_profile"] == "compact"
        task_id = prepared_payload["task_id"]

        executed = (
            await client.call_tool(
                "execute_task",
                {"task_id": task_id, "sql": "SELECT 1 AS answer"},
            )
        ).data
        executed_payload = _tool_payload(executed)
        assert executed_payload["status"] == "completed"
        assert executed_payload["execution"]["status"] == "success"
        assert executed_payload["execution"]["data"] == [{"answer": 1}]
        assert executed_payload["observability"]["timed_out"] is False
        assert executed_payload["observability"]["inline_resolution_attempts"] == 0


@pytest.mark.asyncio
async def test_daemon_execute_task_resolves_async_read_inline(monkeypatch):
    """execute_task should inline-poll async read executions to a final result."""
    daemon_tasks._TASKS.clear()
    daemon_tasks._register_task(
        daemon_tasks.PreparedTask(
            task_id="task-123",
            connection="demo",
            question="What is the symbol?",
            context={},
        )
    )

    async def fake_validate_sql(*args, **kwargs):
        return {
            "valid": True,
            "query_id": "query-123",
            "is_write": False,
            "write_confirmation_required": False,
        }

    async def fake_run_sql(*args, **kwargs):
        return {
            "status": "submitted",
            "query_id": "exec-123",
            "execution_id": "exec-123",
            "state": "running",
            "is_write": False,
        }

    poll_calls = {"count": 0}

    async def fake_get_result(query_id: str, connection: str):
        assert query_id == "exec-123"
        assert connection == "demo"
        poll_calls["count"] += 1
        if poll_calls["count"] == 1:
            return {"status": "running", "query_id": query_id, "execution_id": query_id}
        return {
            "status": "complete",
            "query_id": query_id,
            "execution_id": query_id,
            "data": [{"symbol": "SOL"}],
            "columns": ["symbol"],
            "rows_returned": 1,
        }

    monkeypatch.setattr(daemon_tasks, "_validate_sql", fake_validate_sql)
    monkeypatch.setattr(daemon_tasks, "_run_sql", fake_run_sql)
    monkeypatch.setattr(daemon_tasks, "_get_result", fake_get_result, raising=False)
    monkeypatch.setattr(daemon_tasks, "_INLINE_RESULT_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(daemon_tasks, "_INLINE_RESULT_POLL_SECONDS", 0.01)

    payload = await daemon_tasks._execute_task(task_id="task-123", sql="SELECT 'SOL' AS symbol")

    assert payload["status"] == "completed"
    assert payload["execution"]["status"] == "success"
    assert payload["execution"]["data"] == [{"symbol": "SOL"}]
    assert poll_calls["count"] == 2
    assert payload["observability"]["inline_resolution_attempts"] == 2


@pytest.mark.asyncio
async def test_daemon_prepare_task_expands_ambiguous_context_and_supports_refinement(
    tmp_path, monkeypatch
):
    """prepare_task should expand context and expose disambiguation for ambiguous queries."""
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("Read protocol first.\n")
    (connection_path / "domain").mkdir(parents=True, exist_ok=True)
    (connection_path / "domain" / "model.md").write_text(
        "\n\n".join(
            [
                "Helium Mobile traffic metrics must come from helium_mobile_traffic.",
                "Brownfield traffic uses operator_type = 'brownfield'.",
                "Do not answer Helium Mobile traffic questions from total network traffic tables.",
                "Rewarded traffic must exclude non_rewarded_bytes.",
            ]
        )
    )
    (connection_path / "instructions").mkdir(parents=True, exist_ok=True)
    (connection_path / "instructions" / "business_rules.yaml").write_text(
        yaml.dump(
            {
                "rules": [
                    "Helium Mobile traffic questions should use helium_mobile_traffic.",
                    "Brownfield traffic requires filtering operator_type = brownfield.",
                    "Do not use network_traffic for Helium Mobile subscriber traffic.",
                ]
            }
        )
    )
    (connection_path / "instructions" / "sql_rules.md").write_text(
        "\n\n".join(
            [
                "When multiple traffic tables exist, prefer the most specific product table.",
                "Apply rewarded_bytes filters before aggregation.",
                "Brownfield queries must filter operator_type = 'brownfield'.",
            ]
        )
    )
    (connection_path / "schema").mkdir(parents=True, exist_ok=True)
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.dump(
            {
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "helium_mobile_traffic",
                        "schema": "main",
                        "full_name": "main.helium_mobile_traffic",
                        "description": "Helium Mobile rewarded subscriber traffic by operator",
                        "columns": [
                            {"name": "operator_type", "type": "TEXT"},
                            {"name": "rewarded_bytes", "type": "BIGINT"},
                            {"name": "traffic_date", "type": "DATE"},
                        ],
                    },
                    {
                        "name": "network_traffic",
                        "schema": "main",
                        "full_name": "main.network_traffic",
                        "description": "Total network traffic including non-rewarded traffic",
                        "columns": [
                            {"name": "operator_type", "type": "TEXT"},
                            {"name": "total_bytes", "type": "BIGINT"},
                            {"name": "non_rewarded_bytes", "type": "BIGINT"},
                        ],
                    },
                ],
            }
        )
    )
    (connection_path / "examples").mkdir(parents=True, exist_ok=True)
    (connection_path / "examples" / "helium_mobile_brownfield.yaml").write_text(
        yaml.dump(
            {
                "intent": "How much Helium Mobile brownfield traffic was there?",
                "sql": (
                    "SELECT SUM(rewarded_bytes) FROM helium_mobile_traffic "
                    "WHERE operator_type = 'brownfield'"
                ),
                "tables": ["helium_mobile_traffic"],
                "keywords": ["helium mobile", "brownfield", "rewarded traffic"],
                "notes": "Use the Helium Mobile-specific traffic table.",
            }
        )
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.setenv("TOOL_MODE", "daemon")
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    server = _create_server()
    async with Client(server) as client:
        prepared = (
            await client.call_tool(
                "prepare_task",
                {
                    "question": "How much Helium Mobile brownfield traffic was there?",
                    "connection": connection_name,
                    "context": {
                        "previous_sql": "SELECT SUM(total_bytes) FROM network_traffic",
                        "error": "Used the wrong traffic source and forgot the brownfield filter.",
                        "avoid_tables": ["main.network_traffic"],
                        "must_apply_filters": ["operator_type = 'brownfield'"],
                    },
                },
            )
        ).data
        prepared_payload = _tool_payload(prepared)

    assert prepared_payload["status"] == "context_ready"
    assert prepared_payload["observability"]["context_profile"] == "expanded"
    assert "suggested_sql" not in prepared_payload["context"]
    disambiguation = prepared_payload["context"]["disambiguation"]
    assert disambiguation["ambiguous"] is True
    assert disambiguation["recommended_tables"][0]["identifier"] == "main.helium_mobile_traffic"
    assert any(
        table["identifier"] == "main.network_traffic"
        for table in disambiguation["competing_tables"]
    )
    assert disambiguation["avoid_tables"] == ["main.network_traffic"]
    assert "operator_type = 'brownfield'" in disambiguation["must_apply_filters"]
    assert prepared_payload["context"]["examples"][0]["tables"] == ["helium_mobile_traffic"]
    assert len(prepared_payload["context"]["candidate_tables"]) == 2
    assert len(prepared_payload["context"]["rules"]) >= 3
    assert "Rewarded traffic must exclude non_rewarded_bytes." in (
        prepared_payload["context"]["domain_context"]
    )
    assert "Do not use network_traffic for Helium Mobile subscriber traffic." in (
        prepared_payload["context"]["business_rules_context"]
    )


@pytest.mark.asyncio
async def test_daemon_prepare_task_uses_decision_hints_and_lean_context_in_compact_mode(
    tmp_path, monkeypatch
):
    """Compact daemon context should prioritize decision hints over raw full-context dumps."""
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("Read protocol first.\n")
    (connection_path / "domain").mkdir(parents=True, exist_ok=True)
    (connection_path / "domain" / "model.md").write_text(
        "\n\n".join(
            [
                "Customer revenue lives in revenue_facts.",
                "Revenue should never come from activity_rollups.",
                "Use daily snapshots for revenue period questions.",
                "Final domain note that would be cropped by excerpt-based selection.",
            ]
        )
    )
    (connection_path / "instructions").mkdir(parents=True, exist_ok=True)
    (connection_path / "instructions" / "business_rules.yaml").write_text(
        "\n".join(
            [
                "rules:",
                '  - "Use revenue_facts for revenue totals."',
                '  - "Do not use activity_rollups for revenue totals."',
                '  - "Apply snapshot_date for period-end questions."',
                '  - "Final business rule that must remain visible in compact mode."',
            ]
        )
        + "\n"
    )
    (connection_path / "instructions" / "sql_rules.md").write_text(
        "\n\n".join(
            [
                "Use binary units when the business rules say so.",
                "Date windows are inclusive unless otherwise specified.",
                "Prefer the most specific fact table available.",
            ]
        )
    )
    (connection_path / "schema").mkdir(parents=True, exist_ok=True)
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.dump(
            {
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "revenue_facts",
                        "schema": "main",
                        "full_name": "main.revenue_facts",
                        "description": "Revenue fact table",
                        "columns": [
                            {"name": "snapshot_date", "type": "DATE"},
                            {"name": "revenue_amount", "type": "DOUBLE"},
                        ],
                    },
                    {
                        "name": "activity_rollups",
                        "schema": "main",
                        "full_name": "main.activity_rollups",
                        "description": "Secondary activity rollup table",
                        "columns": [
                            {"name": "activity_date", "type": "DATE"},
                            {"name": "activity_total", "type": "DOUBLE"},
                        ],
                    }
                ],
            }
        )
    )
    (connection_path / "examples").mkdir(parents=True, exist_ok=True)
    (connection_path / "examples" / "revenue_total.yaml").write_text(
        yaml.dump(
            {
                "intent": "What was revenue yesterday?",
                "sql": "SELECT SUM(revenue_amount) FROM revenue_facts",
                "tables": ["revenue_facts"],
                "keywords": ["revenue", "total"],
            }
        )
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.setenv("TOOL_MODE", "daemon")
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    server = _create_server()
    async with Client(server) as client:
        prepared = (
            await client.call_tool(
                "prepare_task",
                {"question": "What was total revenue?", "connection": connection_name},
            )
        ).data
        prepared_payload = _tool_payload(prepared)

    assert prepared_payload["status"] == "context_ready"
    assert prepared_payload["observability"]["context_profile"] == "compact"
    assert "full_schema" not in prepared_payload["context"]
    assert "decision_hints" in prepared_payload["context"]
    assert "must_follow_rules" in prepared_payload["context"]["decision_hints"]
    assert "Use revenue_facts for revenue totals." in (
        prepared_payload["context"]["decision_hints"]["must_follow_rules"]
    )
    assert any(
        "activity_rollups" in rule
        for rule in prepared_payload["context"]["decision_hints"]["anti_patterns"]
    )
    assert prepared_payload["context"]["decision_hints"]["preferred_tables"] == [
        "main.revenue_facts"
    ]
    assert "Final domain note that would be cropped by excerpt-based selection." not in str(
        prepared_payload["context"].get("domain_context")
    )
    assert "Final business rule that must remain visible in compact mode." not in str(
        prepared_payload["context"].get("business_rules_context")
    )


@pytest.mark.asyncio
async def test_daemon_prepare_task_orders_semantic_guidance_before_schema_context(
    tmp_path, monkeypatch
):
    """Daemon context should emit rules and disambiguation before schema-heavy fields."""
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("Read protocol first.\n")
    (connection_path / "domain").mkdir(parents=True, exist_ok=True)
    (connection_path / "domain" / "model.md").write_text(
        "Use helium facts for helium questions.\nDo not use generic traffic totals.\n"
    )
    (connection_path / "instructions").mkdir(parents=True, exist_ok=True)
    (connection_path / "instructions" / "business_rules.yaml").write_text(
        "\n".join(
            [
                "rules:",
                '  - "Use wifi_total_bytes for Helium network traffic totals."',
                '  - "Do not use wifi_traffic_total for Helium network traffic totals."',
            ]
        )
        + "\n"
    )
    (connection_path / "instructions" / "sql_rules.md").write_text(
        "Use binary units for Tb/Gb reporting.\n"
    )
    (connection_path / "schema").mkdir(parents=True, exist_ok=True)
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.dump(
            {
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "daily_stats_cdrs",
                        "schema": "main",
                        "full_name": "main.daily_stats_cdrs",
                        "description": "Daily network stats",
                        "columns": [
                            {"name": "wifi_total_bytes", "type": "BIGINT"},
                            {"name": "wifi_traffic_total", "type": "BIGINT"},
                        ],
                    }
                ],
            }
        )
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.setenv("TOOL_MODE", "daemon")
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    server = _create_server()
    async with Client(server) as client:
        prepared = (
            await client.call_tool(
                "prepare_task",
                {
                    "question": "What was total Helium network traffic on 2026-03-01?",
                    "connection": connection_name,
                },
            )
        ).data
        prepared_payload = _tool_payload(prepared)

    context_keys = list(prepared_payload["context"].keys())
    assert context_keys.index("disambiguation") < context_keys.index("candidate_tables")
    assert context_keys.index("decision_hints") < context_keys.index("candidate_tables")
    assert context_keys.index("business_rules_context") < context_keys.index("candidate_tables")
    assert context_keys.index("domain_context") < context_keys.index("candidate_tables")
    assert context_keys.index("sql_rules_context") < context_keys.index("candidate_tables")
    assert context_keys.index("examples") < context_keys.index("candidate_tables")
    assert "full_schema" not in context_keys


@pytest.mark.asyncio
async def test_daemon_prepare_task_includes_semantic_intent_preview_when_metric_matches(
    tmp_path, monkeypatch
):
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("Read protocol first.\n")
    (connection_path / "domain").mkdir(parents=True, exist_ok=True)
    (connection_path / "domain" / "model.md").write_text(
        "Revenue questions map to revenue facts.\n"
    )
    (connection_path / "instructions").mkdir(parents=True, exist_ok=True)
    (connection_path / "instructions" / "business_rules.yaml").write_text("rules: []\n")
    (connection_path / "instructions" / "sql_rules.md").write_text(
        "Use approved metrics when available.\n"
    )
    (connection_path / "schema").mkdir(parents=True, exist_ok=True)
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.dump(
            {
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "revenue_facts",
                        "schema": "main",
                        "full_name": "main.revenue_facts",
                        "description": "Revenue fact table",
                        "columns": [
                            {"name": "revenue_amount", "type": "DOUBLE"},
                        ],
                    }
                ],
            }
        )
    )
    (connection_path / "metrics").mkdir(parents=True, exist_ok=True)
    (connection_path / "metrics" / "catalog.yaml").write_text(
        yaml.dump(
            {
                "version": "1.0.0",
                "provider_id": connection_name,
                "metrics": [
                    {
                        "name": "revenue",
                        "display_name": "revenue",
                        "description": "Total revenue",
                        "dimensions": [],
                        "status": "approved",
                    }
                ],
            }
        )
    )
    (connection_path / "metrics" / "bindings.yaml").write_text(
        yaml.dump(
            {
                "version": "1.0.0",
                "provider_id": connection_name,
                "bindings": {
                    "revenue": {
                        "metric_name": "revenue",
                        "sql": "SELECT SUM(revenue_amount) AS answer FROM revenue_facts",
                        "tables": ["revenue_facts"],
                        "dimensions": {},
                    }
                },
            }
        )
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.setenv("TOOL_MODE", "daemon")
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    server = _create_server()
    async with Client(server) as client:
        prepared = (
            await client.call_tool(
                "prepare_task",
                {"question": "Show revenue", "connection": connection_name},
            )
        ).data
        prepared_payload = _tool_payload(prepared)

    semantic_intent = prepared_payload["context"]["semantic_intent"]
    assert semantic_intent["status"] == "ready"
    assert semantic_intent["meta_query"]["measures"][0]["metric_name"] == "revenue"
    assert semantic_intent["resolved_plan"]["sql"] == (
        "SELECT SUM(revenue_amount) AS answer FROM revenue_facts"
    )
    assert semantic_intent["confidence"]["semantic"] > 0.0


@pytest.mark.asyncio
async def test_daemon_prepare_task_includes_full_context_only_for_expanded_refinement(
    tmp_path, monkeypatch
):
    """Expanded refinement context should unlock fuller raw guidance and schema detail."""
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("Read protocol first.\n")
    (connection_path / "domain").mkdir(parents=True, exist_ok=True)
    (connection_path / "domain" / "model.md").write_text(
        "\n\n".join(
            [
                "Revenue metrics live in revenue_facts.",
                "Use snapshot_date for period-end revenue.",
                "Do not use activity_rollups for revenue totals.",
                "Long tail context that should only appear in expanded refinement mode.",
            ]
        )
    )
    (connection_path / "instructions").mkdir(parents=True, exist_ok=True)
    (connection_path / "instructions" / "business_rules.yaml").write_text(
        "\n".join(
            [
                "rules:",
                '  - "Use revenue_facts for revenue totals."',
                '  - "Do not use activity_rollups for revenue totals."',
                '  - "Use snapshot_date for period-end questions."',
                '  - "Long tail rule that should only appear in expanded refinement mode."',
            ]
        )
        + "\n"
    )
    (connection_path / "instructions" / "sql_rules.md").write_text(
        "\n\n".join(
            [
                "Use binary units when business rules require them.",
                "Period ending on a date is inclusive.",
            ]
        )
    )
    (connection_path / "schema").mkdir(parents=True, exist_ok=True)
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.dump(
            {
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "revenue_facts",
                        "schema": "main",
                        "full_name": "main.revenue_facts",
                        "description": "Revenue fact table",
                        "columns": [
                            {"name": "snapshot_date", "type": "DATE"},
                            {"name": "revenue_amount", "type": "DOUBLE"},
                        ],
                    },
                    {
                        "name": "activity_rollups",
                        "schema": "main",
                        "full_name": "main.activity_rollups",
                        "description": "Secondary activity rollup table",
                        "columns": [
                            {"name": "activity_date", "type": "DATE"},
                            {"name": "activity_total", "type": "DOUBLE"},
                        ],
                    },
                ],
            }
        )
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.setenv("TOOL_MODE", "daemon")
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    server = _create_server()
    async with Client(server) as client:
        prepared = (
            await client.call_tool(
                "prepare_task",
                {
                    "question": "What was total revenue at period end?",
                    "connection": connection_name,
                    "context": {
                        "previous_sql": "SELECT SUM(activity_total) FROM activity_rollups",
                        "error": "Wrong table for revenue totals.",
                        "avoid_tables": ["main.activity_rollups"],
                    },
                },
            )
        ).data
        prepared_payload = _tool_payload(prepared)

    assert prepared_payload["status"] == "context_ready"
    assert prepared_payload["observability"]["context_profile"] == "expanded"
    assert "Long tail context that should only appear in expanded refinement mode." in (
        prepared_payload["context"]["domain_context"]
    )
    assert "Long tail rule that should only appear in expanded refinement mode." in (
        prepared_payload["context"]["business_rules_context"]
    )
    schema_table_names = {
        table["full_name"] for table in prepared_payload["context"]["full_schema"]["tables"]
    }
    assert schema_table_names == {"main.revenue_facts", "main.activity_rollups"}


@pytest.mark.asyncio
async def test_daemon_prepare_task_returns_timeout_observability(monkeypatch):
    """prepare_task should fail cleanly when context assembly exceeds its deadline."""

    def fake_build_prepare_context(*args, **kwargs):
        import time

        time.sleep(0.05)
        return {}

    monkeypatch.setattr(daemon_tasks, "_build_prepare_context", fake_build_prepare_context)
    monkeypatch.setattr(daemon_tasks, "HostDbMcpRuntime", lambda connection: object())
    monkeypatch.setattr(daemon_tasks, "_resolve_connection_name", lambda connection: "demo")
    monkeypatch.setattr(daemon_tasks, "_PREPARE_TASK_TIMEOUT_SECONDS", 0.01)

    payload = await daemon_tasks._prepare_task(question="slow question", connection="demo")

    assert payload["status"] == "timeout"
    assert payload["observability"]["timed_out"] is True
    assert payload["observability"]["stage"] == "prepare_task"


@pytest.mark.asyncio
async def test_daemon_execute_task_returns_timeout_observability(monkeypatch):
    """execute_task should fail cleanly when execution exceeds its deadline."""
    daemon_tasks._TASKS.clear()
    daemon_tasks._register_task(
        daemon_tasks.PreparedTask(
            task_id="task-timeout",
            connection="demo",
            question="slow query",
            context={},
        )
    )

    async def fake_validate_sql(*args, **kwargs):
        return {"valid": True, "query_id": "query-123", "write_confirmation_required": False}

    async def fake_run_sql(*args, **kwargs):
        await asyncio.sleep(0.05)
        return {"status": "success", "data": [{"answer": 1}]}

    monkeypatch.setattr(daemon_tasks, "_validate_sql", fake_validate_sql)
    monkeypatch.setattr(daemon_tasks, "_run_sql", fake_run_sql)
    monkeypatch.setattr(daemon_tasks, "_EXECUTE_TASK_TIMEOUT_SECONDS", 0.01)

    payload = await daemon_tasks._execute_task(task_id="task-timeout", sql="SELECT 1")

    assert payload["status"] == "timeout"
    assert payload["observability"]["timed_out"] is True
    assert payload["observability"]["stage"] == "execute_task"


@pytest.mark.asyncio
async def test_daemon_mode_prepare_task_serializes_date_values(tmp_path, monkeypatch):
    """prepare_task should normalize YAML date values into JSON-safe strings."""
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("Read protocol first.\n")
    (connection_path / "domain").mkdir(parents=True, exist_ok=True)
    (connection_path / "domain" / "model.md").write_text("Token metadata lives in token_prices.\n")
    (connection_path / "instructions").mkdir(parents=True, exist_ok=True)
    (connection_path / "instructions" / "business_rules.yaml").write_text(
        yaml.dump({"rules": ["Use token metadata for symbol lookups."]})
    )
    (connection_path / "schema").mkdir(parents=True, exist_ok=True)
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.dump(
            {
                "dialect": "sqlite",
                "tables": [
                    {
                        "name": "token_prices",
                        "schema": "main",
                        "full_name": "main.token_prices",
                        "description": "Token metadata snapshots",
                        "columns": [
                            {"name": "block_date", "type": "DATE"},
                            {"name": "symbol", "type": "TEXT"},
                        ],
                    }
                ],
            }
        )
    )
    (connection_path / "examples").mkdir(parents=True, exist_ok=True)
    (connection_path / "examples" / "latest_price.yaml").write_text(
        yaml.dump(
            {
                "intent": "Get the latest SOL price",
                "sql": "SELECT symbol FROM token_prices WHERE block_date = DATE '2026-02-15'",
                "tables": ["token_prices"],
                "keywords": ["latest", date(2026, 2, 15)],
                "notes": "Dates in example metadata should be serialized safely.",
            }
        )
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.setenv("TOOL_MODE", "daemon")
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    server = _create_server()
    async with Client(server) as client:
        prepared = (
            await client.call_tool(
                "prepare_task",
                {"question": "What is the latest SOL price?", "connection": connection_name},
            )
        ).data
        prepared_payload = _tool_payload(prepared)

    assert prepared_payload["status"] == "context_ready"
    assert prepared_payload["context"]["examples"][0]["keywords"] == ["latest", "2026-02-15"]


@pytest.mark.asyncio
async def test_exec_only_mode_exec_tool_routes_command(tmp_path, monkeypatch):
    """Exec-only mode should expose a working exec tool."""
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("read me first\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    fake_manager = MagicMock()
    fake_manager.execute.side_effect = [
        {
            "stdout": "read me first\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
        {
            "stdout": "/workspace\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
    ]

    with (
        patch("db_mcp.server.get_settings") as mock_settings,
        patch("db_mcp.tools.exec.get_exec_session_manager", return_value=fake_manager),
    ):
        mock_settings.return_value.tool_mode = "exec-only"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = connection_name

        server = _create_server()
        async with Client(server) as client:
            await client.call_tool(
                "exec",
                {
                    "connection": connection_name,
                    "command": "cat PROTOCOL.md",
                    "timeout_seconds": 15,
                },
            )
            result = (
                await client.call_tool(
                    "exec",
                    {"connection": connection_name, "command": "pwd", "timeout_seconds": 15},
                )
            ).data
            payload = _tool_payload(result)

    assert payload["stdout"] == "/workspace\n"
    assert fake_manager.execute.call_count == 2


@pytest.mark.asyncio
async def test_exec_only_mode_requires_protocol_read_first(tmp_path, monkeypatch):
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("read me first\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    fake_manager = MagicMock()

    with (
        patch("db_mcp.server.get_settings") as mock_settings,
        patch("db_mcp.tools.exec.get_exec_session_manager", return_value=fake_manager),
    ):
        mock_settings.return_value.tool_mode = "exec-only"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = connection_name

        server = _create_server()
        async with Client(server) as client:
            result = (
                await client.call_tool(
                    "exec",
                    {"connection": connection_name, "command": "pwd", "timeout_seconds": 15},
                )
            ).data
            payload = _tool_payload(result)

    assert payload["exit_code"] == 1
    assert "PROTOCOL.md" in payload["stderr"]
    fake_manager.execute.assert_not_called()


@pytest.mark.asyncio
async def test_exec_only_mode_accepts_protocol_read_and_then_allows_commands(
    tmp_path,
    monkeypatch,
):
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("read me first\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    fake_manager = MagicMock()
    fake_manager.execute.side_effect = [
        {
            "stdout": "read me first\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
        {
            "stdout": "/workspace\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
    ]

    with (
        patch("db_mcp.server.get_settings") as mock_settings,
        patch("db_mcp.tools.exec.get_exec_session_manager", return_value=fake_manager),
    ):
        mock_settings.return_value.tool_mode = "exec-only"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = connection_name

        server = _create_server()
        async with Client(server) as client:
            protocol_result = (
                await client.call_tool(
                    "exec",
                    {
                        "connection": connection_name,
                        "command": "cat PROTOCOL.md",
                        "timeout_seconds": 15,
                    },
                )
            ).data
            protocol_payload = _tool_payload(protocol_result)
            command_result = (
                await client.call_tool(
                    "exec",
                    {"connection": connection_name, "command": "pwd", "timeout_seconds": 15},
                )
            ).data
            command_payload = _tool_payload(command_result)

    assert protocol_payload["exit_code"] == 0
    assert command_payload["stdout"] == "/workspace\n"
    assert fake_manager.execute.call_count == 2


@pytest.mark.asyncio
async def test_exec_only_mode_invalidates_protocol_ack_when_file_changes(tmp_path, monkeypatch):
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    protocol_path = connection_path / "PROTOCOL.md"
    protocol_path.write_text("v1\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    fake_manager = MagicMock()
    fake_manager.execute.return_value = {
        "stdout": "v1\n",
        "stderr": "",
        "exit_code": 0,
        "duration_ms": 10.0,
        "truncated": False,
    }

    with (
        patch("db_mcp.server.get_settings") as mock_settings,
        patch("db_mcp.tools.exec.get_exec_session_manager", return_value=fake_manager),
    ):
        mock_settings.return_value.tool_mode = "exec-only"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = connection_name

        server = _create_server()
        async with Client(server) as client:
            await client.call_tool(
                "exec",
                {
                    "connection": connection_name,
                    "command": "cat PROTOCOL.md",
                    "timeout_seconds": 15,
                },
            )
            protocol_path.write_text("v2\n")
            result = (
                await client.call_tool(
                    "exec",
                    {"connection": connection_name, "command": "pwd", "timeout_seconds": 15},
                )
            ).data
            payload = _tool_payload(result)

    assert payload["exit_code"] == 1
    assert "PROTOCOL.md" in payload["stderr"]


@pytest.mark.asyncio
async def test_code_mode_routes_python_code(tmp_path, monkeypatch):
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("read me first\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    fake_manager = MagicMock()
    fake_manager.execute.side_effect = [
        {
            "stdout": "read me first\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
        {
            "stdout": "[{'name': 'Customer', 'score': 25}]\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
        {
            "stdout": "3\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
    ]

    with (
        patch("db_mcp.server.get_settings") as mock_settings,
        patch("db_mcp.tools.code.get_exec_session_manager", return_value=fake_manager),
    ):
        mock_settings.return_value.tool_mode = "code"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = connection_name

        server = _create_server()
        async with Client(server) as client:
            await client.call_tool(
                "code",
                {
                    "connection": connection_name,
                    "code": "print(dbmcp.read_protocol())",
                    "timeout_seconds": 15,
                },
            )
            await client.call_tool(
                "code",
                {
                    "connection": connection_name,
                    "code": "print(dbmcp.find_tables('customer'))",
                    "timeout_seconds": 15,
                },
            )
            result = (
                await client.call_tool(
                    "code",
                    {
                        "connection": connection_name,
                        "code": "print(dbmcp.scalar('SELECT 3'))",
                        "timeout_seconds": 15,
                    },
                )
            ).data
            payload = _tool_payload(result)

    assert payload["stdout"] == "3\n"
    assert fake_manager.execute.call_count == 3


@pytest.mark.asyncio
async def test_code_mode_requires_protocol_read_first(tmp_path, monkeypatch):
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("read me first\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    fake_manager = MagicMock()

    with (
        patch("db_mcp.server.get_settings") as mock_settings,
        patch("db_mcp.tools.code.get_exec_session_manager", return_value=fake_manager),
    ):
        mock_settings.return_value.tool_mode = "code"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = connection_name

        server = _create_server()
        async with Client(server) as client:
            result = (
                await client.call_tool(
                    "code",
                    {
                        "connection": connection_name,
                        "code": "print(dbmcp.scalar('SELECT 1'))",
                        "timeout_seconds": 15,
                    },
                )
            ).data
            payload = _tool_payload(result)

    assert payload["exit_code"] == 1
    assert "PROTOCOL.md" in payload["stderr"]
    fake_manager.execute.assert_not_called()


@pytest.mark.asyncio
async def test_code_mode_invalidates_protocol_ack_when_file_changes(tmp_path, monkeypatch):
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    protocol_path = connection_path / "PROTOCOL.md"
    protocol_path.write_text("v1\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    fake_manager = MagicMock()
    fake_manager.execute.return_value = {
        "stdout": "v1\n",
        "stderr": "",
        "exit_code": 0,
        "duration_ms": 10.0,
        "truncated": False,
    }

    with (
        patch("db_mcp.server.get_settings") as mock_settings,
        patch("db_mcp.tools.code.get_exec_session_manager", return_value=fake_manager),
    ):
        mock_settings.return_value.tool_mode = "code"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = connection_name

        server = _create_server()
        async with Client(server) as client:
            await client.call_tool(
                "code",
                {
                    "connection": connection_name,
                    "code": "print(dbmcp.read_protocol())",
                    "timeout_seconds": 15,
                },
            )
            protocol_path.write_text("v2\n")
            result = (
                await client.call_tool(
                    "code",
                    {
                        "connection": connection_name,
                        "code": "print(dbmcp.scalar('SELECT 1'))",
                        "timeout_seconds": 15,
                    },
                )
            ).data
            payload = _tool_payload(result)

    assert payload["exit_code"] == 1
    assert "PROTOCOL.md" in payload["stderr"]


@pytest.mark.asyncio
async def test_code_mode_surfaces_confirmation_required(tmp_path, monkeypatch):
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    _write_sql_connector(connection_path)
    (connection_path / "PROTOCOL.md").write_text("read me first\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    fake_manager = MagicMock()
    fake_manager.execute.side_effect = [
        {
            "stdout": "read me first\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
        {
            "stdout": "[{'name': 'Customer', 'score': 25}]\n",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10.0,
            "truncated": False,
        },
        {
            "stdout": "",
            "stderr": (
                '{"type":"db_mcp_code_mode_error","kind":"confirm_required",'
                '"message":"Write statement requires confirmation. '
                'Re-run code(..., confirmed=True)."}'
            ),
            "exit_code": 40,
            "duration_ms": 10.0,
            "truncated": False,
        },
    ]

    with (
        patch("db_mcp.server.get_settings") as mock_settings,
        patch("db_mcp.tools.code.get_exec_session_manager", return_value=fake_manager),
    ):
        mock_settings.return_value.tool_mode = "code"
        mock_settings.return_value.tool_profile = "auto"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = connection_name

        server = _create_server()
        async with Client(server) as client:
            await client.call_tool(
                "code",
                {
                    "connection": connection_name,
                    "code": "print(dbmcp.read_protocol())",
                    "timeout_seconds": 15,
                },
            )
            await client.call_tool(
                "code",
                {
                    "connection": connection_name,
                    "code": "print(dbmcp.find_tables('customer'))",
                    "timeout_seconds": 15,
                },
            )
            result = (
                await client.call_tool(
                    "code",
                    {
                        "connection": connection_name,
                        "code": 'dbmcp.execute("CREATE TABLE x(id INTEGER)")',
                        "timeout_seconds": 15,
                    },
                )
            ).data
            payload = _tool_payload(result)

    assert payload["status"] == "confirm_required"
    assert payload["exit_code"] == 1
    assert "confirmed=True" in payload["message"]


@pytest.mark.asyncio
async def test_search_tools_returns_relevant_matches(tmp_path):
    """search_tools should surface best matching active tools."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql", "database_url": "sqlite:///tmp/test.db"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_reg_cls.get_instance.return_value = mock_registry
        mock_settings.return_value.tool_mode = "detailed"
        mock_settings.return_value.tool_profile = "full"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "test"

        server = _create_server()
        async with Client(server) as client:
            result = (await client.call_tool("search_tools", {"query": "sql", "limit": 5})).data
            payload = _tool_payload(result)

    names = [item["name"] for item in payload["tools"]]
    assert "run_sql" in names
    assert payload["count"] >= 1


@pytest.mark.asyncio
async def test_export_tool_sdk_renders_python_wrappers(tmp_path):
    """export_tool_sdk should return runnable Python wrapper code."""
    connector_yaml = tmp_path / "connector.yaml"
    connector_yaml.write_text(yaml.dump({"type": "sql", "database_url": "sqlite:///tmp/test.db"}))
    conn_info = ConnectionInfo(
        name="test", path=tmp_path, type="sql", dialect="", description="", is_default=True
    )

    with (
        patch("db_mcp.registry.ConnectionRegistry") as mock_reg_cls,
        patch("db_mcp.server.get_settings") as mock_settings,
    ):
        mock_registry = MagicMock()
        mock_registry.discover.return_value = {"test": conn_info}
        mock_reg_cls.get_instance.return_value = mock_registry
        mock_settings.return_value.tool_mode = "detailed"
        mock_settings.return_value.tool_profile = "full"
        mock_settings.return_value.auth0_enabled = False
        mock_settings.return_value.auth0_domain = ""
        mock_settings.return_value.connection_name = "test"

        server = _create_server()
        async with Client(server) as client:
            result = (
                await client.call_tool("export_tool_sdk", {"language": "python", "query": "sql"})
            ).data
            payload = _tool_payload(result)

    assert payload["status"] == "ok"
    assert payload["language"] == "python"
    assert "class DbMcpTools:" in payload["code"]
    assert "async def run_sql(" in payload["code"]


def test_all_db_mcp_modules_importable():
    """Guard against PyInstaller missing modules.

    Every db_mcp submodule must be importable. If a new module is added
    but only imported lazily (inside a function), PyInstaller won't bundle
    it and the binary will break at runtime. This test catches that by
    importing every module at test time.
    """
    import db_mcp

    failures = []

    for importer, modname, ispkg in pkgutil.walk_packages(
        path=db_mcp.__path__,
        prefix="db_mcp.",
    ):
        try:
            importlib.import_module(modname)
        except Exception as exc:
            failures.append(f"{modname}: {exc}")

    assert not failures, "The following db_mcp modules failed to import:\n" + "\n".join(failures)
