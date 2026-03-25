"""Tests for deterministic semantic planning."""

from db_mcp_models import Dimension, DimensionType, ExpectedCardinality, Metric

from db_mcp.planner.meta_query import compile_metric_intent, resolve_metric
from db_mcp.semantic.core_loader import ConnectionSemanticCore


def _semantic_core() -> ConnectionSemanticCore:
    return ConnectionSemanticCore(
        provider_id="demo",
        metrics=[
            Metric(
                name="revenue",
                display_name="Total Revenue",
                description="Total revenue",
                sql="SELECT SUM(amount) AS revenue FROM orders",
                dimensions=["region"],
            ),
            Metric(
                name="dau",
                display_name="Daily Active Users",
                description="Daily active users",
                sql="SELECT COUNT(DISTINCT user_id) AS dau FROM sessions",
            ),
        ],
        dimensions=[
            Dimension(
                name="region",
                display_name="Region",
                description="Customer region",
                column="customers.region",
                type=DimensionType.GEOGRAPHIC,
            )
        ],
        metric_bindings={},
    )


def test_resolve_metric_prefers_exact_alias_match():
    match = resolve_metric("show total revenue", _semantic_core())
    assert match is not None
    assert match.metric.name == "revenue"
    assert match.matched_alias == "Total Revenue"
    assert match.score >= 80


def test_compile_metric_intent_marks_dimension_requests_as_many():
    plan = compile_metric_intent(
        intent="show total revenue by region",
        connection="demo",
        semantic_core=_semantic_core(),
    )

    assert plan.measures[0].metric_name == "revenue"
    assert [dimension.name for dimension in plan.dimensions] == ["region"]
    assert plan.expected_cardinality == ExpectedCardinality.MANY
    assert plan.warnings == []
