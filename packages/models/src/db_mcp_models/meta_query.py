"""Semantic meta-query models for intent orchestration."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExpectedCardinality(str, Enum):
    """Expected logical result shape declared during semantic planning."""

    ONE = "ONE"
    MANY = "MANY"


class ObservedCardinality(str, Enum):
    """Observed result shape after execution."""

    EMPTY = "EMPTY"
    ONE = "ONE"
    MANY = "MANY"


class MetaMeasure(BaseModel):
    """A semantic measure requested by the intent."""

    metric_name: str = Field(..., description="Canonical metric identifier")
    display_name: str | None = Field(default=None, description="Human-readable metric label")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Explicit metric parameter values used for this request",
    )


class MetaDimension(BaseModel):
    """A semantic dimension requested by the intent."""

    name: str = Field(..., description="Canonical dimension identifier")
    display_name: str | None = Field(default=None, description="Human-readable dimension label")


class MetaFilter(BaseModel):
    """A semantic filter declared in business terms."""

    field: str = Field(..., description="Semantic field identifier")
    operator: str = Field(default="=", description="Filter operator")
    value: Any = Field(..., description="Filter value")


class MetaTimeContext(BaseModel):
    """Explicit temporal context supplied alongside the intent."""

    start: str | None = Field(default=None, description="Inclusive start boundary")
    end: str | None = Field(default=None, description="Inclusive end boundary")
    timezone: str | None = Field(default=None, description="IANA timezone name")


class MetaQueryPlan(BaseModel):
    """Connection-agnostic semantic plan compiled from user intent."""

    intent: str = Field(..., description="Original natural-language request")
    measures: list[MetaMeasure] = Field(
        default_factory=list,
        description="Requested semantic measures",
    )
    dimensions: list[MetaDimension] = Field(
        default_factory=list,
        description="Requested semantic dimensions",
    )
    filters: list[MetaFilter] = Field(
        default_factory=list,
        description="Requested semantic filters",
    )
    time_context: MetaTimeContext | None = Field(
        default=None,
        description="Explicit temporal context for the semantic request",
    )
    source_scope: list[str] = Field(
        default_factory=list,
        description="Connections eligible to satisfy the plan",
    )
    expected_cardinality: ExpectedCardinality = Field(
        default=ExpectedCardinality.ONE,
        description="Expected logical result shape",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Planner warnings or unsupported semantic requests",
    )
    semantic_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the semantic resolution itself",
    )
