from __future__ import annotations

import json

from click.testing import CliRunner

from db_mcp.benchmark.cli import main


def test_benchmark_app_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "benchmark" in result.output.lower()


def test_benchmark_preflight_json(monkeypatch, tmp_path):
    payload = {
        "status": "pass",
        "connection": "bench",
        "checks": [{"name": "claude_cli", "status": "pass"}],
    }
    monkeypatch.setattr(
        "db_mcp.benchmark.cli.run_preflight",
        lambda connection, case_pack="cases.yaml": payload,
    )

    runner = CliRunner()
    result = runner.invoke(main, ["preflight", "--connection", "bench", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "pass"


def test_benchmark_run_prints_run_directory(monkeypatch, tmp_path):
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    monkeypatch.setattr(
        "db_mcp.benchmark.cli.run_benchmark_suite_from_cli",
        lambda **kwargs: run_dir,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--connection",
            "bench",
            "--model",
            "claude-sonnet-4-5-20250929",
            "--case-pack",
            "cases_complex.yaml",
            "--output-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert str(run_dir) in result.output


def test_benchmark_run_passes_selected_scenarios(monkeypatch, tmp_path):
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    captured: dict[str, object] = {}

    def fake_run_benchmark_suite_from_cli(**kwargs):
        captured.update(kwargs)
        return run_dir

    monkeypatch.setattr(
        "db_mcp.benchmark.cli.run_benchmark_suite_from_cli",
        fake_run_benchmark_suite_from_cli,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--connection",
            "bench",
            "--model",
            "claude-sonnet-4-5-20250929",
            "--scenario",
            "runtime_daemon",
            "--scenario",
            "db_mcp",
            "--output-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert captured["scenarios"] == ("runtime_daemon", "db_mcp")


def test_benchmark_run_prints_progress(monkeypatch, tmp_path):
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()

    def fake_run_benchmark_suite_from_cli(**kwargs):
        progress_callback = kwargs["progress_callback"]
        progress_callback(
            {
                "case_id": "count_items",
                "scenario": "db_mcp",
                "repeat": 1,
                "completed_attempts": 1,
                "total_attempts": 2,
                "duration_ms": 1200.0,
                "result": "PASS",
            }
        )
        progress_callback(
            {
                "case_id": "count_items",
                "scenario": "raw_dsn",
                "repeat": 1,
                "completed_attempts": 2,
                "total_attempts": 2,
                "duration_ms": 2400.0,
                "result": "FAIL",
            }
        )
        return run_dir

    monkeypatch.setattr(
        "db_mcp.benchmark.cli.run_benchmark_suite_from_cli",
        fake_run_benchmark_suite_from_cli,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--connection",
            "bench",
            "--model",
            "claude-sonnet-4-5-20250929",
            "--case-pack",
            "cases_complex.yaml",
            "--output-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert "1/2" in result.output
    assert "count_items" in result.output
    assert "db_mcp" in result.output
    assert "PASS" in result.output
    assert "FAIL" in result.output


def test_benchmark_run_aborts_on_keyboard_interrupt(monkeypatch, tmp_path):
    def fake_run_benchmark_suite_from_cli(**kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "db_mcp.benchmark.cli.run_benchmark_suite_from_cli",
        fake_run_benchmark_suite_from_cli,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--connection",
            "bench",
            "--model",
            "claude-sonnet-4-5-20250929",
            "--case-pack",
            "cases_complex.yaml",
            "--output-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "Aborted" in result.output


def test_benchmark_summarize_json(monkeypatch, tmp_path):
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    payload = {
        "totals": {"attempts": 2},
        "scenario_summary": {"db_mcp": {"correct": 1}, "raw_dsn": {"correct": 0}},
    }
    monkeypatch.setattr("db_mcp.benchmark.cli.summarize_run_directory", lambda path: payload)

    runner = CliRunner()
    result = runner.invoke(main, ["summarize", str(run_dir), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["totals"]["attempts"] == 2
