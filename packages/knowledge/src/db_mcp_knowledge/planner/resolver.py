"""Resolve semantic plans into executable metric plans."""

from __future__ import annotations

from db_mcp_models import MetaQueryPlan, MetricExecutionPlan
from sqlglot import exp, parse_one

from db_mcp_knowledge.semantic.core_loader import ConnectionSemanticCore
from db_mcp_knowledge.vault.paths import METRICS_BINDINGS_FILE


def _render_metric_sql(metric_sql: str, parameters: dict[str, object]) -> str:
    try:
        return metric_sql.format(**parameters)
    except KeyError as exc:
        missing = exc.args[0]
        raise ValueError(f"Missing metric parameter: {missing}") from exc


def _required_metric_parameters(metric) -> list[str]:
    return [param.name for param in metric.parameters if param.required and param.default is None]


def _compile_dimensioned_metric_sql(
    metric_sql: str,
    *,
    projection_sql: str,
    result_alias: str,
    group_by_sql: str | None = None,
) -> str:
    statement = parse_one(metric_sql)
    if statement.__class__.__name__ != "Select":
        raise ValueError(
            "Dimension-aware metric execution currently supports SELECT metrics only."
        )

    dimension_projection = f"{projection_sql} AS {result_alias}"
    dimension_group = group_by_sql or projection_sql

    return (
        statement.copy()
        .select(dimension_projection, append=True)
        .group_by(dimension_group, append=True)
        .sql()
    )


def _compile_filtered_metric_sql(metric_sql: str, predicates: list[str]) -> str:
    if not predicates:
        return metric_sql

    statement = parse_one(metric_sql)
    if statement.__class__.__name__ != "Select":
        raise ValueError("Filter-aware metric execution currently supports SELECT metrics only.")

    where_expression = parse_one(predicates[0], into=exp.Condition)
    for predicate in predicates[1:]:
        where_expression = exp.and_(
            where_expression,
            parse_one(predicate, into=exp.Condition),
        )

    existing_where = statement.args.get("where")
    if existing_where is not None:
        where_expression = exp.and_(existing_where.this, where_expression)

    statement.set("where", exp.Where(this=where_expression))
    return statement.sql()


def resolve_metric_execution_plan(
    *,
    meta_query: MetaQueryPlan,
    connection: str,
    semantic_core: ConnectionSemanticCore,
) -> MetricExecutionPlan:
    """Resolve a single-measure meta-query into an executable metric plan."""
    if len(meta_query.measures) != 1:
        raise ValueError("The first slice supports exactly one metric per intent.")

    measure = meta_query.measures[0]
    metric = semantic_core.get_metric(measure.metric_name)
    if metric is None:
        raise ValueError(f"Resolved metric '{measure.metric_name}' is not available.")

    missing_parameters = [
        name for name in _required_metric_parameters(metric) if name not in measure.parameters
    ]
    if missing_parameters:
        missing = ", ".join(sorted(missing_parameters))
        raise ValueError(f"Missing required metric parameters: {missing}")

    rendered_parameters = {
        param.name: measure.parameters.get(param.name, param.default)
        for param in metric.parameters
    }
    binding = semantic_core.get_metric_binding(metric.name)
    binding_source = "metric.sql"
    metric_sql = metric.sql
    metric_tables = metric.tables
    if binding is not None:
        binding_source = METRICS_BINDINGS_FILE
        metric_sql = binding.sql
        metric_tables = binding.tables or metric_tables

    rendered_sql = _render_metric_sql(metric_sql, rendered_parameters)
    warnings = list(meta_query.warnings)

    if meta_query.filters:
        predicates: list[str] = []
        for meta_filter in meta_query.filters:
            dimension = next(
                (item for item in semantic_core.dimensions if item.name == meta_filter.field),
                None,
            )
            if dimension is None:
                raise ValueError(f"Resolved filter field '{meta_filter.field}' is not available.")

            filter_sql = dimension.column
            filter_tables = dimension.tables

            if binding is not None:
                dimension_binding = binding.dimensions.get(dimension.name)
                if dimension_binding is None:
                    raise ValueError(
                        f"Metric '{metric.name}' has no binding for filter field "
                        f"'{dimension.name}'."
                    )
                filter_sql = dimension_binding.filter_sql or dimension_binding.projection_sql
                filter_tables = dimension_binding.tables or filter_tables

            if metric_tables and filter_tables:
                if not set(metric_tables) & set(filter_tables):
                    raise ValueError(
                        f"Metric '{metric.name}' and filter field '{dimension.name}' "
                        "do not share a table."
                    )

            predicates.append(f"{filter_sql} {meta_filter.operator} {meta_filter.value}")

        rendered_sql = _compile_filtered_metric_sql(rendered_sql, predicates)

    if meta_query.dimensions:
        if len(meta_query.dimensions) > 1:
            raise ValueError("The first slice supports at most one metric dimension.")

        meta_dimension = meta_query.dimensions[0]
        dimension = next(
            (item for item in semantic_core.dimensions if item.name == meta_dimension.name),
            None,
        )
        if dimension is None:
            raise ValueError(f"Resolved dimension '{meta_dimension.name}' is not available.")
        if metric.dimensions and dimension.name not in metric.dimensions:
            raise ValueError(
                f"Metric '{metric.name}' is not approved for dimension '{dimension.name}'."
            )
        dimension_projection = dimension.column
        dimension_group_by = dimension.column
        dimension_tables = dimension.tables

        if binding is not None:
            dimension_binding = binding.dimensions.get(dimension.name)
            if dimension_binding is None:
                raise ValueError(
                    f"Metric '{metric.name}' has no binding for dimension '{dimension.name}'."
                )
            dimension_projection = dimension_binding.projection_sql
            dimension_group_by = dimension_binding.group_by_sql or dimension_projection
            dimension_tables = dimension_binding.tables or dimension_tables

        if metric_tables and dimension_tables:
            if not set(metric_tables) & set(dimension_tables):
                raise ValueError(
                    f"Metric '{metric.name}' and dimension '{dimension.name}' "
                    "do not share a table."
                )

        rendered_sql = _compile_dimensioned_metric_sql(
            rendered_sql,
            projection_sql=dimension_projection,
            result_alias=dimension.name,
            group_by_sql=dimension_group_by,
        )

    return MetricExecutionPlan(
        connection=connection,
        metric_name=metric.name,
        sql=rendered_sql,
        binding_source=binding_source,
        metric_parameters=rendered_parameters,
        expected_cardinality=meta_query.expected_cardinality,
        warnings=warnings,
    )
