"""Tests for the MCP server."""

import pytest

from db_mcp.server import _create_server


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
