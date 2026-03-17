"""Host-facing helpers for the non-MCP code runtime surface."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from db_mcp.code_runtime.backend import CodeResult
from db_mcp.code_runtime.service import CodeRuntimeHostSession, CodeRuntimeService
from db_mcp.exec_runtime import ExecSessionManager, get_exec_session_manager


@dataclass
class CodeModeHost:
    """Small host integration wrapper over the shared code runtime."""

    connection: str
    session_id: str | None = None
    manager: ExecSessionManager | None = None
    service: CodeRuntimeService | None = None
    session: CodeRuntimeHostSession | None = None

    def __post_init__(self) -> None:
        if self.session_id is None:
            self.session_id = f"runtime-{uuid.uuid4()}"
        if self.manager is None:
            self.manager = get_exec_session_manager()
        if self.service is None:
            self.service = CodeRuntimeService(manager=self.manager)
        self.session = (self.service or CodeRuntimeService()).create_session(
            self.connection,
            session_id=self.session_id,
        )
        self.session_id = self.session.session_id

    def instructions(self) -> str:
        return (self.service or CodeRuntimeService()).instructions(self.connection)

    def contract(self) -> dict[str, object]:
        return (self.service or CodeRuntimeService()).contract_for_session(
            self.session_id or "runtime",
        )

    def run(
        self,
        code: str,
        *,
        timeout_seconds: int = 30,
        confirmed: bool = False,
    ) -> CodeResult:
        return (self.service or CodeRuntimeService()).run_session(
            self.session_id or "runtime",
            code,
            timeout_seconds=timeout_seconds,
            confirmed=confirmed,
        )

    def run_file(
        self,
        path: str | Path,
        *,
        timeout_seconds: int = 30,
        confirmed: bool = False,
    ) -> CodeResult:
        file_path = Path(path)
        return self.run(
            file_path.read_text(),
            timeout_seconds=timeout_seconds,
            confirmed=confirmed,
        )

    def close(self) -> bool:
        return (self.service or CodeRuntimeService()).close_session(
            self.session_id or "runtime",
        )
