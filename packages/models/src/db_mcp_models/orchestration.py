"""Typed orchestration models for intent execution."""

from typing import Any

from pydantic import BaseModel, Field

from db_mcp_models.meta_query import ExpectedCardinality, MetaQueryPlan, ObservedCardinality


class MetricExecutionPlan(BaseModel):
    """Single-connection metric execution plan for the first semantic slice."""

    connection: str = Field(..., description="Target connection name")
    metric_name: str = Field(..., description="Resolved metric identifier")
    sql: str = Field(..., description="Compiled SQL to execute")
    binding_source: str = Field(
        default="metric.sql",
        description="Physical source used to compile this execution plan",
    )
    metric_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters applied while rendering SQL",
    )
    expected_cardinality: ExpectedCardinality = Field(
        default=ExpectedCardinality.ONE,
        description="Expected result shape for this execution",
    )
    warnings: list[str] = Field(default_factory=list, description="Resolver warnings")


class ConfidenceVector(BaseModel):
    """Structured confidence values across orchestration stages."""

    semantic: float = Field(default=0.0, ge=0.0, le=1.0)
    binding: float = Field(default=0.0, ge=0.0, le=1.0)
    execution: float = Field(default=0.0, ge=0.0, le=1.0)
    aggregation: float = Field(default=1.0, ge=0.0, le=1.0)
    knowledge_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    answer: float = Field(default=0.0, ge=0.0, le=1.0)


class ResultShape(BaseModel):
    """Expected and observed result shape for one intent answer."""

    expected_cardinality: ExpectedCardinality
    observed_cardinality: ObservedCardinality
    cardinality_validated: bool = Field(
        default=True,
        description="Whether the observed result shape satisfies the expectation",
    )


class AnswerIntentResponse(BaseModel):
    """Structured response contract for the first answer_intent slice."""

    status: str = Field(..., description="success|error|partial")
    answer: str | None = Field(default=None, description="Human-readable summary")
    records: list[dict[str, Any]] = Field(default_factory=list, description="Returned rows")
    meta_query: MetaQueryPlan | None = Field(default=None, description="Semantic plan")
    resolved_plan: MetricExecutionPlan | None = Field(
        default=None,
        description="Connection-bound execution plan",
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Sources, execution ids, and transform chain",
    )
    confidence: ConfidenceVector | None = Field(
        default=None,
        description="Confidence across orchestration stages",
    )
    result_shape: ResultShape | None = Field(default=None, description="Result shape details")
    warnings: list[str] = Field(default_factory=list, description="User-visible caveats")
    error: str | None = Field(default=None, description="Machine-readable error summary")
