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


def test_runtime_contract_endpoint_uses_shared_service(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")

    class FakeRuntimeService:
        def contract(
            self,
            connection: str,
            *,
            session_id: str | None = None,
            interface: str = "native",
        ):
            return {
                "kind": "db-mcp-code-runtime",
                "connection": connection,
                "session_id": session_id,
                "interface": interface,
            }

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)
    monkeypatch.setattr(
        "db_mcp.code_runtime.http.get_code_runtime_service",
        lambda: FakeRuntimeService(),
    )

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        response = client.get(
            "/api/runtime/contract",
            params={"connection": "playground", "interface": "mcp"},
        )

    assert response.status_code == 200
    assert response.json()["connection"] == "playground"
    assert response.json()["interface"] == "mcp"


def test_runtime_run_endpoint_uses_shared_service(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")

    class FakeResult:
        def to_dict(self):
            return {
                "stdout": "59\n",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 12.5,
                "truncated": False,
            }

    class FakeRuntimeService:
        def run(
            self,
            connection: str,
            code: str,
            *,
            session_id: str | None = None,
            timeout_seconds: int = 30,
            confirmed: bool = False,
        ):
            assert connection == "playground"
            assert "dbmcp.scalar" in code
            assert session_id == "session-1"
            assert timeout_seconds == 15
            assert confirmed is False
            return FakeResult()

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)
    monkeypatch.setattr(
        "db_mcp.code_runtime.http.get_code_runtime_service",
        lambda: FakeRuntimeService(),
    )

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        response = client.post(
            "/api/runtime/run",
            json={
                "connection": "playground",
                "code": "print(dbmcp.scalar('SELECT COUNT(*) FROM Customer'))",
                "session_id": "session-1",
                "timeout_seconds": 15,
            },
        )

    assert response.status_code == 200
    assert response.json()["stdout"] == "59\n"


def test_runtime_session_endpoints_use_shared_service(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")

    class FakeSession:
        def __init__(self, connection: str, session_id: str) -> None:
            self.connection = connection
            self.session_id = session_id

    class FakeResult:
        def to_dict(self):
            return {
                "stdout": "3\n",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 10.0,
                "truncated": False,
            }

    class FakeRuntimeService:
        def create_session(self, connection: str, session_id: str | None = None):
            assert connection == "playground"
            assert session_id == "session-1"
            return FakeSession(connection, session_id)

        def contract_for_session(self, session_id: str, *, interface: str = "native"):
            assert session_id == "session-1"
            return {
                "kind": "db-mcp-code-runtime",
                "connection": "playground",
                "session_id": session_id,
                "interface": interface,
            }

        def run_session(
            self,
            session_id: str,
            code: str,
            *,
            timeout_seconds: int = 30,
            confirmed: bool = False,
        ):
            assert session_id == "session-1"
            assert "dbmcp.scalar" in code
            assert timeout_seconds == 15
            assert confirmed is False
            return FakeResult()

        def close_session(self, session_id: str):
            assert session_id == "session-1"
            return True

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)
    monkeypatch.setattr(
        "db_mcp.code_runtime.http.get_code_runtime_service",
        lambda: FakeRuntimeService(),
    )

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())

        create_response = client.post(
            "/api/runtime/sessions",
            json={"connection": "playground", "session_id": "session-1", "interface": "cli"},
        )
        contract_response = client.get(
            "/api/runtime/sessions/session-1/contract",
            params={"interface": "mcp"},
        )
        run_response = client.post(
            "/api/runtime/sessions/session-1/run",
            json={
                "code": "print(dbmcp.scalar('SELECT COUNT(*) FROM Customer'))",
                "timeout_seconds": 15,
            },
        )
        close_response = client.delete("/api/runtime/sessions/session-1")

    assert create_response.status_code == 200
    assert create_response.json()["session_id"] == "session-1"
    assert create_response.json()["interface"] == "cli"
    assert contract_response.status_code == 200
    assert contract_response.json()["session_id"] == "session-1"
    assert contract_response.json()["interface"] == "mcp"
    assert run_response.status_code == 200
    assert run_response.json()["stdout"] == "3\n"
    assert close_response.status_code == 200
    assert close_response.json()["closed"] is True


def test_runtime_session_sdk_invoke_endpoint_uses_shared_service(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")

    class FakeRuntimeService:
        def invoke_session_method(
            self,
            session_id: str,
            method: str,
            *,
            args=None,
            kwargs=None,
            confirmed: bool = False,
        ):
            assert session_id == "session-1"
            assert method == "scalar"
            assert args == ["SELECT 1", None]
            assert kwargs == {}
            assert confirmed is False
            return 1

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)
    monkeypatch.setattr(
        "db_mcp.code_runtime.http.get_code_runtime_service",
        lambda: FakeRuntimeService(),
    )

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        response = client.post(
            "/api/runtime/sessions/session-1/sdk/scalar",
            json={"args": ["SELECT 1", None], "kwargs": {}, "confirmed": False},
        )

    assert response.status_code == 200
    assert response.json()["result"] == 1


def test_runtime_session_sdk_invoke_endpoint_serializes_date_results(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>root</body></html>")

    class FakeRuntimeService:
        def invoke_session_method(
            self,
            session_id: str,
            method: str,
            *,
            args=None,
            kwargs=None,
            confirmed: bool = False,
        ):
            assert session_id == "session-1"
            assert method == "query"
            return [{"block_date": date(2026, 3, 9)}]

    monkeypatch.setattr(ui_server, "STATIC_DIR", static_dir)
    monkeypatch.setattr(ui_server, "validate_static_bundle_provenance", lambda: None)
    monkeypatch.setattr(
        "db_mcp.code_runtime.http.get_code_runtime_service",
        lambda: FakeRuntimeService(),
    )

    with patch("db_mcp.ui_server.DBMCPAgent"):
        client = TestClient(ui_server.create_app())
        response = client.post(
            "/api/runtime/sessions/session-1/sdk/query",
            json={"args": ["SELECT block_date FROM demo", None], "kwargs": {}, "confirmed": False},
        )

    assert response.status_code == 200
    assert response.json()["result"][0]["block_date"] == "2026-03-09"


def test_start_runtime_server_passes_app_instance_to_uvicorn(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr("uvicorn.run", fake_run)

    from db_mcp.code_runtime.http import start_runtime_server

    start_runtime_server(host="127.0.0.1", port=8099)

    assert hasattr(captured["app"], "routes")
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["port"] == 8099
    assert captured["kwargs"]["reload"] is False
    assert captured["kwargs"]["workers"] == 1
