from __future__ import annotations

import sys
from pathlib import Path

from db_mcp.exec_runtime import (
    AllowedEndpoint,
    ExecResult,
    ExecSandboxSpec,
    ExecSessionManager,
    OciExecSandboxBackend,
    ProcessExecSandboxBackend,
    auto_detect_exec_backend,
    derive_allowed_endpoint,
)


class FakeBackend:
    def __init__(self) -> None:
        self.created: list[ExecSandboxSpec] = []
        self.executed: list[tuple[str, str, int]] = []
        self.closed: list[str] = []

    def create_session(self, spec: ExecSandboxSpec) -> str:
        self.created.append(spec)
        return f"ctr-{len(self.created)}"

    def exec_command(self, container_id: str, command: str, timeout_seconds: int) -> ExecResult:
        self.executed.append((container_id, command, timeout_seconds))
        return ExecResult(
            stdout=f"ran:{command}",
            stderr="",
            exit_code=0,
            duration_ms=12.5,
            truncated=False,
        )

    def close_session(self, container_id: str) -> None:
        self.closed.append(container_id)


def test_derive_allowed_endpoint_for_sql_url():
    endpoint = derive_allowed_endpoint("postgresql://user:pass@warehouse.example:5432/analytics")
    assert endpoint == AllowedEndpoint(host="warehouse.example", port=5432)


def test_derive_allowed_endpoint_for_base_url():
    endpoint = derive_allowed_endpoint("", base_url="https://api.example.com/v1/query")
    assert endpoint == AllowedEndpoint(host="api.example.com", port=443)


def test_derive_allowed_endpoint_for_sqlite_is_none():
    assert derive_allowed_endpoint("sqlite:////tmp/example.db") is None


def test_exec_session_manager_reuses_container_for_same_session_and_connection(tmp_path: Path):
    backend = FakeBackend()
    manager = ExecSessionManager(backend=backend)
    connection_path = tmp_path / "playground"
    connection_path.mkdir()

    result_one = manager.execute(
        session_id="sess-1",
        spec=ExecSandboxSpec(
            session_id="sess-1",
            connection="playground",
            connection_path=connection_path,
            allowed_endpoint=None,
            environment={"DATABASE_URL": "sqlite:////tmp/test.db"},
        ),
        command="pwd",
        timeout_seconds=30,
    )
    result_two = manager.execute(
        session_id="sess-1",
        spec=ExecSandboxSpec(
            session_id="sess-1",
            connection="playground",
            connection_path=connection_path,
            allowed_endpoint=None,
            environment={"DATABASE_URL": "sqlite:////tmp/test.db"},
        ),
        command="ls",
        timeout_seconds=30,
    )

    assert result_one["stdout"] == "ran:pwd"
    assert result_two["stdout"] == "ran:ls"
    assert len(backend.created) == 1
    assert backend.executed == [("ctr-1", "pwd", 30), ("ctr-1", "ls", 30)]


def test_exec_session_manager_separates_connections_within_same_session(tmp_path: Path):
    backend = FakeBackend()
    manager = ExecSessionManager(backend=backend)

    first_path = tmp_path / "one"
    second_path = tmp_path / "two"
    first_path.mkdir()
    second_path.mkdir()

    manager.execute(
        session_id="sess-1",
        spec=ExecSandboxSpec(
            session_id="sess-1",
            connection="one",
            connection_path=first_path,
            allowed_endpoint=None,
            environment={},
        ),
        command="pwd",
        timeout_seconds=30,
    )
    manager.execute(
        session_id="sess-1",
        spec=ExecSandboxSpec(
            session_id="sess-1",
            connection="two",
            connection_path=second_path,
            allowed_endpoint=None,
            environment={},
        ),
        command="pwd",
        timeout_seconds=30,
    )

    assert len(backend.created) == 2
    assert [spec.connection for spec in backend.created] == ["one", "two"]


def test_exec_session_manager_closes_idle_sessions(tmp_path: Path):
    backend = FakeBackend()
    clock = iter([100.0, 100.0, 100.0, 106.0])
    manager = ExecSessionManager(backend=backend, idle_ttl_seconds=5, now=lambda: next(clock))
    connection_path = tmp_path / "demo"
    connection_path.mkdir()

    spec = ExecSandboxSpec(
        session_id="sess-1",
        connection="demo",
        connection_path=connection_path,
        allowed_endpoint=None,
        environment={},
    )
    manager.execute(session_id="sess-1", spec=spec, command="pwd", timeout_seconds=30)
    manager.reap_idle_sessions()

    assert backend.closed == ["ctr-1"]


