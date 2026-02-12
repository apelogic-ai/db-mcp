"""Tests for proactive insight detection."""

import tempfile
from pathlib import Path

from db_mcp.insights.detector import (
    Insight,
    InsightStore,
    detect_insights,
    load_insights,
    save_insights,
    scan_and_update,
)


class TestInsightStore:
    def test_add_and_pending(self):
        store = InsightStore()
        i = Insight(
            id="t1", category="error", severity="warning", title="Test", summary="Test insight"
        )
        assert store.add(i) is True
        assert len(store.pending()) == 1

    def test_no_duplicates(self):
        store = InsightStore()
        i1 = Insight(
            id="t1", category="error", severity="warning", title="Test", summary="Test insight"
        )
        i2 = Insight(
            id="t1", category="error", severity="warning", title="Test", summary="Same ID"
        )
        store.add(i1)
        assert store.add(i2) is False
        assert len(store.pending()) == 1

    def test_dismiss(self):
        store = InsightStore()
        i = Insight(
            id="t1", category="error", severity="warning", title="Test", summary="Test insight"
        )
        store.add(i)
        assert store.dismiss("t1") is True
        assert len(store.pending()) == 0

    def test_dismiss_not_found(self):
        store = InsightStore()
        assert store.dismiss("nonexistent") is False

    def test_clear_dismissed(self):
        store = InsightStore()
        i1 = Insight(id="t1", category="error", severity="warning", title="Test1", summary="A")
        i2 = Insight(id="t2", category="error", severity="info", title="Test2", summary="B")
        store.add(i1)
        store.add(i2)
        store.dismiss("t1")
        removed = store.clear_dismissed()
        assert removed == 1
        assert len(store.insights) == 1


class TestPersistence:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            store = InsightStore()
            store.add(
                Insight(
                    id="p1",
                    category="pattern",
                    severity="action",
                    title="Repeated query",
                    summary="Query ran 5 times",
                    details={"count": 5},
                )
            )
            save_insights(path, store)

            loaded = load_insights(path)
            assert len(loaded.pending()) == 1
            assert loaded.pending()[0].id == "p1"
            assert loaded.pending()[0].details["count"] == 5

    def test_load_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            store = load_insights(Path(d))
            assert len(store.pending()) == 0


class TestDetectInsights:
    def _base_analysis(self):
        return {
            "traceCount": 0,
            "repeatedQueries": [],
            "validationFailures": [],
            "validationFailureCount": 0,
            "vocabularyGaps": [],
            "errors": [],
            "knowledgeCaptureCount": 0,
            "insights": {
                "generationCalls": 0,
                "callsWithExamples": 0,
                "exampleHitRate": None,
                "validateFailRate": None,
            },
        }

    def test_repeated_queries(self):
        analysis = self._base_analysis()
        analysis["repeatedQueries"] = [
            {
                "sql_preview": "SELECT count(*) FROM users",
                "full_sql": "SELECT count(*) FROM users",
                "suggested_intent": "count users",
                "count": 5,
                "is_example": False,
            }
        ]
        with tempfile.TemporaryDirectory() as d:
            insights = detect_insights(analysis, Path(d))
        assert len(insights) == 1
        assert insights[0].category == "pattern"
        assert "5 times" in insights[0].summary

    def test_repeated_queries_already_saved(self):
        analysis = self._base_analysis()
        analysis["repeatedQueries"] = [
            {
                "sql_preview": "SELECT 1",
                "full_sql": "SELECT 1",
                "count": 5,
                "is_example": True,  # Already saved
            }
        ]
        with tempfile.TemporaryDirectory() as d:
            insights = detect_insights(analysis, Path(d))
        assert len(insights) == 0

    def test_high_validation_failure_rate(self):
        analysis = self._base_analysis()
        analysis["insights"]["validateFailRate"] = 50
        analysis["validationFailureCount"] = 5
        analysis["validationFailures"] = [{"error_message": "table not found"} for _ in range(5)]
        with tempfile.TemporaryDirectory() as d:
            insights = detect_insights(analysis, Path(d))
        assert any(i.category == "error" for i in insights)

    def test_vocabulary_gaps(self):
        analysis = self._base_analysis()
        analysis["vocabularyGaps"] = [
            {
                "status": "open",
                "terms": [{"term": "ARR"}, {"term": "MRR"}],
            }
        ]
        with tempfile.TemporaryDirectory() as d:
            insights = detect_insights(analysis, Path(d))
        assert any(i.category == "gap" for i in insights)

    def test_no_captures_warning(self):
        analysis = self._base_analysis()
        analysis["traceCount"] = 15
        analysis["knowledgeCaptureCount"] = 0
        with tempfile.TemporaryDirectory() as d:
            insights = detect_insights(analysis, Path(d))
        assert any("No knowledge captured" in i.title for i in insights)

    def test_nothing_detected_on_clean(self):
        analysis = self._base_analysis()
        with tempfile.TemporaryDirectory() as d:
            insights = detect_insights(analysis, Path(d))
        assert len(insights) == 0


