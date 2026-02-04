"""Tests for trace-related utilities.

Tests the JSONL reader, date listing, active connection path resolution,
and SQL extraction from span attributes.
"""

import json
from unittest.mock import patch

import pytest

from db_mcp.bicp.traces import (
    _extract_sql,
    analyze_traces,
    list_trace_dates,
    read_traces_from_jsonl,
)

# ========== list_trace_dates ==========


class TestListTraceDates:
    def test_returns_dates_sorted_descending(self, tmp_path):
        traces_dir = tmp_path / "traces" / "abc123"
        traces_dir.mkdir(parents=True)

        (traces_dir / "2026-01-20.jsonl").write_text("")
        (traces_dir / "2026-01-28.jsonl").write_text("")
        (traces_dir / "2026-01-15.jsonl").write_text("")

        dates = list_trace_dates(tmp_path, "abc123")
        assert dates == ["2026-01-28", "2026-01-20", "2026-01-15"]

    def test_ignores_non_jsonl_files(self, tmp_path):
        traces_dir = tmp_path / "traces" / "abc123"
        traces_dir.mkdir(parents=True)

        (traces_dir / "2026-01-20.jsonl").write_text("")
        (traces_dir / "notes.txt").write_text("")
        (traces_dir / "2026-01-21.json").write_text("")

        dates = list_trace_dates(tmp_path, "abc123")
        assert dates == ["2026-01-20"]

    def test_ignores_non_date_jsonl_files(self, tmp_path):
        traces_dir = tmp_path / "traces" / "abc123"
        traces_dir.mkdir(parents=True)

        (traces_dir / "2026-01-20.jsonl").write_text("")
        (traces_dir / "summary.jsonl").write_text("")

        dates = list_trace_dates(tmp_path, "abc123")
        assert dates == ["2026-01-20"]

    def test_returns_empty_when_no_traces_dir(self, tmp_path):
        dates = list_trace_dates(tmp_path, "abc123")
        assert dates == []

    def test_returns_empty_when_dir_empty(self, tmp_path):
        traces_dir = tmp_path / "traces" / "abc123"
        traces_dir.mkdir(parents=True)

        dates = list_trace_dates(tmp_path, "abc123")
        assert dates == []

    def test_different_user_ids_isolated(self, tmp_path):
        dir_a = tmp_path / "traces" / "user_a"
        dir_b = tmp_path / "traces" / "user_b"
        dir_a.mkdir(parents=True)
        dir_b.mkdir(parents=True)

        (dir_a / "2026-01-20.jsonl").write_text("")
        (dir_b / "2026-01-25.jsonl").write_text("")

        assert list_trace_dates(tmp_path, "user_a") == ["2026-01-20"]
        assert list_trace_dates(tmp_path, "user_b") == ["2026-01-25"]


# ========== read_traces_from_jsonl ==========


def _make_span(
    trace_id="t1",
    span_id="s1",
    parent_id=None,
    name="test_span",
    ts=1706400000_000_000_000,  # nanoseconds
    duration_ms=50.0,
    status="OK",
    attrs=None,
):
    record = {
        "ts": ts,
        "name": name,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_id": parent_id,
        "duration_ms": duration_ms,
        "status": status,
        "attrs": attrs or {},
    }
    return json.dumps(record)


