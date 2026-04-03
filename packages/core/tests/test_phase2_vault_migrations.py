"""Parity tests for Phase 2 vault write unification migrations.

These tests verify behaviors that must be preserved after migrating tool
handlers to delegate to vault_write_typed(). They are written BEFORE the
migration so we can confirm:

  - Behaviors that already exist: tests pass before AND after migration.
  - New behaviors (e.g. dedup on business_rule): tests fail before, pass after.

Each test class corresponds to one tool being migrated.
"""

from unittest.mock import MagicMock

import pytest

CONNECTION = "test-conn"


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def conn_path(tmp_path, monkeypatch):
    """Temp connection dir with all expected subdirectories."""
    conn = tmp_path / CONNECTION
    conn.mkdir()
    (conn / "examples").mkdir()
    (conn / "instructions").mkdir()
    (conn / "metrics").mkdir()

    # Patch get_provider_dir so training/gaps stores resolve to our tmp dir
    monkeypatch.setattr(
        "db_mcp_knowledge.training.store.get_provider_dir",
        lambda provider_id: conn,
    )
    monkeypatch.setattr(
        "db_mcp_knowledge.gaps.store._get_connection_dir",
        lambda provider_id: conn,
    )

    # Patch resolve_connection in all tool modules to return our tmp conn
    mock_conn_obj = MagicMock()

    def _resolve(connection):
        return (mock_conn_obj, CONNECTION, conn)

    monkeypatch.setattr("db_mcp.tools.training.resolve_connection", _resolve)
    monkeypatch.setattr("db_mcp.tools.gaps.resolve_connection", _resolve)
    monkeypatch.setattr("db_mcp.tools.metrics.resolve_connection", _resolve)

    return conn


# ---------------------------------------------------------------------------
# query_approve — dual-write parity
# ---------------------------------------------------------------------------


class TestQueryApproveDualWrite:
    """query_approve must write BOTH the example file AND the feedback log."""

    @pytest.mark.asyncio
    async def test_example_file_created_on_disk(self, conn_path):
        from db_mcp.tools.training import _query_approve

        result = await _query_approve(
            natural_language="count all users",
            sql="SELECT COUNT(*) FROM users",
            connection=CONNECTION,
        )

        assert result["status"] == "approved"
        example_files = list((conn_path / "examples").iterdir())
        assert len(example_files) == 1

    @pytest.mark.asyncio
    async def test_feedback_log_receives_approved_entry(self, conn_path):
        """The feedback log must be written as a side-effect of query_approve."""
        from db_mcp_knowledge.training.store import load_feedback
        from db_mcp_models import FeedbackType

        from db_mcp.tools.training import _query_approve

        await _query_approve(
            natural_language="count all users",
            sql="SELECT COUNT(*) FROM users",
            connection=CONNECTION,
        )

        log = load_feedback(CONNECTION)
        assert len(log.feedback) == 1
        assert log.feedback[0].feedback_type == FeedbackType.APPROVED
        assert log.feedback[0].natural_language == "count all users"

    @pytest.mark.asyncio
    async def test_response_keys_preserved(self, conn_path):
        from db_mcp.tools.training import _query_approve

        result = await _query_approve(
            natural_language="count all users",
            sql="SELECT COUNT(*) FROM users",
            connection=CONNECTION,
        )

        assert result["status"] == "approved"
        assert "example_id" in result
        assert "total_examples" in result
        assert result["total_examples"] == 1


# ---------------------------------------------------------------------------
# query_feedback — dual-write parity
# ---------------------------------------------------------------------------


class TestQueryFeedbackDualWrite:
    """query_feedback(corrected) must write feedback log AND a new example."""

    @pytest.mark.asyncio
    async def test_corrected_feedback_saves_log_entry(self, conn_path):
        from db_mcp_knowledge.training.store import load_feedback
        from db_mcp_models import FeedbackType

        from db_mcp.tools.training import _query_feedback

        await _query_feedback(
            natural_language="count active users",
            generated_sql="SELECT COUNT(*) FROM users",
            feedback_type="corrected",
            corrected_sql="SELECT COUNT(*) FROM users WHERE active = true",
            connection=CONNECTION,
        )

        log = load_feedback(CONNECTION)
        assert len(log.feedback) == 1
        assert log.feedback[0].feedback_type == FeedbackType.CORRECTED

    @pytest.mark.asyncio
    async def test_corrected_feedback_also_saves_example(self, conn_path):
        from db_mcp_knowledge.training.store import load_examples

        from db_mcp.tools.training import _query_feedback

        await _query_feedback(
            natural_language="count active users",
            generated_sql="SELECT COUNT(*) FROM users",
            feedback_type="corrected",
            corrected_sql="SELECT COUNT(*) FROM users WHERE active = true",
            connection=CONNECTION,
        )

        examples = load_examples(CONNECTION)
        assert examples.count() == 1
        assert "active = true" in examples.examples[0].sql

    @pytest.mark.asyncio
    async def test_rejected_feedback_does_not_save_example(self, conn_path):
        from db_mcp_knowledge.training.store import load_examples

        from db_mcp.tools.training import _query_feedback

        await _query_feedback(
            natural_language="count active users",
            generated_sql="SELECT COUNT(*) FROM users",
            feedback_type="rejected",
            connection=CONNECTION,
        )

        examples = load_examples(CONNECTION)
        assert examples.count() == 0

    @pytest.mark.asyncio
    async def test_response_keys_preserved(self, conn_path):
        from db_mcp.tools.training import _query_feedback

        result = await _query_feedback(
            natural_language="count active users",
            generated_sql="SELECT COUNT(*) FROM users",
            feedback_type="corrected",
            corrected_sql="SELECT COUNT(*) FROM users WHERE active = true",
            connection=CONNECTION,
        )

        assert result["status"] == "recorded"
        assert "feedback_id" in result
        assert "feedback_type" in result
        assert "total_feedback" in result


