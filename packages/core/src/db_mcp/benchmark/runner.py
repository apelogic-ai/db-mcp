"""Benchmark runner and report generation."""

from __future__ import annotations

import ast
import csv
import json
import os
import random
import re
import signal
import socket
import subprocess
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any
from urllib.request import urlopen

from db_mcp.benchmark.connection import resolve_sql_connection_access
from db_mcp.benchmark.driver import ClaudeCliDriver, LoopBreakerConfig
from db_mcp.benchmark.loader import load_case_pack
from db_mcp.benchmark.models import BenchmarkAnswer
from db_mcp.benchmark.scoring import execute_gold_sql, score_case
from db_mcp.cli.utils import get_db_mcp_binary_path
from db_mcp.code_runtime.native_adapter import CodeRuntimeNativeAdapter
from db_mcp.traces import get_user_id_from_config

DB_MCP_SCENARIO = "db_mcp"
EXEC_ONLY_SCENARIO = "exec_only"
CODE_MODE_SCENARIO = "code_mode"
RUNTIME_CODE_SCENARIO = "runtime_code"
RUNTIME_NATIVE_SCENARIO = "runtime_native"
RAW_DSN_SCENARIO = "raw_dsn"
SCENARIOS = [
    DB_MCP_SCENARIO,
    EXEC_ONLY_SCENARIO,
    CODE_MODE_SCENARIO,
    RUNTIME_CODE_SCENARIO,
    RUNTIME_NATIVE_SCENARIO,
    RAW_DSN_SCENARIO,
]
DEFAULT_TOOLS = ["Read", "Bash"]
EXEC_ONLY_TOOLS = [""]
CODE_MODE_TOOLS = [""]
RUNTIME_CODE_TOOLS = ["Bash"]
RUNTIME_NATIVE_TOOLS = ["Bash"]
CODE_MODE_SKILL_NAME = "db-mcp-code-benchmark"
RUNTIME_CODE_SKILL_NAME = "db-mcp-runtime-benchmark"
RUNTIME_NATIVE_SKILL_NAME = "db-mcp-runtime-native-benchmark"
RUNTIME_SERVER_READY_TIMEOUT_SECONDS = 30.0


def _mask_database_url(database_url: str) -> str:
    return re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", database_url)


def _json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _resolve_benchmark_db_mcp_binary() -> str:
    configured = os.environ.get("DB_MCP_BENCHMARK_BINARY")
    if configured:
        return configured

    repo_dist_binary = Path(__file__).resolve().parents[3] / "dist" / "db-mcp"
    if repo_dist_binary.exists():
        return str(repo_dist_binary)

    resolved = which(get_db_mcp_binary_path())
    if resolved:
        return resolved

    return get_db_mcp_binary_path()


def _build_empty_mcp_config(path: Path) -> None:
    path.write_text(json.dumps({"mcpServers": {}}, indent=2) + "\n")