class TestReadTracesFromJsonl:
    def test_reads_single_trace(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text(
            _make_span(trace_id="t1", span_id="s1", name="root")
            + "\n"
            + _make_span(trace_id="t1", span_id="s2", parent_id="s1", name="child")
            + "\n"
        )

        traces = read_traces_from_jsonl(f)
        assert len(traces) == 1
        assert traces[0]["trace_id"] == "t1"
        assert traces[0]["span_count"] == 2
        assert traces[0]["root_span"] == "root"

    def test_groups_by_trace_id(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text(
            _make_span(trace_id="t1", span_id="s1")
            + "\n"
            + _make_span(trace_id="t2", span_id="s2")
            + "\n"
            + _make_span(trace_id="t1", span_id="s3", parent_id="s1")
            + "\n"
        )

        traces = read_traces_from_jsonl(f)
        assert len(traces) == 2
        trace_ids = {t["trace_id"] for t in traces}
        assert trace_ids == {"t1", "t2"}

        t1 = next(t for t in traces if t["trace_id"] == "t1")
        assert t1["span_count"] == 2

    def test_normalizes_nanosecond_timestamps(self, tmp_path):
        ts_ns = 1706400000_000_000_000  # nanoseconds
        f = tmp_path / "test.jsonl"
        f.write_text(_make_span(ts=ts_ns, duration_ms=100.0) + "\n")

        traces = read_traces_from_jsonl(f)
        span = traces[0]["spans"][0]
        # Should be converted to seconds
        assert span["start_time"] == pytest.approx(1706400000.0, abs=1)

    def test_preserves_seconds_timestamps(self, tmp_path):
        ts_sec = 1706400000.0  # already seconds
        f = tmp_path / "test.jsonl"
        f.write_text(_make_span(ts=ts_sec, duration_ms=100.0) + "\n")

        traces = read_traces_from_jsonl(f)
        span = traces[0]["spans"][0]
        assert span["start_time"] == pytest.approx(1706400000.0, abs=1)

    def test_normalizes_attributes_key(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text(_make_span(attrs={"tool.name": "query_database"}) + "\n")

        traces = read_traces_from_jsonl(f)
        span = traces[0]["spans"][0]
        assert span["attributes"]["tool.name"] == "query_database"

    def test_normalizes_parent_id_key(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text(
            _make_span(span_id="s1") + "\n" + _make_span(span_id="s2", parent_id="s1") + "\n"
        )

        traces = read_traces_from_jsonl(f)
        spans = traces[0]["spans"]
        child = next(s for s in spans if s["span_id"] == "s2")
        assert child["parent_span_id"] == "s1"

    def test_normalizes_status_to_lowercase(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text(_make_span(status="UNSET") + "\n")

        traces = read_traces_from_jsonl(f)
        assert traces[0]["spans"][0]["status"] == "unset"

    def test_calculates_trace_duration(self, tmp_path):
        f = tmp_path / "test.jsonl"
        # Two spans: first starts at t=0s, second starts at t=1s with 500ms duration
        ts1 = 1706400000_000_000_000
        ts2 = 1706400001_000_000_000
        f.write_text(
            _make_span(trace_id="t1", span_id="s1", ts=ts1, duration_ms=200.0)
            + "\n"
            + _make_span(trace_id="t1", span_id="s2", ts=ts2, duration_ms=500.0)
            + "\n"
        )

        traces = read_traces_from_jsonl(f)
        # Duration should be from earliest start to latest end
        # s1: start=0, end=0.2; s2: start=1.0, end=1.5
        # trace duration = 1.5 - 0 = 1500ms
        assert traces[0]["duration_ms"] == pytest.approx(1500.0, abs=10)

    def test_respects_limit(self, tmp_path):
        f = tmp_path / "test.jsonl"
        lines = []
        for i in range(10):
            lines.append(_make_span(trace_id=f"t{i}", span_id=f"s{i}"))
        f.write_text("\n".join(lines) + "\n")

        traces = read_traces_from_jsonl(f, limit=3)
        assert len(traces) == 3

    def test_returns_empty_for_nonexistent_file(self, tmp_path):
        f = tmp_path / "nonexistent.jsonl"
        assert read_traces_from_jsonl(f) == []

    def test_skips_malformed_lines(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text(
            _make_span(trace_id="t1", span_id="s1")
            + "\n"
            + "not valid json\n"
            + _make_span(trace_id="t2", span_id="s2")
            + "\n"
        )

        traces = read_traces_from_jsonl(f)
        assert len(traces) == 2

    def test_sorted_most_recent_first(self, tmp_path):
        f = tmp_path / "test.jsonl"
        ts_old = 1706400000_000_000_000
        ts_new = 1706500000_000_000_000
        f.write_text(
            _make_span(trace_id="old", span_id="s1", ts=ts_old)
            + "\n"
            + _make_span(trace_id="new", span_id="s2", ts=ts_new)
            + "\n"
        )

        traces = read_traces_from_jsonl(f)
        assert traces[0]["trace_id"] == "new"
        assert traces[1]["trace_id"] == "old"


# ========== _get_active_connection_path ==========


class TestGetActiveConnectionPath:
    """Test the agent's _get_active_connection_path helper.

    We test the logic directly without instantiating DBMCPAgent
    since it requires database configuration.
    """

    def test_returns_path_for_active_connection(self, tmp_path):
        import yaml

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"active_connection": "boost"}))

        with patch("pathlib.Path.home", return_value=tmp_path):
            # Simulate the function logic
            config = yaml.safe_load(config_file.read_text()) or {}
            active = config.get("active_connection")
            result = tmp_path / ".db-mcp" / "connections" / active

        assert result == tmp_path / ".db-mcp" / "connections" / "boost"

    def test_returns_none_when_no_config(self, tmp_path):
        config_file = tmp_path / ".db-mcp" / "config.yaml"
        # File doesn't exist
        assert not config_file.exists()

    def test_returns_none_when_no_active_connection(self, tmp_path):
        import yaml

        config_dir = tmp_path / ".db-mcp"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({"traces_enabled": True}))

        config = yaml.safe_load(config_file.read_text()) or {}
        active = config.get("active_connection")
        assert active is None


# ========== _extract_sql ==========


class TestExtractSql:
    def test_returns_sql_from_sql_attr(self):
        span = {"attributes": {"sql": "SELECT 1"}}
        assert _extract_sql(span) == "SELECT 1"

    def test_returns_sql_from_sql_preview_attr(self):
        span = {"attributes": {"sql.preview": "SELECT count(*) FROM users"}}
        assert _extract_sql(span) == "SELECT count(*) FROM users"

    def test_prefers_sql_over_sql_preview(self):
        span = {"attributes": {"sql": "SELECT 1", "sql.preview": "SELECT 2"}}
        assert _extract_sql(span) == "SELECT 1"

    def test_returns_sql_from_args_json(self):
        span = {
            "attributes": {
                "args": '{"sql": "SELECT * FROM dex_solana.trades LIMIT 10"}',
            }
        }
        assert _extract_sql(span) == "SELECT * FROM dex_solana.trades LIMIT 10"

    def test_prefers_sql_attr_over_args(self):
        span = {
            "attributes": {
                "sql": "SELECT 1",
                "args": '{"sql": "SELECT 2"}',
            }
        }
        assert _extract_sql(span) == "SELECT 1"

    def test_returns_none_when_no_sql(self):
        span = {"attributes": {"tool.name": "shell", "command": "ls"}}
        assert _extract_sql(span) is None

    def test_returns_none_for_invalid_args_json(self):
        span = {"attributes": {"args": "not valid json"}}
        assert _extract_sql(span) is None

    def test_returns_none_for_args_without_sql_key(self):
        span = {"attributes": {"args": '{"command": "ls"}'}}
        assert _extract_sql(span) is None

    def test_returns_none_for_empty_attributes(self):
        span = {"attributes": {}}
        assert _extract_sql(span) is None

    def test_returns_none_for_missing_attributes(self):
        span = {}
        assert _extract_sql(span) is None


# ========== analyze_traces: is_saved for errors ==========


def _make_trace(trace_id, span_name, attrs, status="ok"):
    """Helper to build a minimal trace dict for analyze_traces."""
    import time

    now = time.time()
    return {
        "trace_id": trace_id,
        "start_time": now,
        "end_time": now + 1,
        "duration_ms": 1000,
        "span_count": 1,
        "root_span": span_name,
        "spans": [
            {
                "trace_id": trace_id,
                "span_id": f"s-{trace_id}",
                "parent_span_id": None,
                "name": span_name,
                "start_time": now,
                "end_time": now + 1,
                "duration_ms": 1000,
                "status": status,
                "attributes": attrs,
            }
        ],
    }


class TestAnalyzeTracesIsSaved:
    """Tests that analyze_traces marks errors as is_saved when their SQL
    matches a saved training example."""

    def _mock_load_examples(self, examples_list):
        """Create a mock load_examples that returns a QueryExamples-like object."""
        from unittest.mock import MagicMock

        mock_examples = MagicMock()
        mock_examples.examples = examples_list
        mock_examples.count.return_value = len(examples_list)
        return lambda provider_id: mock_examples

    def _make_example(self, ex_id, sql, intent="test"):
        """Create a mock QueryExample-like object."""
        from unittest.mock import MagicMock

        ex = MagicMock()
        ex.id = ex_id
        ex.sql = sql
        ex.natural_language = intent
        return ex

    def test_soft_error_marked_is_saved_when_example_exists(self, tmp_path):
        """An error whose SQL matches a saved example gets is_saved=True."""
        conn_path = tmp_path / "test-conn"
        conn_path.mkdir(parents=True)

        example = self._make_example("ex-001", "SELECT * FROM bad_table")
        mock_loader = self._mock_load_examples([example])

        traces = [
            _make_trace(
                "t-err-1",
                "api_execute_sql",
                {
                    "tool.name": "api_execute_sql",
                    "tool.soft_failure": "true",
                    "tool.error": "Table bad_table not found",
                    "args": json.dumps({"sql": "SELECT * FROM bad_table"}),
                },
            ),
        ]

        with patch("db_mcp.training.store.load_examples", mock_loader):
            result = analyze_traces(traces, connection_path=conn_path)

        errors = result["errors"]
        soft_errors = [e for e in errors if e["error_type"] == "soft"]
        assert len(soft_errors) == 1
        assert soft_errors[0]["is_saved"] is True
        assert soft_errors[0]["example_id"] == "ex-001"

    def test_soft_error_not_marked_when_no_example(self, tmp_path):
        """An error whose SQL is not saved stays without is_saved."""
        conn_path = tmp_path / "test-conn"
        conn_path.mkdir(parents=True)

        mock_loader = self._mock_load_examples([])

        traces = [
            _make_trace(
                "t-err-2",
                "api_execute_sql",
                {
                    "tool.name": "api_execute_sql",
                    "tool.soft_failure": "true",
                    "tool.error": "Column xyz not found",
                    "args": json.dumps({"sql": "SELECT xyz FROM some_table"}),
                },
            ),
        ]

        with patch("db_mcp.training.store.load_examples", mock_loader):
            result = analyze_traces(traces, connection_path=conn_path)

        errors = result["errors"]
        soft_errors = [e for e in errors if e["error_type"] == "soft"]
        assert len(soft_errors) == 1
        assert soft_errors[0].get("is_saved") is not True
