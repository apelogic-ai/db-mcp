import json
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from db_mcp import ui_server
from db_mcp.ui_server import JSONRPCResponse


def test_connection_new_route_serves_wizard_shell(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    connection_dir = static_dir / "connection"
    new_dir = connection_dir / "new"
    new_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")
    (new_dir / "index.html").write_text("<html><body>wizard shell</body></html>")
    (connection_dir / "index.html").write_text("<html><body>connection shell</body></html>")

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        response = client.get("/connection/new")

    assert response.status_code == 200
    assert "wizard shell" in response.text


def test_connection_detail_route_serves_exported_shell(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    connection_dir = static_dir / "connection"
    connection_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")
    (connection_dir / "index.html").write_text("<html><body>connection shell</body></html>")

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)

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
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)

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
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)

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
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)

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


def test_validate_static_bundle_provenance_accepts_matching_source(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    ui_dir = repo_root / "packages" / "ui"
    static_dir = repo_root / "packages" / "core" / "src" / "db_mcp" / "static"
    (ui_dir / "src").mkdir(parents=True)
    (ui_dir / "public").mkdir(parents=True)
    static_dir.mkdir(parents=True)
    (ui_dir / "src" / "app.tsx").write_text("export default function App() { return null; }\n")
    (ui_dir / "package.json").write_text('{"name":"@db-mcp/ui"}\n')
    (ui_dir / "next.config.js").write_text("module.exports = {};\n")
    (ui_dir / "postcss.config.js").write_text("module.exports = {};\n")
    (ui_dir / "tailwind.config.js").write_text("module.exports = {};\n")
    (ui_dir / "tsconfig.json").write_text('{"compilerOptions":{}}\n')

    source_hash = ui_server._compute_ui_source_hash(ui_dir)
    (static_dir / ".build-info.json").write_text(
        json.dumps(
            {
                "gitSha": "unknown",
                "uiSourceHash": source_hash,
            }
        )
    )

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "_repo_root", lambda: repo_root)
    monkeypatch.delenv("DB_MCP_UI_SKIP_STATIC_CHECK", raising=False)

    ui_server.validate_static_bundle_provenance()


def test_validate_static_bundle_provenance_rejects_stale_source(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    ui_dir = repo_root / "packages" / "ui"
    static_dir = repo_root / "packages" / "core" / "src" / "db_mcp" / "static"
    (ui_dir / "src").mkdir(parents=True)
    (ui_dir / "public").mkdir(parents=True)
    static_dir.mkdir(parents=True)
    (ui_dir / "src" / "app.tsx").write_text("export default function App() { return null; }\n")
    (ui_dir / "package.json").write_text('{"name":"@db-mcp/ui"}\n')
    (ui_dir / "next.config.js").write_text("module.exports = {};\n")
    (ui_dir / "postcss.config.js").write_text("module.exports = {};\n")
    (ui_dir / "tailwind.config.js").write_text("module.exports = {};\n")
    (ui_dir / "tsconfig.json").write_text('{"compilerOptions":{}}\n')
    (static_dir / ".build-info.json").write_text(
        json.dumps(
            {
                "gitSha": "unknown",
                "uiSourceHash": "stale",
            }
        )
    )

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "_repo_root", lambda: repo_root)
    monkeypatch.delenv("DB_MCP_UI_SKIP_STATIC_CHECK", raising=False)

    with pytest.raises(RuntimeError, match="Static UI bundle is stale"):
        ui_server.validate_static_bundle_provenance()
