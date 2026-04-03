"""Tests for vault path constants and helpers."""

from pathlib import Path

from db_mcp_knowledge.vault.paths import (
    BUSINESS_RULES_FILE,
    CONNECTOR_FILE,
    DESCRIPTIONS_FILE,
    DIMENSIONS_FILE,
    DOMAIN_MODEL_FILE,
    EXAMPLES_DIR,
    FEEDBACK_LOG_FILE,
    KNOWLEDGE_GAPS_FILE,
    LEARNINGS_DIR,
    METRICS_BINDINGS_FILE,
    METRICS_CATALOG_FILE,
    PROTOCOL_FILE,
    SQL_RULES_FILE,
    STATE_FILE,
    business_rules_path,
    connector_path,
    descriptions_path,
    dimensions_path,
    domain_model_path,
    examples_dir,
    learnings_dir,
    metrics_bindings_path,
    metrics_catalog_path,
    protocol_path,
    sql_rules_path,
    state_path,
)


class TestConstants:
    def test_file_constants_are_strings(self):
        for name, val in [
            ("CONNECTOR_FILE", CONNECTOR_FILE),
            ("STATE_FILE", STATE_FILE),
            ("PROTOCOL_FILE", PROTOCOL_FILE),
            ("DESCRIPTIONS_FILE", DESCRIPTIONS_FILE),
            ("DOMAIN_MODEL_FILE", DOMAIN_MODEL_FILE),
            ("BUSINESS_RULES_FILE", BUSINESS_RULES_FILE),
            ("SQL_RULES_FILE", SQL_RULES_FILE),
            ("METRICS_CATALOG_FILE", METRICS_CATALOG_FILE),
            ("DIMENSIONS_FILE", DIMENSIONS_FILE),
            ("METRICS_BINDINGS_FILE", METRICS_BINDINGS_FILE),
            ("KNOWLEDGE_GAPS_FILE", KNOWLEDGE_GAPS_FILE),
            ("FEEDBACK_LOG_FILE", FEEDBACK_LOG_FILE),
        ]:
            assert isinstance(val, str), f"{name} should be str"

    def test_dir_constants_are_strings(self):
        assert isinstance(EXAMPLES_DIR, str)
        assert isinstance(LEARNINGS_DIR, str)

    def test_expected_values(self):
        assert CONNECTOR_FILE == "connector.yaml"
        assert STATE_FILE == "state.yaml"
        assert PROTOCOL_FILE == "PROTOCOL.md"
        assert DESCRIPTIONS_FILE == "schema/descriptions.yaml"
        assert DOMAIN_MODEL_FILE == "domain/model.md"
        assert BUSINESS_RULES_FILE == "instructions/business_rules.yaml"
        assert SQL_RULES_FILE == "instructions/sql_rules.md"
        assert METRICS_CATALOG_FILE == "metrics/catalog.yaml"
        assert DIMENSIONS_FILE == "metrics/dimensions.yaml"
        assert METRICS_BINDINGS_FILE == "metrics/bindings.yaml"
        assert KNOWLEDGE_GAPS_FILE == "knowledge_gaps.yaml"
        assert FEEDBACK_LOG_FILE == "feedback_log.yaml"
        assert EXAMPLES_DIR == "examples"
        assert LEARNINGS_DIR == "learnings"


class TestHelperFunctions:
    def test_helpers_return_path_objects(self):
        conn = Path("/tmp/test-conn")
        assert isinstance(connector_path(conn), Path)
        assert isinstance(state_path(conn), Path)
        assert isinstance(protocol_path(conn), Path)
        assert isinstance(descriptions_path(conn), Path)
        assert isinstance(domain_model_path(conn), Path)
        assert isinstance(business_rules_path(conn), Path)
        assert isinstance(sql_rules_path(conn), Path)
        assert isinstance(metrics_catalog_path(conn), Path)
        assert isinstance(dimensions_path(conn), Path)
        assert isinstance(metrics_bindings_path(conn), Path)
        assert isinstance(examples_dir(conn), Path)
        assert isinstance(learnings_dir(conn), Path)

    def test_helpers_build_correct_paths(self):
        conn = Path("/data/connections/mydb")
        assert connector_path(conn) == conn / "connector.yaml"
        assert state_path(conn) == conn / "state.yaml"
        assert protocol_path(conn) == conn / "PROTOCOL.md"
        assert descriptions_path(conn) == conn / "schema" / "descriptions.yaml"
        assert domain_model_path(conn) == conn / "domain" / "model.md"
        assert business_rules_path(conn) == conn / "instructions" / "business_rules.yaml"
        assert sql_rules_path(conn) == conn / "instructions" / "sql_rules.md"
        assert metrics_catalog_path(conn) == conn / "metrics" / "catalog.yaml"
        assert dimensions_path(conn) == conn / "metrics" / "dimensions.yaml"
        assert metrics_bindings_path(conn) == conn / "metrics" / "bindings.yaml"
        assert examples_dir(conn) == conn / "examples"
        assert learnings_dir(conn) == conn / "learnings"
