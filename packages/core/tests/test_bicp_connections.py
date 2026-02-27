"""Tests for BICP connection handlers."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_connections_test_uses_connector_for_named_connection(monkeypatch):
    from db_mcp.bicp.agent import DBMCPAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        conn_path = Path(tmpdir) / ".db-mcp" / "connections" / "top-ledger"
        conn_path.mkdir(parents=True)

        (conn_path / ".env").write_text('DATABASE_URL="trino://user@host:8443/catalog"\n')
        (conn_path / "connector.yaml").write_text(
            "type: sql\ncapabilities:\n  connect_args:\n    http_scheme: http\n"
        )

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "trino"

        mock_connector = MagicMock()
        mock_connector.test_connection.return_value = {"connected": True, "dialect": "trino"}

        with patch("db_mcp.connectors.get_connector", return_value=mock_connector) as mock_get:
            result = await agent._handle_connections_test({"name": "top-ledger"})

        assert result["success"] is True
        mock_get.assert_called_once()
        mock_connector.test_connection.assert_called_once()
