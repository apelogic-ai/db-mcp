from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.error import HTTPError

import yaml
from click.testing import CliRunner

from db_mcp.cli.main import main
from db_mcp.config import reset_settings
from db_mcp.exec_runtime import ExecSessionManager, ProcessExecSandboxBackend
from db_mcp.registry import ConnectionRegistry


def _write_sql_connector(connection_dir: Path, database_url: str) -> None:
    connection_dir.mkdir(parents=True, exist_ok=True)
    (connection_dir / "connector.yaml").write_text(
        yaml.safe_dump(
            {
                "type": "sql",
                "database_url": database_url,
                "capabilities": {"connect_args": {"timeout": 30}},
            },
            sort_keys=False,
        )
    )


def _prepare_connection(tmp_path: Path, monkeypatch) -> str:
    connection_name = "demo"
    connection_path = tmp_path / connection_name
    db_path = tmp_path / "demo.sqlite"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, amount INTEGER)")
        conn.execute("INSERT INTO items(amount) VALUES (10), (20), (30)")
        conn.commit()
    finally:
        conn.close()

    _write_sql_connector(connection_path, f"sqlite:///{db_path}")
    (connection_path / "PROTOCOL.md").write_text("read me first\n")
    (connection_path / "schema").mkdir()
    (connection_path / "schema" / "descriptions.yaml").write_text("tables: []\n")
    (connection_path / "domain").mkdir()
    (connection_path / "domain" / "model.md").write_text("# domain\n")
    (connection_path / "instructions").mkdir()
    (connection_path / "instructions" / "sql_rules.md").write_text("# rules\n")

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()
    return connection_name


def test_runtime_prompt_prints_agent_contract(tmp_path, monkeypatch):
    connection_name = _prepare_connection(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(main, ["runtime", "prompt", "--connection", connection_name])

    assert result.exit_code == 0
    assert "dbmcp.read_protocol()" in result.output
    assert "dbmcp.scalar(sql)" in result.output


def test_runtime_prompt_json_outputs_contract(tmp_path, monkeypatch):
    connection_name = _prepare_connection(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(main, ["runtime", "prompt", "--connection", connection_name, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["connection"] == connection_name
    assert payload["helper_object"] == "dbmcp"
    assert "read_protocol" in payload["helper_methods"]


def test_runtime_prompt_json_outputs_mcp_interface_contract(tmp_path, monkeypatch):
    connection_name = _prepare_connection(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "runtime",
            "prompt",
            "--connection",
            connection_name,
            "--interface",
            "mcp",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["interface"] == "mcp"
    assert payload["tool_name"] == "code"
    assert payload["tool_mode"] == "code"


def test_runtime_run_executes_inline_code(tmp_path, monkeypatch):
    connection_name = _prepare_connection(tmp_path, monkeypatch)
    manager = ExecSessionManager(backend=ProcessExecSandboxBackend())
    monkeypatch.setattr(
        "db_mcp.code_runtime.host.get_exec_session_manager",
        lambda: manager,
    )

    runner = CliRunner()
    session_id = "runtime-cli-inline"
    protocol = runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--code",
            "print(dbmcp.read_protocol())",
        ],
    )
    discovery = runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--code",
            "print(dbmcp.table_names())",
        ],
    )
    result = runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--code",
            "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
        ],
    )

    assert protocol.exit_code == 0
    assert "read me first" in protocol.output
    assert discovery.exit_code == 0
    assert "items" in discovery.output
    assert result.exit_code == 0
    assert result.output.strip() == "3"


def test_runtime_run_executes_file_input(tmp_path, monkeypatch):
    connection_name = _prepare_connection(tmp_path, monkeypatch)
    manager = ExecSessionManager(backend=ProcessExecSandboxBackend())
    monkeypatch.setattr(
        "db_mcp.code_runtime.host.get_exec_session_manager",
        lambda: manager,
    )

    script_path = tmp_path / "query.py"
    script_path.write_text("print(dbmcp.scalar('SELECT COUNT(*) FROM items'))\n")
    session_id = "runtime-cli-file"
    runner = CliRunner()

    runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--code",
            "print(dbmcp.read_protocol())",
        ],
    )
    runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--code",
            "print(dbmcp.table_names())",
        ],
    )
    result = runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--file",
            str(script_path),
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "3"


