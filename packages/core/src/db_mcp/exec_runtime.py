"""Execution runtime backends for exec-only mode."""

from __future__ import annotations

import os
import shlex
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Protocol
from urllib.parse import urlparse

from sqlalchemy.engine import make_url

DEFAULT_EXEC_IMAGE = "db-mcp-exec:latest"
DEFAULT_IDLE_TTL_SECONDS = 900
DEFAULT_MAX_SESSIONS = 16
DEFAULT_OUTPUT_CHARS = 64_000
DEFAULT_RUNTIME_ORDER = ("podman", "nerdctl", "docker")

DEFAULT_PORTS = {
    "clickhouse": 9000,
    "duckdb": None,
    "http": 80,
    "https": 443,
    "mssql": 1433,
    "mysql": 3306,
    "postgres": 5432,
    "postgresql": 5432,
    "pymssql": 1433,
    "sqlite": None,
    "trino": 8080,
}


class ExecRuntimeError(RuntimeError):
    """Raised when the exec runtime cannot create or use a sandbox."""


@dataclass(frozen=True)
class AllowedEndpoint:
    """Single allowed outbound endpoint for a sandbox."""

    host: str
    port: int


@dataclass(frozen=True)
class ExecSandboxSpec:
    """Resolved sandbox inputs for one session+connection."""

    session_id: str
    connection: str
    connection_path: Path
    allowed_endpoint: AllowedEndpoint | None
    environment: dict[str, str]


