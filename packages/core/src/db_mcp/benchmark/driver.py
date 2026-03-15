"""Claude CLI driver and command construction."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DriverResult:
    """Result from a single Claude CLI invocation."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    debug_log_path: Path


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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate()
        except KeyboardInterrupt:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
        duration_ms = (time.time() - started) * 1000
        return DriverResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
            duration_ms=duration_ms,
            debug_log_path=debug_log_path,
        )