def _build_db_mcp_config(path: Path, *, connection_name: str, connections_dir: Path) -> None:
    payload = {
        "mcpServers": {
            "db-mcp": {
                "command": _resolve_benchmark_db_mcp_binary(),
                "args": ["start", "-c", connection_name],
                "env": {
                    "CONNECTIONS_DIR": str(connections_dir),
                    "CONNECTION_NAME": connection_name,
                },
            }
        }
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _build_exec_only_mcp_config(
    path: Path,
    *,
    connection_name: str,
    connections_dir: Path,
) -> None:
    payload = {
        "mcpServers": {
            "db-mcp": {
                "command": _resolve_benchmark_db_mcp_binary(),
                "args": ["start", "-c", connection_name, "--mode", "exec-only"],
                "env": {
                    "CONNECTIONS_DIR": str(connections_dir),
                    "CONNECTION_NAME": connection_name,
                },
            }
        }
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _build_code_mode_mcp_config(
    path: Path,
    *,
    connection_name: str,
    connections_dir: Path,
) -> None:
    payload = {
        "mcpServers": {
            "db-mcp": {
                "command": _resolve_benchmark_db_mcp_binary(),
                "args": ["start", "-c", connection_name, "--mode", "code"],
                "env": {
                    "CONNECTIONS_DIR": str(connections_dir),
                    "CONNECTION_NAME": connection_name,
                },
            }
        }
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _build_prompt(
    case,
    scenario: str,
    connection_name: str,
    database_url: str,
    connect_args: dict[str, Any] | None,
    *,
    runtime_server_url: str | None = None,
    runtime_session_id: str | None = None,
) -> str:
    base = (
        "You are running a benchmark case. "
        "You may take as many tool or shell actions as needed before returning a final answer. "
        "Return only JSON matching the provided schema.\n\n"
        f"Task ID: {case.id}\n"
        f"Question: {case.prompt}\n"
    )
    if scenario == DB_MCP_SCENARIO:
        return base + (
            "\nUse the available db-mcp tools and any built-in tools if helpful. "
            "Do not ask for clarification; produce your best answer."
        )
    if scenario == EXEC_ONLY_SCENARIO:
        return base + (
            "\nYou have db-mcp available only through one MCP tool: "
            '`exec(connection="...", command="...")`.\n'
            "Start by reading PROTOCOL.md with:\n"
            '`exec(connection="...", command="cat PROTOCOL.md")`\n'
            "Use exec for all further inspection and querying. "
            "Do not rely on any built-in tools.\n"
            "Do not ask for clarification; produce your best answer."
        )
    if scenario == CODE_MODE_SCENARIO:
        return base + (
            f"\nFirst, load the project skill `/{CODE_MODE_SKILL_NAME}` and follow it.\n"
            "\nYou have db-mcp available only through one MCP tool: "
            '`code(connection="...", code="...")`.\n'
            "Start by reading PROTOCOL.md with:\n"
            '`code(connection="...", code="print(dbmcp.read_protocol())")`\n'
            "Inside code mode, a Python helper object `dbmcp` is already available.\n"
            "`dbmcp.read_protocol()` returns markdown text, not a structured schema object.\n"
            "Use schema helpers like dbmcp.find_table(...), dbmcp.describe_table(...), "
            "dbmcp.find_columns(...), dbmcp.schema_descriptions(), and dbmcp.table_names() "
            "to inspect the schema, then write the SQL yourself.\n"
            "Use dbmcp.connector(), dbmcp.query(sql), dbmcp.scalar(sql), and "
            "dbmcp.execute(sql) as needed.\n"
            "Do not guess table or column names if the helper methods can resolve them.\n"
            "Do not use dbmcp.plan(...) to generate SQL for you.\n"
            "Do not use dbmcp.finalize_answer(...). Print the final JSON object yourself.\n"
            "Use code for all further inspection and querying. "
            "Do not rely on any built-in tools.\n"
            "Do not ask for clarification; produce your best answer."
        )
    if scenario == RUNTIME_CODE_SCENARIO:
        if runtime_server_url is None or runtime_session_id is None:
            raise ValueError(
                "runtime_code prompt requires runtime_server_url and "
                "runtime_session_id"
            )
        return base + (
            f"\nFirst, load the project skill `/{RUNTIME_CODE_SKILL_NAME}` and follow it.\n"
            "\nA persistent db-mcp runtime server is already running for this attempt.\n"
            "Use Bash to write and run Python files locally.\n"
            "A helper module `dbmcp_host.py` is already present in the working directory.\n"
            "Start your script with:\n"
            "```python\n"
            "from dbmcp_host import dbmcp\n"
            "_ = dbmcp.read_protocol()\n"
            "```\n"
            "Run the script with:\n"
            "`python3 /tmp/dbmcp_runtime.py`\n"
            "A good file shape is:\n"
            "```python\n"
            "import json\n"
            "from dbmcp_host import dbmcp\n"
            "_ = dbmcp.read_protocol()\n"
            "customer = dbmcp.describe_table(\"Customer\")\n"
            "value = dbmcp.scalar(\"SELECT COUNT(*) AS answer FROM Customer\")\n"
            "print(json.dumps({\n"
            "    \"task_id\": \"...\",\n"
            "    \"status\": \"answered\",\n"
            "    \"answer_value\": value,\n"
            "    \"answer_text\": str(value),\n"
            "    \"evidence_sql\": \"SELECT ...\",\n"
            "    \"confidence\": 1.0,\n"
            "    \"failure_reason\": None,\n"
            "})))\n"
            "```\n"
            "The first executable statement in the first runtime script must be "
            "`_ = dbmcp.read_protocol()`.\n"
            "After the protocol acknowledgment, inspect schema with `dbmcp.find_table(...)`, "
            "`dbmcp.describe_table(...)`, `dbmcp.find_columns(...)`, or "
            "`dbmcp.schema_descriptions()` and then write the SQL yourself.\n"
            "For scalar questions, prefer a direct `dbmcp.scalar(\"SELECT ...\")` query.\n"
            "Do not use `dbmcp.plan(...)` to generate SQL for you.\n"
            "If you are not sure about the exact table or column name, use "
            "`dbmcp.find_table(...)`, `dbmcp.describe_table(...)`, "
            "`dbmcp.find_columns(...)`, or `dbmcp.schema_descriptions()` instead of guessing.\n"
            "Do not guess table or column names if the helper methods can resolve them.\n"
            "If you use discovery, do it once, then immediately run the final query.\n"
            "Do not rerun an identical discovery script after it succeeds.\n"
            "`dbmcp.read_protocol()` returns markdown text, not a structured schema object.\n"
            "Do not use `dbmcp.finalize_answer(...)`. Print the final JSON object yourself.\n"
            "Your printed JSON must include at least `\"task_id\"`, `\"status\"`, and "
            "`\"answer_text\"`.\n"
            "Do not print the full protocol or full schema unless you are blocked. "
            "Print only the minimal result you need for the final answer.\n"
            "Keep using the same `dbmcp` object from `dbmcp_host.py` throughout the attempt.\n"
            "Use Bash only to write and run the Python script in this scenario.\n"
            "Do not ask for clarification; produce your best answer."
        )
    if scenario == RUNTIME_NATIVE_SCENARIO:
        if runtime_server_url is None or runtime_session_id is None:
            raise ValueError(
                "runtime_native prompt requires runtime_server_url and "
                "runtime_session_id"
            )
        return base + (
            f"\nFirst, load the project skill `/{RUNTIME_NATIVE_SKILL_NAME}` and follow it.\n"
            "\nA persistent native db-mcp runtime host is already active for this attempt.\n"
            "Use Bash only to write and run local Python files with `python3`.\n"
            "Inside Python, dbmcp is already available as a global native object.\n"
            "Do not import `dbmcp` or `dbmcp_host`.\n"
            "Start your first script with:\n"
            "```python\n"
            "_ = dbmcp.read_protocol()\n"
            "```\n"
            "Run the script with:\n"
            "`python3 /tmp/dbmcp_runtime_native.py`\n"
            "A good file shape is:\n"
            "```python\n"
            "import json\n"
            "_ = dbmcp.read_protocol()\n"
            "customer = dbmcp.describe_table(\"Customer\")\n"
            "value = dbmcp.scalar(\"SELECT COUNT(*) AS answer FROM Customer\")\n"
            "print(json.dumps({\n"
            "    \"task_id\": \"...\",\n"
            "    \"status\": \"answered\",\n"
            "    \"answer_value\": value,\n"
            "    \"answer_text\": str(value),\n"
            "    \"evidence_sql\": \"SELECT ...\",\n"
            "    \"confidence\": 1.0,\n"
            "    \"failure_reason\": None,\n"
            "})))\n"
            "```\n"
            "The first executable statement in the first runtime script must be "
            "`_ = dbmcp.read_protocol()`.\n"
            "After the protocol acknowledgment, inspect schema with `dbmcp.find_table(...)`, "
            "`dbmcp.describe_table(...)`, `dbmcp.find_columns(...)`, or "
            "`dbmcp.schema_descriptions()` and then write the SQL yourself.\n"
            "For scalar questions, prefer a direct `dbmcp.scalar(\"SELECT ...\")` query.\n"
            "Do not use `dbmcp.plan(...)` to generate SQL for you.\n"
            "Do not use `dbmcp.finalize_answer(...)`. Print the final JSON object yourself.\n"
            "If discovery succeeds, do it once, then run the final query next.\n"
            "Do not guess table or column names if the helper methods can resolve them.\n"
            "Do not print the full protocol or full schema unless blocked.\n"
            "Your printed JSON must include at least `\"task_id\"`, `\"status\"`, and "
            "`\"answer_text\"`.\n"
            "Do not ask for clarification; produce your best answer."
        )

    raw_block = {
        "database_url": database_url,
        "connect_args": connect_args or {},
    }
    return base + (
        "\nYou do not have db-mcp. "
        "You only have the database connection details below and built-in tools.\n"
        f"{json.dumps(raw_block, indent=2)}\n"
        "Use Bash if needed, including Python with SQLAlchemy, to inspect the database and answer."
    )


def _parse_raw_debug_metrics(debug_log_path: Path) -> dict[str, int]:
    text = debug_log_path.read_text() if debug_log_path.exists() else ""
    bash_calls = len(
        re.findall(
            r'(?:tool_name"?\s*[:=]\s*"?Bash"?|executePreToolHooks called for tool: Bash)',
            text,
        )
    )
    read_calls = len(
        re.findall(
            r'(?:tool_name"?\s*[:=]\s*"?Read"?|executePreToolHooks called for tool: Read)',
            text,
        )
    )
    exec_calls = len(
        re.findall(
            r'(?:tool_name"?\s*[:=]\s*"?(?:mcp__[^"\n]*__)?exec"?|'
            r"executePreToolHooks called for tool: mcp__db-mcp__exec)",
            text,
        )
    )
    code_calls = len(
        re.findall(
            r'(?:tool_name"?\s*[:=]\s*"?(?:mcp__[^"\n]*__)?code"?|'
            r"executePreToolHooks called for tool: mcp__db-mcp__code)",
            text,
        )
    )
    failures = len(
        re.findall(
            r'(?:status"?\s*[:=]\s*"?error"?|validation error|Tool call failed)',
            text,
            re.IGNORECASE,
        )
    )
    db_exec = len(re.findall(r"(sqlite3|psql|mysql|sqlalchemy|duckdb|trino)", text, re.IGNORECASE))
    return {
        "exploratory_steps": bash_calls + read_calls + exec_calls + code_calls,
        "failed_executions": failures,
        "db_executions": db_exec,
    }


def _materialize_benchmark_skill(attempt_dir: Path, scenario: str, connection_name: str) -> None:
    if scenario not in {CODE_MODE_SCENARIO, RUNTIME_CODE_SCENARIO, RUNTIME_NATIVE_SCENARIO}:
        return

    skill_name = (
        CODE_MODE_SKILL_NAME
        if scenario == CODE_MODE_SCENARIO
        else (
            RUNTIME_CODE_SKILL_NAME
            if scenario == RUNTIME_CODE_SCENARIO
            else RUNTIME_NATIVE_SKILL_NAME
        )
    )
    skill_dir = attempt_dir / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    if scenario == CODE_MODE_SCENARIO:
        body = f"""# {skill_name}

Use this skill for db-mcp benchmark tasks in MCP code mode.

Workflow:
1. Start by reading the protocol with
   `code(connection="{connection_name}", code="print(dbmcp.read_protocol())")`.
2. Stay inside the `code(...)` MCP tool for all inspection and querying.
3. `dbmcp.read_protocol()` returns markdown text, not a structured schema object.
4. Use `dbmcp.find_table(...)`, `dbmcp.describe_table(...)`,
   `dbmcp.find_columns(...)`, `dbmcp.schema_descriptions()`, and
   `dbmcp.table_names()` to inspect the schema, then write the SQL yourself.
5. Do not guess table or column names if the helper methods can resolve them.
6. Prefer the built-in helper object `dbmcp` over manual connector parsing or raw SQLAlchemy setup.
7. For scalar questions, prefer `print(dbmcp.scalar("SELECT ..."))`.
8. Do not use `dbmcp.plan(...)` to generate SQL for you.
9. Do not use `dbmcp.finalize_answer(...)`. Print the final JSON object yourself.
10. Return only the required final JSON.
"""
    elif scenario == RUNTIME_CODE_SCENARIO:
        body = f"""# {skill_name}

Use this skill for db-mcp benchmark tasks in native runtime mode.

Workflow:
1. Use Bash to write a temporary Python script and run it with `python3`.
2. Import the preconfigured runtime object with `from dbmcp_host import dbmcp`.
3. The first executable statement in the first script must be `_ = dbmcp.read_protocol()`.
4. After protocol acknowledgment, inspect schema with `dbmcp.find_table(...)`,
   `dbmcp.describe_table(...)`, `dbmcp.find_columns(...)`, or
   `dbmcp.schema_descriptions()` and then write the SQL yourself.
5. For scalar questions, prefer
   `value = dbmcp.scalar("SELECT ...")`
   after that schema step.
6. Do not use `dbmcp.plan(...)` to generate SQL for you.
7. If you are not sure about the exact table or column name, use
   `dbmcp.find_table(...)`, `dbmcp.describe_table(...)`,
   `dbmcp.find_columns(...)`, or `dbmcp.schema_descriptions()` instead of guessing.
8. If discovery succeeds, do not repeat it. Run the final query next.
9. Do not use `dbmcp.finalize_answer(...)`. Print the final JSON object yourself.
10. `dbmcp.read_protocol()` returns markdown text.
11. For schema discovery, prefer helper methods over guessing names.
12. Acknowledge the protocol silently with `_ = dbmcp.read_protocol()`.
13. Do not print the full protocol or full schema unless you are blocked.
14. Your JSON must include `"task_id"`, `"status"`, and `"answer_text"`.
15. Return only the required final JSON.
"""
    else:
        body = f"""# {skill_name}

Use this skill for db-mcp benchmark tasks in native runtime host mode.

Workflow:
1. Use Bash to write a temporary Python script and run it with `python3`.
2. Inside Python, `dbmcp` is already available as a global object. Do not import it.
3. The first executable statement in the first script must be `_ = dbmcp.read_protocol()`.
4. After protocol acknowledgment, inspect schema with `dbmcp.find_table(...)`,
   `dbmcp.describe_table(...)`, `dbmcp.find_columns(...)`, or
   `dbmcp.schema_descriptions()` and then write the SQL yourself.
5. For scalar questions, prefer `value = dbmcp.scalar("SELECT ...")`.
6. Do not use `dbmcp.plan(...)` to generate SQL for you.
7. Do not use `dbmcp.finalize_answer(...)`. Print the final JSON object yourself.
8. If discovery succeeds, do not repeat it. Run the final query next.
9. `dbmcp.read_protocol()` returns markdown text.
10. Your JSON must include `"task_id"`, `"status"`, and `"answer_text"`.
11. Return only the required final JSON.
"""

    (skill_dir / "SKILL.md").write_text(body)


def _build_runtime_code_host_env(
    attempt_dir: Path,
    *,
    connection_name: str,
    runtime_server_url: str,
    runtime_session_id: str,
) -> dict[str, str]:
    wrapper_dir = attempt_dir / ".runtime-bin"
    wrapper_dir.mkdir(exist_ok=True)
    capture_dir = attempt_dir / "runtime-captures"
    capture_dir.mkdir(exist_ok=True)
    wrapper_path = wrapper_dir / "python3"
    wrapper_path.write_text(
        """#!/bin/sh
set -eu

"$DB_MCP_REAL_PYTHON" - "$@" <<'PY'
import json
import os
import shutil
import sys
from pathlib import Path

argv = sys.argv[1:]
log_path = Path(os.environ["DB_MCP_BENCH_RUNTIME_LOG"])
capture_dir = Path(os.environ["DB_MCP_BENCH_RUNTIME_CAPTURE_DIR"])
capture_dir.mkdir(parents=True, exist_ok=True)

record = {"argv": argv, "cwd": os.getcwd()}
file_arg = next((arg for arg in argv if not arg.startswith("-")), None)
if file_arg:
    file_path = Path(file_arg)
    record["file"] = str(file_path)
    if file_path.exists():
        capture_path = capture_dir / f"{len(list(capture_dir.iterdir())):03d}-{file_path.name}"
        shutil.copyfile(file_path, capture_path)
        record["captured_file"] = str(capture_path)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
PY

exec "$DB_MCP_REAL_PYTHON" "$@"
"""
    )
    wrapper_path.chmod(0o755)
    host_module_path = attempt_dir / "dbmcp_host.py"
    host_module_path.write_text(
        "\n".join(
            [
                "from db_mcp.code_runtime.client import CodeRuntimeClient",
                "",
                f'_client = CodeRuntimeClient("{runtime_server_url}")',
                "_session = _client.create_session("
                f'"{connection_name}", session_id="{runtime_session_id}"'
                ")",
                "dbmcp = _session.sdk()",
                "",
            ]
        )
    )
    path_parts = [str(wrapper_dir)]
    current_path = os.environ.get("PATH")
    if current_path:
        path_parts.append(current_path)
    pythonpath_parts = [str(Path(__file__).resolve().parents[2]), str(attempt_dir)]
    current_pythonpath = os.environ.get("PYTHONPATH")
    if current_pythonpath:
        pythonpath_parts.append(current_pythonpath)
    return {
        "PATH": os.pathsep.join(path_parts),
        "PYTHONPATH": os.pathsep.join(pythonpath_parts),
        "DB_MCP_REAL_PYTHON": which("python3") or "python3",
        "DB_MCP_BENCH_RUNTIME_LOG": str(attempt_dir / "runtime-invocations.jsonl"),
        "DB_MCP_BENCH_RUNTIME_CAPTURE_DIR": str(capture_dir),
    }


def _build_runtime_native_env(
    attempt_dir: Path,
    *,
    connection_name: str,
    runtime_server_url: str,
    runtime_session_id: str,
) -> dict[str, str]:
    adapter = CodeRuntimeNativeAdapter(
        server_url=runtime_server_url,
        connection=connection_name,
        session_id=runtime_session_id,
    )
    return adapter.materialize(attempt_dir).env


def _reserve_runtime_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _wait_for_runtime_server(
    server_url: str,
    *,
    process: subprocess.Popen[str] | None = None,
    timeout_seconds: float = RUNTIME_SERVER_READY_TIMEOUT_SECONDS,
    log_path: Path | None = None,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        if process is not None:
            return_code = process.poll()
            if return_code is not None:
                detail = ""
                if log_path is not None and log_path.exists():
                    try:
                        log_text = log_path.read_text(encoding="utf-8").strip()
                    except OSError:
                        log_text = ""
                    if log_text:
                        detail = f" Log output: {log_text[-500:]}"
                raise RuntimeError(
                    f"Runtime server exited before becoming ready (exit {return_code}).{detail}"
                )
        try:
            with urlopen(f"{server_url}/health", timeout=0.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if payload.get("status") == "healthy":
                    return
        except Exception as exc:  # pragma: no cover - exercised through retries
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"Runtime server did not become ready: {last_error}")


@contextmanager
def _runtime_server_context(
    *,
    connection_name: str,
    connections_dir: Path,
    attempt_dir: Path,
):
    port = _reserve_runtime_port()
    server_url = f"http://127.0.0.1:{port}"
    log_path = attempt_dir / "runtime-server.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                _resolve_benchmark_db_mcp_binary(),
                "runtime",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=attempt_dir,
            env={
                **os.environ,
                "CONNECTIONS_DIR": str(connections_dir),
                "CONNECTION_NAME": connection_name,
            },
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            _wait_for_runtime_server(
                server_url,
                process=process,
                timeout_seconds=RUNTIME_SERVER_READY_TIMEOUT_SECONDS,
                log_path=log_path,
            )
            _json_dump(
                attempt_dir / "runtime-server.json",
                {"server_url": server_url, "port": port, "pid": process.pid},
            )
            yield server_url
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)


def _tools_for_scenario(scenario: str) -> list[str]:
    if scenario == EXEC_ONLY_SCENARIO:
        return EXEC_ONLY_TOOLS
    if scenario == CODE_MODE_SCENARIO:
        return CODE_MODE_TOOLS
    if scenario == RUNTIME_CODE_SCENARIO:
        return RUNTIME_CODE_TOOLS
    if scenario == RUNTIME_NATIVE_SCENARIO:
        return RUNTIME_NATIVE_TOOLS
    return DEFAULT_TOOLS


def _collect_db_mcp_metrics(
    connection_path: Path,
    *,
    session_id: str,
    started_ns: int,
    ended_ns: int,
) -> dict[str, int]:
    traces_root = connection_path / "traces"
    if not traces_root.exists():
        return {"exploratory_steps": 0, "failed_executions": 0, "db_executions": 0}

    user_id = get_user_id_from_config()
    candidate_files = list((traces_root / user_id).glob("*.jsonl")) if user_id else []
    if not candidate_files:
        candidate_files = list(traces_root.glob("**/*.jsonl"))

    exploratory = 0
    failures = 0
    db_exec = 0
    sql_tools = {"run_sql", "get_result", "validate_sql", "get_data", "export_results"}
    for path in candidate_files:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            attrs = record.get("attrs", {}) or {}
            ts = int(record.get("ts", 0))
            same_session = attrs.get("session.id") == session_id
            in_window = started_ns <= ts <= ended_ns
            if not same_session and not in_window:
                continue
            tool_name = attrs.get("tool.name")
            if not tool_name:
                continue
            exploratory += 1
            if tool_name in sql_tools:
                db_exec += 1
            if record.get("status") not in {"OK", "ok"} or attrs.get("tool.soft_failure"):
                failures += 1

    return {
        "exploratory_steps": exploratory,
        "failed_executions": failures,
        "db_executions": db_exec,
    }


def _extract_usage_metrics(raw_stdout: str) -> dict[str, int | float]:
    try:
        payload = json.loads(raw_stdout)
    except json.JSONDecodeError:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "total_cost_usd": 0.0,
        }

    usage = payload.get("usage") if isinstance(payload, dict) else {}
    if not isinstance(usage, dict):
        usage = {}

    def _as_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _as_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "input_tokens": _as_int(usage.get("input_tokens")),
        "output_tokens": _as_int(usage.get("output_tokens")),
        "cache_read_input_tokens": _as_int(usage.get("cache_read_input_tokens")),
        "cache_creation_input_tokens": _as_int(usage.get("cache_creation_input_tokens")),
        "total_cost_usd": _as_float(payload.get("total_cost_usd")),
    }


def _write_attempt_files(
    attempt_dir: Path,
    *,
    prompt: str,
    answer_payload: dict[str, Any],
    expected_rows: list[dict[str, Any]],
    score_payload: dict[str, Any],
    timing_payload: dict[str, Any],
    metadata_payload: dict[str, Any],
    metrics_payload: dict[str, Any],
    raw_stdout: str,
    raw_stderr: str,
) -> None:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    (attempt_dir / "prompt.txt").write_text(prompt)
    (attempt_dir / "stdout.json").write_text(raw_stdout)
    (attempt_dir / "stderr.txt").write_text(raw_stderr)
    _json_dump(attempt_dir / "answer.json", answer_payload)
    _json_dump(attempt_dir / "expected.json", expected_rows)
    _json_dump(attempt_dir / "score.json", score_payload)
    _json_dump(attempt_dir / "timing.json", timing_payload)
    _json_dump(attempt_dir / "metadata.json", metadata_payload)
    _json_dump(attempt_dir / "metrics.json", metrics_payload)


def _extract_answer_payload(raw_stdout: str) -> dict[str, Any]:
    payload = json.loads(raw_stdout)
    if isinstance(payload, dict) and isinstance(payload.get("structured_output"), dict):
        return payload["structured_output"]
    return payload


def _resolve_script_string(expr: ast.AST, symbols: dict[str, str]) -> str | None:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.Name):
        return symbols.get(expr.id)
    if (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "strip"
        and not expr.args
        and not expr.keywords
    ):
        return _resolve_script_string(expr.func.value, symbols)
    return None


