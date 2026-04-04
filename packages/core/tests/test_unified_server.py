"""Tests for unified server: MCP mounted inside FastAPI."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_mcp_server():
    """Mock create_mcp_server to avoid full MCP initialization."""
    mock_server = MagicMock()
    mock_asgi_app = MagicMock()
    mock_server.http_app.return_value = mock_asgi_app
    with patch(
        "db_mcp_server.server.create_mcp_server",
        return_value=mock_server,
    ) as mock_factory:
        yield mock_factory, mock_server, mock_asgi_app


def test_create_app_mounts_mcp_when_requested(mock_mcp_server):
    """create_app(mount_mcp=True) should mount MCP at /mcp."""
    from db_mcp.ui_server import create_app

    app = create_app(mount_mcp=True)

    _mock_factory, mock_server, _mock_asgi = mock_mcp_server
    mock_server.http_app.assert_called_once()
    # Verify /mcp route is mounted
    route_paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/mcp" in route_paths or any("/mcp" in str(r.path) for r in app.routes)


def test_create_app_does_not_mount_mcp_by_default():
    """create_app() without mount_mcp should not import or mount MCP."""
    from db_mcp.ui_server import create_app

    app = create_app()

    route_paths = [getattr(r, "path", "") for r in app.routes]
    assert "/mcp" not in route_paths


def test_create_app_health_still_works(mock_mcp_server):
    """Health endpoint must still work when MCP is mounted."""
    from starlette.testclient import TestClient

    from db_mcp.ui_server import create_app

    app = create_app(mount_mcp=True)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_create_app_api_still_works(mock_mcp_server):
    """REST API routes must still work when MCP is mounted."""
    from starlette.testclient import TestClient

    from db_mcp.ui_server import create_app

    app = create_app(mount_mcp=True)
    client = TestClient(app)
    # POST to a known API method — connections/list should exist
    resp = client.post("/api/connections/list", json={})
    # Should get a response (not 404 from missing route)
    assert resp.status_code != 404


def test_create_unified_app_is_shortcut(mock_mcp_server):
    """create_unified_app() is a convenience wrapper that mounts MCP."""
    from db_mcp.ui_server import create_unified_app

    create_unified_app()
    _mock_factory, mock_server, _mock_asgi = mock_mcp_server
    mock_server.http_app.assert_called_once()
