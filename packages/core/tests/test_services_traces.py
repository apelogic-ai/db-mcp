"""Tests for services/traces.py — trace and insight service functions.

Step 4.05: Replace trace/insight BICP handlers with service calls.
"""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# list_traces
# ---------------------------------------------------------------------------


class TestListTracesLive:
    def test_returns_live_traces(self):
        from db_mcp.services.traces import list_traces

        fake_traces = [{"trace_id": "t1"}, {"trace_id": "t2"}]
        mock_collector = MagicMock()
        mock_collector.get_traces.return_value = fake_traces

        with patch("db_mcp.services.traces._get_collector", return_value=mock_collector):
            result = list_traces(source="live", limit=10)

        assert result["success"] is True
        assert result["source"] == "live"
        assert result["traces"] == fake_traces
        mock_collector.get_traces.assert_called_once_with(limit=10)

    def test_live_uses_default_limit_50(self):
        from db_mcp.services.traces import list_traces

        mock_collector = MagicMock()
        mock_collector.get_traces.return_value = []

        with patch("db_mcp.services.traces._get_collector", return_value=mock_collector):
            list_traces(source="live")

        mock_collector.get_traces.assert_called_once_with(limit=50)


class TestListTracesHistorical:
    def test_returns_historical_traces(self, tmp_path):
        from db_mcp.services.traces import list_traces

        fake_traces = [{"trace_id": "h1"}]

        with (
            patch("db_mcp.services.traces._is_traces_enabled", return_value=True),
            patch("db_mcp.services.traces._get_user_id", return_value="uid123"),
            patch("db_mcp.services.traces._get_traces_dir", return_value=tmp_path),
            patch("db_mcp.services.traces._read_traces_from_jsonl", return_value=fake_traces),
        ):
            result = list_traces(
                source="historical",
                connection_path=tmp_path,
                date_str="2026-01-20",
                limit=100,
            )

        assert result["success"] is True
        assert result["source"] == "historical"
        assert result["traces"] == fake_traces

    def test_historical_uses_default_limit_500(self, tmp_path):
        from db_mcp.services.traces import list_traces

        with (
            patch("db_mcp.services.traces._is_traces_enabled", return_value=True),
            patch("db_mcp.services.traces._get_user_id", return_value="uid123"),
            patch("db_mcp.services.traces._get_traces_dir", return_value=tmp_path),
            patch("db_mcp.services.traces._read_traces_from_jsonl", return_value=[]) as mock_read,
        ):
            list_traces(source="historical", connection_path=tmp_path, date_str="2026-01-20")

        mock_read.assert_called_once()
        _, kwargs = mock_read.call_args
        assert kwargs.get("limit") == 500 or mock_read.call_args[0][1] == 500

    def test_historical_error_when_traces_disabled(self, tmp_path):
        from db_mcp.services.traces import list_traces

        with patch("db_mcp.services.traces._is_traces_enabled", return_value=False):
            result = list_traces(
                source="historical",
                connection_path=tmp_path,
                date_str="2026-01-20",
            )

        assert result["success"] is False
        assert "not enabled" in result["error"].lower()

    def test_historical_error_when_no_user_id(self, tmp_path):
        from db_mcp.services.traces import list_traces

        with (
            patch("db_mcp.services.traces._is_traces_enabled", return_value=True),
            patch("db_mcp.services.traces._get_user_id", return_value=None),
        ):
            result = list_traces(
                source="historical",
                connection_path=tmp_path,
                date_str="2026-01-20",
            )

        assert result["success"] is False
        assert "user_id" in result["error"].lower()

    def test_historical_error_when_no_connection_path(self):
        from db_mcp.services.traces import list_traces

        with (
            patch("db_mcp.services.traces._is_traces_enabled", return_value=True),
            patch("db_mcp.services.traces._get_user_id", return_value="uid123"),
        ):
            result = list_traces(source="historical", connection_path=None, date_str="2026-01-20")

        assert result["success"] is False
        assert "connection" in result["error"].lower()

    def test_unknown_source_returns_error(self):
        from db_mcp.services.traces import list_traces

        result = list_traces(source="unknown")

        assert result["success"] is False
        assert "unknown" in result["error"].lower()


# ---------------------------------------------------------------------------
# clear_traces
# ---------------------------------------------------------------------------


class TestClearTraces:
    def test_clears_live_collector(self):
        from db_mcp.services.traces import clear_traces

        mock_collector = MagicMock()

        with patch("db_mcp.services.traces._get_collector", return_value=mock_collector):
            result = clear_traces()

        assert result["success"] is True
        mock_collector.clear.assert_called_once()


# ---------------------------------------------------------------------------
# get_trace_dates
# ---------------------------------------------------------------------------


class TestGetTraceDates:
    def test_returns_dates_when_enabled(self, tmp_path):
        from db_mcp.services.traces import get_trace_dates

        with (
            patch("db_mcp.services.traces._is_traces_enabled", return_value=True),
            patch("db_mcp.services.traces._get_user_id", return_value="uid123"),
            patch(
                "db_mcp.services.traces._list_trace_dates_from_dir",
                return_value=["2026-01-28", "2026-01-27"],
            ),
        ):
            result = get_trace_dates(connection_path=tmp_path)

        assert result["success"] is True
        assert result["enabled"] is True
        assert result["dates"] == ["2026-01-28", "2026-01-27"]

    def test_returns_enabled_false_when_disabled(self, tmp_path):
        from db_mcp.services.traces import get_trace_dates

        with patch("db_mcp.services.traces._is_traces_enabled", return_value=False):
            result = get_trace_dates(connection_path=tmp_path)

        assert result["success"] is True
        assert result["enabled"] is False
        assert result["dates"] == []

    def test_returns_empty_dates_when_no_user_id(self, tmp_path):
        from db_mcp.services.traces import get_trace_dates

        with (
            patch("db_mcp.services.traces._is_traces_enabled", return_value=True),
            patch("db_mcp.services.traces._get_user_id", return_value=None),
        ):
            result = get_trace_dates(connection_path=tmp_path)

        assert result["success"] is True
        assert result["enabled"] is True
        assert result["dates"] == []

    def test_returns_empty_dates_when_no_connection_path(self):
        from db_mcp.services.traces import get_trace_dates

        with (
            patch("db_mcp.services.traces._is_traces_enabled", return_value=True),
            patch("db_mcp.services.traces._get_user_id", return_value="uid123"),
        ):
            result = get_trace_dates(connection_path=None)

        assert result["success"] is True
        assert result["enabled"] is True
        assert result["dates"] == []