def _extract_runtime_answer_template(script: str) -> dict[str, Any] | None:
    try:
        module = ast.parse(script)
    except SyntaxError:
        return None

    symbols: dict[str, str] = {}
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            resolved = _resolve_script_string(node.value, symbols)
            if resolved is not None:
                symbols[node.targets[0].id] = resolved

    for node in module.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        print_call = node.value
        if not isinstance(print_call.func, ast.Name) or print_call.func.id != "print":
            continue
        if not print_call.args:
            continue
        dumps_call = print_call.args[0]
        if (
            not isinstance(dumps_call, ast.Call)
            or not isinstance(dumps_call.func, ast.Attribute)
            or dumps_call.func.attr != "dumps"
            or not isinstance(dumps_call.func.value, ast.Name)
            or dumps_call.func.value.id != "json"
            or not dumps_call.args
            or not isinstance(dumps_call.args[0], ast.Dict)
        ):
            continue

        payload: dict[str, Any] = {}
        mapping = dumps_call.args[0]
        for key_node, value_node in zip(mapping.keys, mapping.values, strict=False):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            key = key_node.value
            if key in {"task_id", "status", "answer_text", "evidence_sql", "failure_reason"}:
                payload[key] = _resolve_script_string(value_node, symbols)
            elif key == "confidence" and isinstance(value_node, ast.Constant):
                payload[key] = value_node.value
        if payload:
            return payload
    return None


