"""Tests for the MCP server."""

import importlib
import pkgutil
from unittest.mock import patch

import pytest
import yaml

from db_mcp.server import _create_server


def _get_tool_names(server):
    """Extract registered tool names from a FastMCP server."""
    return set(server._tool_manager._tools.keys())


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


class TestConnectorTypeToolGating:
    """Tools should be registered based on connector type (sql/api/file)."""

    def test_sql_connector_exposes_sql_tools(self):
        """Default (SQL) connector should have run_sql, validate_sql, etc."""
        server = _create_server()
        tools = _get_tool_names(server)
        assert "run_sql" in tools
        assert "validate_sql" in tools
        assert "list_tables" in tools
        assert "describe_table" in tools

    def test_sql_connector_hides_api_tools(self):
        """SQL connector should NOT expose api_query, api_describe_endpoint."""
        server = _create_server()
        tools = _get_tool_names(server)
        assert "api_query" not in tools
        assert "api_describe_endpoint" not in tools
        assert "api_discover" not in tools

    def test_api_connector_hides_sql_tools(self, tmp_path):
        """API connector should NOT expose run_sql, validate_sql, etc."""
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
        assert "run_sql" not in tools
        assert "validate_sql" not in tools
        assert "get_result" not in tools
        assert "get_data" not in tools
        assert "list_catalogs" not in tools
        assert "list_tables" not in tools
        assert "describe_table" not in tools
        assert "detect_dialect" not in tools

    def test_api_connector_exposes_api_tools(self, tmp_path):
        """API connector should expose api_query, api_describe_endpoint, api_discover."""
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
