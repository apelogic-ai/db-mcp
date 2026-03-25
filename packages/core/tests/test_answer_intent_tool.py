"""Tests for the first answer_intent orchestration slice."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from db_mcp_models import (
    BoundaryMode,
    Dimension,
    Metric,
    MetricBinding,
    MetricDimensionBinding,
    MetricParameter,
    SemanticPolicy,
)
from db_mcp_models.policy import TimeWindowPolicy, UnitConversionPolicy

from db_mcp.config import reset_settings
from db_mcp.semantic.core_loader import ConnectionSemanticCore, load_connection_semantic_core
from db_mcp.tools.intent import _answer_intent


class _DummySpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def get_attribute(self, key: str):
        return self.attributes.get(key)

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


@pytest.fixture
def semantic_core():
    return ConnectionSemanticCore(
        provider_id="test-conn",
        metrics=[
            Metric(
                name="revenue",
                display_name="Revenue",
                description="Total revenue",
                sql="SELECT {start_date} AS start_date, SUM(amount) AS revenue FROM orders",
                tables=["orders"],
                parameters=[
                    MetricParameter(name="start_date", type="date", required=True),
                ],
                dimensions=["region"],
            )
        ],
        dimensions=[
            Dimension(
                name="region",
                description="Region",
                column="orders.region",
                tables=["orders"],
            )
        ],
        metric_bindings={
            "revenue": MetricBinding(
                metric_name="revenue",
                sql="SELECT {start_date} AS bound_start_date, "
                "SUM(total_amount) AS revenue FROM finance_orders",
                tables=["finance_orders"],
                dimensions={
                    "region": MetricDimensionBinding(
                        dimension_name="region",
                        projection_sql="finance_orders.sales_region",
                        group_by_sql="finance_orders.sales_region",
                        tables=["finance_orders"],
                    )
                },
            )
        },
        policy=SemanticPolicy(provider_id="test-conn"),
    )


@pytest.mark.asyncio
async def test_answer_intent_executes_metric_and_returns_structured_contract(
    monkeypatch,
    semantic_core,
):
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: semantic_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-1",
                "rows_returned": 1,
                "data": [{"start_date": "2026-01-01", "revenue": 42}],
            }
        ),
    )

    result = await _answer_intent(
        intent="show revenue",
        connection="test-conn",
        options={"metric_parameters": {"start_date": "'2026-01-01'"}},
    )
    payload = result.structuredContent

    assert payload["status"] == "success"
    assert payload["meta_query"]["measures"][0]["metric_name"] == "revenue"
    assert payload["resolved_plan"]["connection"] == "test-conn"
    assert (
        payload["resolved_plan"]["sql"]
        == "SELECT DATE '2026-01-01' AS bound_start_date, "
        "SUM(total_amount) AS revenue FROM finance_orders"
    )
    assert payload["provenance"]["sources"] == ["test-conn"]
    assert payload["provenance"]["executions"] == ["exec-1"]
    assert payload["result_shape"]["expected_cardinality"] == "ONE"
    assert payload["result_shape"]["observed_cardinality"] == "ONE"
    assert payload["records"] == [{"start_date": "2026-01-01", "revenue": 42}]


@pytest.mark.asyncio
async def test_answer_intent_records_semantic_knowledge_files(monkeypatch, semantic_core):
    span = _DummySpan()
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.trace.get_current_span",
        lambda: span,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: semantic_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-knowledge",
                "rows_returned": 1,
                "data": [{"start_date": "2026-01-01", "revenue": 42}],
            }
        ),
    )

    await _answer_intent(
        intent="show revenue",
        connection="test-conn",
        options={"metric_parameters": {"start_date": "'2026-01-01'"}},
    )

    assert span.attributes["knowledge.files_used"] == [
        "metrics/catalog.yaml",
        "metrics/bindings.yaml",
        "metrics/dimensions.yaml",
    ]


@pytest.mark.asyncio
async def test_answer_intent_requires_metric_parameters(monkeypatch, semantic_core):
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: semantic_core,
    )

    result = await _answer_intent(
        intent="show revenue",
        connection="test-conn",
        options={},
    )
    payload = result.structuredContent

    assert payload["status"] == "error"
    assert payload["error"] == "Missing required metric parameters: start_date"
    assert payload["meta_query"]["measures"][0]["metric_name"] == "revenue"


@pytest.mark.asyncio
async def test_answer_intent_executes_metric_by_dimension(monkeypatch, semantic_core):
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: semantic_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-2",
                "rows_returned": 2,
                "data": [
                    {"region": "US", "revenue": 20},
                    {"region": "EU", "revenue": 22},
                ],
            }
        ),
    )

    result = await _answer_intent(
        intent="show revenue by region",
        connection="test-conn",
        options={"metric_parameters": {"start_date": "'2026-01-01'"}},
    )
    payload = result.structuredContent

    assert payload["status"] == "success"
    assert payload["meta_query"]["dimensions"] == [{"name": "region", "display_name": None}]
    assert payload["resolved_plan"]["sql"] == (
        "SELECT CAST('2026-01-01' AS DATE) AS bound_start_date, "
        "SUM(total_amount) AS revenue, "
        "finance_orders.sales_region AS region "
        "FROM finance_orders GROUP BY finance_orders.sales_region"
    )
    assert payload["result_shape"]["expected_cardinality"] == "MANY"
    assert payload["result_shape"]["observed_cardinality"] == "MANY"


@pytest.mark.asyncio
async def test_answer_intent_executes_binding_only_metric(monkeypatch, semantic_core):
    binding_only_core = ConnectionSemanticCore(
        provider_id="test-conn",
        metrics=[
            Metric(
                name="bookings",
                display_name="Bookings",
                description="Total bookings",
                sql="",
                dimensions=[],
            )
        ],
        dimensions=[],
        metric_bindings={
            "bookings": MetricBinding(
                metric_name="bookings",
                sql="SELECT COUNT(*) AS bookings FROM booking_facts",
                tables=["booking_facts"],
            )
        },
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: binding_only_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-3",
                "rows_returned": 1,
                "data": [{"bookings": 9}],
            }
        ),
    )

    result = await _answer_intent(
        intent="show bookings",
        connection="test-conn",
        options={},
    )
    payload = result.structuredContent

    assert payload["status"] == "success"
    assert payload["resolved_plan"]["sql"] == "SELECT COUNT(*) AS bookings FROM booking_facts"
    assert payload["resolved_plan"]["binding_source"] == "metrics/bindings.yaml"
    assert payload["provenance"]["binding_source"] == "metrics/bindings.yaml"


@pytest.mark.asyncio
async def test_answer_intent_uses_time_context_to_fill_metric_parameters(monkeypatch):
    time_core = ConnectionSemanticCore(
        provider_id="test-conn",
        metrics=[
            Metric(
                name="revenue",
                display_name="Revenue",
                description="Total revenue",
                sql="",
                parameters=[
                    MetricParameter(name="start_date", type="date", required=True),
                    MetricParameter(name="end_date", type="date", required=True),
                ],
            )
        ],
        dimensions=[],
        metric_bindings={
            "revenue": MetricBinding(
                metric_name="revenue",
                sql=(
                    "SELECT {start_date} AS start_date, {end_date} AS end_date, "
                    "SUM(total_amount) AS revenue FROM finance_orders"
                ),
                tables=["finance_orders"],
            )
        },
        policy=SemanticPolicy(provider_id="test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: time_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-4",
                "rows_returned": 1,
                "data": [{"revenue": 15}],
            }
        ),
    )

    result = await _answer_intent(
        intent="show revenue",
        connection="test-conn",
        options={
            "time_context": {
                "start": "2026-01-01",
                "end": "2026-01-31",
                "timezone": "UTC",
            }
        },
    )
    payload = result.structuredContent

    assert payload["status"] == "success"
    assert payload["meta_query"]["time_context"] == {
        "start": "2026-01-01",
        "end": "2026-01-31",
        "timezone": "UTC",
    }
    assert payload["meta_query"]["measures"][0]["parameters"] == {
        "start_date": "DATE '2026-01-01'",
        "end_date": "DATE '2026-01-31'",
    }
    assert payload["resolved_plan"]["metric_parameters"] == {
        "start_date": "DATE '2026-01-01'",
        "end_date": "DATE '2026-01-31'",
    }


@pytest.mark.asyncio
async def test_answer_intent_metric_parameters_override_time_context(monkeypatch):
    time_core = ConnectionSemanticCore(
        provider_id="test-conn",
        metrics=[
            Metric(
                name="revenue",
                display_name="Revenue",
                description="Total revenue",
                sql="",
                parameters=[
                    MetricParameter(name="start_date", type="date", required=True),
                    MetricParameter(name="end_date", type="date", required=True),
                ],
            )
        ],
        dimensions=[],
        metric_bindings={
            "revenue": MetricBinding(
                metric_name="revenue",
                sql=(
                    "SELECT {start_date} AS start_date, {end_date} AS end_date, "
                    "SUM(total_amount) AS revenue FROM finance_orders"
                ),
                tables=["finance_orders"],
            )
        },
        policy=SemanticPolicy(provider_id="test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: time_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-5",
                "rows_returned": 1,
                "data": [{"revenue": 22}],
            }
        ),
    )

    result = await _answer_intent(
        intent="show revenue",
        connection="test-conn",
        options={
            "time_context": {
                "start": "2026-01-01",
                "end": "2026-01-31",
            },
            "metric_parameters": {
                "start_date": "'2026-01-05'",
            },
        },
    )
    payload = result.structuredContent

    assert payload["status"] == "success"
    assert payload["resolved_plan"]["metric_parameters"] == {
        "start_date": "DATE '2026-01-05'",
        "end_date": "DATE '2026-01-31'",
    }


@pytest.mark.asyncio
async def test_answer_intent_applies_semantic_filters_via_binding(monkeypatch):
    filter_core = ConnectionSemanticCore(
        provider_id="test-conn",
        metrics=[
            Metric(
                name="revenue",
                display_name="Revenue",
                description="Total revenue",
                sql="",
            )
        ],
        dimensions=[
            Dimension(
                name="region",
                description="Sales region",
                column="orders.region",
                tables=["orders"],
            )
        ],
        metric_bindings={
            "revenue": MetricBinding(
                metric_name="revenue",
                sql="SELECT SUM(total_amount) AS revenue FROM finance_orders",
                tables=["finance_orders"],
                dimensions={
                    "region": MetricDimensionBinding(
                        dimension_name="region",
                        projection_sql="finance_orders.sales_region",
                        group_by_sql="finance_orders.sales_region",
                        tables=["finance_orders"],
                        filter_sql="finance_orders.sales_region",
                    )
                },
            )
        },
        policy=SemanticPolicy(provider_id="test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: filter_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-6",
                "rows_returned": 1,
                "data": [{"revenue": 7}],
            }
        ),
    )

    result = await _answer_intent(
        intent="show revenue",
        connection="test-conn",
        options={
            "filters": [
                {
                    "field": "region",
                    "operator": "=",
                    "value": "'US'",
                }
            ]
        },
    )
    payload = result.structuredContent

    assert payload["status"] == "success"
    assert payload["meta_query"]["filters"] == [
        {"field": "region", "operator": "=", "value": "'US'"}
    ]
    assert payload["resolved_plan"]["sql"] == (
        "SELECT SUM(total_amount) AS revenue "
        "FROM finance_orders WHERE finance_orders.sales_region = 'US'"
    )


@pytest.mark.asyncio
async def test_answer_intent_rejects_unknown_filter_field(monkeypatch):
    filter_core = ConnectionSemanticCore(
        provider_id="test-conn",
        metrics=[
            Metric(
                name="revenue",
                display_name="Revenue",
                description="Total revenue",
                sql="",
            )
        ],
        dimensions=[],
        metric_bindings={
            "revenue": MetricBinding(
                metric_name="revenue",
                sql="SELECT SUM(total_amount) AS revenue FROM finance_orders",
                tables=["finance_orders"],
            )
        },
        policy=SemanticPolicy(provider_id="test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: filter_core,
    )

    result = await _answer_intent(
        intent="show revenue",
        connection="test-conn",
        options={
            "filters": [
                {
                    "field": "region",
                    "operator": "=",
                    "value": "'US'",
                }
            ]
        },
    )
    payload = result.structuredContent

    assert payload["status"] == "error"
    assert payload["error"] == "Resolved filter field 'region' is not available."


@pytest.mark.asyncio
async def test_answer_intent_infers_period_ending_window_from_intent(monkeypatch):
    policy_core = ConnectionSemanticCore(
        provider_id="test-conn",
        metrics=[
            Metric(
                name="total_data_traffic",
                display_name="Total Data Traffic",
                description="Total data traffic",
                sql="",
                tables=["dwh.public.daily_stats_cdrs"],
                parameters=[
                    MetricParameter(name="start_date", type="date", required=True),
                    MetricParameter(name="end_date", type="date", required=True),
                ],
            )
        ],
        dimensions=[],
        metric_bindings={
            "total_data_traffic": MetricBinding(
                metric_name="total_data_traffic",
                sql=(
                    "SELECT SUM(wifi_total_bytes) / 1099511627776 AS answer "
                    "FROM dwh.public.daily_stats_cdrs "
                    "WHERE date >= {start_date} AND date < {end_date}"
                ),
                tables=["dwh.public.daily_stats_cdrs"],
            )
        },
        policy=SemanticPolicy(
            provider_id="test-conn",
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
        ),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: policy_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-period",
                "rows_returned": 1,
                "data": [{"answer": 2719}],
            }
        ),
    )

    result = await _answer_intent(
        intent=(
            "What was the total data traffic on the Helium network "
            "during the 30-day period ending on 2026-03-01 (Tb)"
        ),
        connection="test-conn",
        options={},
    )
    payload = result.structuredContent

    assert payload["status"] == "success"
    assert payload["resolved_plan"]["metric_parameters"] == {
        "start_date": "DATE '2026-01-31'",
        "end_date": "DATE '2026-03-02'",
    }


@pytest.mark.asyncio
async def test_answer_intent_infers_single_day_window_and_coerces_date_literals(monkeypatch):
    policy_core = ConnectionSemanticCore(
        provider_id="test-conn",
        metrics=[
            Metric(
                name="brownfield_sites_with_traffic",
                display_name="Brownfield Sites With Traffic",
                description="Brownfield sites carrying traffic",
                sql="",
                tables=["dwh.public.daily_stats_cdrs_bf"],
                parameters=[
                    MetricParameter(name="start_date", type="date", required=True),
                    MetricParameter(name="end_date", type="date", required=True),
                ],
            )
        ],
        dimensions=[],
        metric_bindings={
            "brownfield_sites_with_traffic": MetricBinding(
                metric_name="brownfield_sites_with_traffic",
                sql=(
                    "SELECT COALESCE(SUM(sites_count), 0) AS answer "
                    "FROM dwh.public.daily_stats_cdrs_bf "
                    "WHERE date >= CAST({start_date} AS DATE) "
                    "AND date < CAST({end_date} AS DATE)"
                ),
                tables=["dwh.public.daily_stats_cdrs_bf"],
            )
        },
        policy=SemanticPolicy(
            provider_id="test-conn",
            time_windows=[
                TimeWindowPolicy(
                    applies_to=["daily_stats"],
                    end_inclusive=True,
                    end_parameter_mode=BoundaryMode.EXCLUSIVE_UPPER_BOUND,
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.resolve_connection",
        lambda connection: (object(), "test-conn", "/tmp/test-conn"),
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine.load_connection_semantic_core",
        lambda provider_id: policy_core,
    )
    monkeypatch.setattr(
        "db_mcp.orchestrator.engine._run_sql",
        AsyncMock(
            return_value={
                "status": "success",
                "execution_id": "exec-single-day",
                "rows_returned": 1,
                "data": [{"answer": 3136}],
            }
        ),
    )

    result = await _answer_intent(
        intent="How many brownfield sites carried traffic on 2026-02-15?",
        connection="test-conn",
        options={},
    )
    payload = result.structuredContent

    assert payload["status"] == "success"
    assert payload["resolved_plan"]["metric_parameters"] == {
        "start_date": "DATE '2026-02-15'",
        "end_date": "DATE '2026-02-16'",
    }
    assert payload["resolved_plan"]["sql"] == (
        "SELECT COALESCE(SUM(sites_count), 0) AS answer "
        "FROM dwh.public.daily_stats_cdrs_bf "
        "WHERE date >= CAST(DATE '2026-02-15' AS DATE) "
        "AND date < CAST(DATE '2026-02-16' AS DATE)"
    )


def test_load_connection_semantic_core_reads_connection_local_playground_artifacts(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    connections_dir = repo_root / "src" / "db_mcp" / "data"

    monkeypatch.setenv("CONNECTIONS_DIR", str(connections_dir))
    monkeypatch.setenv("CONNECTION_NAME", "playground")
    reset_settings()

    semantic_core = load_connection_semantic_core("playground")

    assert {metric.name for metric in semantic_core.metrics} >= {
        "total_customers",
        "invoice_revenue",
        "invoice_revenue_in_window",
    }
    assert {dimension.name for dimension in semantic_core.dimensions} == {"billing_country"}
    assert semantic_core.get_metric_binding("invoice_revenue_in_window") is not None

    reset_settings()