def _recover_runtime_answer_payload(
    *,
    attempt_dir: Path,
    connector: Any,
) -> dict[str, Any] | None:
    invocations = _read_runtime_invocations(attempt_dir)
    for invocation in reversed(invocations):
        script = _load_runtime_script_text(invocation)
        if not script:
            continue
        template = _extract_runtime_answer_template(script)
        if not template:
            continue
        evidence_sql = template.get("evidence_sql")
        if not isinstance(evidence_sql, str) or not evidence_sql.strip():
            continue
        rows = connector.execute_sql(evidence_sql)
        answer_value: Any
        if not rows:
            answer_value = None
        elif len(rows) == 1 and len(rows[0]) == 1:
            answer_value = next(iter(rows[0].values()))
        else:
            answer_value = rows
        answer_text = template.get("answer_text")
        if not isinstance(answer_text, str) or not answer_text:
            answer_text = "" if answer_value is None else str(answer_value)
        return {
            "task_id": template.get("task_id") or attempt_dir.name.split("__", 1)[0],
            "status": template.get("status") or "answered",
            "answer_value": answer_value,
            "answer_text": answer_text,
            "evidence_sql": evidence_sql,
            "confidence": template.get("confidence"),
            "failure_reason": template.get("failure_reason"),
        }
    return None


