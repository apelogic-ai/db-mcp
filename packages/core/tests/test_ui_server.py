from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from db_mcp import ui_server
from db_mcp.ui_server import JSONRPCResponse


def test_connection_detail_route_serves_exported_shell(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    connection_dir = static_dir / "connection"
    connection_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")
    (connection_dir / "index.html").write_text("<html><body>connection shell</body></html>")

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        response = client.get("/connection/playground")

    assert response.status_code == 200
    assert "connection shell" in response.text


def test_connection_insights_route_serves_exported_shell(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    insights_dir = static_dir / "connection" / "insights"
    insights_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")
    (insights_dir / "index.html").write_text("<html><body>connection insights shell</body></html>")

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        response = client.get("/connection/playground/insights")

    assert response.status_code == 200
    assert "connection insights shell" in response.text


def test_root_redirects_to_connections(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/connections/"


def test_bicp_handler_serializes_date_results(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)

    class FakeAgent:
        async def handle_request(self, request):
            return JSONRPCResponse(
                id=request.id,
                result={
                    "rows": [
                        {"block_date": date(2026, 3, 9)},
                    ]
                },
            )

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        monkeypatch.setattr(ui_server, "_agent", FakeAgent())
        response = client.post(
            "/bicp",
            json={"jsonrpc": "2.0", "id": 1, "method": "sample_table", "params": {}},
        )

    assert response.status_code == 200
    assert response.json()["result"]["rows"][0]["block_date"] == "2026-03-09"
