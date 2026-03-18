from __future__ import annotations

import json
import signal
import sqlite3
import threading
import uuid
from pathlib import Path

import pytest
import yaml

from db_mcp.benchmark.connection import resolve_sql_connection_access
from db_mcp.benchmark.driver import (
    ClaudeCliDriver,
    DriverResult,
    LoopBreakerConfig,
    _watch_runtime_loop,
    build_claude_command,
)
from db_mcp.benchmark.loader import load_case_pack
from db_mcp.benchmark.runner import (
    CODE_MODE_SCENARIO,
    EXEC_ONLY_SCENARIO,
    RUNTIME_CODE_SCENARIO,
    RUNTIME_NATIVE_SCENARIO,
    _extract_answer_payload,
    _extract_answer_payload_with_recovery,
    _resolve_benchmark_db_mcp_binary,
    _runtime_server_context,
    _validate_runtime_attempt,
    run_benchmark_suite,
    summarize_run_directory,
)
from db_mcp.benchmark.scoring import execute_gold_sql, score_case
from db_mcp.config import reset_settings
from db_mcp.registry import ConnectionRegistry


class FakeDriver:
    def __init__(self, outputs: dict[str, dict]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

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
        loop_breaker=None,
    ) -> DriverResult:
        config_text = mcp_config_path.read_text()
        if '"exec-only"' in config_text:
            scenario = EXEC_ONLY_SCENARIO
        elif '"code"' in config_text:
            scenario = CODE_MODE_SCENARIO
        elif "dbmcp is already available as a global" in prompt:
            scenario = RUNTIME_NATIVE_SCENARIO
        elif "from dbmcp_host import dbmcp" in prompt:
            scenario = RUNTIME_CODE_SCENARIO
        elif "db-mcp" in config_text:
            scenario = "db_mcp"
        else:
            scenario = "raw_dsn"
        self.calls.append(
            {
                "scenario": scenario,
                "session_id": session_id,
                "model": model,
                "tools": tools,
                "prompt": prompt,
                "env": env or {},
            }
        )
        if env and env.get("DB_MCP_BENCH_RUNTIME_LOG"):
            capture_dir = Path(env["DB_MCP_BENCH_RUNTIME_CAPTURE_DIR"])
            capture_dir.mkdir(parents=True, exist_ok=True)
            captured_file = capture_dir / "000-runtime.py"
            if scenario == RUNTIME_NATIVE_SCENARIO:
                captured_file.write_text(
                    "_ = dbmcp.read_protocol()\n"
                    "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))\n"
                )
            else:
                captured_file.write_text(
                    "from dbmcp_host import dbmcp\n"
                    "_ = dbmcp.read_protocol()\n"
                    "print(dbmcp.scalar('SELECT COUNT(*) FROM items'))\n"
                )
            Path(env["DB_MCP_BENCH_RUNTIME_LOG"]).write_text(
                json.dumps(
                    {
                        "argv": ["python3", "/tmp/runtime.py"],
                        "captured_file": str(captured_file),
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "kind": "host_client_call",
                        "method": "scalar",
                        "session_id": "runtime-session",
                    }
                )
                + "\n"
            )
        if scenario == EXEC_ONLY_SCENARIO:
            debug_log_path.write_text(
                "executePreToolHooks called for tool: mcp__db-mcp__exec\n"
                "Tool call failed: exec returned non-zero exit code\n"
            )
        elif scenario == CODE_MODE_SCENARIO:
            debug_log_path.write_text(
                "executePreToolHooks called for tool: mcp__db-mcp__code\n"
                "Tool call failed: code returned non-zero exit code\n"
            )
        elif scenario == RUNTIME_CODE_SCENARIO:
            debug_log_path.write_text(
                '{"tool_name":"Bash"}\n'
                "python3 /tmp/runtime.py\n"
            )
        elif scenario == RUNTIME_NATIVE_SCENARIO:
            debug_log_path.write_text(
                '{"tool_name":"Bash"}\n'
                "python3 /tmp/runtime_native.py\n"
            )
        else:
            debug_log_path.write_text(
                '{"tool_name":"Bash"}\n{"tool_name":"Bash","status":"error"}\n'
            )
        return DriverResult(
            stdout=json.dumps(self.outputs[scenario]),
            stderr="",
            exit_code=0,
            duration_ms=123.0,
            debug_log_path=debug_log_path,
        )


class FakeRuntimeServerContext:
    def __init__(self, url: str = "http://127.0.0.1:8765") -> None:
        self.url = url

    def __enter__(self) -> str:
        return self.url

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class NoRuntimeInvocationDriver(FakeDriver):
    def run(self, **kwargs) -> DriverResult:
        result = super().run(**kwargs)
        env = kwargs.get("env") or {}
        if env.get("DB_MCP_BENCH_RUNTIME_LOG"):
            Path(env["DB_MCP_BENCH_RUNTIME_LOG"]).write_text("")
        return result


class RuntimeImportPreambleDriver(FakeDriver):
    def run(self, **kwargs) -> DriverResult:
        result = super().run(**kwargs)
        env = kwargs.get("env") or {}
        if env.get("DB_MCP_BENCH_RUNTIME_LOG"):
            capture_dir = Path(env["DB_MCP_BENCH_RUNTIME_CAPTURE_DIR"])
            capture_dir.mkdir(parents=True, exist_ok=True)
            captured_file = capture_dir / "000-runtime.py"
            captured_file.write_text(
                'import json\n\n_ = dbmcp.read_protocol()\nprint(json.dumps({"ok": True}))\n'
            )
            Path(env["DB_MCP_BENCH_RUNTIME_LOG"]).write_text(
                json.dumps(
                    {
                        "argv": ["python3", "/tmp/runtime.py"],
                        "captured_file": str(captured_file),
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "kind": "host_client_call",
                        "method": "read_protocol",
                        "session_id": "runtime-session",
                    }
                )
                + "\n"
            )
        return result


class RuntimeNativeGlobalDriver(FakeDriver):
    def run(self, **kwargs) -> DriverResult:
        result = super().run(**kwargs)
        env = kwargs.get("env") or {}
        if env.get("DB_MCP_BENCH_RUNTIME_LOG"):
            capture_dir = Path(env["DB_MCP_BENCH_RUNTIME_CAPTURE_DIR"])
            capture_dir.mkdir(parents=True, exist_ok=True)
            captured_file = capture_dir / "000-runtime-native.py"
            captured_file.write_text(
                "_ = dbmcp.read_protocol()\n"
                'print({"task_id": "count_items"})\n'
            )
            Path(env["DB_MCP_BENCH_RUNTIME_LOG"]).write_text(
                json.dumps(
                    {
                        "argv": ["python3", "/tmp/runtime_native.py"],
                        "captured_file": str(captured_file),
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "kind": "host_client_call",
                        "method": "read_protocol",
                        "session_id": "runtime-session",
                    }
                )
                + "\n"
            )
        return result


