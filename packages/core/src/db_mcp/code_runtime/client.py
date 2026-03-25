"""Python client for the db-mcp host runtime HTTP API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from db_mcp.code_runtime.backend import CodeResult


def _request_json(
    method: str,
    url: str,
    payload: dict[str, object] | None = None,
    *,
    timeout: int = 30,
) -> dict[str, object]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:  # pragma: no cover - thin transport wrapper
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(body or f"Runtime server error: HTTP {exc.code}") from exc
    except URLError as exc:  # pragma: no cover - thin transport wrapper
        raise RuntimeError(f"Unable to reach runtime server: {exc.reason}") from exc

    payload_obj = json.loads(body)
    if not isinstance(payload_obj, dict):
        raise RuntimeError("Runtime server returned non-object JSON")
    return payload_obj


def _append_host_client_log(record: dict[str, object]) -> None:
    log_path = os.environ.get("DB_MCP_BENCH_RUNTIME_LOG")
    if not log_path:
        return
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(log_path).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        return


@dataclass
class RemoteDbMcpSdk:
    """Python-native facade over a persistent remote db-mcp runtime session."""

    session: "CodeRuntimeSessionClient"

    def _invoke(
        self,
        method: str,
        *args: object,
        confirmed: bool = False,
        **kwargs: object,
    ) -> object:
        _append_host_client_log(
            {
                "kind": "host_client_call",
                "method": method,
                "session_id": self.session.session_id,
                "connection": self.session.connection,
            }
        )
        payload = _request_json(
            "POST",
            (
                f"{self.session.server_url.rstrip('/')}"
                f"/api/runtime/sessions/{self.session.session_id}/sdk/{method}"
            ),
            {
                "args": list(args),
                "kwargs": kwargs,
                "confirmed": confirmed,
            },
        )
        return payload.get("result")

    def read_protocol(self) -> str:
        return str(self._invoke("read_protocol"))

    def connector(self) -> dict[str, object]:
        return dict(self._invoke("connector") or {})

    def schema_descriptions(self) -> dict[str, object]:
        return dict(self._invoke("schema_descriptions") or {})

    def table_names(self) -> list[str]:
        return list(self._invoke("table_names") or [])

    def describe_table(self, name: str) -> dict[str, object] | None:
        payload = self._invoke("describe_table", name)
        return dict(payload) if isinstance(payload, dict) else None

    def find_tables(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        return list(self._invoke("find_tables", query, limit) or [])

    def find_table(self, query: str) -> dict[str, object] | None:
        payload = self._invoke("find_table", query)
        return dict(payload) if isinstance(payload, dict) else None

    def find_columns(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        return list(self._invoke("find_columns", query, limit) or [])

    def relevant_examples(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        return list(self._invoke("relevant_examples", query, limit) or [])

    def relevant_rules(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        return list(self._invoke("relevant_rules", query, limit) or [])

    def plan(self, question: str) -> dict[str, object]:
        return dict(self._invoke("plan", question) or {})

    def answer_intent(
        self,
        intent: str,
        options: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return dict(self._invoke("answer_intent", intent, options) or {})

    def query(self, sql: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        return list(self._invoke("query", sql, params) or [])

    def scalar(self, sql: str, params: dict[str, object] | None = None) -> object:
        return self._invoke("scalar", sql, params)

    def execute(
        self,
        sql: str,
        params: dict[str, object] | None = None,
        *,
        confirmed: bool = False,
    ) -> dict[str, object]:
        return dict(self._invoke("execute", sql, params, confirmed=confirmed) or {})

    def finalize_answer(self, **kwargs: object) -> dict[str, object]:
        return dict(self._invoke("finalize_answer", **kwargs) or {})


@dataclass
class CodeRuntimeSessionClient:
    """Client for one persistent runtime session."""

    server_url: str
    connection: str
    session_id: str

    def sdk(self) -> RemoteDbMcpSdk:
        return RemoteDbMcpSdk(self)

    def contract(self) -> dict[str, object]:
        return _request_json(
            "GET",
            f"{self.server_url.rstrip('/')}/api/runtime/sessions/{self.session_id}/contract",
        )

    def run(
        self,
        code: str,
        *,
        timeout_seconds: int = 30,
        confirmed: bool = False,
    ) -> CodeResult:
        payload = _request_json(
            "POST",
            f"{self.server_url.rstrip('/')}/api/runtime/sessions/{self.session_id}/run",
            {
                "code": code,
                "timeout_seconds": timeout_seconds,
                "confirmed": confirmed,
            },
            timeout=timeout_seconds + 5,
        )
        return CodeResult(
            stdout=str(payload.get("stdout", "") or ""),
            stderr=str(payload.get("stderr", "") or ""),
            exit_code=int(payload.get("exit_code", 1) or 0),
            duration_ms=float(payload.get("duration_ms", 0.0) or 0.0),
            truncated=bool(payload.get("truncated", False)),
            status=str(payload.get("status", "completed") or "completed"),
            message=(
                str(payload.get("message"))
                if payload.get("message") is not None
                else None
            ),
        )

    def close(self) -> bool:
        payload = _request_json(
            "DELETE",
            f"{self.server_url.rstrip('/')}/api/runtime/sessions/{self.session_id}",
        )
        return bool(payload.get("closed", False))


@dataclass
class CodeRuntimeClient:
    """Top-level client for creating persistent runtime sessions."""

    server_url: str

    def create_session(
        self,
        connection: str,
        *,
        session_id: str | None = None,
    ) -> CodeRuntimeSessionClient:
        payload = _request_json(
            "POST",
            f"{self.server_url.rstrip('/')}/api/runtime/sessions",
            {"connection": connection, "session_id": session_id},
        )
        resolved_session_id = str(payload["session_id"])
        return CodeRuntimeSessionClient(
            server_url=self.server_url,
            connection=connection,
            session_id=resolved_session_id,
        )