class TestScanAndUpdate:
    def test_scan_adds_new_insights(self):
        analysis = {
            "traceCount": 20,
            "repeatedQueries": [
                {
                    "sql_preview": "SELECT 1",
                    "full_sql": "SELECT 1",
                    "suggested_intent": "test",
                    "count": 4,
                    "is_example": False,
                }
            ],
            "validationFailures": [],
            "validationFailureCount": 0,
            "vocabularyGaps": [],
            "errors": [],
            "knowledgeCaptureCount": 0,
            "insights": {
                "generationCalls": 0,
                "callsWithExamples": 0,
                "exampleHitRate": None,
                "validateFailRate": None,
            },
        }
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            store = scan_and_update(path, analysis)
            assert len(store.pending()) >= 1

            # Second scan shouldn't duplicate
            store2 = scan_and_update(path, analysis)
            assert len(store2.pending()) == len(store.pending())


class TestConversationalSuggestions:
    def test_should_suggest_insights_with_pending_and_time(self):
        """Test that suggestions are made when insights exist and time threshold is met."""
        import time

        from db_mcp.insights.detector import should_suggest_insights

        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            store = InsightStore()
            # Add a pending insight
            insight = Insight(
                id="test",
                category="pattern",
                severity="action",
                title="Test",
                summary="Test insight",
            )
            store.add(insight)
            # Set last processed time to 25 hours ago
            store.last_processed_at = time.time() - (25 * 3600)
            save_insights(path, store)

            # Should suggest (has insights and >24h)
            assert should_suggest_insights(path, threshold_hours=24.0) is True

    def test_should_not_suggest_no_insights(self):
        """Test that no suggestions are made when no insights exist."""
        import time

        from db_mcp.insights.detector import should_suggest_insights

        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            store = InsightStore()
            store.last_processed_at = time.time() - (25 * 3600)  # Old timestamp
            save_insights(path, store)

            # Should not suggest (no insights)
            assert should_suggest_insights(path, threshold_hours=24.0) is False

    def test_should_not_suggest_recent_processing(self):
        """Test that no suggestions are made when insights were recently processed."""
        import time

        from db_mcp.insights.detector import should_suggest_insights

        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            store = InsightStore()
            # Add a pending insight
            insight = Insight(
                id="test",
                category="pattern",
                severity="action",
                title="Test",
                summary="Test insight",
            )
            store.add(insight)
            # Set last processed time to 1 hour ago
            store.last_processed_at = time.time() - 3600
            save_insights(path, store)

            # Should not suggest (recent processing)
            assert should_suggest_insights(path, threshold_hours=24.0) is False

    def test_mark_insights_processed_updates_timestamp(self):
        """Test that marking insights as processed updates the timestamp."""
        import time

        from db_mcp.insights.detector import mark_insights_processed

        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            store = InsightStore()
            store.last_processed_at = 0.0  # Never processed
            save_insights(path, store)

            # Mark as processed
            before_time = time.time()
            mark_insights_processed(path)
            after_time = time.time()

            # Load and check timestamp was updated
            updated_store = load_insights(path)
            assert updated_store.last_processed_at >= before_time
            assert updated_store.last_processed_at <= after_time

    def test_persistence_includes_last_processed_at(self):
        """Test that last_processed_at is saved and loaded correctly."""
        import time

        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            store = InsightStore()
            test_time = time.time() - 12345
            store.last_processed_at = test_time
            save_insights(path, store)

            # Load and verify
            loaded_store = load_insights(path)
            assert loaded_store.last_processed_at == test_time