class RuntimeStructuredFailureDriver(FakeDriver):
    def run(self, **kwargs) -> DriverResult:
        super().run(**kwargs)
        env = kwargs.get("env") or {}
        if env.get("DB_MCP_BENCH_RUNTIME_LOG"):
            capture_dir = Path(env["DB_MCP_BENCH_RUNTIME_CAPTURE_DIR"])
            capture_dir.mkdir(parents=True, exist_ok=True)
            captured_file = capture_dir / "001-runtime.py"
            captured_file.write_text(
                "\n".join(
                    [
                        "import json",
                        "from dbmcp_host import dbmcp",
                        "_ = dbmcp.read_protocol()",
                        "sql = \"SELECT COUNT(*) AS answer FROM items\"",
                        "answer = dbmcp.scalar(sql)",
                        "print(json.dumps({",
                        "    \"task_id\": \"count_items\",",
                        "    \"status\": \"answered\",",
                        "    \"answer_value\": answer,",
                        "    \"answer_text\": str(answer),",
                        "    \"evidence_sql\": sql,",
                        "    \"confidence\": 1.0,",
                        "    \"failure_reason\": None,",
                        "}))",
                    ]
                )
            )
            Path(env["DB_MCP_BENCH_RUNTIME_LOG"]).write_text(
                json.dumps(
                    {
                        "argv": ["python3", "/tmp/runtime.py"],
                        "captured_file": str(captured_file),
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "kind": "host_client_call",
                        "method": "read_protocol",
                        "session_id": "runtime-session",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "kind": "host_client_call",
                        "method": "scalar",
                        "session_id": "runtime-session",
                    }
                )
                + "\n"
            )
        return DriverResult(
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "error_max_structured_output_retries",
                    "is_error": True,
                    "errors": ["Failed to provide valid structured output after 5 attempts"],
                }
            ),
            stderr="",
            exit_code=0,
            duration_ms=123.0,
            debug_log_path=kwargs["debug_log_path"],
        )


@pytest.fixture()
def benchmark_connection(tmp_path, monkeypatch):
    connections_dir = tmp_path / "connections"
    conn_path = connections_dir / "bench"
    conn_path.mkdir(parents=True)

    db_path = tmp_path / "bench.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, category TEXT, amount INTEGER)")
        conn.execute("INSERT INTO items(category, amount) VALUES ('a', 10), ('b', 20), ('a', 30)")
        conn.commit()
    finally:
        conn.close()

    (conn_path / "connector.yaml").write_text(
        yaml.safe_dump(
            {
                "type": "sql",
                "database_url": f"sqlite:///{db_path}",
                "capabilities": {"connect_args": {"timeout": 30}},
            },
            sort_keys=False,
        )
    )
    (conn_path / "benchmark").mkdir()
    (conn_path / "benchmark" / "cases.yaml").write_text(
        yaml.safe_dump(
            {
                "cases": [
                    {
                        "id": "count_items",
                        "category": "aggregate",
                        "prompt": "How many items are there?",
                        "gold_sql": "SELECT COUNT(*) AS answer FROM items",
                        "comparison": "scalar_exact",
                    },
                    {
                        "id": "cats",
                        "category": "set",
                        "prompt": "What categories exist?",
                        "gold_sql": "SELECT DISTINCT category FROM items",
                        "comparison": "set_unordered",
                        "normalization": ["lower", "strip"],
                    },
                ]
            },
            sort_keys=False,
        )
    )
    (conn_path / "benchmark" / "cases_complex.yaml").write_text(
        yaml.safe_dump(
            {
                "cases": [
                    {
                        "id": "top_category",
                        "category": "ranking",
                        "prompt": "Which category has the highest total amount?",
                        "gold_sql": (
                            "SELECT category AS answer FROM items "
                            "GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1"
                        ),
                        "comparison": "scalar_exact",
                    }
                ]
            },
            sort_keys=False,
        )
    )

    monkeypatch.setenv("CONNECTIONS_DIR", str(connections_dir))
    monkeypatch.setenv("CONNECTION_NAME", "bench")
    ConnectionRegistry.reset()
    reset_settings()

    return conn_path


def test_load_case_pack_reads_connection_benchmark_cases(benchmark_connection):
    cases = load_case_pack(benchmark_connection)
    assert [case.id for case in cases] == ["count_items", "cats"]
    assert cases[0].comparison == "scalar_exact"


def test_load_case_pack_reads_custom_case_pack(benchmark_connection):
    cases = load_case_pack(benchmark_connection, case_pack="cases_complex.yaml")
    assert [case.id for case in cases] == ["top_category"]


def test_repo_playground_case_pack_loads():
    repo_root = Path(__file__).resolve().parents[1]
    connection_path = repo_root / "src" / "db_mcp" / "data" / "playground"

    cases = load_case_pack(connection_path)

    assert len(cases) >= 1
    assert cases[-1].id == "playlists_mentioning_music"
    case_by_id = {case.id: case for case in cases}
    assert case_by_id["top_country_by_revenue"].comparison == "scalar_exact"
    assert case_by_id["top_sales_support_agent"].comparison == "scalar_exact"
    assert case_by_id["longest_track"].comparison == "scalar_exact"
    assert case_by_id["top_customer_by_spend_name"].comparison == "scalar_exact"
    assert case_by_id["top_customer_by_spend_total"].comparison == "scalar_numeric_tolerance"


def test_repo_playground_complex_case_pack_loads():
    repo_root = Path(__file__).resolve().parents[1]
    connection_path = repo_root / "src" / "db_mcp" / "data" / "playground"

    cases = load_case_pack(connection_path, case_pack="cases_complex.yaml")

    assert len(cases) == 5
    assert {case.id for case in cases} == {
        "top_artist_by_revenue_name",
        "top_artist_by_revenue_total",
        "customer_with_most_distinct_artists",
        "top_support_rep_by_revenue",
        "top_video_customer",
    }


def test_repo_playground_full_case_pack_loads():
    repo_root = Path(__file__).resolve().parents[1]
    connection_path = repo_root / "src" / "db_mcp" / "data" / "playground"

    cases = load_case_pack(connection_path, case_pack="cases_full.yaml")

    assert len(cases) == 15
    assert len({case.id for case in cases}) == 15
    assert cases[0].id == "total_customers"
    assert cases[-1].id == "top_video_customer"


def test_repo_top_ledger_case_pack_loads():
    repo_root = Path(__file__).resolve().parents[1]
    connection_path = repo_root / "src" / "db_mcp" / "data" / "top-ledger"

    cases = load_case_pack(connection_path)

    assert len(cases) == 10
    assert cases[0].id == "sol_symbol_lookup"
    assert cases[-1].id == "top_named_token_by_buy_count_feb15"
    case_by_id = {case.id: case for case in cases}
    assert case_by_id["canonical_token_symbols"].comparison == "set_unordered"
    assert case_by_id["latest_sol_price_feb15"].comparison == "scalar_numeric_tolerance"
    assert case_by_id["unique_pools_sentence_feb01"].comparison == "contains_text"


