"""TDD tests for the vault schema registry (Phase 1).

Tests cover:
- SchemaEntry structure
- registry register() / lookup() API
- vault_write_typed() core flow:
    - unknown schema key raises KeyError
    - invalid content raises ValidationError before disk write
    - pre-hook raising aborts write
    - post-hooks fire after successful write
- Approved example entry: post-hook appends feedback log
- Corrected feedback entry: post-hook saves example for CORRECTED type
- Business rule entry: pre-hook aborts on duplicate; write succeeds on new rule
- Metric / dimension entries: write to catalogs
- Metric binding entry: pre-hook validates metric + dimensions exist
- Gap dismissal entry: pre-hook rejects unknown / non-open gaps
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from db_mcp_models import (
    FeedbackType,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _provider_dir(tmp: Path) -> Path:
    d = tmp / "connections" / "test"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Registry infrastructure
# ---------------------------------------------------------------------------


class TestRegistryAPI:
    def test_lookup_returns_entry(self):
        from pydantic import BaseModel

        from db_mcp_knowledge.vault.schema_registry import SchemaEntry, lookup, register

        class Dummy(BaseModel):
            value: str

        def writer(m, pid, cp):
            return {"saved": True}

        register("test_schema", SchemaEntry(model=Dummy, writer=writer))
        entry = lookup("test_schema")
        assert entry.model is Dummy

    def test_lookup_unknown_key_raises(self):
        from db_mcp_knowledge.vault.schema_registry import lookup

        with pytest.raises(KeyError):
            lookup("__nonexistent_schema_key__")

    def test_register_overwrites_existing(self):
        from pydantic import BaseModel

        from db_mcp_knowledge.vault.schema_registry import SchemaEntry, lookup, register

        class M1(BaseModel):
            x: int

        class M2(BaseModel):
            y: int

        def w(m, pid, cp):
            return {}

        register("overwrite_test", SchemaEntry(model=M1, writer=w))
        register("overwrite_test", SchemaEntry(model=M2, writer=w))
        assert lookup("overwrite_test").model is M2


# ---------------------------------------------------------------------------
# vault_write_typed — core flow
# ---------------------------------------------------------------------------


class TestVaultWriteTyped:
    def test_unknown_schema_key_raises_keyerror(self):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with pytest.raises(KeyError):
            vault_write_typed("__no_such_key__", {}, "p", Path("/tmp"))

    def test_invalid_content_raises_validation_error_before_write(self, tmp_path):
        """Writer must not be called if content fails Pydantic validation."""
        from pydantic import BaseModel

        from db_mcp_knowledge.vault.schema_registry import SchemaEntry, register, vault_write_typed

        writes: list[str] = []

        class Strict(BaseModel):
            required_int: int

        def writer(m, pid, cp):
            writes.append("called")
            return {"saved": True}

        register("strict_test", SchemaEntry(model=Strict, writer=writer))

        with pytest.raises(ValidationError):
            vault_write_typed("strict_test", {"required_int": "not-an-int"}, "p", tmp_path)

        assert writes == [], "writer must NOT be called when validation fails"

    def test_pre_hook_raises_aborts_write(self, tmp_path):
        from pydantic import BaseModel

        from db_mcp_knowledge.vault.schema_registry import SchemaEntry, register, vault_write_typed

        writes: list[str] = []

        class M(BaseModel):
            val: str

        def aborting_hook(m, pid, cp):
            raise ValueError("pre-hook abort")

        def writer(m, pid, cp):
            writes.append("called")
            return {"saved": True}

        register("pre_hook_test", SchemaEntry(model=M, writer=writer, pre_hooks=[aborting_hook]))

        with pytest.raises(ValueError, match="pre-hook abort"):
            vault_write_typed("pre_hook_test", {"val": "x"}, "p", tmp_path)

        assert writes == [], "writer must NOT be called after pre-hook raises"

    def test_post_hooks_fire_after_write(self, tmp_path):
        from pydantic import BaseModel

        from db_mcp_knowledge.vault.schema_registry import SchemaEntry, register, vault_write_typed

        fired: list[str] = []

        class M(BaseModel):
            val: str

        def writer(m, pid, cp):
            return {"saved": True}

        def post_hook(m, pid, cp):
            fired.append(m.val)

        register("post_hook_test", SchemaEntry(model=M, writer=writer, post_hooks=[post_hook]))
        vault_write_typed("post_hook_test", {"val": "hello"}, "p", tmp_path)

        assert fired == ["hello"]

    def test_writer_return_value_is_returned(self, tmp_path):
        from pydantic import BaseModel

        from db_mcp_knowledge.vault.schema_registry import SchemaEntry, register, vault_write_typed

        class M(BaseModel):
            x: int

        def writer(m, pid, cp):
            return {"saved": True, "value": m.x}

        register("return_test", SchemaEntry(model=M, writer=writer))
        result = vault_write_typed("return_test", {"x": 42}, "p", tmp_path)
        assert result == {"saved": True, "value": 42}


# ---------------------------------------------------------------------------
# approved_example entry
# ---------------------------------------------------------------------------


class TestApprovedExampleEntry:
    @pytest.fixture
    def pdir(self, tmp_path):
        return _provider_dir(tmp_path)

    def test_valid_example_saves_to_disk(self, tmp_path, pdir):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.training.store.get_provider_dir", return_value=pdir):
            result = vault_write_typed(
                "approved_example",
                {
                    "id": "abc12345",
                    "natural_language": "count users",
                    "sql": "SELECT COUNT(*) FROM users",
                },
                "test",
                tmp_path,
            )

        assert result.get("saved") is True
        example_file = pdir / "examples" / "abc12345.yaml"
        assert example_file.exists()

    def test_post_hook_appends_approved_feedback(self, tmp_path, pdir):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.training.store.get_provider_dir", return_value=pdir):
            vault_write_typed(
                "approved_example",
                {
                    "id": "feed0001",
                    "natural_language": "count users",
                    "sql": "SELECT COUNT(*) FROM users",
                },
                "test",
                tmp_path,
            )

            # Feedback log should have an APPROVED entry
            from db_mcp_knowledge.training.store import load_feedback

            log = load_feedback("test")

        assert len(log.feedback) == 1
        assert log.feedback[0].feedback_type == FeedbackType.APPROVED
        assert log.feedback[0].natural_language == "count users"

    def test_invalid_example_does_not_write(self, tmp_path, pdir):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.training.store.get_provider_dir", return_value=pdir):
            with pytest.raises(ValidationError):
                vault_write_typed(
                    "approved_example",
                    {"id": "x", "sql": "SELECT 1"},  # missing natural_language
                    "test",
                    tmp_path,
                )

        # Nothing written
        assert not (pdir / "examples").exists()


# ---------------------------------------------------------------------------
# corrected_feedback entry
# ---------------------------------------------------------------------------


class TestCorrectedFeedbackEntry:
    @pytest.fixture
    def pdir(self, tmp_path):
        return _provider_dir(tmp_path)

    def test_corrected_feedback_saves_log_and_example(self, tmp_path, pdir):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.training.store.get_provider_dir", return_value=pdir):
            vault_write_typed(
                "corrected_feedback",
                {
                    "id": "fb000001",
                    "natural_language": "count active users",
                    "generated_sql": "SELECT COUNT(*) FROM users",
                    "feedback_type": "corrected",
                    "corrected_sql": "SELECT COUNT(*) FROM users WHERE active = true",
                },
                "test",
                tmp_path,
            )

            from db_mcp_knowledge.training.store import load_examples, load_feedback

            log = load_feedback("test")
            examples = load_examples("test")

        assert len(log.feedback) == 1
        assert log.feedback[0].feedback_type == FeedbackType.CORRECTED
        assert examples.count() == 1
        assert "active = true" in examples.examples[0].sql

    def test_rejected_feedback_does_not_save_example(self, tmp_path, pdir):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.training.store.get_provider_dir", return_value=pdir):
            vault_write_typed(
                "corrected_feedback",
                {
                    "id": "fb000002",
                    "natural_language": "count active users",
                    "generated_sql": "SELECT COUNT(*) FROM users",
                    "feedback_type": "rejected",
                },
                "test",
                tmp_path,
            )

            from db_mcp_knowledge.training.store import load_examples, load_feedback

            log = load_feedback("test")
            examples = load_examples("test")

        assert len(log.feedback) == 1
        assert log.feedback[0].feedback_type == FeedbackType.REJECTED
        assert examples.count() == 0


# ---------------------------------------------------------------------------
# business_rule entry
# ---------------------------------------------------------------------------


class TestBusinessRuleEntry:
    @pytest.fixture
    def pdir(self, tmp_path):
        return _provider_dir(tmp_path)

    def test_new_rule_saved(self, tmp_path, pdir):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.training.store.get_provider_dir", return_value=pdir):
            result = vault_write_typed(
                "business_rule",
                {"rule": "Always filter by tenant_id"},
                "test",
                tmp_path,
            )

        assert result.get("added") is True
        assert result["total_rules"] == 1

    def test_duplicate_rule_raises_before_write(self, tmp_path, pdir):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.training.store.get_provider_dir", return_value=pdir):
            vault_write_typed("business_rule", {"rule": "Rule A"}, "test", tmp_path)
            with pytest.raises(ValueError, match="already exists"):
                vault_write_typed("business_rule", {"rule": "Rule A"}, "test", tmp_path)

    def test_empty_rule_rejected(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with pytest.raises(ValidationError):
            vault_write_typed("business_rule", {"rule": ""}, "test", tmp_path)


# ---------------------------------------------------------------------------
# metric entry
# ---------------------------------------------------------------------------


class TestMetricEntry:
    def test_metric_saved_to_catalog(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        result = vault_write_typed(
            "metric",
            {
                "name": "dau",
                "description": "Daily active users",
                "sql": "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE date = :date",
            },
            "test",
            tmp_path,
        )

        assert result.get("saved") is True
        from db_mcp_knowledge.metrics.store import load_metrics

        catalog = load_metrics("test", connection_path=tmp_path)
        assert catalog.get_metric("dau") is not None

    def test_metric_missing_name_raises(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with pytest.raises(ValidationError):
            vault_write_typed(
                "metric",
                {"description": "No name metric"},
                "test",
                tmp_path,
            )


# ---------------------------------------------------------------------------
# dimension entry
# ---------------------------------------------------------------------------


class TestDimensionEntry:
    def test_dimension_saved_to_catalog(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        result = vault_write_typed(
            "dimension",
            {
                "name": "country",
                "description": "User country",
                "column": "users.country",
            },
            "test",
            tmp_path,
        )

        assert result.get("saved") is True
        from db_mcp_knowledge.metrics.store import load_dimensions

        catalog = load_dimensions("test", connection_path=tmp_path)
        assert catalog.get_dimension("country") is not None


# ---------------------------------------------------------------------------
# metric_binding entry
# ---------------------------------------------------------------------------


class TestMetricBindingEntry:
    def test_binding_saved_when_metric_exists(self, tmp_path):
        from db_mcp_knowledge.metrics.store import add_metric
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        # Seed the metric catalog
        add_metric(
            "test",
            name="dau",
            description="Daily active users",
            sql="SELECT 1",
            connection_path=tmp_path,
        )

        result = vault_write_typed(
            "metric_binding",
            {
                "metric_name": "dau",
                "sql": "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE date = :date",
                "tables": ["sessions"],
            },
            "test",
            tmp_path,
        )

        assert result.get("saved") is True

    def test_pre_hook_aborts_when_metric_missing(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with pytest.raises(ValueError, match="not found in catalog"):
            vault_write_typed(
                "metric_binding",
                {
                    "metric_name": "nonexistent_metric",
                    "sql": "SELECT 1",
                },
                "test",
                tmp_path,
            )

    def test_pre_hook_aborts_when_dimension_missing(self, tmp_path):
        from db_mcp_knowledge.metrics.store import add_metric
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        add_metric(
            "test",
            name="dau",
            description="DAU",
            sql="SELECT 1",
            connection_path=tmp_path,
        )

        with pytest.raises(ValueError, match="Dimension 'missing_dim' not found"):
            vault_write_typed(
                "metric_binding",
                {
                    "metric_name": "dau",
                    "sql": "SELECT 1",
                    "dimensions": {
                        "missing_dim": {
                            "dimension_name": "missing_dim",
                            "projection_sql": "country",
                        }
                    },
                },
                "test",
                tmp_path,
            )


# ---------------------------------------------------------------------------
# gap_dismissal entry
# ---------------------------------------------------------------------------


class TestGapDismissalEntry:
    @pytest.fixture
    def pdir(self, tmp_path):
        return _provider_dir(tmp_path)

    def test_dismiss_open_gap(self, tmp_path, pdir):
        from db_mcp_models import GapSource, GapStatus

        from db_mcp_knowledge.gaps.store import add_gap, load_gaps
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.gaps.store._get_connection_dir", return_value=pdir):
            add_gap("test", "CUI", GapSource.TRACES)
            gaps = load_gaps("test")
            gap_id = gaps.gaps[0].id

            vault_write_typed(
                "gap_dismissal",
                {"gap_id": gap_id, "reason": "not a real term"},
                "test",
                tmp_path,
            )

            gaps_after = load_gaps("test")

        assert gaps_after.gaps[0].status == GapStatus.DISMISSED

    def test_pre_hook_rejects_unknown_gap(self, tmp_path, pdir):
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.gaps.store._get_connection_dir", return_value=pdir):
            with pytest.raises(ValueError, match="not found or not open"):
                vault_write_typed(
                    "gap_dismissal",
                    {"gap_id": "no_such_id"},
                    "test",
                    tmp_path,
                )

    def test_pre_hook_rejects_already_dismissed_gap(self, tmp_path, pdir):
        from db_mcp_models import GapSource

        from db_mcp_knowledge.gaps.store import add_gap, dismiss_gap, load_gaps
        from db_mcp_knowledge.vault.schema_registry import vault_write_typed

        with patch("db_mcp_knowledge.gaps.store._get_connection_dir", return_value=pdir):
            add_gap("test", "TRM", GapSource.TRACES)
            gap_id = load_gaps("test").gaps[0].id
            dismiss_gap("test", gap_id)

            with pytest.raises(ValueError, match="not found or not open"):
                vault_write_typed(
                    "gap_dismissal",
                    {"gap_id": gap_id},
                    "test",
                    tmp_path,
                )
