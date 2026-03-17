from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from db_mcp.code_runtime import CodeModeHost, CodeModeRuntime, CodeRuntimeClient
from db_mcp.code_runtime.service import CodeRuntimeService
from db_mcp.config import reset_settings
from db_mcp.exec_runtime import ExecSessionManager, ProcessExecSandboxBackend
from db_mcp.registry import ConnectionRegistry
from db_mcp.tools.code import _code


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


@pytest.fixture()
def code_mode_connection(tmp_path, monkeypatch) -> tuple[str, Path]:
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
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.safe_dump(
            {
                "tables": [
                    {
                        "name": "items",
                        "schema": "main",
                        "full_name": "main.items",
                        "description": "Line items available for sale.",
                        "columns": [
                            {
                                "name": "id",
                                "type": "INTEGER",
                                "description": "Primary key for the item row.",
                            },
                            {
                                "name": "amount",
                                "type": "INTEGER",
                                "description": "Stored amount for the item.",
                            },
                        ],
                    }
                ]
            },
            sort_keys=False,
        )
    )
    (connection_path / "domain").mkdir()
    (connection_path / "domain" / "model.md").write_text("# domain\n")
    (connection_path / "instructions").mkdir()
    (connection_path / "instructions" / "sql_rules.md").write_text("# rules\n")
    (connection_path / "instructions" / "business_rules.yaml").write_text(
        yaml.safe_dump(
            {
                "rules": [
                    "Use items.amount for amount-based totals.",
                    "Items are never soft deleted.",
                ]
            },
            sort_keys=False,
        )
    )
    (connection_path / "examples").mkdir()
    (connection_path / "examples" / "count_items.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "count_items",
                "intent": "Count items in the catalog",
                "sql": "SELECT COUNT(*) FROM items",
                "tables": ["items"],
                "keywords": ["count items", "catalog size"],
                "notes": "Use this for simple item counts.",
                "validated": True,
            },
            sort_keys=False,
        )
    )
    (connection_path / "learnings").mkdir()
    (connection_path / "learnings" / "patterns.md").write_text(
        "# Patterns\n\n- Prefer the items table for catalog-level item counts.\n"
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(tmp_path))
    monkeypatch.setenv("CONNECTION_NAME", connection_name)
    monkeypatch.delenv("CONNECTION_PATH", raising=False)
    reset_settings()
    ConnectionRegistry.reset()

    return connection_name, connection_path


@pytest.mark.asyncio
async def test_code_mode_process_backend_can_query_with_runtime_helper(
    code_mode_connection,
    monkeypatch,
):
    connection_name, _ = code_mode_connection
    manager = ExecSessionManager(backend=ProcessExecSandboxBackend())
    ctx = type("Ctx", (), {"session_id": "sess-1"})()

    monkeypatch.setattr("db_mcp.tools.code.get_exec_session_manager", lambda: manager)

    protocol_result = await _code(
        connection=connection_name,
        code="print(dbmcp.read_protocol())",
        timeout_seconds=10,
        ctx=ctx,
    )
    discovery_result = await _code(
        connection=connection_name,
        code="print(dbmcp.find_tables('item'))",
        timeout_seconds=10,
        ctx=ctx,
    )
    query_result = await _code(
        connection=connection_name,
        code="print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
        timeout_seconds=10,
        ctx=ctx,
    )

    assert protocol_result["exit_code"] == 0
    assert "read me first" in str(protocol_result["stdout"])
    assert discovery_result["exit_code"] == 0
    assert query_result["exit_code"] == 0
    assert str(query_result["stdout"]).strip() == "3"