def test_oci_backend_uses_selected_runtime():
    backend = OciExecSandboxBackend(runtime="podman", runner=lambda *args, **kwargs: None)
    spec = ExecSandboxSpec(
        session_id="sess-1",
        connection="demo",
        connection_path=Path("/tmp/demo"),
        allowed_endpoint=None,
        environment={},
    )

    command = backend._build_run_command(spec, "ctr-1")

    assert command[0] == "podman"


def test_auto_detect_exec_backend_prefers_available_oci_runtime(monkeypatch):
    monkeypatch.delenv("DB_MCP_EXEC_BACKEND", raising=False)
    monkeypatch.setattr(
        "db_mcp.exec_runtime.which",
        lambda cmd: "/usr/bin/podman" if cmd == "podman" else None,
    )
    monkeypatch.setattr(
        "db_mcp.exec_runtime._oci_runtime_is_available",
        lambda runtime, **_: runtime == "podman",
        raising=False,
    )

    backend = auto_detect_exec_backend()

    assert isinstance(backend, OciExecSandboxBackend)
    assert backend.runtime == "podman"


def test_auto_detect_exec_backend_falls_back_when_oci_daemon_is_unreachable(monkeypatch):
    monkeypatch.delenv("DB_MCP_EXEC_BACKEND", raising=False)
    monkeypatch.setattr(
        "db_mcp.exec_runtime.which",
        lambda cmd: "/usr/bin/docker" if cmd == "docker" else None,
    )
    monkeypatch.setattr(
        "db_mcp.exec_runtime._oci_runtime_is_available",
        lambda runtime, **_: False,
        raising=False,
    )

    backend = auto_detect_exec_backend()

    assert isinstance(backend, ProcessExecSandboxBackend)


def test_auto_detect_exec_backend_falls_back_to_process(monkeypatch):
    monkeypatch.delenv("DB_MCP_EXEC_BACKEND", raising=False)
    monkeypatch.setattr("db_mcp.exec_runtime.which", lambda cmd: None)

    backend = auto_detect_exec_backend()

    assert isinstance(backend, ProcessExecSandboxBackend)


def test_process_backend_runs_command_in_connection_path_and_persists_writes(tmp_path: Path):
    backend = ProcessExecSandboxBackend()
    connection_path = tmp_path / "demo"
    connection_path.mkdir()
    spec = ExecSandboxSpec(
        session_id="sess-1",
        connection="demo",
        connection_path=connection_path,
        allowed_endpoint=None,
        environment={"FOO": "bar"},
    )

    session_id = backend.create_session(spec)
    result = backend.exec_command(
        session_id,
        "printf '%s' \"$FOO\" > note.txt && pwd",
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(connection_path)
    assert (connection_path / "note.txt").read_text() == "bar"


def test_process_backend_prefers_current_python_for_python3_commands(tmp_path: Path):
    backend = ProcessExecSandboxBackend()
    connection_path = tmp_path / "demo"
    connection_path.mkdir()
    spec = ExecSandboxSpec(
        session_id="sess-1",
        connection="demo",
        connection_path=connection_path,
        allowed_endpoint=None,
        environment={},
    )

    session_id = backend.create_session(spec)
    result = backend.exec_command(
        session_id,
        "python3 -c 'import sys; print(sys.executable)'",
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    assert Path(result.stdout.strip()).resolve() == Path(sys.executable).resolve()


def test_process_backend_uses_real_python_when_sys_executable_is_packaged_binary(
    tmp_path: Path,
    monkeypatch,
):
    backend = ProcessExecSandboxBackend()
    connection_path = tmp_path / "demo"
    connection_path.mkdir()
    spec = ExecSandboxSpec(
        session_id="sess-1",
        connection="demo",
        connection_path=connection_path,
        allowed_endpoint=None,
        environment={"DB_MCP_REAL_PYTHON": sys.executable},
    )

    monkeypatch.setattr(sys, "executable", str(connection_path / "dist" / "db-mcp"))

    session_id = backend.create_session(spec)
    result = backend.exec_command(
        session_id,
        "python3 -c 'import sys; print(sys.executable)'",
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    assert Path(result.stdout.strip()).resolve() == Path(
        spec.environment["DB_MCP_REAL_PYTHON"]
    ).resolve()


def test_process_backend_reports_timeout(tmp_path: Path):
    backend = ProcessExecSandboxBackend()
    connection_path = tmp_path / "demo"
    connection_path.mkdir()
    spec = ExecSandboxSpec(
        session_id="sess-1",
        connection="demo",
        connection_path=connection_path,
        allowed_endpoint=None,
        environment={},
    )

    session_id = backend.create_session(spec)

    try:
        backend.exec_command(session_id, "sleep 2", timeout_seconds=1)
    except Exception as exc:
        assert "timeout" in str(exc).lower()
    else:
        raise AssertionError("expected timeout error")