@dataclass(frozen=True)
class ExecResult:
    """Normalized exec result returned to the MCP tool."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 3),
            "truncated": self.truncated,
        }


class ExecSandboxBackend(Protocol):
    """Backend interface for session-scoped sandboxes."""

    def create_session(self, spec: ExecSandboxSpec) -> str: ...

    def exec_command(
        self,
        container_id: str,
        command: str,
        timeout_seconds: int,
    ) -> ExecResult: ...

    def close_session(self, container_id: str) -> None: ...


@dataclass
class _ActiveSession:
    container_id: str
    spec: ExecSandboxSpec
    last_used_at: float


def derive_allowed_endpoint(
    database_url: str | None,
    *,
    base_url: str | None = None,
) -> AllowedEndpoint | None:
    """Derive the single allowed outbound endpoint for a connection."""
    if base_url:
        parsed = urlparse(base_url)
        if not parsed.hostname:
            return None
        scheme = (parsed.scheme or "https").lower()
        port = parsed.port or DEFAULT_PORTS.get(scheme)
        if port is None:
            return None
        return AllowedEndpoint(host=parsed.hostname, port=port)

    if not database_url:
        return None

    try:
        url = make_url(database_url)
    except Exception:
        parsed = urlparse(database_url)
        if not parsed.hostname:
            return None
        scheme = (parsed.scheme or "").split("+", 1)[0].lower()
        port = parsed.port or DEFAULT_PORTS.get(scheme)
        if port is None:
            return None
        return AllowedEndpoint(host=parsed.hostname, port=port)

    dialect = url.drivername.split("+", 1)[0].lower()
    if dialect in {"sqlite", "duckdb"}:
        return None
    if not url.host:
        return None
    port = url.port or DEFAULT_PORTS.get(dialect)
    if port is None:
        return None
    return AllowedEndpoint(host=url.host, port=port)


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    omitted = len(text) - limit
    marker = f"\n...[truncated {omitted} chars]..."
    keep = max(limit - len(marker), 0)
    return text[:keep] + marker, True


def _oci_runtime_is_available(
    runtime: str,
    *,
    runner=subprocess.run,
    timeout_seconds: int = 3,
) -> bool:
    """Return whether an OCI runtime is installed and reachable."""
    if not which(runtime):
        return False

    try:
        completed = runner(
            [runtime, "info"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False

    return completed.returncode == 0


class OciExecSandboxBackend:
    """OCI runtime-backed implementation for exec-only sandboxes."""

    def __init__(
        self,
        *,
        runtime: str = "docker",
        image: str | None = None,
        output_chars: int = DEFAULT_OUTPUT_CHARS,
        runner=subprocess.run,
        clock=time.monotonic,
    ) -> None:
        self.runtime = runtime
        self.image = image or os.environ.get("DB_MCP_EXEC_IMAGE", DEFAULT_EXEC_IMAGE)
        self.output_chars = output_chars
        self._runner = runner
        self._clock = clock

    def create_session(self, spec: ExecSandboxSpec) -> str:
        container_name = self._container_name(spec)
        command = self._build_run_command(spec, container_name)
        try:
            self._runner(command, capture_output=True, text=True, check=True)
        except FileNotFoundError as exc:
            raise ExecRuntimeError(
                f"{self.runtime} is required for OCI exec mode but is not installed"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise ExecRuntimeError(f"failed to start exec sandbox: {stderr or exc}") from exc
        return container_name

    def exec_command(self, container_id: str, command: str, timeout_seconds: int) -> ExecResult:
        exec_command = self._build_exec_command(container_id, command, timeout_seconds)
        started = self._clock()
        try:
            completed = self._runner(
                exec_command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds + 2,
            )
        except FileNotFoundError as exc:
            raise ExecRuntimeError(
                f"{self.runtime} is required for OCI exec mode but is not installed"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ExecRuntimeError(
                f"exec sandbox exceeded timeout window ({timeout_seconds}s)"
            ) from exc
        duration_ms = (self._clock() - started) * 1000

        stdout, stdout_truncated = _truncate_text(completed.stdout or "", self.output_chars)
        stderr, stderr_truncated = _truncate_text(completed.stderr or "", self.output_chars)
        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            truncated=stdout_truncated or stderr_truncated,
        )

    def close_session(self, container_id: str) -> None:
        try:
            self._runner(
                [self.runtime, "rm", "-f", container_id],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return

    def _container_name(self, spec: ExecSandboxSpec) -> str:
        session_part = "".join(c for c in spec.session_id.lower() if c.isalnum())[:24] or "session"
        conn_part = "".join(c for c in spec.connection.lower() if c.isalnum())[:20] or "connection"
        return f"dbmcp-exec-{session_part}-{conn_part}"

    def _build_run_command(self, spec: ExecSandboxSpec, container_name: str) -> list[str]:
        command = [
            self.runtime,
            "run",
            "-d",
            "--rm",
            "--name",
            container_name,
            "-w",
            "/workspace",
            "-v",
            f"{spec.connection_path}:/workspace",
            "--memory",
            os.environ.get("DB_MCP_EXEC_MEMORY", "1g"),
            "--cpus",
            os.environ.get("DB_MCP_EXEC_CPUS", "1.0"),
            "--pids-limit",
            os.environ.get("DB_MCP_EXEC_PIDS_LIMIT", "128"),
            "--cap-drop",
            "ALL",
        ]

        for key, value in sorted(spec.environment.items()):
            command.extend(["-e", f"{key}={value}"])

        keepalive = self._build_keepalive_command(spec.allowed_endpoint)
        if spec.allowed_endpoint is None:
            command.extend(["--network", "none"])
        else:
            resolved_ip = socket.gethostbyname(spec.allowed_endpoint.host)
            command.extend(["--network", "bridge", "--cap-add", "NET_ADMIN"])
            command.extend(["--add-host", f"{spec.allowed_endpoint.host}:{resolved_ip}"])
            keepalive = self._build_keepalive_command(
                spec.allowed_endpoint,
                resolved_ip=resolved_ip,
            )

        command.extend([self.image, "/bin/bash", "-lc", keepalive])
        return command

    def _build_exec_command(
        self,
        container_id: str,
        command: str,
        timeout_seconds: int,
    ) -> list[str]:
        return [
            self.runtime,
            "exec",
            "-w",
            "/workspace",
            container_id,
            "timeout",
            "--signal=TERM",
            f"{timeout_seconds}s",
            "/bin/bash",
            "-lc",
            command,
        ]

    def _build_keepalive_command(
        self,
        endpoint: AllowedEndpoint | None,
        *,
        resolved_ip: str | None = None,
    ) -> str:
        keepalive = "trap 'exit 0' TERM INT; while true; do sleep 3600; done"
        if endpoint is None or resolved_ip is None:
            return keepalive
        return (
            "iptables -P OUTPUT DROP"
            " && iptables -A OUTPUT -o lo -j ACCEPT"
            " && iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT"
            f" && iptables -A OUTPUT -p tcp -d {shlex.quote(resolved_ip)}"
            f" --dport {endpoint.port} -j ACCEPT"
            f" && {keepalive}"
        )


class ProcessExecSandboxBackend:
    """Best-effort local process backend when no OCI runtime is available."""

    def __init__(
        self,
        *,
        output_chars: int = DEFAULT_OUTPUT_CHARS,
        clock=time.monotonic,
    ) -> None:
        self.output_chars = output_chars
        self._clock = clock
        self._sessions: dict[str, ExecSandboxSpec] = {}

    def create_session(self, spec: ExecSandboxSpec) -> str:
        session_key = self._session_key(spec)
        self._sessions[session_key] = spec
        return session_key

    def exec_command(self, container_id: str, command: str, timeout_seconds: int) -> ExecResult:
        spec = self._sessions.get(container_id)
        if spec is None:
            raise ExecRuntimeError(f"unknown exec session: {container_id}")

        env = {
            "PATH": os.environ.get(
                "DB_MCP_EXEC_PATH",
                "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            ),
            "HOME": str(spec.connection_path),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        env.update(spec.environment)

        started = self._clock()
        process = subprocess.Popen(
            ["/bin/bash", "-lc", command],
            cwd=spec.connection_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self._terminate_process_group(process.pid)
            raise ExecRuntimeError(f"process exec timeout after {timeout_seconds}s") from exc

        self._terminate_process_group(process.pid)
        duration_ms = (self._clock() - started) * 1000
        stdout, stdout_truncated = _truncate_text(stdout or "", self.output_chars)
        stderr, stderr_truncated = _truncate_text(stderr or "", self.output_chars)
        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
            duration_ms=duration_ms,
            truncated=stdout_truncated or stderr_truncated,
        )

    def close_session(self, container_id: str) -> None:
        self._sessions.pop(container_id, None)

    def _session_key(self, spec: ExecSandboxSpec) -> str:
        return f"process:{spec.session_id}:{spec.connection}"

    def _terminate_process_group(self, pid: int) -> None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError:
            return


def auto_detect_exec_backend() -> ExecSandboxBackend:
    """Pick the strongest available exec backend on this machine."""
    forced = os.environ.get("DB_MCP_EXEC_BACKEND", "auto").strip().lower()
    if forced == "process":
        return ProcessExecSandboxBackend()

    runtimes = DEFAULT_RUNTIME_ORDER if forced == "auto" else (forced,)
    for runtime in runtimes:
        if runtime in {"docker", "podman", "nerdctl"} and _oci_runtime_is_available(runtime):
            return OciExecSandboxBackend(runtime=runtime)

    return ProcessExecSandboxBackend()


class ExecSessionManager:
    """Reuses one sandbox per MCP session and connection."""

    def __init__(
        self,
        *,
        backend: ExecSandboxBackend,
        idle_ttl_seconds: int = DEFAULT_IDLE_TTL_SECONDS,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        now=time.monotonic,
    ) -> None:
        self._backend = backend
        self._idle_ttl_seconds = idle_ttl_seconds
        self._max_sessions = max_sessions
        self._now = now
        self._sessions: dict[tuple[str, str], _ActiveSession] = {}

    def execute(
        self,
        *,
        session_id: str,
        spec: ExecSandboxSpec,
        command: str,
        timeout_seconds: int,
    ) -> dict[str, object]:
        self.reap_idle_sessions()

        key = (session_id, spec.connection)
        active = self._sessions.get(key)
        if active is None:
            self._evict_if_needed()
            active = _ActiveSession(
                container_id=self._backend.create_session(spec),
                spec=spec,
                last_used_at=self._now(),
            )
            self._sessions[key] = active

        result = self._backend.exec_command(active.container_id, command, timeout_seconds)
        active.last_used_at = self._now()
        return result.to_dict()

    def reap_idle_sessions(self) -> None:
        cutoff = self._now() - self._idle_ttl_seconds
        expired = [key for key, active in self._sessions.items() if active.last_used_at < cutoff]
        for key in expired:
            active = self._sessions.pop(key)
            self._backend.close_session(active.container_id)

    def close_all(self) -> None:
        for active in self._sessions.values():
            self._backend.close_session(active.container_id)
        self._sessions.clear()

    def _evict_if_needed(self) -> None:
        if len(self._sessions) < self._max_sessions:
            return
        oldest_key, oldest_session = min(
            self._sessions.items(),
            key=lambda item: item[1].last_used_at,
        )
        self._backend.close_session(oldest_session.container_id)
        self._sessions.pop(oldest_key, None)


_manager: ExecSessionManager | None = None


def get_exec_session_manager() -> ExecSessionManager:
    """Return the process-global exec session manager."""
    global _manager
    if _manager is None:
        _manager = ExecSessionManager(backend=auto_detect_exec_backend())
    return _manager


def shutdown_exec_session_manager() -> None:
    """Close all live sandboxes and clear the global manager."""
    global _manager
    if _manager is None:
        return
    _manager.close_all()
    _manager = None
