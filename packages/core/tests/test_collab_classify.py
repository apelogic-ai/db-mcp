"""Tests for file classification (additive vs shared-state)."""

from db_mcp.collab.classify import classify_files, is_additive, is_auto_mergeable_shared


class TestIsAdditive:
    """Test individual file classification."""

    # Additive files
    def test_example_yaml(self):
        assert is_additive("examples/abc123.yaml") is True

    def test_learning_failure(self):
        assert is_additive("learnings/failures/def456.yaml") is True

    def test_learning_patterns_md(self):
        assert is_additive("learnings/patterns.md") is True

    def test_learning_schema_gotchas_md(self):
        assert is_additive("learnings/schema_gotchas.md") is True

    def test_learning_trace_analysis_md(self):
        assert is_additive("learnings/trace-analysis-patterns.md") is True

    def test_trace_jsonl(self):
        assert is_additive("traces/user123/2026-02-06.jsonl") is True

    def test_trace_dir(self):
        assert is_additive("traces/user123") is True

    # Nested paths that should NOT match (depth-sensitive matching)
    def test_nested_example_not_additive(self):
        assert is_additive("examples/nested/foo.yaml") is False

    def test_deeply_nested_example_not_additive(self):
        assert is_additive("examples/nested/deep/file.yaml") is False

    def test_nested_learning_failure_not_additive(self):
        assert is_additive("learnings/failures/deep/foo.yaml") is False

    def test_nested_learning_md_not_additive(self):
        assert is_additive("learnings/deep/foo.md") is False

    def test_traces_single_level(self):
        assert is_additive("traces/anything") is True

    def test_traces_deep_via_globstar(self):
        assert is_additive("traces/any/depth/anything") is True

    def test_traces_two_levels(self):
        assert is_additive("traces/a/b") is True

    # Shared-state files
    def test_schema_descriptions(self):
        assert is_additive("schema/descriptions.yaml") is False

    def test_domain_model(self):
        assert is_additive("domain/model.md") is False

    def test_business_rules(self):
        assert is_additive("instructions/business_rules.yaml") is False

    def test_sql_rules(self):
        assert is_additive("instructions/sql_rules.md") is False

    def test_metrics_catalog(self):
        assert is_additive("metrics/catalog.yaml") is False

    def test_metrics_dimensions(self):
        assert is_additive("metrics/dimensions.yaml") is False

    def test_knowledge_gaps(self):
        assert is_additive("knowledge_gaps.yaml") is False

    def test_feedback_log(self):
        assert is_additive("feedback_log.yaml") is False

    def test_collab_manifest(self):
        assert is_additive(".collab.yaml") is False

    def test_protocol_md(self):
        assert is_additive("PROTOCOL.md") is False


class TestClassifyFiles:
    """Test batch classification."""

    def test_all_additive(self):
        files = [
            "examples/a.yaml",
            "examples/b.yaml",
            "learnings/failures/c.yaml",
        ]
        additive, shared = classify_files(files)
        assert additive == files
        assert shared == []

    def test_all_shared(self):
        files = [
            "schema/descriptions.yaml",
            "domain/model.md",
        ]
        additive, shared = classify_files(files)
        assert additive == []
        assert shared == files

    def test_mixed(self):
        files = [
            "examples/a.yaml",
            "schema/descriptions.yaml",
            "learnings/patterns.md",
            "instructions/business_rules.yaml",
            "traces/u1/2026-01-01.jsonl",
        ]
        additive, shared = classify_files(files)
        assert additive == [
            "examples/a.yaml",
            "learnings/patterns.md",
            "traces/u1/2026-01-01.jsonl",
        ]
        assert shared == [
            "schema/descriptions.yaml",
            "instructions/business_rules.yaml",
        ]

    def test_empty_list(self):
        additive, shared = classify_files([])
        assert additive == []
        assert shared == []

    def test_nested_not_classified_as_additive(self):
        """Nested paths should be shared-state, not additive."""
        files = [
            "examples/nested/deep/file.yaml",
            "learnings/failures/deep/foo.yaml",
            "learnings/deep/foo.md",
        ]
        additive, shared = classify_files(files)
        assert additive == []
        assert shared == files


class TestAutoMergeableShared:
    def test_collab_yaml_only(self):
        assert is_auto_mergeable_shared([".collab.yaml"]) is True

    def test_collab_yaml_with_other(self):
        assert is_auto_mergeable_shared([".collab.yaml", "schema/foo.yaml"]) is False

    def test_empty(self):
        assert is_auto_mergeable_shared([]) is True

    def test_non_collab(self):
        assert is_auto_mergeable_shared(["schema/foo.yaml"]) is False
