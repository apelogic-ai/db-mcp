"""Shared runtime service used by MCP, CLI, and UI adapters."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from db_mcp.code_runtime.backend import CodeResult
from db_mcp.code_runtime.contract import build_code_mode_contract, build_code_mode_instructions
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

    def instructions(self, connection: str) -> str:
        return build_code_mode_instructions(connection)

    def contract(self, connection: str, *, session_id: str | None = None) -> dict[str, object]:
        return build_code_mode_contract(connection, session_id=session_id)

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
        return session

    def get_session(self, session_id: str) -> CodeRuntimeHostSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown runtime session: {session_id}") from exc

    def contract_for_session(self, session_id: str) -> dict[str, object]:
        session = self.get_session(session_id)
        return self.contract(session.connection, session_id=session.session_id)

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
        if session is None:
            return False
        self.manager.close_session(session_id=session.session_id, connection=session.connection)
        return True


_service: CodeRuntimeService | None = None


def get_code_runtime_service() -> CodeRuntimeService:
    """Return a process-global runtime service."""
    global _service
    if _service is None:
        _service = CodeRuntimeService()
    return _service
