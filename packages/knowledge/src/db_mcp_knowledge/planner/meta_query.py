"""Deterministic metric-first semantic planning."""

from __future__ import annotations

import re
from dataclasses import dataclass

from db_mcp_models import (
    Dimension,
    ExpectedCardinality,
    MetaDimension,
    MetaMeasure,
    MetaQueryPlan,
    MetaTimeContext,
    Metric,
)

from db_mcp_knowledge.semantic.core_loader import ConnectionSemanticCore

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _normalize(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _match_alias_score(intent_norm: str, alias: str) -> int:
    alias_norm = _normalize(alias)
    if not alias_norm:
        return 0
    if intent_norm == alias_norm:
        return 100
    if re.search(rf"\b{re.escape(alias_norm)}\b", intent_norm):
        return 80 + len(alias_norm.split())

    alias_tokens = set(alias_norm.split())
    intent_tokens = set(intent_norm.split())
    overlap = len(alias_tokens & intent_tokens)
    if overlap == 0:
        return 0
    return 10 + overlap


@dataclass(slots=True)
class MetricMatch:
    """Resolved metric plus metadata about the lexical match."""

    metric: Metric
    score: int
    matched_alias: str


def resolve_metric(intent: str, semantic_core: ConnectionSemanticCore) -> MetricMatch | None:
    """Resolve one approved metric from intent using deterministic lexical rules."""
    intent_norm = _normalize(intent)
    best: MetricMatch | None = None

    for metric in semantic_core.metrics:
        aliases = [metric.name]
        if metric.display_name:
            aliases.append(metric.display_name)
        for alias in aliases:
            score = _match_alias_score(intent_norm, alias)
            if score <= 0:
                continue
            if best is None or score > best.score or (
                score == best.score and metric.name < best.metric.name
            ):
                best = MetricMatch(metric=metric, score=score, matched_alias=alias)

    return best


def detect_dimensions(intent: str, semantic_core: ConnectionSemanticCore) -> list[Dimension]:
    """Detect mentioned dimensions without attempting SQL compilation yet."""
    intent_norm = _normalize(intent)
    matched: list[Dimension] = []

    for dimension in semantic_core.dimensions:
        aliases = [dimension.name]
        if dimension.display_name:
            aliases.append(dimension.display_name)
        aliases.extend(dimension.synonyms)
        if any(_match_alias_score(intent_norm, alias) >= 80 for alias in aliases):
            matched.append(dimension)

    matched.sort(key=lambda item: item.name)
    return matched


def compile_metric_intent(
    *,
    intent: str,
    connection: str,
    semantic_core: ConnectionSemanticCore,
    metric_parameters: dict[str, object] | None = None,
    time_context: dict[str, str] | None = None,
) -> MetaQueryPlan:
    """Compile a metric-first meta query from intent."""
    metric_match = resolve_metric(intent, semantic_core)
    if metric_match is None:
        raise ValueError("No approved metric matched the intent.")

    matched_dimensions = detect_dimensions(intent, semantic_core)
    warnings: list[str] = []
    expected_cardinality = ExpectedCardinality.ONE
    if matched_dimensions:
        expected_cardinality = ExpectedCardinality.MANY
    if len(matched_dimensions) > 1:
        warnings.append("The first slice supports at most one metric dimension.")

    confidence = min(1.0, metric_match.score / 100.0)
    return MetaQueryPlan(
        intent=intent,
        measures=[
            MetaMeasure(
                metric_name=metric_match.metric.name,
                display_name=metric_match.metric.display_name,
                parameters=metric_parameters or {},
            )
        ],
        dimensions=[
            MetaDimension(name=dimension.name, display_name=dimension.display_name)
            for dimension in matched_dimensions
        ],
        time_context=MetaTimeContext(**time_context) if time_context else None,
        source_scope=[connection],
        expected_cardinality=expected_cardinality,
        warnings=warnings,
        semantic_confidence=confidence,
    )
