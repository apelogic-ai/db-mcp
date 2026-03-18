"""Claude CLI driver and command construction."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass
class DriverResult:
    """Result from a single Claude CLI invocation."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    debug_log_path: Path


@dataclass(frozen=True)
class LoopBreakerConfig:
    """Configuration for aborting obviously stuck benchmark attempts."""

    runtime_log_path: Path
    repetition_limit: int = 3
    poll_interval_seconds: float = 0.1


def build_claude_command(
    *,
    prompt: str,
    model: str,
    session_id: str,
    mcp_config_path: Path,
    json_schema: dict,
    debug_log_path: Path,
    workdir: Path,
    tools: list[str],
) -> list[str]:
    """Build the Claude Code command for one attempt."""
    return [
        "claude",
        "--print",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(json_schema, separators=(",", ":")),
        "--model",
        model,
        "--session-id",
        session_id,
        "--no-session-persistence",
        "--strict-mcp-config",
        "--mcp-config",
        str(mcp_config_path),
        "--debug-file",
        str(debug_log_path),
        "--permission-mode",
        "bypassPermissions",
        "--tools",
        ",".join(tools),
        "--",
        prompt,
    ]


class ClaudeCliDriver:
    """Subprocess-backed driver for the real Claude Code CLI."""

    def run(
        self,
        *,
        prompt: str,
        json_schema: dict,
        session_id: str,
        mcp_config_path: Path,
        model: str,
        workdir: Path,
        debug_log_path: Path,
        tools: list[str],
        env: dict[str, str] | None = None,
        loop_breaker: LoopBreakerConfig | None = None,
    ) -> DriverResult:
        command = build_claude_command(
            prompt=prompt,
            model=model,
            session_id=session_id,
            mcp_config_path=mcp_config_path,
            json_schema=json_schema,
            debug_log_path=debug_log_path,
            workdir=workdir,
            tools=tools,
        )
        started = time.time()
        process = subprocess.Popen(
            command,
            cwd=workdir,
            env={**os.environ, **(env or {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        loop_breaker_stop = threading.Event()
        loop_breaker_thread = None
        if loop_breaker is not None:
            loop_breaker_thread = threading.Thread(
                target=_watch_runtime_loop,
                args=(process.pid, loop_breaker, loop_breaker_stop),
                daemon=True,
            )
            loop_breaker_thread.start()
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except TypeError:
                    stdout, stderr = process.communicate()
                    break
                except subprocess.TimeoutExpired:
                    continue
        except KeyboardInterrupt:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
        finally:
            loop_breaker_stop.set()
            if loop_breaker_thread is not None:
                loop_breaker_thread.join(timeout=0.5)
        duration_ms = (time.time() - started) * 1000
        return DriverResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
            duration_ms=duration_ms,
            debug_log_path=debug_log_path,
        )


def _watch_runtime_loop(pid: int, config: LoopBreakerConfig, stop_event: threading.Event) -> None:
    """Abort a Claude attempt when it repeats the same runtime script too many times."""
    seen_lines = 0
    consecutive_identical = 0
    last_hash: str | None = None

    while not stop_event.wait(config.poll_interval_seconds):
        if not config.runtime_log_path.exists():
            continue
        try:
            lines = config.runtime_log_path.read_text().splitlines()
        except OSError:
            continue

        for raw_line in lines[seen_lines:]:
            seen_lines += 1
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            captured_file = payload.get("captured_file")
            if not captured_file:
                continue
            capture_path = Path(str(captured_file))
            if not capture_path.exists():
                continue
            try:
                content = capture_path.read_text()
            except OSError:
                continue
            content_hash = sha256(content.encode("utf-8")).hexdigest()
            if content_hash == last_hash:
                consecutive_identical += 1
            else:
                last_hash = content_hash
                consecutive_identical = 1

            if consecutive_identical >= config.repetition_limit:
                try:
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                return
