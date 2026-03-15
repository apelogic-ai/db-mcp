"""Benchmark runner and report generation."""

from __future__ import annotations

import csv
import json
import random
import re
import subprocess
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any

from db_mcp.benchmark.connection import resolve_sql_connection_access
from db_mcp.benchmark.driver import ClaudeCliDriver
from db_mcp.benchmark.loader import load_case_pack
from db_mcp.benchmark.models import BenchmarkAnswer
from db_mcp.benchmark.scoring import execute_gold_sql, score_case
from db_mcp.cli.utils import get_db_mcp_binary_path
from db_mcp.traces import get_user_id_from_config

DB_MCP_SCENARIO = "db_mcp"
RAW_DSN_SCENARIO = "raw_dsn"
SCENARIOS = [DB_MCP_SCENARIO, RAW_DSN_SCENARIO]
DEFAULT_TOOLS = ["Read", "Bash"]


def _mask_database_url(database_url: str) -> str:
    return re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", database_url)


def _json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _build_empty_mcp_config(path: Path) -> None:
    path.write_text(json.dumps({"mcpServers": {}}, indent=2) + "\n")


def _build_db_mcp_config(path: Path, *, connection_name: str, connections_dir: Path) -> None:
    payload = {
        "mcpServers": {
            "db-mcp": {
                "command": get_db_mcp_binary_path(),
                "args": ["start", "-c", connection_name],
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
    database_url: str,
    connect_args: dict[str, Any] | None,
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
    bash_calls = len(re.findall(r'tool_name"?\s*[:=]\s*"?Bash"?', text))
    failures = len(re.findall(r"error", text, re.IGNORECASE))
    db_exec = len(re.findall(r"(sqlite3|psql|mysql|sqlalchemy|duckdb)", text, re.IGNORECASE))
    return {
        "exploratory_steps": bash_calls,
        "failed_executions": failures,
        "db_executions": db_exec,
    }


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


def _materialize_output_root(output_root: Path, connection_name: str) -> Path:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{connection_name}-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "attempts").mkdir(exist_ok=True)
    return run_dir


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


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
                else:
                    _build_empty_mcp_config(mcp_config_path)

                prompt = _build_prompt(case, scenario, access.database_url, access.connect_args)
                debug_log_path = attempt_dir / "debug.log"
                started_ns = time.time_ns()
                result = driver.run(
                    prompt=prompt,
                    json_schema=schema,
                    session_id=session_id,
                    mcp_config_path=mcp_config_path,
                    model=model,
                    workdir=attempt_dir,
                    debug_log_path=debug_log_path,
                    tools=DEFAULT_TOOLS,
                )
                ended_ns = time.time_ns()

                structured_failure = False
                try:
                    answer_payload = _extract_answer_payload(result.stdout)
                    answer = BenchmarkAnswer.model_validate(answer_payload)
                    answer_payload = answer.model_dump()
                except Exception as exc:
                    structured_failure = True
                    answer_payload = {
                        "task_id": case.id,
                        "status": "failed",
                        "answer_value": None,
                        "answer_text": "",
                        "evidence_sql": None,
                        "confidence": None,
                        "failure_reason": f"Invalid JSON response: {exc}",
                    }

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