def test_repo_top_ledger_complex_case_pack_loads():
    repo_root = Path(__file__).resolve().parents[1]
    connection_path = repo_root / "src" / "db_mcp" / "data" / "top-ledger"

    cases = load_case_pack(connection_path, case_pack="cases_complex.yaml")

    assert len(cases) == 5
    assert {case.id for case in cases} == {
        "top_token_by_unique_traders_symbol_feb10",
        "top_token_by_unique_traders_count_feb10",
        "top_fee_program_name_feb15",
        "top_fee_program_total_feb15",
        "top_named_token_buy_volume_feb15",
    }


def test_repo_top_ledger_full_case_pack_loads():
    repo_root = Path(__file__).resolve().parents[1]
    connection_path = repo_root / "src" / "db_mcp" / "data" / "top-ledger"

    cases = load_case_pack(connection_path, case_pack="cases_full.yaml")

    assert len(cases) == 15
    assert len({case.id for case in cases}) == 15
    assert cases[0].id == "sol_symbol_lookup"
    assert cases[-1].id == "top_named_token_buy_volume_feb15"


def test_repo_top_ledger_hard_case_pack_loads():
    repo_root = Path(__file__).resolve().parents[1]
    connection_path = repo_root / "src" / "db_mcp" / "data" / "top-ledger"

    cases = load_case_pack(connection_path, case_pack="cases_hard.yaml")

    assert len(cases) == 3
    assert {case.id for case in cases} == {
        "copy_trading_top_pair_feb15",
        "non_canonical_top_trader_density_symbol_feb10",
        "top_outer_program_avg_fee_feb15",
    }


def test_load_case_pack_rejects_missing_gold_sql(tmp_path):
    conn_path = tmp_path / "broken"
    (conn_path / "benchmark").mkdir(parents=True)
    (conn_path / "benchmark" / "cases.yaml").write_text(
        yaml.safe_dump(
            {
                "cases": [
                    {
                        "id": "bad",
                        "category": "x",
                        "prompt": "?",
                        "comparison": "scalar_exact",
                    }
                ]
            }
        )
    )

    with pytest.raises(ValueError):
        load_case_pack(conn_path)


def test_resolve_sql_connection_access_returns_database_url_and_connect_args(benchmark_connection):
    access = resolve_sql_connection_access("bench")
    assert access.connection_name == "bench"
    assert access.database_url.startswith("sqlite:///")
    assert access.connect_args == {"timeout": 30}


def test_execute_gold_sql_and_score_cases(benchmark_connection):
    access = resolve_sql_connection_access("bench")
    cases = load_case_pack(benchmark_connection)

    expected_scalar = execute_gold_sql(access.connector, cases[0])
    score_scalar = score_case(
        cases[0],
        expected_scalar,
        {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "There are 3 items.",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.8,
            "failure_reason": None,
        },
    )
    assert score_scalar.correct is True

    expected_set = execute_gold_sql(access.connector, cases[1])
    score_set = score_case(
        cases[1],
        expected_set,
        {
            "task_id": "cats",
            "status": "answered",
            "answer_value": ["B", "A"],
            "answer_text": "A and B",
            "evidence_sql": None,
            "confidence": None,
            "failure_reason": None,
        },
    )
    assert score_set.correct is True


def test_score_case_scalar_exact_accepts_semantically_equivalent_object_answer():
    score = score_case(
        type("Case", (), {"id": "customer", "comparison": "scalar_exact", "normalization": []})(),
        [{"answer": "Marc Dubois"}],
        {
            "task_id": "customer",
            "status": "answered",
            "answer_value": {
                "customer_id": 41,
                "first_name": "Marc",
                "last_name": "Dubois",
                "distinct_artists": 22,
            },
            "answer_text": (
                "Marc Dubois (CustomerId: 41) has purchased tracks from the greatest "
                "number of distinct artists."
            ),
            "evidence_sql": None,
            "confidence": None,
            "failure_reason": None,
        },
    )

    assert score.correct is True


def test_score_case_scalar_exact_accepts_numeric_value_from_object_answer():
    case = type(
        "Case",
        (),
        {"id": "trader_count", "comparison": "scalar_exact", "normalization": []},
    )()
    score = score_case(
        case,
        [{"answer": 1279725}],
        {
            "task_id": "trader_count",
            "status": "answered",
            "answer_value": {
                "symbol": "SOL",
                "unique_traders": 1279725,
            },
            "answer_text": "SOL had 1279725 unique traders.",
            "evidence_sql": None,
            "confidence": None,
            "failure_reason": None,
        },
    )

    assert score.correct is True


def test_score_case_set_unordered_accepts_object_keys_for_symbol_mapping():
    score = score_case(
        type(
            "Case",
            (),
            {
                "id": "symbols",
                "comparison": "set_unordered",
                "normalization": ["strip", "lower"],
            },
        )(),
        [{"symbol": "SOL"}, {"symbol": "USDC"}, {"symbol": "USDT"}],
        {
            "task_id": "symbols",
            "status": "answered",
            "answer_value": {
                "SOL": "So11111111111111111111111111111111111111112",
                "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            },
            "answer_text": "SOL, USDC, USDT",
            "evidence_sql": None,
            "confidence": None,
            "failure_reason": None,
        },
    )

    assert score.correct is True


def test_score_case_contains_text_accepts_formatted_numeric_text():
    score = score_case(
        type(
            "Case",
            (),
            {
                "id": "sentence_count",
                "comparison": "contains_text",
                "normalization": ["strip", "lower"],
            },
        )(),
        [{"answer": 108948}],
        {
            "task_id": "sentence_count",
            "status": "answered",
            "answer_value": 108948,
            "answer_text": "On 2026-02-01, there were 108,948 unique pools that traded.",
            "evidence_sql": None,
            "confidence": None,
            "failure_reason": None,
        },
    )

    assert score.correct is True


def test_build_claude_command_includes_strict_mcp_and_schema(tmp_path):
    cmd = build_claude_command(
        prompt="answer",
        model="claude-sonnet-4-5-20250929",
        session_id=str(uuid.uuid4()),
        mcp_config_path=tmp_path / "mcp.json",
        json_schema={"type": "object"},
        debug_log_path=tmp_path / "debug.log",
        workdir=tmp_path,
        tools=["Read", "Bash"],
    )
    assert "--print" in cmd
    assert "--strict-mcp-config" in cmd
    assert "--json-schema" in cmd
    assert "--mcp-config" in cmd
    assert "--tools" in cmd
    assert cmd[-2] == "--"
    assert cmd[-1] == "answer"


def test_extract_answer_payload_uses_structured_output_wrapper():
    payload = _extract_answer_payload(
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "structured_output": {
                    "task_id": "count_items",
                    "status": "answered",
                    "answer_value": 3,
                    "answer_text": "3",
                    "evidence_sql": "SELECT COUNT(*) FROM items",
                    "confidence": 0.9,
                    "failure_reason": None,
                },
            }
        )
    )

    assert payload["task_id"] == "count_items"
    assert payload["status"] == "answered"
    assert payload["answer_value"] == 3