# ---------------------------------------------------------------------------
# query_add_rule — parity + new dedup behavior
# ---------------------------------------------------------------------------


class TestQueryAddRuleDedup:
    @pytest.mark.asyncio
    async def test_new_rule_is_saved(self, conn_path):
        from db_mcp.tools.training import _query_add_rule

        result = await _query_add_rule(rule="Always filter by tenant_id", connection=CONNECTION)

        assert result["status"] == "added"
        assert result["total_rules"] == 1

    @pytest.mark.asyncio
    async def test_duplicate_rule_returns_error(self, conn_path):
        """After migration, a duplicate rule must return an error, not silently add.

        NOTE: This test FAILS before migration (current code silently appends),
        and passes after (registry pre-hook raises ValueError on duplicate).
        """
        from db_mcp.tools.training import _query_add_rule

        await _query_add_rule(rule="Rule A", connection=CONNECTION)
        result = await _query_add_rule(rule="Rule A", connection=CONNECTION)

        assert result["status"] == "error"
        assert "already exists" in result["error"]


# ---------------------------------------------------------------------------
# dismiss_knowledge_gap — error path parity
# ---------------------------------------------------------------------------


class TestDismissKnowledgeGapParity:
    @pytest.mark.asyncio
    async def test_dismiss_open_gap_succeeds(self, conn_path):
        from db_mcp_knowledge.gaps.store import add_gap, load_gaps
        from db_mcp_models import GapSource

        from db_mcp.tools.gaps import _dismiss_knowledge_gap

        add_gap(CONNECTION, "CUI", GapSource.TRACES)
        gap_id = load_gaps(CONNECTION).gaps[0].id

        result = await _dismiss_knowledge_gap(gap_id=gap_id, connection=CONNECTION)

        assert result["status"] == "success"
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_dismiss_unknown_gap_returns_error(self, conn_path):
        from db_mcp.tools.gaps import _dismiss_knowledge_gap

        result = await _dismiss_knowledge_gap(gap_id="no_such_id", connection=CONNECTION)

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_dismiss_already_dismissed_returns_error(self, conn_path):
        from db_mcp_knowledge.gaps.store import add_gap, load_gaps
        from db_mcp_models import GapSource

        from db_mcp.tools.gaps import _dismiss_knowledge_gap

        add_gap(CONNECTION, "CUI", GapSource.TRACES)
        gap_id = load_gaps(CONNECTION).gaps[0].id

        await _dismiss_knowledge_gap(gap_id=gap_id, connection=CONNECTION)
        result = await _dismiss_knowledge_gap(gap_id=gap_id, connection=CONNECTION)

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_dismiss_group_dismisses_siblings(self, conn_path):
        from db_mcp_knowledge.gaps.store import load_gaps, merge_trace_gaps
        from db_mcp_models import GapStatus

        from db_mcp.tools.gaps import _dismiss_knowledge_gap

        merge_trace_gaps(
            CONNECTION,
            [
                {
                    "terms": [
                        {"term": "CUI", "searchCount": 2, "session": "s1", "timestamp": 0},
                        {"term": "chargeable_unit", "searchCount": 1, "session": "s1",
                         "timestamp": 0},
                    ],
                    "suggestedRule": None,
                    "schemaMatches": [],
                }
            ],
        )
        gaps = load_gaps(CONNECTION)
        assert len(gaps.gaps) == 2
        gap_id = gaps.gaps[0].id

        result = await _dismiss_knowledge_gap(gap_id=gap_id, connection=CONNECTION)

        assert result["count"] == 2
        gaps_after = load_gaps(CONNECTION)
        assert all(g.status == GapStatus.DISMISSED for g in gaps_after.gaps)
