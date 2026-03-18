"""Shared runtime service used by MCP, CLI, and UI adapters."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from db_mcp.code_runtime.backend import CodeResult, HostDbMcpRuntime
from db_mcp.code_runtime.interface import (
    RUNTIME_INTERFACE_NATIVE,
    RuntimeInterface,
    build_runtime_contract,
    build_runtime_instructions,
)
from db_mcp.code_runtime.runtime import CodeModeRuntime
from db_mcp.exec_runtime import ExecSessionManager, get_exec_session_manager


@dataclass(frozen=True)
class CodeRuntimeHostSession:
    """Host-managed runtime session."""

    session_id: str
    connection: str


@dataclass
class CodeRuntimeService:
    """Connection-scoped service facade over the shared code runtime."""

    manager: ExecSessionManager = field(default_factory=get_exec_session_manager)
    _sessions: dict[str, CodeRuntimeHostSession] = field(default_factory=dict)
    _host_runtimes: dict[str, HostDbMcpRuntime] = field(default_factory=dict)

    def instructions(
        self,
        connection: str,
        *,
        interface: RuntimeInterface = RUNTIME_INTERFACE_NATIVE,
    ) -> str:
        return build_runtime_instructions(connection, interface=interface)

    def contract(
        self,
        connection: str,
        *,
        session_id: str | None = None,
        interface: RuntimeInterface = RUNTIME_INTERFACE_NATIVE,
    ) -> dict[str, object]:
        return build_runtime_contract(connection, interface=interface, session_id=session_id)

    def create_session(
        self,
        connection: str,
        *,
        session_id: str | None = None,
    ) -> CodeRuntimeHostSession:
        resolved_session_id = session_id or f"runtime-{uuid.uuid4()}"
        existing = self._sessions.get(resolved_session_id)
        if existing is not None:
            if existing.connection != connection:
                raise ValueError(
                    f"runtime session {resolved_session_id!r} already belongs to "
                    f"{existing.connection!r}"
                )
            return existing

        session = CodeRuntimeHostSession(
            session_id=resolved_session_id,
            connection=connection,
        )
        self._sessions[resolved_session_id] = session
        self._host_runtimes[resolved_session_id] = HostDbMcpRuntime(connection)
        return session

    def get_session(self, session_id: str) -> CodeRuntimeHostSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown runtime session: {session_id}") from exc

    def contract_for_session(
        self,
        session_id: str,
        *,
        interface: RuntimeInterface = RUNTIME_INTERFACE_NATIVE,
    ) -> dict[str, object]:
        session = self.get_session(session_id)
        return self.contract(
            session.connection,
            session_id=session.session_id,
            interface=interface,
        )

    def run(
        self,
        connection: str,
        code: str,
        *,
        session_id: str,
        timeout_seconds: int = 30,
        confirmed: bool = False,
    ) -> CodeResult:
        runtime = CodeModeRuntime(
            connection=connection,
            session_id=session_id,
            manager=self.manager,
        )
        return runtime.run(
            code,
            timeout_seconds=timeout_seconds,
            confirmed=confirmed,
        )

    def run_session(
        self,
        session_id: str,
        code: str,
        *,
        timeout_seconds: int = 30,
        confirmed: bool = False,
    ) -> CodeResult:
        session = self.get_session(session_id)
        return self.run(
            session.connection,
            code,
            session_id=session.session_id,
            timeout_seconds=timeout_seconds,
            confirmed=confirmed,
        )

    def close_session(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        self._host_runtimes.pop(session_id, None)
        if session is None:
            return False
        self.manager.close_session(session_id=session.session_id, connection=session.connection)
        return True

    def invoke_session_method(
        self,
        session_id: str,
        method: str,
        *,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
        confirmed: bool = False,
    ) -> object:
        session = self.get_session(session_id)
        runtime = self._host_runtimes.get(session_id)
        if (
            runtime is None
            or runtime.connection != session.connection
            or runtime.confirmed != confirmed
        ):
            runtime = HostDbMcpRuntime(session.connection, confirmed=confirmed)
            self._host_runtimes[session_id] = runtime

        target = getattr(runtime, method, None)
        if target is None or method.startswith("_"):
            raise AttributeError(f"unknown runtime sdk method: {method}")
        return target(*(args or []), **(kwargs or {}))


_service: CodeRuntimeService | None = None


def get_code_runtime_service() -> CodeRuntimeService:
    """Return a process-global runtime service."""
    global _service
    if _service is None:
        _service = CodeRuntimeService()
    return _service
