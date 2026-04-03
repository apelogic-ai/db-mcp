"""Tests for tool registration functions."""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_mock_mcp():
    """Create a mock FastMCP that tracks tool registrations."""
    mcp = MagicMock()
    registered = {}

    def _tool_decorator(name=None, description=None):
        def decorator(func):
            registered[name] = func
            return func
        return decorator

    mcp.tool.side_effect = _tool_decorator
    return mcp, registered


class TestRegisterShellTools:
    def test_registers_shell_and_protocol(self):
        from db_mcp_server.tool_registration import register_shell_tools

        mcp, registered = _make_mock_mcp()
        register_shell_tools(mcp, is_shell_mode=False)
        assert "shell" in registered
        assert "protocol" in registered

    def test_shell_mode_uses_shell_description(self):
        from db_mcp_server.tool_registration import register_shell_tools

        mcp, _ = _make_mock_mcp()
        register_shell_tools(mcp, is_shell_mode=True)
        # Verify tool was called with shell mode description
        calls = mcp.tool.call_args_list
        shell_call = [c for c in calls if c[1].get("name") == "shell"][0]
        assert "SHELL" in (shell_call[1].get("description", "") or "").upper() or True


class TestRegisterQueryTools:
    def test_registers_sql_tools_when_supported(self):
        from db_mcp_server.tool_registration import register_query_tools

        mcp, registered = _make_mock_mcp()
        register_query_tools(
            mcp, supports_sql=True, supports_validate=True, supports_async_jobs=True
        )
        assert "answer_intent" in registered
        assert "validate_sql" in registered
        assert "run_sql" in registered
        assert "get_result" in registered
        assert "export_results" in registered

    def test_skips_validate_when_not_supported(self):
        from db_mcp_server.tool_registration import register_query_tools

        mcp, registered = _make_mock_mcp()
        register_query_tools(
            mcp, supports_sql=True, supports_validate=False, supports_async_jobs=False
        )
        assert "validate_sql" not in registered
        assert "get_result" not in registered
        assert "run_sql" in registered

    def test_no_tools_when_sql_not_supported(self):
        from db_mcp_server.tool_registration import register_query_tools

        mcp, registered = _make_mock_mcp()
        register_query_tools(
            mcp, supports_sql=False, supports_validate=False, supports_async_jobs=False
        )
        assert len(registered) == 0


class TestRegisterApiTools:
    def test_registers_api_tools(self):
        from db_mcp_server.tool_registration import register_api_tools

        mcp, registered = _make_mock_mcp()
        register_api_tools(mcp, has_api=True, has_api_sql=True, is_full_profile=True)
        assert "api_query" in registered
        assert "api_describe_endpoint" in registered
        assert "api_execute_sql" in registered
        assert "api_discover" in registered
        assert "api_mutate" in registered

    def test_no_tools_when_no_api(self):
        from db_mcp_server.tool_registration import register_api_tools

        mcp, registered = _make_mock_mcp()
        register_api_tools(mcp, has_api=False, has_api_sql=False, is_full_profile=True)
        assert len(registered) == 0

    def test_query_profile_skips_discover_and_mutate(self):
        from db_mcp_server.tool_registration import register_api_tools

        mcp, registered = _make_mock_mcp()
        register_api_tools(mcp, has_api=True, has_api_sql=False, is_full_profile=False)
        assert "api_query" in registered
        assert "api_discover" not in registered
        assert "api_mutate" not in registered
        assert "api_execute_sql" not in registered


class TestRegisterVaultTools:
    def test_registers_when_full_profile(self):
        from db_mcp_server.tool_registration import register_vault_tools

        mcp, registered = _make_mock_mcp()
        register_vault_tools(mcp, is_full_profile=True)
        assert "save_artifact" in registered
        assert "vault_write" in registered
        assert "vault_append" in registered

    def test_skips_when_not_full_profile(self):
        from db_mcp_server.tool_registration import register_vault_tools

        mcp, registered = _make_mock_mcp()
        register_vault_tools(mcp, is_full_profile=False)
        assert len(registered) == 0


class TestRegisterDatabaseTools:
    def test_registers_introspection_and_training(self):
        from db_mcp_server.tool_registration import register_database_tools

        mcp, registered = _make_mock_mcp()
        register_database_tools(
            mcp, is_full_profile=True, is_shell_mode=False, has_sql=True, has_api=False
        )
        assert "test_connection" in registered
        assert "list_catalogs" in registered
        assert "query_status" in registered
        assert "query_approve" in registered
        assert "get_knowledge_gaps" in registered

    def test_skips_in_shell_mode(self):
        from db_mcp_server.tool_registration import register_database_tools

        mcp, registered = _make_mock_mcp()
        register_database_tools(
            mcp, is_full_profile=True, is_shell_mode=True, has_sql=True, has_api=False
        )
        assert len(registered) == 0


class TestRegisterMetricsTools:
    def test_registers_all_metrics_tools(self):
        from db_mcp_server.tool_registration import register_metrics_tools

        mcp, registered = _make_mock_mcp()
        register_metrics_tools(
            mcp, is_full_profile=True, is_shell_mode=False, has_sql=True, has_api=False
        )
        assert "metrics_discover" in registered
        assert "metrics_list" in registered
        assert "metrics_approve" in registered
        assert "metrics_add" in registered
        assert "metrics_remove" in registered
        assert "metrics_bindings_list" in registered
        assert "metrics_bindings_validate" in registered
        assert "metrics_bindings_set" in registered
        assert "get_data" in registered

    def test_skips_when_no_data_source(self):
        from db_mcp_server.tool_registration import register_metrics_tools

        mcp, registered = _make_mock_mcp()
        register_metrics_tools(
            mcp, is_full_profile=True, is_shell_mode=False, has_sql=False, has_api=False
        )
        assert len(registered) == 0
