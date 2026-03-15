"""Benchmark data models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ComparisonType = Literal[
    "scalar_exact",
    "scalar_numeric_tolerance",
    "rowset_unordered",
    "set_unordered",
    "contains_text",
]


class BenchmarkCase(BaseModel):
    """Single benchmark case for a specific connection."""

    id: str
    category: str
    prompt: str
    gold_sql: str
    comparison: ComparisonType
    tolerance: float | None = None
    normalization: list[str] = Field(default_factory=list)


class BenchmarkAnswer(BaseModel):
    """Structured answer schema returned by Claude."""

    task_id: str
    status: Literal["answered", "failed", "needs_clarification"]
    answer_value: Any = None
    answer_text: str
    evidence_sql: str | None = None
    confidence: float | None = None
    failure_reason: str | None = None


class ScoreResult(BaseModel):
    """Deterministic score for one attempt."""

    case_id: str
    comparison: ComparisonType
    correct: bool
    expected: Any
    actual: Any
    details: str = ""