def test_extract_answer_payload_with_recovery_uses_runtime_capture_when_structured_output_fails(
    benchmark_connection,
    tmp_path,
):
    raw_stdout = json.dumps(
        {
            "type": "result",
            "subtype": "error_max_structured_output_retries",
            "is_error": True,
            "errors": ["Failed to provide valid structured output after 5 attempts"],
        }
    )
    attempt_dir = tmp_path / "attempt"
    capture_dir = attempt_dir / "runtime-captures"
    capture_dir.mkdir(parents=True)
    captured_file = capture_dir / "001-runtime.py"
    captured_file.write_text(
        "\n".join(
            [
                "import json",
                "from dbmcp_host import dbmcp",
                "_ = dbmcp.read_protocol()",
                "sql = \"SELECT COUNT(*) AS answer FROM items\"",
                "answer = dbmcp.scalar(sql)",
                "print(json.dumps({",
                "    \"task_id\": \"count_items\",",
                "    \"status\": \"answered\",",
                "    \"answer_value\": answer,",
                "    \"answer_text\": str(answer),",
                "    \"evidence_sql\": sql,",
                "    \"confidence\": 1.0,",
                "    \"failure_reason\": None,",
                "}))",
            ]
        )
    )
    (attempt_dir / "runtime-invocations.jsonl").write_text(
        json.dumps({"argv": ["python3", "/tmp/runtime.py"], "captured_file": str(captured_file)})
        + "\n"
        + json.dumps(
            {
                "kind": "host_client_call",
                "method": "read_protocol",
                "session_id": "runtime-session",
                "connection": "bench",
            }
        )
        + "\n"
        + json.dumps(
            {
                "kind": "host_client_call",
                "method": "scalar",
                "session_id": "runtime-session",
                "connection": "bench",
            }
        )
        + "\n"
    )

    access = resolve_sql_connection_access("bench")
    payload = _extract_answer_payload_with_recovery(
        raw_stdout,
        attempt_dir=attempt_dir,
        connector=access.connector,
    )

    assert payload["task_id"] == "count_items"
    assert payload["status"] == "answered"
    assert payload["answer_value"] == 3
    assert payload["evidence_sql"] == "SELECT COUNT(*) AS answer FROM items"


