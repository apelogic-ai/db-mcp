"""Tests for multi-connection support (connection parameter on tools)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db_mcp.tools.utils import _resolve_connection_path

# =============================================================================
# _resolve_connection_path tests
# =============================================================================


class TestResolveConnectionPath:
    def test_none_returns_none(self):
        assert _resolve_connection_path(None) is None

    def test_resolves_with_connections_dir_setting(self):
        mock_settings = MagicMock()
        mock_settings.connections_dir = "/custom/connections"
        with patch("db_mcp.tools.utils.get_settings", return_value=mock_settings):
            result = _resolve_connection_path("prod")
        assert result == str(Path("/custom/connections/prod"))

    def test_resolves_with_default_base(self):
        mock_settings = MagicMock()
        mock_settings.connections_dir = ""
        with patch("db_mcp.tools.utils.get_settings", return_value=mock_settings):
            result = _resolve_connection_path("staging")
        assert result == str(Path.home() / ".db-mcp" / "connections" / "staging")

    def test_resolves_with_none_connections_dir(self):
        mock_settings = MagicMock()
        mock_settings.connections_dir = None
        with patch("db_mcp.tools.utils.get_settings", return_value=mock_settings):
            result = _resolve_connection_path("dev")
        assert result == str(Path.home() / ".db-mcp" / "connections" / "dev")


# =============================================================================
# Tool integration tests (mock get_connector)
# =============================================================================


@pytest.mark.asyncio
class TestDatabaseToolsConnection:
    """Test that database tools pass connection_path through to get_connector."""

    @patch("db_mcp.tools.database.get_connector")
    async def test_list_catalogs_passes_connection(self, mock_gc):
        from db_mcp.tools.database import _list_catalogs

        mock_connector = MagicMock()
        mock_connector.get_catalogs.return_value = ["cat1"]
        mock_gc.return_value = mock_connector

        with patch("db_mcp.tools.database._resolve_connection_path", return_value="/path/to/prod"):
            await _list_catalogs(connection="prod")

        mock_gc.assert_called_once_with(connection_path="/path/to/prod")

    @patch("db_mcp.tools.database.get_connector")
    async def test_list_catalogs_none_connection(self, mock_gc):
        from db_mcp.tools.database import _list_catalogs

        mock_connector = MagicMock()
        mock_connector.get_catalogs.return_value = []
        mock_gc.return_value = mock_connector

        await _list_catalogs()
        mock_gc.assert_called_once_with(connection_path=None)

    @patch("db_mcp.tools.database.get_connector")
    async def test_list_schemas_passes_connection(self, mock_gc):
        from db_mcp.tools.database import _list_schemas

        mock_connector = MagicMock()
        mock_connector.get_schemas.return_value = []
        mock_gc.return_value = mock_connector

        with patch("db_mcp.tools.database._resolve_connection_path", return_value="/p/staging"):
            await _list_schemas(connection="staging")

        mock_gc.assert_called_once_with(connection_path="/p/staging")

    @patch("db_mcp.tools.database.get_connector")
    async def test_list_tables_passes_connection(self, mock_gc):
        from db_mcp.tools.database import _list_tables

        mock_connector = MagicMock()
        mock_connector.get_tables.return_value = []
        mock_gc.return_value = mock_connector

        with patch("db_mcp.tools.database._resolve_connection_path", return_value="/p/dev"):
            await _list_tables(connection="dev")

        mock_gc.assert_called_once_with(connection_path="/p/dev")

    @patch("db_mcp.tools.database.get_connector")
    async def test_describe_table_passes_connection(self, mock_gc):
        from db_mcp.tools.database import _describe_table

        mock_connector = MagicMock()
        mock_connector.get_columns.return_value = []
        mock_gc.return_value = mock_connector

        with patch("db_mcp.tools.database._resolve_connection_path", return_value="/p/prod"):
            await _describe_table(table_name="users", connection="prod")

        mock_gc.assert_called_once_with(connection_path="/p/prod")

    @patch("db_mcp.tools.database.get_connector")
    async def test_sample_table_passes_connection(self, mock_gc):
        from db_mcp.tools.database import _sample_table

        mock_connector = MagicMock()
        mock_connector.get_table_sample.return_value = []
        mock_gc.return_value = mock_connector

        with patch("db_mcp.tools.database._resolve_connection_path", return_value="/p/prod"):
            await _sample_table(table_name="users", connection="prod")

        mock_gc.assert_called_once_with(connection_path="/p/prod")


@pytest.mark.asyncio
class TestGenerationToolsConnection:
    """Test that generation tools pass connection_path through."""

    @patch("db_mcp.tools.generation.get_connector")
    @patch("db_mcp.connectors.get_connector_capabilities")
    @patch("db_mcp.tools.generation.validate_read_only", return_value=(True, None))
    @patch("db_mcp.tools.generation.explain_sql")
    async def test_validate_sql_passes_connection(self, mock_explain, mock_ro, mock_caps, mock_gc):
        from db_mcp.tools.generation import _validate_sql

        mock_connector = MagicMock()
        mock_gc.return_value = mock_connector
        mock_caps.return_value = {"supports_validate_sql": True}
        mock_explain_result = MagicMock()
        mock_explain_result.valid = False
        mock_explain_result.error = "test"
        mock_explain.return_value = mock_explain_result

        with patch("db_mcp.tools.utils._resolve_connection_path", return_value="/p/prod"):
            await _validate_sql(sql="SELECT 1", connection="prod")

        mock_gc.assert_called_once_with(connection_path="/p/prod")

    @patch("db_mcp.tools.generation.get_connector")
    @patch("db_mcp.connectors.get_connector_capabilities")
    @patch("db_mcp.tools.generation.validate_read_only", return_value=(True, None))
    @patch("db_mcp.tools.generation.explain_sql")
    async def test_validate_sql_passes_connection_to_explain(self, mock_explain, mock_ro, mock_caps, mock_gc):
        """Verify explain_sql receives connection_path when _validate_sql is called with connection."""
        from db_mcp.tools.generation import _validate_sql

        mock_connector = MagicMock()
        mock_gc.return_value = mock_connector
        mock_caps.return_value = {"supports_validate_sql": True}
        from db_mcp.validation.explain import ExplainResult, CostTier
        mock_explain_result = ExplainResult(
            valid=True,
            estimated_rows=10,
            estimated_cost=1.0,
            cost_tier=CostTier.AUTO,
            tier_reason="test",
        )
        mock_explain.return_value = mock_explain_result

        with patch("db_mcp.tools.utils._resolve_connection_path", return_value="/p/prod"):
            await _validate_sql(sql="SELECT 1", connection="prod")

        mock_explain.assert_called_once_with("SELECT 1", connection_path="/p/prod")


@pytest.mark.asyncio
class TestTestConnectionMultiConn:
    """Test that _test_connection passes connection_path through."""

    @patch("db_mcp.tools.database.get_connector")
    async def test_test_connection_with_connection(self, mock_gc):
        from db_mcp.tools.database import _test_connection

        mock_connector = MagicMock()
        mock_connector.test_connection.return_value = {"status": "ok"}
        mock_gc.return_value = mock_connector

        with patch("db_mcp.tools.database._resolve_connection_path", return_value="/p/staging"):
            await _test_connection(connection="staging")

        mock_gc.assert_called_once_with(connection_path="/p/staging")

    @patch("db_mcp.tools.database.get_connector")
    async def test_test_connection_without_connection(self, mock_gc):
        from db_mcp.tools.database import _test_connection

        mock_connector = MagicMock()
        mock_connector.test_connection.return_value = {"status": "ok"}
        mock_gc.return_value = mock_connector

        await _test_connection()

        mock_gc.assert_called_once_with(connection_path=None)


@pytest.mark.asyncio
class TestShellToolConnection:
    """Test that shell tool uses connection path."""

    @patch("db_mcp.tools.shell.run_sandboxed")
    @patch("db_mcp.tools.shell.validate_command")
    async def test_shell_with_connection(self, mock_validate, mock_run):
        from db_mcp.tools.shell import _shell

        mock_validate.return_value = MagicMock(ok=True, is_write=False)
        mock_run.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}

        with patch(
            "db_mcp.tools.utils._resolve_connection_path",
            return_value="/custom/connections/prod",
        ):
            # Need the path to exist for the check
            with patch.object(Path, "exists", return_value=True):
                await _shell(command="ls", connection="prod")

        # Verify run_sandboxed was called with the resolved connection path
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert str(call_args[0][1]) == "/custom/connections/prod"

    @patch("db_mcp.tools.shell.get_connection_path")
    @patch("db_mcp.tools.shell.run_sandboxed")
    @patch("db_mcp.tools.shell.validate_command")
    async def test_shell_without_connection_uses_default(self, mock_validate, mock_run, mock_gcp):
        from db_mcp.tools.shell import _shell

        mock_validate.return_value = MagicMock(ok=True, is_write=False)
        mock_run.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}
        default_path = Path("/default/path")
        mock_gcp.return_value = default_path

        with patch.object(Path, "exists", return_value=True):
            await _shell(command="ls")

        mock_run.assert_called_once()
        assert mock_run.call_args[0][1] == default_path