def _extract_answer_payload_with_recovery(
    raw_stdout: str,
    *,
    attempt_dir: Path | None = None,
    connector: Any | None = None,
) -> dict[str, Any]:
    try:
        payload = _extract_answer_payload(raw_stdout)
    except Exception:
        if attempt_dir is not None and connector is not None:
            recovered = _recover_runtime_answer_payload(
                attempt_dir=attempt_dir,
                connector=connector,
            )
            if recovered is not None:
                return recovered
        raise

    if isinstance(payload, dict) and {
        "task_id",
        "status",
        "answer_text",
    }.issubset(payload):
        return payload

    if attempt_dir is not None and connector is not None:
        recovered = _recover_runtime_answer_payload(
            attempt_dir=attempt_dir,
            connector=connector,
        )
        if recovered is not None:
            return recovered

    return payload


def _materialize_output_root(output_root: Path, connection_name: str) -> Path:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{connection_name}-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "attempts").mkdir(exist_ok=True)
    return run_dir


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _runtime_failure_answer(case_id: str, reason: str) -> dict[str, Any]:
    return {
        "task_id": case_id,
        "status": "failed",
        "answer_value": None,
        "answer_text": "",
        "evidence_sql": None,
        "confidence": None,
        "failure_reason": reason,
    }


def _read_runtime_invocations(attempt_dir: Path) -> list[dict[str, Any]]:
    log_path = attempt_dir / "runtime-invocations.jsonl"
    if not log_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for raw_line in log_path.read_text().splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _load_runtime_script_text(invocation: dict[str, Any]) -> str:
    captured_file = invocation.get("captured_file")
    if isinstance(captured_file, str) and captured_file:
        capture_path = Path(captured_file)
        if capture_path.exists():
            return capture_path.read_text()
    code = invocation.get("code")
    return code if isinstance(code, str) else ""