def test_summarize_run_directory_and_fake_driver_smoke(benchmark_connection, tmp_path):
    outputs = {
        "db_mcp": {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.12,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_read_input_tokens": 40,
                "cache_creation_input_tokens": 10,
            },
            "structured_output": {
                "task_id": "count_items",
                "status": "answered",
                "answer_value": 3,
                "answer_text": "3",
                "evidence_sql": "SELECT COUNT(*) FROM items",
                "confidence": 0.9,
                "failure_reason": None,
            },
        },
        EXEC_ONLY_SCENARIO: {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.09,
            "usage": {
                "input_tokens": 90,
                "output_tokens": 19,
                "cache_read_input_tokens": 7,
                "cache_creation_input_tokens": 0,
            },
            "structured_output": {
                "task_id": "count_items",
                "status": "answered",
                "answer_value": 3,
                "answer_text": "3",
                "evidence_sql": "SELECT COUNT(*) FROM items",
                "confidence": 0.7,
                "failure_reason": None,
            },
        },
        CODE_MODE_SCENARIO: {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.1,
            "usage": {
                "input_tokens": 95,
                "output_tokens": 21,
                "cache_read_input_tokens": 8,
                "cache_creation_input_tokens": 0,
            },
            "structured_output": {
                "task_id": "count_items",
                "status": "answered",
                "answer_value": 3,
                "answer_text": "3",
                "evidence_sql": "SELECT COUNT(*) FROM items",
                "confidence": 0.75,
                "failure_reason": None,
            },
        },
        RUNTIME_CODE_SCENARIO: {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.11,
            "usage": {
                "input_tokens": 88,
                "output_tokens": 24,
                "cache_read_input_tokens": 7,
                "cache_creation_input_tokens": 0,
            },
            "structured_output": {
                "task_id": "count_items",
                "status": "answered",
                "answer_value": 3,
                "answer_text": "3",
                "evidence_sql": "SELECT COUNT(*) FROM items",
                "confidence": 0.73,
                "failure_reason": None,
            },
        },
        RUNTIME_NATIVE_SCENARIO: {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.105,
            "usage": {
                "input_tokens": 84,
                "output_tokens": 22,
                "cache_read_input_tokens": 6,
                "cache_creation_input_tokens": 0,
            },
            "structured_output": {
                "task_id": "count_items",
                "status": "answered",
                "answer_value": 3,
                "answer_text": "3",
                "evidence_sql": "SELECT COUNT(*) FROM items",
                "confidence": 0.74,
                "failure_reason": None,
            },
        },
        "raw_dsn": {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.08,
            "usage": {
                "input_tokens": 80,
                "output_tokens": 18,
                "cache_read_input_tokens": 5,
                "cache_creation_input_tokens": 0,
            },
            "structured_output": {
                "task_id": "count_items",
                "status": "answered",
                "answer_value": 2,
                "answer_text": "2",
                "evidence_sql": "SELECT COUNT(*) FROM items",
                "confidence": 0.3,
                "failure_reason": None,
            },
        },
    }
    driver = FakeDriver(outputs)
    runtime_server_calls: list[tuple[str, Path]] = []

    class FakeRuntimeServer:
        def __enter__(self):
            runtime_server_calls.append(("enter", Path("/tmp/fake")))
            return "http://127.0.0.1:8765"

        def __exit__(self, exc_type, exc, tb):
            runtime_server_calls.append(("exit", Path("/tmp/fake")))
            return False

    run_dir = run_benchmark_suite(
        connection_name="bench",
        connection_path=benchmark_connection,
        model="claude-sonnet-4-5-20250929",
        repeats=1,
        selected_case_ids=["count_items"],
        output_root=tmp_path,
        driver=driver,
        shuffle_seed=7,
        runtime_server_factory=lambda **_: FakeRuntimeServer(),
    )

    assert (run_dir / "summary.json").exists()
    assert (run_dir / "summary.csv").exists()
    attempts = list((run_dir / "attempts").iterdir())
    assert len(attempts) == 6

    summary = summarize_run_directory(run_dir)
    assert summary["totals"]["attempts"] == 6
    assert summary["scenario_summary"]["db_mcp"]["correct"] == 1
    assert summary["scenario_summary"][EXEC_ONLY_SCENARIO]["correct"] == 1
    assert summary["scenario_summary"][CODE_MODE_SCENARIO]["correct"] == 1
    assert summary["scenario_summary"][RUNTIME_CODE_SCENARIO]["correct"] == 1
    assert summary["scenario_summary"][RUNTIME_NATIVE_SCENARIO]["correct"] == 1
    assert summary["scenario_summary"]["raw_dsn"]["correct"] == 0
    assert summary["scenario_summary"]["db_mcp"]["input_tokens"] == 100
    assert summary["scenario_summary"]["db_mcp"]["output_tokens"] == 20
    assert summary["scenario_summary"]["db_mcp"]["cache_read_input_tokens"] == 40
    assert summary["scenario_summary"]["db_mcp"]["cache_creation_input_tokens"] == 10
    assert summary["scenario_summary"]["db_mcp"]["total_cost_usd"] == 0.12
    assert summary["scenario_summary"][EXEC_ONLY_SCENARIO]["input_tokens"] == 90
    assert summary["scenario_summary"][EXEC_ONLY_SCENARIO]["output_tokens"] == 19
    assert summary["scenario_summary"][EXEC_ONLY_SCENARIO]["total_cost_usd"] == 0.09
    assert summary["scenario_summary"][EXEC_ONLY_SCENARIO]["exploratory_steps"] == 1
    assert summary["scenario_summary"][EXEC_ONLY_SCENARIO]["failed_executions"] == 1
    assert summary["scenario_summary"][CODE_MODE_SCENARIO]["input_tokens"] == 95
    assert summary["scenario_summary"][CODE_MODE_SCENARIO]["output_tokens"] == 21
    assert summary["scenario_summary"][CODE_MODE_SCENARIO]["total_cost_usd"] == 0.1
    assert summary["scenario_summary"][CODE_MODE_SCENARIO]["exploratory_steps"] == 1
    assert summary["scenario_summary"][CODE_MODE_SCENARIO]["failed_executions"] == 1
    assert summary["scenario_summary"][RUNTIME_CODE_SCENARIO]["input_tokens"] == 88
    assert summary["scenario_summary"][RUNTIME_CODE_SCENARIO]["output_tokens"] == 24
    assert summary["scenario_summary"][RUNTIME_CODE_SCENARIO]["total_cost_usd"] == 0.11
    assert summary["scenario_summary"][RUNTIME_CODE_SCENARIO]["exploratory_steps"] == 1
    assert summary["scenario_summary"][RUNTIME_CODE_SCENARIO]["failed_executions"] == 0
    assert summary["scenario_summary"][RUNTIME_NATIVE_SCENARIO]["input_tokens"] == 84
    assert summary["scenario_summary"][RUNTIME_NATIVE_SCENARIO]["output_tokens"] == 22
    assert summary["scenario_summary"][RUNTIME_NATIVE_SCENARIO]["total_cost_usd"] == 0.105
    assert summary["scenario_summary"][RUNTIME_NATIVE_SCENARIO]["exploratory_steps"] == 1
    assert summary["scenario_summary"][RUNTIME_NATIVE_SCENARIO]["failed_executions"] == 0
    assert summary["scenario_summary"]["raw_dsn"]["input_tokens"] == 80
    assert summary["scenario_summary"]["raw_dsn"]["output_tokens"] == 18
    assert summary["scenario_summary"]["raw_dsn"]["total_cost_usd"] == 0.08
    assert len(driver.calls) == 6
    by_scenario = {call["scenario"]: call for call in driver.calls}
    assert by_scenario[EXEC_ONLY_SCENARIO]["tools"] == [""]
    assert "cat PROTOCOL.md" in str(by_scenario[EXEC_ONLY_SCENARIO]["prompt"])
    assert "Do not rely on any built-in tools." in str(by_scenario[EXEC_ONLY_SCENARIO]["prompt"])
    assert by_scenario[CODE_MODE_SCENARIO]["tools"] == [""]
    assert "/db-mcp-code-benchmark" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert "print(dbmcp.read_protocol())" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert "`dbmcp.read_protocol()` returns markdown text" in str(
        by_scenario[CODE_MODE_SCENARIO]["prompt"]
    )
    assert "Python helper object `dbmcp`" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert "dbmcp.find_table(...)" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert "dbmcp.describe_table(...)" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert "dbmcp.find_columns(...)" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert "write the SQL yourself" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert "Print the final JSON object yourself" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert "Do not guess table or column names" in str(by_scenario[CODE_MODE_SCENARIO]["prompt"])
    assert by_scenario[RUNTIME_CODE_SCENARIO]["tools"] == ["Bash"]
    assert "/db-mcp-runtime-benchmark" in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert "from dbmcp_host import dbmcp" in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert "python3 /tmp/dbmcp_runtime.py" in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert (
        "The first executable statement in the first runtime script must be "
        "`_ = dbmcp.read_protocol()`."
        in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    )
    assert (
        "After the protocol acknowledgment, inspect schema with `dbmcp.find_table(...)`, "
        "`dbmcp.describe_table(...)`, `dbmcp.find_columns(...)`, or "
        "`dbmcp.schema_descriptions()` and then write the SQL yourself."
        in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    )
    assert "For scalar questions, prefer a direct `dbmcp.scalar(\"SELECT ...\")` query" in str(
        by_scenario[RUNTIME_CODE_SCENARIO]["prompt"]
    )
    assert "Do not use `dbmcp.plan(...)` to generate SQL for you." in str(
        by_scenario[RUNTIME_CODE_SCENARIO]["prompt"]
    )
    assert "dbmcp.find_table(...)" in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert "dbmcp.describe_table(...)" in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert "dbmcp.find_columns(...)" in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert "dbmcp.schema_descriptions()" in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert '"task_id"' in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert '"status"' in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert '"answer_text"' in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert "Do not guess table or column names" in str(
        by_scenario[RUNTIME_CODE_SCENARIO]["prompt"]
    )
    assert "Do not rerun an identical discovery script after it succeeds." in str(
        by_scenario[RUNTIME_CODE_SCENARIO]["prompt"]
    )
    assert "_ = dbmcp.read_protocol()" in str(by_scenario[RUNTIME_CODE_SCENARIO]["prompt"])
    assert "Do not print the full protocol or full schema" in str(
        by_scenario[RUNTIME_CODE_SCENARIO]["prompt"]
    )
    assert by_scenario[RUNTIME_NATIVE_SCENARIO]["tools"] == ["Bash"]
    assert "/db-mcp-runtime-native-benchmark" in str(
        by_scenario[RUNTIME_NATIVE_SCENARIO]["prompt"]
    )
    assert "dbmcp is already available as a global native object" in str(
        by_scenario[RUNTIME_NATIVE_SCENARIO]["prompt"]
    )
    assert "Do not import `dbmcp` or `dbmcp_host`." in str(
        by_scenario[RUNTIME_NATIVE_SCENARIO]["prompt"]
    )
    assert "python3 /tmp/dbmcp_runtime_native.py" in str(
        by_scenario[RUNTIME_NATIVE_SCENARIO]["prompt"]
    )
    assert "_ = dbmcp.read_protocol()" in str(by_scenario[RUNTIME_NATIVE_SCENARIO]["prompt"])
    assert "You do not have db-mcp." in str(by_scenario["raw_dsn"]["prompt"])
    exec_attempt = next(path for path in attempts if EXEC_ONLY_SCENARIO in path.name)
    exec_mcp_config = (exec_attempt / "mcp-config.json").read_text()
    assert '"--mode"' in exec_mcp_config
    assert '"exec-only"' in exec_mcp_config
    code_attempt = next(path for path in attempts if CODE_MODE_SCENARIO in path.name)
    code_mcp_config = (code_attempt / "mcp-config.json").read_text()
    assert '"--mode"' in code_mcp_config
    assert '"code"' in code_mcp_config
    runtime_attempt = next(path for path in attempts if RUNTIME_CODE_SCENARIO in path.name)
    runtime_native_attempt = next(
        path for path in attempts if RUNTIME_NATIVE_SCENARIO in path.name
    )
    runtime_mcp_config = (runtime_attempt / "mcp-config.json").read_text()
    assert runtime_mcp_config.strip() == '{\n  "mcpServers": {}\n}'
    assert runtime_server_calls == [
        ("enter", Path("/tmp/fake")),
        ("exit", Path("/tmp/fake")),
        ("enter", Path("/tmp/fake")),
        ("exit", Path("/tmp/fake")),
    ]
    assert (code_attempt / ".claude" / "skills" / "db-mcp-code-benchmark" / "SKILL.md").exists()
    assert (
        runtime_attempt / ".claude" / "skills" / "db-mcp-runtime-benchmark" / "SKILL.md"
    ).exists()
    assert (
        runtime_native_attempt
        / ".claude"
        / "skills"
        / "db-mcp-runtime-native-benchmark"
        / "SKILL.md"
    ).exists()
    assert (runtime_attempt / "dbmcp_host.py").exists()
    assert not (runtime_native_attempt / "dbmcp_host.py").exists()
    assert (runtime_native_attempt / ".native-runtime" / "sitecustomize.py").exists()


