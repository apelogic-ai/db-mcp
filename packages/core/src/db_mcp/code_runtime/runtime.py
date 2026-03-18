"""Runtime-native adapter over the shared code runtime backend."""

from __future__ import annotations

from dataclasses import dataclass, field

from db_mcp.code_runtime.backend import CodeResult, CodeSession, create_code_session, run_code
from db_mcp.exec_runtime import ExecSessionManager, get_exec_session_manager


@dataclass
class CodeModeRuntime:
    """Host-facing runtime adapter for shared code execution."""

    connection: str
    session_id: str
    manager: ExecSessionManager = field(default_factory=get_exec_session_manager)

    def create_session(self) -> CodeSession:
        return create_code_session(self.connection, self.session_id)

    def run(
        self,
        code: str,
        *,
        timeout_seconds: int = 30,
        confirmed: bool = False,
    ) -> CodeResult:
        session = self.create_session()
        return run_code(
            session,
            code,
            timeout_seconds=timeout_seconds,
            confirmed=confirmed,
            manager=self.manager,
        )