def _script_acknowledges_protocol_first(script: str) -> bool:
    try:
        module = ast.parse(script)
    except SyntaxError:
        return script.lstrip().startswith("_ = dbmcp.read_protocol()")

    def _is_protocol_ack_statement(node: ast.stmt) -> bool:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            return False
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "_":
            return False
        call = node.value
        if not isinstance(call, ast.Call) or call.args or call.keywords:
            return False
        func = call.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "read_protocol"
            and isinstance(func.value, ast.Name)
            and func.value.id == "dbmcp"
        )

    def _is_ignorable_preamble(node: ast.stmt) -> bool:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return True
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            return isinstance(node.value.value, str)
        return False

    for node in module.body:
        if _is_ignorable_preamble(node):
            continue
        return _is_protocol_ack_statement(node)
    return False


def _validate_runtime_attempt(attempt_dir: Path, *, scenario: str) -> str | None:
    invocations = _read_runtime_invocations(attempt_dir)
    if not invocations:
        return (
            f"{scenario} attempt never used the dbmcp host runtime client. "
            "Use the preconfigured dbmcp object before answering."
        )

    host_calls = [record for record in invocations if record.get("kind") == "host_client_call"]
    if not host_calls:
        return (
            f"{scenario} attempt never used the dbmcp host runtime client. "
            "Use the preconfigured dbmcp object before answering."
        )

    script_invocations = [record for record in invocations if record.get("captured_file")]
    if not script_invocations:
        if scenario == RUNTIME_NATIVE_SCENARIO:
            python_invocations = [record for record in invocations if "argv" in record]
            if not python_invocations:
                return f"{scenario} attempt never executed a Python host script."
            if host_calls[0].get("method") != "read_protocol":
                return (
                    f"{scenario} attempt did not acknowledge the protocol before using the "
                    "native dbmcp object."
                )
            return None
        return f"{scenario} attempt never executed a Python host script."

    first_script = _load_runtime_script_text(script_invocations[0])
    if scenario == RUNTIME_NATIVE_SCENARIO and "dbmcp_host" in first_script:
        return (
            "runtime_native attempt imported dbmcp_host instead of using the injected native "
            "`dbmcp` object."
        )
    if not _script_acknowledges_protocol_first(first_script):
        return (
            f"{scenario} attempt did not acknowledge the protocol as its first executable "
            "statement. The first runtime script must begin by calling "
            "`_ = dbmcp.read_protocol()`."
        )
    return None