def test_run_benchmark_suite_reports_progress_updates(benchmark_connection, tmp_path):
    outputs = {
        "db_mcp": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.9,
            "failure_reason": None,
        },
        EXEC_ONLY_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.7,
            "failure_reason": None,
        },
        CODE_MODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.75,
            "failure_reason": None,
        },
        RUNTIME_CODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.73,
            "failure_reason": None,
        },
        RUNTIME_NATIVE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.74,
            "failure_reason": None,
        },
        "raw_dsn": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 2,
            "answer_text": "2",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.3,
            "failure_reason": None,
        },
    }
    driver = FakeDriver(outputs)
    progress_updates: list[dict[str, object]] = []

    run_benchmark_suite(
        connection_name="bench",
        connection_path=benchmark_connection,
        model="claude-sonnet-4-5-20250929",
        repeats=1,
        selected_case_ids=["count_items"],
        output_root=tmp_path,
        driver=driver,
        shuffle_seed=7,
        progress_callback=progress_updates.append,
        runtime_server_factory=lambda **_: FakeRuntimeServerContext(),
    )

    assert len(progress_updates) == 6
    assert [update["completed_attempts"] for update in progress_updates] == [1, 2, 3, 4, 5, 6]
    assert all(update["total_attempts"] == 6 for update in progress_updates)
    assert {update["scenario"] for update in progress_updates} == {
        "db_mcp",
        EXEC_ONLY_SCENARIO,
        CODE_MODE_SCENARIO,
        RUNTIME_CODE_SCENARIO,
        RUNTIME_NATIVE_SCENARIO,
        "raw_dsn",
    }
    assert progress_updates[0]["case_id"] == "count_items"
    assert isinstance(progress_updates[0]["duration_ms"], float)
    assert progress_updates[0]["result"] in {"PASS", "FAIL"}


def test_claude_cli_driver_interrupts_active_process(monkeypatch, tmp_path):
    events: list[tuple[str, int | None]] = []

    class FakeProcess:
        pid = 43210

        def communicate(self):
            raise KeyboardInterrupt

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            return 130

        def kill(self):
            events.append(("kill", None))

    def fake_popen(*args, **kwargs):
        events.append(("popen", None))
        return FakeProcess()

    def fake_killpg(pid, sig):
        events.append(("killpg", pid))

    monkeypatch.setattr("db_mcp.benchmark.driver.subprocess.Popen", fake_popen)
    monkeypatch.setattr("db_mcp.benchmark.driver.os.killpg", fake_killpg)

    driver = ClaudeCliDriver()
    with pytest.raises(KeyboardInterrupt):
        driver.run(
            prompt="answer",
            json_schema={"type": "object"},
            session_id=str(uuid.uuid4()),
            mcp_config_path=tmp_path / "mcp.json",
            model="claude-sonnet-4-5-20250929",
            workdir=tmp_path,
            debug_log_path=tmp_path / "debug.log",
            tools=["Read", "Bash"],
        )

    assert ("killpg", 43210) in events


def test_claude_cli_driver_passes_custom_environment(monkeypatch, tmp_path):
    captured_env: dict[str, str] = {}

    class FakeProcess:
        pid = 54321
        returncode = 0

        def communicate(self):
            return ("{}", "")

    def fake_popen(*args, **kwargs):
        nonlocal captured_env
        captured_env = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr("db_mcp.benchmark.driver.subprocess.Popen", fake_popen)

    driver = ClaudeCliDriver()
    driver.run(
        prompt="answer",
        json_schema={"type": "object"},
        session_id=str(uuid.uuid4()),
        mcp_config_path=tmp_path / "mcp.json",
        model="claude-sonnet-4-5-20250929",
        workdir=tmp_path,
        debug_log_path=tmp_path / "debug.log",
        tools=["Bash"],
        env={"DB_MCP_BENCHMARK": "1"},
    )

    assert captured_env["DB_MCP_BENCHMARK"] == "1"


def test_claude_cli_driver_loop_breaker_kills_repeated_runtime_scripts(monkeypatch, tmp_path):
    runtime_log = tmp_path / "runtime-invocations.jsonl"
    capture = tmp_path / "runtime.py"
    capture.write_text("print('same script')\n")
    runtime_log.write_text(
        "\n".join(
            json.dumps({"captured_file": str(capture)})
            for _ in range(3)
        )
        + "\n"
    )

    killed: list[int] = []
    stop_event = threading.Event()

    def fake_killpg(pid, sig):
        killed.append(pid)

    monkeypatch.setattr("db_mcp.benchmark.driver.os.killpg", fake_killpg)

    _watch_runtime_loop(
        12345,
        LoopBreakerConfig(
            runtime_log_path=runtime_log,
            repetition_limit=3,
            poll_interval_seconds=0,
        ),
        stop_event,
    )

    assert killed == [12345]


def test_resolve_benchmark_db_mcp_binary_prefers_repo_dist(monkeypatch):
    expected = str(Path(__file__).resolve().parents[1] / "dist" / "db-mcp")
    monkeypatch.delenv("DB_MCP_BENCHMARK_BINARY", raising=False)
    monkeypatch.setattr("db_mcp.benchmark.runner.which", lambda _: "/tmp/venv/bin/db-mcp")
    monkeypatch.setattr(
        "db_mcp.benchmark.runner.Path.exists",
        lambda path: str(path) == expected,
    )

    resolved = _resolve_benchmark_db_mcp_binary()

    assert resolved == expected


