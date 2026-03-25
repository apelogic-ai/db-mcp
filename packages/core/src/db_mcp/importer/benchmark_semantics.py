"""Bootstrap candidate semantic artifacts from benchmark packs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlglot import exp, parse_one

from db_mcp.benchmark.loader import load_case_pack
from db_mcp.benchmark.models import BenchmarkCase

_DATE_LITERAL_RE = re.compile(r"(?:DATE\s+'([^']+)'|CAST\('([^']+)' AS DATE\))", re.IGNORECASE)
_COLUMN_EXPR_RE = r"(?:CAST\([^)]+\)|[A-Za-z0-9_\.\"]+)"
_COMMENT_PREFIX_RE = re.compile(r"^\s*--\s?")
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "before",
    "by",
    "during",
    "ending",
    "ever",
    "for",
    "how",
    "in",
    "many",
    "network",
    "of",
    "on",
    "or",
    "recorded",
    "show",
    "the",
    "to",
    "total",
    "was",
    "what",
    "which",
}


@dataclass(slots=True)
class DimensionSpec:
    name: str
    expression_sql: str
    group_by_sql: str


@dataclass(slots=True)
class CaseSemanticSeed:
    case: BenchmarkCase
    reference_sql: str
    base_sql: str
    signature: str
    tables: list[str]
    time_context: dict[str, str]
    dimension: DimensionSpec | None


def _slugify(text: str) -> str:
    return _NON_WORD_RE.sub("_", text.lower()).strip("_")


def _titleize(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("_") if part)


def _extract_reference_sql(gold_sql: str) -> str:
    comment_lines: list[str] = []
    for line in gold_sql.splitlines():
        if not line.lstrip().startswith("--"):
            continue
        stripped = _COMMENT_PREFIX_RE.sub("", line).rstrip()
        if stripped.lower().startswith("reference query"):
            continue
        if stripped:
            comment_lines.append(stripped)

    if comment_lines:
        candidate = "\n".join(comment_lines).strip()
        if re.search(r"\b(select|with)\b", candidate, re.IGNORECASE):
            return candidate

    return gold_sql.strip()


def _extract_date_literal(value: str) -> str | None:
    match = _DATE_LITERAL_RE.fullmatch(value.strip())
    if not match:
        return None
    return match.group(1) or match.group(2)


def _plus_one_day(raw: str) -> str:
    return (date.fromisoformat(raw) + timedelta(days=1)).isoformat()


def _parameterize_time_filters(sql: str) -> tuple[str, dict[str, str]]:
    time_context: dict[str, str] = {}
    parameterized = sql

    between_re = re.compile(
        rf"(?P<column>{_COLUMN_EXPR_RE})\s+BETWEEN\s+"
        rf"(?P<start>(?:DATE\s+'[^']+'|CAST\('[^']+' AS DATE\)))\s+AND\s+"
        rf"(?P<end>(?:DATE\s+'[^']+'|CAST\('[^']+' AS DATE\)))",
        re.IGNORECASE,
    )

    def replace_between(match: re.Match[str]) -> str:
        start = _extract_date_literal(match.group("start"))
        end = _extract_date_literal(match.group("end"))
        if not start or not end:
            return match.group(0)
        time_context.setdefault("start", start)
        time_context.setdefault("end", _plus_one_day(end))
        column = match.group("column")
        return (
            f"{column} >= CAST({{start_date}} AS DATE) AND "
            f"{column} < CAST({{end_date}} AS DATE)"
        )

    parameterized = between_re.sub(replace_between, parameterized)

    equality_re = re.compile(
        rf"(?P<column>{_COLUMN_EXPR_RE})\s*=\s*"
        rf"(?P<date>(?:DATE\s+'[^']+'|CAST\('[^']+' AS DATE\)))",
        re.IGNORECASE,
    )

    def replace_equality(match: re.Match[str]) -> str:
        raw = _extract_date_literal(match.group("date"))
        if not raw:
            return match.group(0)
        time_context.setdefault("start", raw)
        time_context.setdefault("end", _plus_one_day(raw))
        column = match.group("column")
        return (
            f"{column} >= CAST({{start_date}} AS DATE) AND "
            f"{column} < CAST({{end_date}} AS DATE)"
        )

    parameterized = equality_re.sub(replace_equality, parameterized)

    lte_re = re.compile(
        rf"(?P<column>{_COLUMN_EXPR_RE})\s*<=\s*"
        rf"(?P<date>(?:DATE\s+'[^']+'|CAST\('[^']+' AS DATE\)))",
        re.IGNORECASE,
    )

    def replace_lte(match: re.Match[str]) -> str:
        raw = _extract_date_literal(match.group("date"))
        if not raw:
            return match.group(0)
        time_context.setdefault("end", _plus_one_day(raw))
        column = match.group("column")
        return f"{column} < CAST({{end_date}} AS DATE)"

    parameterized = lte_re.sub(replace_lte, parameterized)
    return parameterized, time_context


def _normalize_signature(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def _extract_tables(sql: str) -> list[str]:
    tables = re.findall(r'\b(?:FROM|JOIN)\s+([A-Za-z0-9_\."]+)', sql, re.IGNORECASE)
    unique: list[str] = []
    for table in tables:
        if table not in unique:
            unique.append(table)
    return unique


def _group_dimension_seed(statement: exp.Expression) -> DimensionSpec | None:
    if not isinstance(statement, exp.Select):
        return None

    answer_expr = next(
        (
            expression
            for expression in statement.expressions
            if isinstance(expression, exp.Alias) and expression.alias_or_name == "answer"
        ),
        None,
    )
    group = statement.args.get("group")
    if answer_expr is None or group is None or len(group.expressions) != 1:
        return None

    non_answer = [
        expression
        for expression in statement.expressions
        if expression is not answer_expr
    ]
    if len(non_answer) != 1:
        return None

    dimension_expr = non_answer[0]
    dimension_alias = dimension_expr.alias_or_name
    if not dimension_alias:
        return None

    projection = (
        dimension_expr.this.sql()
        if isinstance(dimension_expr, exp.Alias)
        else dimension_expr.sql()
    )
    group_by_sql = group.expressions[0].sql()
    return DimensionSpec(
        name=_slugify(dimension_alias),
        expression_sql=projection,
        group_by_sql=group_by_sql,
    )


def _derive_base_sql(reference_sql: str) -> tuple[str, DimensionSpec | None]:
    statement = parse_one(reference_sql)
    dimension = _group_dimension_seed(statement)
    if dimension is None:
        base = statement.copy()
        if isinstance(base, exp.Select) and len(base.expressions) == 1:
            expression = base.expressions[0]
            aliased = (
                expression.copy()
                if isinstance(expression, exp.Alias)
                else exp.alias_(expression.copy(), "answer")
            )
            if isinstance(aliased, exp.Alias):
                aliased.set("alias", exp.to_identifier("answer"))
            base.set("expressions", [aliased])
        return base.sql(), None

    answer_expr = next(
        expression
        for expression in statement.expressions
        if isinstance(expression, exp.Alias) and expression.alias_or_name == "answer"
    )
    base = statement.copy()
    base.set("expressions", [answer_expr.copy()])
    base.set("group", None)
    base.set("order", None)
    return base.sql(), dimension


def _derive_metric_name(prompts: list[str], *, has_dimension: bool) -> str:
    joined = " ".join(prompts).lower()
    joined = re.sub(r"\([^)]*\)", " ", joined)
    joined = re.sub(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", " ", joined)
    joined = re.sub(r"\b\d+-day\b", " ", joined)
    joined = re.sub(r"\bbefore or on\b", " ", joined)
    joined = re.sub(r"\bduring .*? period ending on\b", " ", joined)
    joined = re.sub(r"\bon the helium network\b", " ", joined)
    joined = re.sub(r"\bwhat was\b", " ", joined)
    joined = re.sub(r"\bhow many\b", " ", joined)
    joined = re.sub(r"\bon which date was\b", " ", joined)

    tokens = [
        token
        for token in _slugify(joined).split("_")
        if token and token not in _STOP_WORDS
    ]

    if has_dimension:
        filtered: list[str] = []
        skip = False
        for token in tokens:
            if token == "billing":
                skip = True
                continue
            if skip and token == "country":
                skip = False
                continue
            if token == "by":
                continue
            filtered.append(token)
        tokens = filtered or tokens

    if "rewarded" in tokens and "unrewarded" not in tokens:
        if "traffic" in tokens:
            return "rewarded_traffic_tb" if "tb" in tokens else "rewarded_traffic"
    if "unrewarded" in tokens and "traffic" in tokens:
        return "unrewarded_traffic_gb" if "gb" in tokens else "unrewarded_traffic"
    if "dau" in tokens and "highest" in tokens:
        return "max_daily_dau"
    if "date" in tokens and "highest" in tokens and "traffic" in tokens:
        return "max_daily_traffic_date"
    if "users" in tokens and "served" in tokens:
        return "users_served"
    if "brownfield" in tokens and "called" in tokens:
        return "brownfield_called_station_ids_with_traffic"
    if "brownfield" in tokens and "sites" in tokens:
        return "brownfield_sites_with_traffic"

    if "total" not in tokens:
        tokens.insert(0, "total")
    if "traffic" in tokens and "tb" in tokens:
        return "_".join(["total"] + [t for t in tokens if t not in {"total"}])
    if "traffic" in tokens and "gb" in tokens:
        return "_".join(["total"] + [t for t in tokens if t not in {"total"}])
    return "_".join(tokens[:8] or ["imported_metric"])


def _infer_tags(prompts: list[str]) -> list[str]:
    tags: list[str] = []
    joined = " ".join(prompts).lower()
    for candidate in ("traffic", "rewards", "brownfield", "usage", "dau", "users"):
        if candidate in joined and candidate not in tags:
            tags.append(candidate)
    return tags


def _load_evidence_flags(connection_path: Path) -> dict[str, Any]:
    examples_dir = connection_path / "examples"
    example_count = len(list(examples_dir.glob("*.yaml"))) if examples_dir.exists() else 0
    return {
        "business_rules": (connection_path / "instructions" / "business_rules.yaml").exists(),
        "domain_model": (connection_path / "domain" / "model.md").exists(),
        "examples": example_count,
        "schema_descriptions": (connection_path / "schema" / "descriptions.yaml").exists(),
    }


def _analyze_case(case: BenchmarkCase) -> CaseSemanticSeed:
    reference_sql = _extract_reference_sql(case.gold_sql)
    base_sql, dimension = _derive_base_sql(reference_sql)
    parameterized_sql, time_context = _parameterize_time_filters(base_sql)
    signature = _normalize_signature(parameterized_sql)
    return CaseSemanticSeed(
        case=case,
        reference_sql=reference_sql,
        base_sql=parameterized_sql,
        signature=signature,
        tables=_extract_tables(parameterized_sql),
        time_context=time_context,
        dimension=dimension,
    )


def _metric_parameters_for_sql(sql: str) -> list[dict[str, str]]:
    parameters: list[dict[str, str]] = []
    if "{start_date}" in sql:
        parameters.append(
            {"name": "start_date", "type": "date", "description": "Inclusive date boundary."}
        )
    if "{end_date}" in sql:
        parameters.append(
            {"name": "end_date", "type": "date", "description": "Exclusive date boundary."}
        )
    return parameters


def _render_metrics_yaml(provider_id: str, metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": "1.0.0", "provider_id": provider_id, "metrics": metrics}


def _render_dimensions_yaml(provider_id: str, dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": "1.0.0", "provider_id": provider_id, "dimensions": dimensions}


def _render_bindings_yaml(provider_id: str, bindings: dict[str, Any]) -> dict[str, Any]:
    return {"version": "1.0.0", "provider_id": provider_id, "bindings": bindings}


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(payload, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def bootstrap_semantics_from_benchmark(
    *,
    connection_path: Path,
    output_connection_path: Path | None = None,
    case_pack: str = "cases.yaml",
    emit_mode: str = "candidate",
) -> dict[str, Any]:
    """Bootstrap semantic artifacts from a benchmark pack into a connection path."""
    cases = load_case_pack(connection_path, case_pack=case_pack)
    output_path = output_connection_path or connection_path
    provider_id = output_path.name
    evidence_used = _load_evidence_flags(connection_path)

    analyzed: list[CaseSemanticSeed] = []
    unsupported_cases: list[str] = []
    for case in cases:
        try:
            analyzed.append(_analyze_case(case))
        except Exception:
            unsupported_cases.append(case.id)

    clusters: dict[str, list[CaseSemanticSeed]] = {}
    for item in analyzed:
        clusters.setdefault(item.signature, []).append(item)

    metrics_payload: list[dict[str, Any]] = []
    dimensions_payload: list[dict[str, Any]] = []
    bindings_payload: dict[str, Any] = {}
    semantic_cases: list[dict[str, Any]] = []
    dimension_names: set[str] = set()
    used_metric_names: set[str] = set()
    cases_grouped: dict[str, list[str]] = {}

    status = "approved" if emit_mode in {"approved", "temp_overlay"} else "candidate"

    for signature, cluster in sorted(
        clusters.items(),
        key=lambda item: sorted(c.case.id for c in item[1]),
    ):
        prompts = [item.case.prompt for item in cluster]
        dimension = next((item.dimension for item in cluster if item.dimension is not None), None)
        metric_name = _derive_metric_name(prompts, has_dimension=dimension is not None)
        original_metric_name = metric_name
        suffix = 2
        while metric_name in used_metric_names:
            metric_name = f"{original_metric_name}_{suffix}"
            suffix += 1
        used_metric_names.add(metric_name)
        description = prompts[0].rstrip("?")
        parameters = _metric_parameters_for_sql(cluster[0].base_sql)

        metric_entry = {
            "name": metric_name,
            "display_name": _titleize(metric_name),
            "description": description,
            "tables": cluster[0].tables,
            "parameters": parameters,
            "tags": _infer_tags(prompts),
            "status": status,
        }
        if dimension is not None:
            metric_entry["dimensions"] = [dimension.name]
        metrics_payload.append(metric_entry)

        binding_entry: dict[str, Any] = {
            "metric_name": metric_name,
            "sql": cluster[0].base_sql,
        }
        if cluster[0].tables:
            binding_entry["tables"] = cluster[0].tables
        if dimension is not None:
            binding_entry["dimensions"] = {
                dimension.name: {
                    "dimension_name": dimension.name,
                    "projection_sql": dimension.expression_sql,
                    "group_by_sql": dimension.group_by_sql,
                    "tables": cluster[0].tables,
                }
            }
            if dimension.name not in dimension_names:
                dimensions_payload.append(
                    {
                        "name": dimension.name,
                        "display_name": _titleize(dimension.name),
                        "description": f"Imported grouping dimension '{dimension.name}'.",
                        "type": "categorical",
                        "column": dimension.expression_sql,
                        "tables": cluster[0].tables,
                        "status": status,
                    }
                )
                dimension_names.add(dimension.name)
        bindings_payload[metric_name] = binding_entry
        cases_grouped[metric_name] = sorted(item.case.id for item in cluster)

    for item in analyzed:
        case_payload = item.case.model_dump(mode="python", exclude_none=True)
        if item.time_context:
            case_payload["answer_intent_options"] = {"time_context": item.time_context}
        elif "answer_intent_options" in case_payload:
            case_payload.pop("answer_intent_options")
        semantic_cases.append(case_payload)

    _write_yaml(
        output_path / "metrics" / "catalog.yaml",
        _render_metrics_yaml(provider_id, metrics_payload),
    )
    _write_yaml(
        output_path / "metrics" / "dimensions.yaml",
        _render_dimensions_yaml(provider_id, dimensions_payload),
    )
    _write_yaml(
        output_path / "metrics" / "bindings.yaml",
        _render_bindings_yaml(provider_id, bindings_payload),
    )
    _write_yaml(
        output_path / "benchmark" / "cases_semantic.yaml",
        {"cases": semantic_cases},
    )

    report = {
        "connection": connection_path.name,
        "source_case_pack": f"benchmark/{case_pack}",
        "cases_seen": len(cases),
        "clusters_created": len(clusters),
        "metrics_created": len(metrics_payload),
        "dimensions_created": len(dimensions_payload),
        "cases_grouped": cases_grouped,
        "unsupported_cases": sorted(unsupported_cases),
        "ambiguous_cases": [],
        "warnings": [],
        "evidence_used": evidence_used,
        "output_connection_path": str(output_path),
    }
    _write_yaml(output_path / "metrics" / "import_report.yaml", report)
    return report