@pytest.mark.asyncio
async def test_code_mode_requires_confirmation_for_helper_writes(
    code_mode_connection,
    monkeypatch,
):
    connection_name, _ = code_mode_connection
    manager = ExecSessionManager(backend=ProcessExecSandboxBackend())
    ctx = type("Ctx", (), {"session_id": "sess-2"})()

    monkeypatch.setattr("db_mcp.tools.code.get_exec_session_manager", lambda: manager)

    await _code(
        connection=connection_name,
        code="print(dbmcp.read_protocol())",
        timeout_seconds=10,
        ctx=ctx,
    )
    await _code(
        connection=connection_name,
        code="print(dbmcp.find_tables('item'))",
        timeout_seconds=10,
        ctx=ctx,
    )

    result = await _code(
        connection=connection_name,
        code='dbmcp.execute("CREATE TABLE writes(id INTEGER)")',
        timeout_seconds=10,
        ctx=ctx,
    )

    assert result["status"] == "confirm_required"
    assert result["exit_code"] == 1
    assert "confirmed=True" in str(result["message"])


@pytest.mark.asyncio
async def test_code_mode_allows_confirmed_helper_writes(
    code_mode_connection,
    monkeypatch,
):
    connection_name, _ = code_mode_connection
    manager = ExecSessionManager(backend=ProcessExecSandboxBackend())
    ctx = type("Ctx", (), {"session_id": "sess-3"})()

    monkeypatch.setattr("db_mcp.tools.code.get_exec_session_manager", lambda: manager)

    await _code(
        connection=connection_name,
        code="print(dbmcp.read_protocol())",
        timeout_seconds=10,
        ctx=ctx,
    )
    await _code(
        connection=connection_name,
        code="print(dbmcp.find_tables('item'))",
        timeout_seconds=10,
        ctx=ctx,
    )

    result = await _code(
        connection=connection_name,
        code='print(dbmcp.execute("CREATE TABLE writes(id INTEGER)"))',
        confirmed=True,
        timeout_seconds=10,
        ctx=ctx,
    )

    assert result["exit_code"] == 0
    assert "statement_type" in str(result["stdout"])


def test_runtime_native_adapter_uses_shared_backend(code_mode_connection):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-1",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    protocol_result = runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    discovery_result = runtime.run("print(dbmcp.find_tables('item'))", timeout_seconds=10)
    query_result = runtime.run(
        "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
        timeout_seconds=10,
    )

    assert protocol_result.exit_code == 0
    assert "read me first" in protocol_result.stdout
    assert discovery_result.exit_code == 0
    assert query_result.exit_code == 0
    assert query_result.stdout.strip() == "3"


def test_runtime_native_adapter_exposes_structured_table_names(code_mode_connection):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-2",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    protocol_result = runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    result = runtime.run("print(dbmcp.table_names())", timeout_seconds=10)

    assert protocol_result.exit_code == 0
    assert result.exit_code == 0
    assert "items" in result.stdout