def test_runtime_server_context_waits_for_process_and_terminates_process_group(
    monkeypatch, tmp_path
):
    events: list[tuple[str, object]] = []

    class FakeProcess:
        pid = 43210

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            return 0

        def poll(self):
            return None

    def fake_popen(*args, **kwargs):
        events.append(("popen", args[0]))
        return FakeProcess()

    def fake_wait(server_url, *, process=None, timeout_seconds=0.0, log_path=None):
        events.append(("wait_for_server", server_url))
        events.append(("wait_process", process.pid if process else None))
        events.append(("wait_timeout", timeout_seconds))
        events.append(("wait_log_path", log_path.name if log_path else None))

    def fake_killpg(pid, sig):
        events.append(("killpg", (pid, sig)))

    monkeypatch.setattr("db_mcp.benchmark.runner.subprocess.Popen", fake_popen)
    monkeypatch.setattr("db_mcp.benchmark.runner._reserve_runtime_port", lambda: 8099)
    monkeypatch.setattr("db_mcp.benchmark.runner._wait_for_runtime_server", fake_wait)
    monkeypatch.setattr("db_mcp.benchmark.runner.os.killpg", fake_killpg)
    (tmp_path / "attempt").mkdir()

    with _runtime_server_context(
        connection_name="playground",
        connections_dir=tmp_path / "connections",
        attempt_dir=tmp_path / "attempt",
    ) as server_url:
        assert server_url == "http://127.0.0.1:8099"

    assert ("wait_process", 43210) in events
    assert ("wait_timeout", 30.0) in events
    assert ("wait_log_path", "runtime-server.log") in events
    assert ("killpg", (43210, signal.SIGTERM)) in events
    assert ("wait", 5) in events


def test_runtime_code_attempt_persists_prompt_and_invocation_log(benchmark_connection, tmp_path):
    outputs = {
        "db_mcp": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.9,
            "failure_reason": None,
        },
        EXEC_ONLY_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.7,
            "failure_reason": None,
        },
        CODE_MODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.75,
            "failure_reason": None,
        },
        RUNTIME_CODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.73,
            "failure_reason": None,
        },
        RUNTIME_NATIVE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.74,
            "failure_reason": None,
        },
        "raw_dsn": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 2,
            "answer_text": "2",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.3,
            "failure_reason": None,
        },
    }
    driver = FakeDriver(outputs)

    run_dir = run_benchmark_suite(
        connection_name="bench",
        connection_path=benchmark_connection,
        model="claude-sonnet-4-5-20250929",
        repeats=1,
        selected_case_ids=["count_items"],
        output_root=tmp_path,
        driver=driver,
        shuffle_seed=7,
        runtime_server_factory=lambda **_: FakeRuntimeServerContext(),
    )

    runtime_attempt = next(
        path for path in (run_dir / "attempts").iterdir() if RUNTIME_CODE_SCENARIO in path.name
    )

    prompt_text = (runtime_attempt / "prompt.txt").read_text()
    invocation = json.loads(
        (runtime_attempt / "runtime-invocations.jsonl").read_text().splitlines()[0]
    )
    skill_text = (
        runtime_attempt / ".claude" / "skills" / "db-mcp-runtime-benchmark" / "SKILL.md"
    ).read_text()

    assert "from dbmcp_host import dbmcp" in prompt_text
    assert "python3 /tmp/dbmcp_runtime.py" in prompt_text
    assert (
        "The first executable statement in the first runtime script must be "
        "`_ = dbmcp.read_protocol()`."
        in prompt_text
    )
    assert (
        "After the protocol acknowledgment, inspect schema with `dbmcp.find_table(...)`, "
        "`dbmcp.describe_table(...)`, `dbmcp.find_columns(...)`, or "
        "`dbmcp.schema_descriptions()` and then write the SQL yourself."
        in prompt_text
    )
    assert (
        "For scalar questions, prefer a direct `dbmcp.scalar(\"SELECT ...\")` query"
        in prompt_text
    )
    assert "Do not use `dbmcp.plan(...)` to generate SQL for you." in prompt_text
    assert "dbmcp.find_table(...)" in prompt_text
    assert "dbmcp.describe_table(...)" in prompt_text
    assert "dbmcp.find_columns(...)" in prompt_text
    assert "dbmcp.schema_descriptions()" in prompt_text
    assert '"task_id"' in prompt_text
    assert '"status"' in prompt_text
    assert '"answer_text"' in prompt_text
    assert "Do not guess table or column names" in prompt_text
    assert "Do not rerun an identical discovery script after it succeeds." in prompt_text
    assert "_ = dbmcp.read_protocol()" in prompt_text
    assert "Do not print the full protocol or full schema" in prompt_text
    assert invocation["argv"] == ["python3", "/tmp/runtime.py"]
    assert Path(invocation["captured_file"]).exists()
    assert "`from dbmcp_host import dbmcp`" in skill_text
    assert (
        "The first executable statement in the first script must be "
        "`_ = dbmcp.read_protocol()`."
        in skill_text
    )
    assert "inspect schema with `dbmcp.find_table(...)`" in skill_text
    assert "`dbmcp.describe_table(...)`" in skill_text
    assert '`value = dbmcp.scalar("SELECT ...")`' in skill_text
    assert "Do not use `dbmcp.plan(...)` to generate SQL for you." in skill_text
    assert "dbmcp.find_table(...)" in skill_text
    assert "dbmcp.describe_table(...)" in skill_text
    assert "dbmcp.find_columns(...)" in skill_text
    assert "dbmcp.schema_descriptions()" in skill_text
    assert "If discovery succeeds, do not repeat it. Run the final query next." in skill_text
    assert "`dbmcp.read_protocol()` returns markdown text." in skill_text
    assert "Acknowledge the protocol silently" in skill_text
    assert '"task_id"' in skill_text
    assert '"status"' in skill_text
    assert '"answer_text"' in skill_text
    assert (runtime_attempt / "dbmcp_host.py").exists()
    wrapper_text = (runtime_attempt / ".runtime-bin" / "python3").read_text()
    assert '"$DB_MCP_REAL_PYTHON" - "$@" <<' in wrapper_text
    assert 'exec "$DB_MCP_REAL_PYTHON" "$@"' in wrapper_text