def test_runtime_run_json_surfaces_confirmation_required(tmp_path, monkeypatch):
    connection_name = _prepare_connection(tmp_path, monkeypatch)
    manager = ExecSessionManager(backend=ProcessExecSandboxBackend())
    monkeypatch.setattr(
        "db_mcp.code_runtime.host.get_exec_session_manager",
        lambda: manager,
    )

    runner = CliRunner()
    session_id = "runtime-cli-confirm"
    runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--code",
            "print(dbmcp.read_protocol())",
        ],
    )
    runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--code",
            "print(dbmcp.table_names())",
        ],
    )
    result = runner.invoke(
        main,
        [
            "runtime",
            "run",
            "--connection",
            connection_name,
            "--session-id",
            session_id,
            "--json",
            "--code",
            'dbmcp.execute("CREATE TABLE writes(id INTEGER)")',
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "confirm_required"
    assert "confirmed=True" in payload["message"]


def test_runtime_exec_posts_to_runtime_server(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def read(self):
            return json.dumps(
                {
                    "stdout": "3\n",
                    "stderr": "",
                    "exit_code": 0,
                    "duration_ms": 10.0,
                    "truncated": False,
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    script_path = tmp_path / "query.py"
    script_path.write_text("print(dbmcp.scalar('SELECT COUNT(*) FROM items'))\n")

    monkeypatch.setattr("db_mcp.cli.commands.runtime_cmd.urlopen", fake_urlopen)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "runtime",
            "exec",
            "--server-url",
            "http://127.0.0.1:8765",
            "--connection",
            "demo",
            "--session-id",
            "runtime-session",
            "--file",
            str(script_path),
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "3"
    assert captured["url"] == "http://127.0.0.1:8765/api/runtime/run"
    assert captured["body"] == {
        "connection": "demo",
        "code": "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))\n",
        "session_id": "runtime-session",
        "timeout_seconds": 30,
        "confirmed": False,
    }


def test_runtime_exec_surfaces_server_errors(monkeypatch):
    class FakeResponse:
        def close(self):
            return None

        def read(self):
            return b'{"detail":"boom"}'

    def fake_urlopen(request, timeout=0):
        raise HTTPError(request.full_url, 500, "server error", hdrs=None, fp=FakeResponse())

    monkeypatch.setattr("db_mcp.cli.commands.runtime_cmd.urlopen", fake_urlopen)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "runtime",
            "exec",
            "--server-url",
            "http://127.0.0.1:8765",
            "--connection",
            "demo",
            "--session-id",
            "runtime-session",
            "--code",
            "print('x')",
        ],
    )

    assert result.exit_code == 1
    assert "boom" in result.output


def test_runtime_serve_invokes_runtime_server(monkeypatch):
    captured: dict[str, object] = {}

    def fake_start_runtime_server(*, host: str, port: int) -> None:
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(
        "db_mcp.cli.commands.runtime_cmd.start_runtime_server",
        fake_start_runtime_server,
    )

    runner = CliRunner()
    result = runner.invoke(main, ["runtime", "serve", "--host", "127.0.0.1", "--port", "8099"])

    assert result.exit_code == 0
    assert captured == {"host": "127.0.0.1", "port": 8099}


def test_runtime_without_subcommand_starts_mcp_runtime_mode(tmp_path, monkeypatch):
    connection_name = _prepare_connection(tmp_path, monkeypatch)
    monkeypatch.setenv("TOOL_MODE", "shell")
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    monkeypatch.setattr(
        "db_mcp.cli.commands.core.load_config",
        lambda: {"active_connection": connection_name, "tool_mode": "shell"},
    )

    captured: dict[str, object] = {}

    def fake_server_main() -> None:
        import os

        captured["connection_name"] = os.environ.get("CONNECTION_NAME")
        captured["tool_mode"] = os.environ.get("TOOL_MODE")
        captured["runtime_interface"] = os.environ.get("RUNTIME_INTERFACE")

    monkeypatch.setattr("db_mcp.server.main", fake_server_main)

    runner = CliRunner()
    result = runner.invoke(main, ["runtime"])

    assert result.exit_code == 0
    assert captured["connection_name"] == connection_name
    assert captured["tool_mode"] == "code"
    assert captured["runtime_interface"] == "native"


def test_runtime_without_subcommand_proxies_to_local_service(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "db_mcp.cli.commands.runtime_cmd.load_local_service_state",
        lambda: {"mcp_url": "http://127.0.0.1:8000/mcp"},
    )
    monkeypatch.setattr(
        "db_mcp.cli.commands.runtime_cmd.local_service_is_healthy",
        lambda state: True,
    )

    def fake_proxy(url: str) -> None:
        captured["url"] = url

    monkeypatch.setattr(
        "db_mcp.cli.commands.runtime_cmd._proxy_runtime_to_local_service",
        fake_proxy,
    )
    monkeypatch.setattr(
        "db_mcp.cli.commands.runtime_cmd.start_cmd.callback",
        lambda connection, mode: (_ for _ in ()).throw(AssertionError("fallback should not run")),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["runtime"])

    assert result.exit_code == 0
    assert captured == {"url": "http://127.0.0.1:8000/mcp"}
