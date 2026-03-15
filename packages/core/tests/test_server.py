"""Tests for the MCP server."""

import importlib
import pkgutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastmcp.client import Client

from db_mcp.config import reset_settings
from db_mcp.insights.detector import Insight, InsightStore, load_insights, save_insights
from db_mcp.registry import ConnectionInfo, ConnectionRegistry
from db_mcp.server import _create_server


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


def test_server_exposes_improvement_tools():
    """Backward-compat improvement tools should be exposed."""
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