def test_runtime_code_attempt_fails_without_runtime_invocation(benchmark_connection, tmp_path):
    outputs = {
        "db_mcp": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.9,
            "failure_reason": None,
        },
        EXEC_ONLY_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.7,
            "failure_reason": None,
        },
        CODE_MODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.75,
            "failure_reason": None,
        },
        RUNTIME_CODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.73,
            "failure_reason": None,
        },
        RUNTIME_NATIVE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.74,
            "failure_reason": None,
        },
        "raw_dsn": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 2,
            "answer_text": "2",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.3,
            "failure_reason": None,
        },
    }
    driver = NoRuntimeInvocationDriver(outputs)

    run_dir = run_benchmark_suite(
        connection_name="bench",
        connection_path=benchmark_connection,
        model="claude-sonnet-4-5-20250929",
        repeats=1,
        selected_case_ids=["count_items"],
        output_root=tmp_path,
        driver=driver,
        shuffle_seed=7,
        runtime_server_factory=lambda **_: FakeRuntimeServerContext(),
    )

    runtime_attempt = next(
        path for path in (run_dir / "attempts").iterdir() if RUNTIME_CODE_SCENARIO in path.name
    )
    answer = json.loads((runtime_attempt / "answer.json").read_text())
    score = json.loads((runtime_attempt / "score.json").read_text())
    summary = json.loads((run_dir / "summary.json").read_text())

    assert answer["status"] == "failed"
    assert "dbmcp host runtime client" in answer["failure_reason"]
    assert score["correct"] is False
    assert summary["scenario_summary"][RUNTIME_CODE_SCENARIO]["correct"] == 0


def test_runtime_native_attempt_allows_inline_host_execution_without_captured_file(tmp_path):
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    (attempt_dir / "runtime-invocations.jsonl").write_text(
        json.dumps({"argv": [], "cwd": str(attempt_dir)})
        + "\n"
        + json.dumps(
            {
                "kind": "host_client_call",
                "method": "read_protocol",
                "session_id": "runtime-session",
                "connection": "bench",
            }
        )
        + "\n"
        + json.dumps(
            {
                "kind": "host_client_call",
                "method": "scalar",
                "session_id": "runtime-session",
                "connection": "bench",
            }
        )
        + "\n"
    )

    assert _validate_runtime_attempt(attempt_dir, scenario=RUNTIME_NATIVE_SCENARIO) is None


def test_runtime_code_attempt_allows_import_preamble_before_protocol_ack(
    benchmark_connection, tmp_path
):
    outputs = {
        "db_mcp": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.9,
            "failure_reason": None,
        },
        EXEC_ONLY_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.7,
            "failure_reason": None,
        },
        CODE_MODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.75,
            "failure_reason": None,
        },
        RUNTIME_CODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.73,
            "failure_reason": None,
        },
        RUNTIME_NATIVE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.74,
            "failure_reason": None,
        },
        "raw_dsn": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 2,
            "answer_text": "2",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.3,
            "failure_reason": None,
        },
    }
    driver = RuntimeImportPreambleDriver(outputs)

    run_dir = run_benchmark_suite(
        connection_name="bench",
        connection_path=benchmark_connection,
        model="claude-sonnet-4-5-20250929",
        repeats=1,
        selected_case_ids=["count_items"],
        output_root=tmp_path,
        driver=driver,
        shuffle_seed=7,
        runtime_server_factory=lambda **_: FakeRuntimeServerContext(),
    )

    runtime_attempt = next(
        path for path in (run_dir / "attempts").iterdir() if RUNTIME_CODE_SCENARIO in path.name
    )
    answer = json.loads((runtime_attempt / "answer.json").read_text())
    score = json.loads((runtime_attempt / "score.json").read_text())

    assert answer["status"] == "answered"
    assert answer["failure_reason"] is None
    assert score["correct"] is True


def test_runtime_native_attempt_uses_injected_global_without_import(
    benchmark_connection, tmp_path
):
    outputs = {
        "db_mcp": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.9,
            "failure_reason": None,
        },
        EXEC_ONLY_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.7,
            "failure_reason": None,
        },
        CODE_MODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.75,
            "failure_reason": None,
        },
        RUNTIME_CODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.73,
            "failure_reason": None,
        },
        RUNTIME_NATIVE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.74,
            "failure_reason": None,
        },
        "raw_dsn": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 2,
            "answer_text": "2",
            "evidence_sql": "SELECT COUNT(*) FROM items",
            "confidence": 0.3,
            "failure_reason": None,
        },
    }
    driver = RuntimeNativeGlobalDriver(outputs)

    run_dir = run_benchmark_suite(
        connection_name="bench",
        connection_path=benchmark_connection,
        model="claude-sonnet-4-5-20250929",
        repeats=1,
        selected_case_ids=["count_items"],
        output_root=tmp_path,
        driver=driver,
        shuffle_seed=7,
        runtime_server_factory=lambda **_: FakeRuntimeServerContext(),
    )

    runtime_attempt = next(
        path for path in (run_dir / "attempts").iterdir() if RUNTIME_NATIVE_SCENARIO in path.name
    )
    prompt_text = (runtime_attempt / "prompt.txt").read_text()
    script_text = Path(
        json.loads((runtime_attempt / "runtime-invocations.jsonl").read_text().splitlines()[0])[
            "captured_file"
        ]
    ).read_text()
    answer = json.loads((runtime_attempt / "answer.json").read_text())

    assert "Do not import `dbmcp` or `dbmcp_host`." in prompt_text
    assert "dbmcp is already available as a global native object" in prompt_text
    assert "dbmcp_host" not in script_text
    assert script_text.startswith("_ = dbmcp.read_protocol()")
    assert answer["status"] == "answered"


def test_run_benchmark_suite_recovers_runtime_answer_after_structured_output_failure(
    benchmark_connection, tmp_path
):
    outputs = {
        "db_mcp": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) AS answer FROM items",
            "confidence": 0.9,
            "failure_reason": None,
        },
        EXEC_ONLY_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) AS answer FROM items",
            "confidence": 0.7,
            "failure_reason": None,
        },
        CODE_MODE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) AS answer FROM items",
            "confidence": 0.75,
            "failure_reason": None,
        },
        RUNTIME_CODE_SCENARIO: {
            "task_id": "count_items",
            "status": "failed",
            "answer_value": None,
            "answer_text": "",
            "evidence_sql": None,
            "confidence": None,
            "failure_reason": "placeholder",
        },
        RUNTIME_NATIVE_SCENARIO: {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 3,
            "answer_text": "3",
            "evidence_sql": "SELECT COUNT(*) AS answer FROM items",
            "confidence": 0.74,
            "failure_reason": None,
        },
        "raw_dsn": {
            "task_id": "count_items",
            "status": "answered",
            "answer_value": 2,
            "answer_text": "2",
            "evidence_sql": "SELECT COUNT(*) AS answer FROM items",
            "confidence": 0.3,
            "failure_reason": None,
        },
    }
    driver = RuntimeStructuredFailureDriver(outputs)

    run_dir = run_benchmark_suite(
        connection_name="bench",
        connection_path=benchmark_connection,
        model="claude-sonnet-4-5-20250929",
        repeats=1,
        selected_case_ids=["count_items"],
        output_root=tmp_path,
        driver=driver,
        shuffle_seed=7,
        runtime_server_factory=lambda **_: FakeRuntimeServerContext(),
    )

    runtime_attempt = next(
        path for path in (run_dir / "attempts").iterdir() if RUNTIME_CODE_SCENARIO in path.name
    )
    answer = json.loads((runtime_attempt / "answer.json").read_text())
    score = json.loads((runtime_attempt / "score.json").read_text())

    assert answer["status"] == "answered"
    assert answer["answer_value"] == 3
    assert score["correct"] is True