def test_runtime_native_adapter_exposes_kb_backed_discovery_helpers(code_mode_connection):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-3",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    result = runtime.run(
        "\n".join(
            [
                "import json",
                "payload = {",
                "    'tables': dbmcp.find_tables('item count'),",
                "    'columns': dbmcp.find_columns('amount'),",
                "    'examples': dbmcp.relevant_examples('count items'),",
                "    'rules': dbmcp.relevant_rules('items amount'),",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        timeout_seconds=10,
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["tables"][0]["name"] == "items"
    assert payload["columns"][0]["table"] == "items"
    assert payload["columns"][0]["name"] == "amount"
    assert payload["examples"][0]["id"] == "count_items"
    assert "items.amount" in payload["rules"][0]["text"]


def test_runtime_native_adapter_can_describe_table_from_schema_artifacts(code_mode_connection):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-4",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    result = runtime.run(
        "\n".join(
            [
                "import json",
                "print(json.dumps(dbmcp.describe_table('Items')))",
            ]
        ),
        timeout_seconds=10,
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["name"] == "items"
    assert payload["full_name"] == "main.items"
    assert payload["columns"][1]["name"] == "amount"


def test_runtime_native_adapter_exposes_find_table_and_plan(code_mode_connection):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-plan-1",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    result = runtime.run(
        "\n".join(
            [
                "import json",
                "payload = {",
                "    'table': dbmcp.find_table('items'),",
                "    'plan': dbmcp.plan('How many items are in the catalog?'),",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        timeout_seconds=10,
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["table"]["name"] == "items"
    assert payload["plan"]["table"]["name"] == "items"
    assert "COUNT(*)" in payload["plan"]["suggested_sql"]


def test_runtime_native_adapter_requires_query_before_finalize(code_mode_connection):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-finalize-1",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    runtime.run("print(dbmcp.find_tables('item'))", timeout_seconds=10)
    result = runtime.run(
        "print(dbmcp.finalize_answer(task_id='count_items', answer_value=3))",
        timeout_seconds=10,
    )

    assert result.exit_code == 1
    assert "Run the final query first" in result.stderr


def test_runtime_native_adapter_finalizes_answer_payload(code_mode_connection):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-finalize-2",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    runtime.run("print(dbmcp.find_tables('item'))", timeout_seconds=10)
    runtime.run("print(dbmcp.scalar('SELECT COUNT(*) FROM items'))", timeout_seconds=10)
    result = runtime.run(
        "\n".join(
            [
                "import json",
                "payload = dbmcp.finalize_answer(",
                "    task_id='count_items',",
                "    answer_value=3,",
                "    evidence_sql='SELECT COUNT(*) FROM items',",
                ")",
                "print(json.dumps(payload))",
            ]
        ),
        timeout_seconds=10,
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task_id"] == "count_items"
    assert payload["status"] == "answered"
    assert payload["answer_value"] == 3
    assert payload["answer_text"] == "3"
    assert payload["evidence_sql"] == "SELECT COUNT(*) FROM items"


def test_runtime_native_adapter_marks_repeated_identical_invalid_scripts_as_stuck(
    code_mode_connection,
):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-stuck-1",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    code = "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))"
    first = runtime.run(code, timeout_seconds=10)
    second = runtime.run(code, timeout_seconds=10)
    third = runtime.run(code, timeout_seconds=10)

    assert first.exit_code == 1
    assert second.exit_code == 1
    assert third.exit_code == 1
    assert third.status == "stuck"
    assert "Session is stuck" in (third.message or "")
    assert "schema_resolution" in (third.message or "")


def test_runtime_native_adapter_requires_schema_resolution_before_query(code_mode_connection):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-fsm-1",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    protocol_result = runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    query_result = runtime.run(
        "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
        timeout_seconds=10,
    )

    assert protocol_result.exit_code == 0
    assert query_result.exit_code == 1
    assert "Resolve schema first" in query_result.stderr
    assert "dbmcp.find_tables" in query_result.stderr


def test_runtime_native_adapter_requires_query_after_successful_discovery(
    code_mode_connection,
):
    connection_name, _ = code_mode_connection
    runtime = CodeModeRuntime(
        connection=connection_name,
        session_id="runtime-fsm-2",
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    protocol_result = runtime.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    discovery_result = runtime.run(
        "print(dbmcp.find_tables('item'))",
        timeout_seconds=10,
    )
    repeated_discovery = runtime.run(
        "print(dbmcp.table_names())",
        timeout_seconds=10,
    )
    final_query = runtime.run(
        "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
        timeout_seconds=10,
    )

    assert protocol_result.exit_code == 0
    assert discovery_result.exit_code == 0
    assert repeated_discovery.exit_code == 1
    assert "Run the final query next" in repeated_discovery.stderr
    assert final_query.exit_code == 0
    assert final_query.stdout.strip() == "3"


def test_code_runtime_service_shares_contract_and_execution_backend(code_mode_connection):
    connection_name, _ = code_mode_connection
    service = CodeRuntimeService(
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    contract = service.contract(connection_name)
    protocol_result = service.run(
        connection_name,
        "print(dbmcp.read_protocol())",
        session_id="service-1",
        timeout_seconds=10,
    )
    discovery_result = service.run(
        connection_name,
        "print(dbmcp.find_tables('item'))",
        session_id="service-1",
        timeout_seconds=10,
    )
    query_result = service.run(
        connection_name,
        "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
        session_id="service-1",
        timeout_seconds=10,
    )

    assert contract["kind"] == "db-mcp-code-runtime"
    assert contract["connection"] == connection_name
    assert "find_table" in contract["helper_methods"]
    assert "plan" in contract["helper_methods"]
    assert "finalize_answer" in contract["helper_methods"]
    assert protocol_result.exit_code == 0
    assert "read me first" in protocol_result.stdout
    assert discovery_result.exit_code == 0
    assert query_result.exit_code == 0
    assert query_result.stdout.strip() == "3"


def test_code_runtime_service_manages_explicit_host_sessions(code_mode_connection):
    connection_name, _ = code_mode_connection
    service = CodeRuntimeService(
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )

    session = service.create_session(connection_name, session_id="host-session-1")
    contract = service.contract_for_session(session.session_id)
    protocol_result = service.run_session(
        session.session_id,
        "print(dbmcp.read_protocol())",
        timeout_seconds=10,
    )
    discovery_result = service.run_session(
        session.session_id,
        "print(dbmcp.find_table('items'))",
        timeout_seconds=10,
    )
    query_result = service.run_session(
        session.session_id,
        "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
        timeout_seconds=10,
    )
    closed = service.close_session(session.session_id)

    assert session.session_id == "host-session-1"
    assert contract["session_id"] == "host-session-1"
    assert protocol_result.exit_code == 0
    assert discovery_result.exit_code == 0
    assert query_result.exit_code == 0
    assert query_result.stdout.strip() == "3"
    assert closed is True
    with pytest.raises(KeyError):
        service.contract_for_session(session.session_id)


def test_code_runtime_service_invokes_sdk_methods_via_connector(monkeypatch, tmp_path):
    connection_path = tmp_path / "dialect-demo"
    connection_path.mkdir(parents=True)
    (connection_path / "PROTOCOL.md").write_text("read me first\n")
    (connection_path / "connector.yaml").write_text("type: sql\n")
    (connection_path / "schema").mkdir()
    (connection_path / "schema" / "descriptions.yaml").write_text(
        yaml.safe_dump({"tables": [{"name": "items", "columns": [{"name": "amount"}]}]})
    )
    (connection_path / "domain").mkdir()
    (connection_path / "domain" / "model.md").write_text("# domain\n")
    (connection_path / "instructions").mkdir()
    (connection_path / "instructions" / "sql_rules.md").write_text("# rules\n")
    (connection_path / "instructions" / "business_rules.yaml").write_text("rules: []\n")

    class FakeConnector:
        def __init__(self) -> None:
            self.queries: list[tuple[str, dict | None]] = []

        def execute_sql(self, sql: str, params: dict | None = None):
            self.queries.append((sql, params))
            return [{"answer": 3}]

    fake_connector = FakeConnector()

    monkeypatch.setattr(
        "db_mcp.code_runtime.backend.resolve_connection",
        lambda connection: (fake_connector, "dialect-demo", str(connection_path)),
    )

    service = CodeRuntimeService(
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )
    session = service.create_session("dialect-demo", session_id="host-session-query")

    protocol = service.invoke_session_method(session.session_id, "read_protocol")
    scalar = service.invoke_session_method(
        session.session_id,
        "scalar",
        args=["SELECT COUNT(*) AS answer FROM items"],
    )
    rows = service.invoke_session_method(
        session.session_id,
        "query",
        args=["SELECT COUNT(*) AS answer FROM items"],
    )

    assert protocol == "read me first\n"
    assert scalar == 3
    assert rows == [{"answer": 3}]
    assert fake_connector.queries == [
        ("SELECT COUNT(*) AS answer FROM items", None),
        ("SELECT COUNT(*) AS answer FROM items", None),
    ]


def test_code_mode_host_uses_service_managed_session(code_mode_connection):
    connection_name, _ = code_mode_connection
    service = CodeRuntimeService(
        manager=ExecSessionManager(backend=ProcessExecSandboxBackend()),
    )
    host = CodeModeHost(
        connection=connection_name,
        session_id="host-wrapper-1",
        service=service,
    )

    contract = host.contract()
    protocol_result = host.run("print(dbmcp.read_protocol())", timeout_seconds=10)
    discovery_result = host.run("print(dbmcp.find_table('items'))", timeout_seconds=10)
    query_result = host.run(
        "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
        timeout_seconds=10,
    )
    closed = host.close()

    assert contract["session_id"] == "host-wrapper-1"
    assert protocol_result.exit_code == 0
    assert discovery_result.exit_code == 0
    assert query_result.stdout.strip() == "3"
    assert closed is True
    with pytest.raises(KeyError):
        service.get_session("host-wrapper-1")


def test_code_runtime_client_uses_session_http_api(monkeypatch):
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        calls.append((request.method, request.full_url, body))
        if request.method == "POST" and request.full_url.endswith("/api/runtime/sessions"):
            return FakeResponse(
                {
                    "kind": "db-mcp-code-runtime",
                    "connection": "demo",
                    "session_id": "client-session-1",
                }
            )
        if request.method == "GET" and request.full_url.endswith(
            "/api/runtime/sessions/client-session-1/contract"
        ):
            return FakeResponse(
                {
                    "kind": "db-mcp-code-runtime",
                    "connection": "demo",
                    "session_id": "client-session-1",
                }
            )
        if request.method == "POST" and request.full_url.endswith(
            "/api/runtime/sessions/client-session-1/sdk/scalar"
        ):
            return FakeResponse({"result": 3})
        if request.method == "POST" and request.full_url.endswith(
            "/api/runtime/sessions/client-session-1/run"
        ):
            return FakeResponse(
                {
                    "stdout": "3\n",
                    "stderr": "",
                    "exit_code": 0,
                    "duration_ms": 9.5,
                    "truncated": False,
                }
            )
        if request.method == "DELETE" and request.full_url.endswith(
            "/api/runtime/sessions/client-session-1"
        ):
            return FakeResponse({"session_id": "client-session-1", "closed": True})
        raise AssertionError(f"unexpected request: {request.method} {request.full_url}")

    monkeypatch.setattr("db_mcp.code_runtime.client.urlopen", fake_urlopen)

    client = CodeRuntimeClient("http://127.0.0.1:8765")
    session = client.create_session("demo", session_id="client-session-1")
    contract = session.contract()
    scalar = session.sdk().scalar("SELECT COUNT(*) FROM items")
    result = session.run("print(dbmcp.scalar('SELECT COUNT(*) FROM items'))", timeout_seconds=15)
    closed = session.close()

    assert session.session_id == "client-session-1"
    assert contract["connection"] == "demo"
    assert scalar == 3
    assert result.exit_code == 0
    assert result.stdout == "3\n"
    assert closed is True
    assert calls == [
        (
            "POST",
            "http://127.0.0.1:8765/api/runtime/sessions",
            {"connection": "demo", "session_id": "client-session-1"},
        ),
        (
            "GET",
            "http://127.0.0.1:8765/api/runtime/sessions/client-session-1/contract",
            None,
        ),
        (
            "POST",
            "http://127.0.0.1:8765/api/runtime/sessions/client-session-1/sdk/scalar",
            {
                "args": ["SELECT COUNT(*) FROM items", None],
                "kwargs": {},
                "confirmed": False,
            },
        ),
        (
            "POST",
            "http://127.0.0.1:8765/api/runtime/sessions/client-session-1/run",
            {
                "code": "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))",
                "timeout_seconds": 15,
                "confirmed": False,
            },
        ),
        (
            "DELETE",
            "http://127.0.0.1:8765/api/runtime/sessions/client-session-1",
            None,
        ),
    ]
