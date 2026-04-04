"""Tests for TUI API client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def test_api_client_is_importable():
    from db_mcp_cli.tui.client import APIClient

    assert APIClient is not None


def test_api_client_construction():
    from db_mcp_cli.tui.client import APIClient

    client = APIClient(base_url="http://localhost:8080")
    assert client.base_url == "http://localhost:8080"
    assert client.last_execution_ts == 0.0


def test_api_client_health_check_success():
    from db_mcp_cli.tui.client import APIClient

    client = APIClient(base_url="http://localhost:8080")
    mock_resp = MagicMock()
    mock_resp.status = 200

    with patch("db_mcp_cli.tui.client.urlopen", return_value=mock_resp):
        assert client.check_health() is True


def test_api_client_health_check_failure():
    from urllib.error import URLError

    from db_mcp_cli.tui.client import APIClient

    client = APIClient(base_url="http://localhost:8080")

    with patch("db_mcp_cli.tui.client.urlopen", side_effect=URLError("refused")):
        assert client.check_health() is False


def test_api_client_fetch_executions_returns_feed_events():
    from db_mcp_cli.tui.client import APIClient

    client = APIClient(base_url="http://localhost:8080")
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "traces": [
            {
                "execution_id": "abc-1",
                "state": "succeeded",
                "sql": "SELECT 1",
                "duration_ms": 5.0,
                "rows_returned": 1,
                "created_at": 1743681600.0,
            },
        ],
    }).encode()

    with patch("db_mcp_cli.tui.client.urlopen", return_value=mock_resp):
        events = client.fetch_executions()

    assert len(events) == 1
    assert events[0].id == "abc-1"
    assert events[0].done is True
    assert client.last_execution_ts == 1743681600.0


def test_api_client_fetch_status():
    from db_mcp_cli.tui.client import APIClient

    client = APIClient(base_url="http://localhost:8080")

    health_resp = MagicMock()
    health_resp.status = 200

    conn_resp = MagicMock()
    conn_resp.read.return_value = json.dumps({
        "connections": [{"name": "mydb", "active": True}],
    }).encode()

    def fake_urlopen(url_or_req, **_):
        if isinstance(url_or_req, str) and "/health" in url_or_req:
            return health_resp
        return conn_resp

    with patch("db_mcp_cli.tui.client.urlopen", side_effect=fake_urlopen):
        status = client.fetch_status()

    assert status.server_healthy is True
    assert status.connection == "mydb"
