"""Tests for business-rule normalization helpers."""

from pathlib import Path

import yaml
from db_mcp_models import BoundaryMode, SemanticPolicy
from db_mcp_models.policy import TimeWindowPolicy, UnitConversionPolicy

from db_mcp.bicp.traces import _check_knowledge_status
from db_mcp.business_rules import compile_semantic_policy, extract_business_rule_texts
from db_mcp.training.store import load_instructions


def test_extract_business_rule_texts_supports_top_level_rule_list() -> None:
    payload = [
        {"rule": "Use binary units.", "severity": "critical"},
        {"rule": "Date windows are inclusive.", "keywords": ["date"]},
    ]

    assert extract_business_rule_texts(payload) == [
        "Use binary units.",
        "Date windows are inclusive.",
    ]


def test_load_instructions_supports_top_level_rule_list(tmp_path: Path, monkeypatch) -> None:
    provider_path = tmp_path / "demo"
    instructions_dir = provider_path / "instructions"
    instructions_dir.mkdir(parents=True)
    (instructions_dir / "business_rules.yaml").write_text(
        yaml.safe_dump(
            [
                {"rule": "Use binary units.", "severity": "critical"},
                {"rule": "Date windows are inclusive.", "severity": "critical"},
            ],
            sort_keys=False,
        )
    )

    monkeypatch.setattr(
        "db_mcp.training.store.get_provider_dir",
        lambda provider_id: provider_path,
    )

    instructions = load_instructions("demo")

    assert instructions.provider_id == "demo"
    assert instructions.rules == [
        "Use binary units.",
        "Date windows are inclusive.",
    ]


def test_check_knowledge_status_counts_top_level_rule_list(tmp_path: Path) -> None:
    connection_path = tmp_path / "demo"
    (connection_path / "instructions").mkdir(parents=True)
    (connection_path / "instructions" / "business_rules.yaml").write_text(
        yaml.safe_dump(
            [
                {"rule": "Use binary units.", "severity": "critical"},
                {"rule": "Date windows are inclusive.", "severity": "critical"},
            ],
            sort_keys=False,
        )
    )

    status = _check_knowledge_status(connection_path)

    assert status["ruleCount"] == 2


def test_compile_semantic_policy_extracts_time_window_and_unit_rules() -> None:
    payload = [
        {
            "rule": (
                "Period ending on X is INCLUSIVE of day X. "
                "The end-date boundary must be date <= X or date < X + 1 day."
            )
        },
        {
            "rule": (
                "For daily_stats tables with date column: "
                "N-day window ending on X = WHERE date >= DATE 'X' - INTERVAL '(N-1)' DAY "
                "AND date <= DATE 'X'."
            )
        },
        {
            "rule": (
                "ALWAYS use binary (IEC) conversion for data volumes. "
                "1 GB = 1073741824 bytes (1024^3). 1 TB = 1099511627776 bytes (1024^4)."
            )
        },
    ]

    policy = compile_semantic_policy("nova", payload)

    assert policy == SemanticPolicy(
        provider_id="nova",
        time_windows=[
            TimeWindowPolicy(
                applies_to=["daily_stats"],
                end_inclusive=True,
                end_parameter_mode=BoundaryMode.EXCLUSIVE_UPPER_BOUND,
            )
        ],
        unit_conversion=UnitConversionPolicy(
            gb_divisor=1073741824,
            tb_divisor=1099511627776,
        ),
    )