def summarize_run_directory(run_dir: Path) -> dict[str, Any]:
    """Summarize an existing benchmark run directory and rewrite report files."""
    attempts_root = run_dir / "attempts"
    scenario_summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "attempts": 0,
            "correct": 0,
            "total_duration_ms": 0.0,
            "db_executions": 0,
            "failed_executions": 0,
            "exploratory_steps": 0,
            "structured_failures": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "total_cost_usd": 0.0,
        }
    )
    category_summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {"attempts": 0, "correct": 0}
    )

    for attempt_dir in sorted(attempts_root.iterdir()):
        if not attempt_dir.is_dir():
            continue
        score = _read_json(attempt_dir / "score.json")
        timing = _read_json(attempt_dir / "timing.json")
        metadata = _read_json(attempt_dir / "metadata.json")
        metrics = _read_json(attempt_dir / "metrics.json")

        scenario = metadata["scenario"]
        category = metadata["category"]
        bucket = scenario_summary[scenario]
        bucket["attempts"] += 1
        bucket["correct"] += 1 if score["correct"] else 0
        bucket["total_duration_ms"] += timing["duration_ms"]
        bucket["db_executions"] += metrics.get("db_executions", 0)
        bucket["failed_executions"] += metrics.get("failed_executions", 0)
        bucket["exploratory_steps"] += metrics.get("exploratory_steps", 0)
        bucket["structured_failures"] += 1 if metadata.get("structured_failure") else 0
        bucket["input_tokens"] += metrics.get("input_tokens", 0)
        bucket["output_tokens"] += metrics.get("output_tokens", 0)
        bucket["cache_read_input_tokens"] += metrics.get("cache_read_input_tokens", 0)
        bucket["cache_creation_input_tokens"] += metrics.get("cache_creation_input_tokens", 0)
        bucket["total_cost_usd"] += metrics.get("total_cost_usd", 0.0)

        category_summary[category]["attempts"] += 1
        category_summary[category]["correct"] += 1 if score["correct"] else 0

    summary = {
        "run_dir": str(run_dir),
        "totals": {"attempts": sum(v["attempts"] for v in scenario_summary.values())},
        "scenario_summary": {},
        "category_summary": category_summary,
    }

    csv_rows: list[dict[str, Any]] = []
    for scenario, bucket in scenario_summary.items():
        attempts = bucket["attempts"]
        avg_duration = bucket["total_duration_ms"] / attempts if attempts else 0.0
        row = {
            "scenario": scenario,
            "attempts": attempts,
            "correct": bucket["correct"],
            "accuracy": (bucket["correct"] / attempts) if attempts else 0.0,
            "avg_duration_ms": round(avg_duration, 3),
            "db_executions": bucket["db_executions"],
            "failed_executions": bucket["failed_executions"],
            "exploratory_steps": bucket["exploratory_steps"],
            "structured_failures": bucket["structured_failures"],
            "input_tokens": bucket["input_tokens"],
            "output_tokens": bucket["output_tokens"],
            "cache_read_input_tokens": bucket["cache_read_input_tokens"],
            "cache_creation_input_tokens": bucket["cache_creation_input_tokens"],
            "total_cost_usd": round(bucket["total_cost_usd"], 6),
        }
        summary["scenario_summary"][scenario] = row
        csv_rows.append(row)

    _json_dump(run_dir / "summary.json", summary)
    with open(run_dir / "summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario",
                "attempts",
                "correct",
                "accuracy",
                "avg_duration_ms",
                "db_executions",
                "failed_executions",
                "exploratory_steps",
                "structured_failures",
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
                "total_cost_usd",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    return summary


def run_benchmark_suite(
    *,
    connection_name: str,
    connection_path: Path,
    model: str,
    repeats: int,
    selected_case_ids: list[str] | None,
    output_root: Path,
    case_pack: str = "cases.yaml",
    driver=None,
    shuffle_seed: int | None = None,
    progress_callback=None,
    runtime_server_factory=None,
) -> Path:
    """Run the benchmark suite for one connection."""
    access = resolve_sql_connection_access(connection_name)
    cases = load_case_pack(connection_path, selected_case_ids, case_pack=case_pack)
    run_dir = _materialize_output_root(output_root, connection_name)
    rng = random.Random(shuffle_seed)
    driver = driver or ClaudeCliDriver()
    schema = BenchmarkAnswer.model_json_schema()
    connections_dir = connection_path.parent
    total_attempts = repeats * len(cases) * len(SCENARIOS)
    completed_attempts = 0
    runtime_server_factory = runtime_server_factory or _runtime_server_context

    for repeat in range(1, repeats + 1):
        for case in cases:
            scenario_order = list(SCENARIOS)
            rng.shuffle(scenario_order)
            for scenario in scenario_order:
                session_id = str(uuid.uuid4())
                attempt_id = f"{case.id}__{scenario}__r{repeat}"
                attempt_dir = run_dir / "attempts" / attempt_id
                attempt_dir.mkdir(parents=True, exist_ok=True)

                mcp_config_path = attempt_dir / "mcp-config.json"
                if scenario == DB_MCP_SCENARIO:
                    _build_db_mcp_config(
                        mcp_config_path,
                        connection_name=connection_name,
                        connections_dir=connections_dir,
                    )
                elif scenario == EXEC_ONLY_SCENARIO:
                    _build_exec_only_mcp_config(
                        mcp_config_path,
                        connection_name=connection_name,
                        connections_dir=connections_dir,
                    )
                elif scenario == CODE_MODE_SCENARIO:
                    _build_code_mode_mcp_config(
                        mcp_config_path,
                        connection_name=connection_name,
                        connections_dir=connections_dir,
                    )
                else:
                    _build_empty_mcp_config(mcp_config_path)

                runtime_server_url: str | None = None
                if scenario in {RUNTIME_CODE_SCENARIO, RUNTIME_NATIVE_SCENARIO}:
                    runtime_server_cm = runtime_server_factory(
                        connection_name=connection_name,
                        connections_dir=connections_dir,
                        attempt_dir=attempt_dir,
                    )
                else:
                    runtime_server_cm = None

                if runtime_server_cm is not None:
                    runtime_server_context = runtime_server_cm
                else:
                    runtime_server_context = None

                _materialize_benchmark_skill(attempt_dir, scenario, connection_name)
                debug_log_path = attempt_dir / "debug.log"
                run_env = None
                loop_breaker = (
                    LoopBreakerConfig(
                        runtime_log_path=attempt_dir / "runtime-invocations.jsonl",
                    )
                    if scenario in {RUNTIME_CODE_SCENARIO, RUNTIME_NATIVE_SCENARIO}
                    else None
                )
                if runtime_server_context is None:
                    prompt = _build_prompt(
                        case,
                        scenario,
                        connection_name,
                        access.database_url,
                        access.connect_args,
                    )
                    (attempt_dir / "prompt.txt").write_text(prompt)
                    started_ns = time.time_ns()
                    result = driver.run(
                        prompt=prompt,
                        json_schema=schema,
                        session_id=session_id,
                        mcp_config_path=mcp_config_path,
                        model=model,
                        workdir=attempt_dir,
                        debug_log_path=debug_log_path,
                        tools=_tools_for_scenario(scenario),
                        env=run_env,
                        loop_breaker=loop_breaker,
                    )
                    ended_ns = time.time_ns()
                else:
                    with runtime_server_context as runtime_server_url:
                        run_env = (
                            _build_runtime_code_host_env(
                                attempt_dir,
                                connection_name=connection_name,
                                runtime_server_url=runtime_server_url,
                                runtime_session_id=session_id,
                            )
                            if scenario == RUNTIME_CODE_SCENARIO
                            else _build_runtime_native_env(
                                attempt_dir,
                                connection_name=connection_name,
                                runtime_server_url=runtime_server_url,
                                runtime_session_id=session_id,
                            )
                        )
                        prompt = _build_prompt(
                            case,
                            scenario,
                            connection_name,
                            access.database_url,
                            access.connect_args,
                            runtime_server_url=runtime_server_url,
                            runtime_session_id=session_id,
                        )
                        (attempt_dir / "prompt.txt").write_text(prompt)
                        started_ns = time.time_ns()
                        result = driver.run(
                            prompt=prompt,
                            json_schema=schema,
                            session_id=session_id,
                            mcp_config_path=mcp_config_path,
                            model=model,
                            workdir=attempt_dir,
                            debug_log_path=debug_log_path,
                            tools=_tools_for_scenario(scenario),
                            env=run_env,
                            loop_breaker=loop_breaker,
                        )
                        ended_ns = time.time_ns()

                structured_failure = False
                try:
                    answer_payload = _extract_answer_payload_with_recovery(
                        result.stdout,
                        attempt_dir=attempt_dir,
                        connector=access.connector,
                    )
                    answer = BenchmarkAnswer.model_validate(answer_payload)
                    answer_payload = answer.model_dump()
                except Exception as exc:
                    structured_failure = True
                    answer_payload = _runtime_failure_answer(
                        case.id,
                        f"Invalid JSON response: {exc}",
                    )

                if scenario in {RUNTIME_CODE_SCENARIO, RUNTIME_NATIVE_SCENARIO}:
                    if runtime_failure := _validate_runtime_attempt(
                        attempt_dir,
                        scenario=scenario,
                    ):
                        structured_failure = True
                        answer_payload = _runtime_failure_answer(
                            case.id,
                            runtime_failure,
                        )

                expected_rows = execute_gold_sql(access.connector, case)
                score = score_case(case, expected_rows, answer_payload)
                if scenario == DB_MCP_SCENARIO:
                    metrics = _collect_db_mcp_metrics(
                        connection_path,
                        session_id=session_id,
                        started_ns=started_ns,
                        ended_ns=ended_ns,
                    )
                else:
                    metrics = _parse_raw_debug_metrics(debug_log_path)
                metrics.update(_extract_usage_metrics(result.stdout))

                _write_attempt_files(
                    attempt_dir,
                    prompt=prompt,
                    answer_payload=answer_payload,
                    expected_rows=expected_rows,
                    score_payload=score.model_dump(),
                    timing_payload={"duration_ms": result.duration_ms},
                    metadata_payload={
                        "scenario": scenario,
                        "case_id": case.id,
                        "category": case.category,
                        "repeat": repeat,
                        "session_id": session_id,
                        "connection_name": connection_name,
                        "database_url_masked": _mask_database_url(access.database_url),
                        "structured_failure": structured_failure,
                    },
                    metrics_payload=metrics,
                    raw_stdout=result.stdout,
                    raw_stderr=result.stderr,
                )

                completed_attempts += 1
                if progress_callback is not None:
                    progress_callback(
                        {
                            "case_id": case.id,
                            "scenario": scenario,
                            "repeat": repeat,
                            "completed_attempts": completed_attempts,
                            "total_attempts": total_attempts,
                            "duration_ms": result.duration_ms,
                            "result": "PASS" if score.correct else "FAIL",
                        }
                    )

    summarize_run_directory(run_dir)
    return run_dir


def probe_claude_ready() -> None:
    """Fail if Claude CLI is missing or unauthenticated."""
    if which("claude") is None:
        raise RuntimeError("claude CLI not found on PATH")
    probe_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    result = subprocess.run(
        [
            "claude",
            "--print",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(probe_schema, separators=(",", ":")),
            '--system-prompt',
            'Return {"ok": true}.',
            'Return {"ok": true}.',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Claude auth probe failed")


def run_preflight(connection: str, case_pack: str = "cases.yaml") -> dict[str, Any]:
    """Run benchmark-specific preflight checks."""
    checks: list[dict[str, Any]] = []
    try:
        access = resolve_sql_connection_access(connection)
        checks.append(
            {
                "name": "resolve_connection",
                "status": "pass",
                "details": {"connection_path": str(access.connection_path)},
            }
        )
    except Exception as exc:
        checks.append(
            {
                "name": "resolve_connection",
                "status": "fail",
                "details": {"error": str(exc)},
            }
        )
        return {"status": "fail", "connection": connection, "checks": checks}

    try:
        cases = load_case_pack(access.connection_path, case_pack=case_pack)
        checks.append(
            {
                "name": "load_case_pack",
                "status": "pass",
                "details": {"cases": len(cases), "case_pack": case_pack},
            }
        )
    except Exception as exc:
        checks.append({"name": "load_case_pack", "status": "fail", "details": {"error": str(exc)}})

    try:
        probe_claude_ready()
        checks.append({"name": "claude_cli", "status": "pass", "details": {}})
    except Exception as exc:
        checks.append({"name": "claude_cli", "status": "fail", "details": {"error": str(exc)}})

    try:
        auth = access.connector.test_connection()
        checks.append({"name": "db_auth", "status": "pass", "details": auth})
    except Exception as exc:
        checks.append({"name": "db_auth", "status": "fail", "details": {"error": str(exc)}})

    try:
        rows = access.connector.execute_sql("SELECT 1 AS benchmark_probe")
        checks.append(
            {
                "name": "db_read_only_probe",
                "status": "pass",
                "details": {"rows_returned": len(rows)},
            }
        )
    except Exception as exc:
        checks.append(
            {"name": "db_read_only_probe", "status": "fail", "details": {"error": str(exc)}}
        )

    try:
        binary = get_db_mcp_binary_path()
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "db-mcp --version failed")
        checks.append({"name": "db_mcp_binary", "status": "pass", "details": {"binary": binary}})
    except Exception as exc:
        checks.append({"name": "db_mcp_binary", "status": "fail", "details": {"error": str(exc)}})

    status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    return {"status": status, "connection": connection, "checks": checks}


def run_benchmark_suite_from_cli(
    *,
    connection: str,
    model: str,
    cases: tuple[str, ...],
    repeats: int,
    output_root: Path,
    case_pack: str = "cases.yaml",
    seed: int | None = None,
    progress_callback=None,
) -> Path:
    access = resolve_sql_connection_access(connection)
    return run_benchmark_suite(
        connection_name=connection,
        connection_path=access.connection_path,
        model=model,
        repeats=repeats,
        selected_case_ids=list(cases) or None,
        output_root=output_root,
        case_pack=case_pack,
        shuffle_seed=seed,
        progress_callback=progress_callback,
    )
