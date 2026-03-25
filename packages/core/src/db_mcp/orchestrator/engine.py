"""First semantic orchestration slice for answer_intent."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from db_mcp_models import (
    AnswerIntentResponse,
    BoundaryMode,
    ConfidenceVector,
    ExpectedCardinality,
    MetaFilter,
    ObservedCardinality,
    ResultShape,
)
from opentelemetry import trace

from db_mcp.planner.meta_query import compile_metric_intent
from db_mcp.planner.resolver import resolve_metric_execution_plan
from db_mcp.semantic.core_loader import load_connection_semantic_core
from db_mcp.tools.generation import _run_sql, _validate_sql
from db_mcp.tools.utils import resolve_connection

_ROLLING_WINDOW_RE = re.compile(
    r"(?P<days>\d+)-day period ending on (?P<anchor>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_SINGLE_DAY_RE = re.compile(r"\bon (?P<anchor>\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_QUOTED_ISO_DATE_RE = re.compile(r"^'(?P<value>\d{4}-\d{2}-\d{2})'$")


def _record_knowledge_files(*paths: str) -> None:
    current_span = trace.get_current_span()
    try:
        getter = current_span.get_attribute
    except AttributeError:
        getter = None
    try:
        setter = current_span.set_attribute
    except AttributeError:
        setter = None
    if not callable(setter):
        return
    existing = list(getter("knowledge.files_used") or []) if callable(getter) else []
    seen = set(existing)
    for path in paths:
        if not path or path in seen:
            continue
        existing.append(path)
        seen.add(path)
    setter("knowledge.files_used", existing)


def _structured_payload(result: Any) -> dict[str, Any]:
    payload = getattr(result, "structuredContent", result)
    if isinstance(payload, dict):
        return payload
    return {"status": "error", "error": "Unexpected execution result payload."}


def _metric_parameters_from_options(options: dict[str, Any] | None) -> dict[str, Any]:
    if not options:
        return {}
    params = options.get("metric_parameters", {})
    return params if isinstance(params, dict) else {}


def _time_context_from_options(options: dict[str, Any] | None) -> dict[str, str] | None:
    if not options:
        return None
    raw_time_context = options.get("time_context")
    if not isinstance(raw_time_context, dict):
        return None

    time_context: dict[str, str] = {}
    for key in ("start", "end", "timezone"):
        value = raw_time_context.get(key)
        if isinstance(value, str) and value:
            time_context[key] = value
    return time_context or None


def _filters_from_options(options: dict[str, Any] | None) -> list[MetaFilter]:
    if not options:
        return []
    raw_filters = options.get("filters")
    if not isinstance(raw_filters, list):
        return []

    filters: list[MetaFilter] = []
    for raw_filter in raw_filters:
        if not isinstance(raw_filter, dict):
            continue
        field = raw_filter.get("field")
        value = raw_filter.get("value")
        if not isinstance(field, str) or not field:
            continue
        filters.append(
            MetaFilter(
                field=field,
                operator=str(raw_filter.get("operator", "=")),
                value=value,
            )
        )
    return filters


def _sql_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _sql_date_literal(value: str) -> str:
    return f"DATE '{value}'"


def _normalize_date_literal(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if _ISO_DATE_RE.fullmatch(stripped):
        return _sql_date_literal(stripped)
    match = _QUOTED_ISO_DATE_RE.fullmatch(stripped)
    if match:
        return _sql_date_literal(match.group("value"))
    return value


def _coerce_metric_parameters(
    parameters: dict[str, Any],
    *,
    metric,
) -> dict[str, Any]:
    if not parameters:
        return {}
    parameter_types = {param.name: param.type for param in metric.parameters}
    coerced: dict[str, Any] = {}
    for name, value in parameters.items():
        if parameter_types.get(name) == "date":
            coerced[name] = _normalize_date_literal(value)
        else:
            coerced[name] = value
    return coerced


def _matching_time_window_policy(semantic_core, *, tables: list[str]) -> Any | None:
    for policy in semantic_core.policy.time_windows:
        if not policy.applies_to:
            return policy
        normalized_hints = [hint.casefold() for hint in policy.applies_to]
        for table in tables:
            lowered = table.casefold()
            if any(hint in lowered for hint in normalized_hints):
                return policy
    return None


def _infer_time_context_from_intent(
    *,
    intent: str,
    semantic_core,
    metric,
    binding,
) -> dict[str, str] | None:
    tables = []
    if binding is not None:
        tables.extend(binding.tables)
    tables.extend(metric.tables)
    policy = _matching_time_window_policy(semantic_core, tables=tables)
    if policy is None:
        return None

    rolling_match = _ROLLING_WINDOW_RE.search(intent)
    if rolling_match:
        days = int(rolling_match.group("days"))
        anchor = date.fromisoformat(rolling_match.group("anchor"))
        start = anchor - timedelta(days=days - 1)
        if (
            policy.end_inclusive
            and policy.end_parameter_mode == BoundaryMode.EXCLUSIVE_UPPER_BOUND
        ):
            end = anchor + timedelta(days=1)
        else:
            end = anchor
        return {"start": start.isoformat(), "end": end.isoformat()}

    single_day_match = _SINGLE_DAY_RE.search(intent)
    if single_day_match:
        anchor = date.fromisoformat(single_day_match.group("anchor"))
        if policy.end_parameter_mode == BoundaryMode.EXCLUSIVE_UPPER_BOUND:
            end = anchor + timedelta(days=1)
        else:
            end = anchor
        return {"start": anchor.isoformat(), "end": end.isoformat()}

    return None


def _merge_metric_parameters(
    *,
    explicit_parameters: dict[str, Any],
    time_context: dict[str, str] | None,
    parameter_names: set[str] | None = None,
) -> dict[str, Any]:
    merged = dict(explicit_parameters)
    if not time_context:
        return merged

    inferred = {
        "start_date": _sql_literal(time_context["start"])
        for _ in [0]
        if "start" in time_context
    }
    inferred.update(
        {
            "end_date": _sql_literal(time_context["end"])
            for _ in [0]
            if "end" in time_context
        }
    )
    inferred.update(
        {
            "start_time": _sql_literal(time_context["start"])
            for _ in [0]
            if "start" in time_context
        }
    )
    inferred.update(
        {
            "end_time": _sql_literal(time_context["end"])
            for _ in [0]
            if "end" in time_context
        }
    )

    for name, value in inferred.items():
        if parameter_names is not None and name not in parameter_names:
            continue
        merged.setdefault(name, value)

    return merged


def _observed_cardinality(rows_returned: int) -> ObservedCardinality:
    if rows_returned <= 0:
        return ObservedCardinality.EMPTY
    if rows_returned == 1:
        return ObservedCardinality.ONE
    return ObservedCardinality.MANY


def _answer_confidence(
    *,
    semantic: float,
    binding: float,
    execution: float,
    knowledge_coverage: float,
    cardinality_validated: bool,
) -> float:
    raw = (semantic + binding + execution + knowledge_coverage) / 4.0
    if not cardinality_validated:
        raw *= 0.6
    return round(raw, 4)


def _answer_summary(metric_name: str, connection: str, rows_returned: int) -> str:
    row_word = "row" if rows_returned == 1 else "rows"
    return (
        f"Executed metric '{metric_name}' on connection '{connection}' "
        f"and returned {rows_returned} {row_word}."
    )


def _binding_confidence(binding_source: str) -> float:
    return 1.0 if binding_source == "metrics/bindings.yaml" else 0.7


def preview_answer_intent(
    *,
    intent: str,
    connection: str,
    provider_id: str | None = None,
    connection_path: Path | str | None = None,
    options: dict[str, Any] | None = None,
) -> AnswerIntentResponse:
    """Resolve a metric intent into a deterministic semantic execution preview."""
    resolved_provider_id = provider_id
    if resolved_provider_id is None:
        _, resolved_provider_id, _ = resolve_connection(connection)
    if connection_path is None:
        semantic_core = load_connection_semantic_core(resolved_provider_id)
    else:
        semantic_core = load_connection_semantic_core(
            resolved_provider_id,
            connection_path=connection_path,
        )
    _record_knowledge_files(
        "metrics/catalog.yaml",
        "metrics/bindings.yaml",
        *(
            ["metrics/dimensions.yaml"]
            if semantic_core.dimensions
            else []
        ),
    )

    time_context = _time_context_from_options(options)
    metric_parameters = _metric_parameters_from_options(options)
    semantic_filters = _filters_from_options(options)
    candidate_metrics = sorted(metric.name for metric in semantic_core.metrics)

    if not semantic_core.metrics:
        return AnswerIntentResponse(
            status="error",
            error="No approved metrics are available for this connection.",
            warnings=[
                "Add or approve metrics before using answer_intent on this connection.",
            ],
        )

    try:
        meta_query = compile_metric_intent(
            intent=intent,
            connection=connection,
            semantic_core=semantic_core,
            metric_parameters=metric_parameters,
            time_context=time_context,
        )
    except ValueError:
        return AnswerIntentResponse(
            status="error",
            error="No approved metric matched the intent.",
            warnings=[
                f"Available metrics: {', '.join(candidate_metrics)}",
            ],
        )

    metric_name = meta_query.measures[0].metric_name
    metric = semantic_core.get_metric(metric_name)
    if metric is None:
        return AnswerIntentResponse(
            status="error",
            meta_query=meta_query,
            error=f"Resolved metric '{metric_name}' is not available.",
        )

    binding = semantic_core.get_metric_binding(metric.name)
    if time_context is None:
        time_context = _infer_time_context_from_intent(
            intent=intent,
            semantic_core=semantic_core,
            metric=metric,
            binding=binding,
        )

    metric_parameters = _merge_metric_parameters(
        explicit_parameters=_coerce_metric_parameters(metric_parameters, metric=metric),
        time_context=time_context,
        parameter_names={param.name for param in metric.parameters},
    )
    metric_parameters = _coerce_metric_parameters(metric_parameters, metric=metric)
    meta_query.measures[0].parameters = metric_parameters
    meta_query.filters = semantic_filters

    try:
        resolved_plan = resolve_metric_execution_plan(
            meta_query=meta_query,
            connection=connection,
            semantic_core=semantic_core,
        )
    except ValueError as exc:
        return AnswerIntentResponse(
            status="error",
            meta_query=meta_query,
            error=str(exc),
            warnings=[
                "Pass explicit SQL-safe literals in options.metric_parameters.",
            ],
            confidence=ConfidenceVector(
                semantic=meta_query.semantic_confidence,
                binding=0.0,
                execution=0.0,
                knowledge_coverage=1.0 if semantic_core.dimensions else 0.5,
                answer=0.0,
            ),
        )
    binding_confidence = _binding_confidence(resolved_plan.binding_source)
    return AnswerIntentResponse(
        status="ready",
        meta_query=meta_query,
        resolved_plan=resolved_plan,
        provenance={
            "sources": [connection],
            "transform_chain": ["semantic_resolve", "metric_sql"],
            "semantic_bindings": {
                "metric": metric.name,
                "dimensions": [dimension.name for dimension in meta_query.dimensions],
            },
            "binding_source": resolved_plan.binding_source,
        },
        confidence=ConfidenceVector(
            semantic=meta_query.semantic_confidence,
            binding=binding_confidence,
            execution=0.0,
            knowledge_coverage=1.0,
            answer=0.0,
        ),
        warnings=list(meta_query.warnings),
    )


async def answer_intent(
    *,
    intent: str,
    connection: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a metric intent and execute it via the existing SQL path."""
    preview = preview_answer_intent(intent=intent, connection=connection, options=options)
    if preview.status != "ready":
        return preview.model_dump(mode="json")

    assert preview.meta_query is not None  # populated by preview success path
    assert preview.resolved_plan is not None  # populated by preview success path
    meta_query = preview.meta_query
    resolved_plan = preview.resolved_plan

    run_payload = _structured_payload(await _run_sql(connection=connection, sql=resolved_plan.sql))
    if (
        run_payload.get("status") == "error"
        and run_payload.get("error") == "Validation required. Use validate_sql first."
    ):
        validation_payload = _structured_payload(
            await _validate_sql(connection=connection, sql=resolved_plan.sql)
        )
        if not validation_payload.get("valid"):
            response = AnswerIntentResponse(
                status="error",
                meta_query=meta_query,
                resolved_plan=resolved_plan,
                error=str(validation_payload.get("error") or "Metric validation failed."),
                warnings=list(meta_query.warnings),
                provenance={
                    "sources": [connection],
                    "transform_chain": ["semantic_resolve", "metric_sql", "validate_sql"],
                    "binding_source": resolved_plan.binding_source,
                },
                confidence=ConfidenceVector(
                    semantic=meta_query.semantic_confidence,
                    binding=_binding_confidence(resolved_plan.binding_source),
                    execution=0.0,
                    knowledge_coverage=1.0,
                    answer=0.0,
                ),
            )
            return response.model_dump(mode="json")

        query_id = validation_payload.get("query_id")
        run_payload = _structured_payload(
            await _run_sql(connection=connection, query_id=query_id)
        )

    if run_payload.get("status") != "success":
        execution_id = run_payload.get("execution_id")
        binding_confidence = _binding_confidence(resolved_plan.binding_source)
        response = AnswerIntentResponse(
            status="error",
            meta_query=meta_query,
            resolved_plan=resolved_plan,
            error=str(run_payload.get("error") or "Metric execution failed."),
            warnings=list(meta_query.warnings),
            provenance={
                "sources": [connection],
                "executions": [execution_id] if execution_id else [],
                "transform_chain": ["semantic_resolve", "metric_sql", "run_sql"],
                "binding_source": resolved_plan.binding_source,
            },
            confidence=ConfidenceVector(
                semantic=meta_query.semantic_confidence,
                binding=binding_confidence,
                execution=0.0,
                knowledge_coverage=1.0,
                answer=0.0,
            ),
        )
        return response.model_dump(mode="json")

    rows_returned = int(run_payload.get("rows_returned") or 0)
    observed = _observed_cardinality(rows_returned)
    cardinality_validated = (
        meta_query.expected_cardinality == ExpectedCardinality.MANY
        or observed in {ObservedCardinality.EMPTY, ObservedCardinality.ONE}
    )

    binding_confidence = _binding_confidence(resolved_plan.binding_source)
    confidence = ConfidenceVector(
        semantic=meta_query.semantic_confidence,
        binding=binding_confidence,
        execution=1.0,
        knowledge_coverage=1.0,
        answer=_answer_confidence(
            semantic=meta_query.semantic_confidence,
            binding=binding_confidence,
            execution=1.0,
            knowledge_coverage=1.0,
            cardinality_validated=cardinality_validated,
        ),
    )

    warnings = list(meta_query.warnings)
    if not cardinality_validated:
        warnings.append("Observed result shape violated expected cardinality.")

    execution_id = run_payload.get("execution_id")
    response = AnswerIntentResponse(
        status="success",
        answer=_answer_summary(
            meta_query.measures[0].display_name or meta_query.measures[0].metric_name,
            connection,
            rows_returned,
        ),
        records=run_payload.get("data", []),
        meta_query=meta_query,
        resolved_plan=resolved_plan,
        provenance={
            "sources": [connection],
            "executions": [execution_id] if execution_id else [],
            "transform_chain": ["semantic_resolve", "metric_sql", "run_sql"],
            "semantic_bindings": {
                "metric": meta_query.measures[0].metric_name,
                "dimensions": [dimension.name for dimension in meta_query.dimensions],
            },
            "binding_source": resolved_plan.binding_source,
        },
        confidence=confidence,
        result_shape=ResultShape(
            expected_cardinality=meta_query.expected_cardinality,
            observed_cardinality=observed,
            cardinality_validated=cardinality_validated,
        ),
        warnings=warnings,
    )
    return response.model_dump(mode="json")
