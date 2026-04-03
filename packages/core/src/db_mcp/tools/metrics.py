"""Metrics and dimensions MCP tools — discover, manage, and catalog business metrics."""

from pathlib import Path

from db_mcp_knowledge.metrics.mining import mine_metrics_and_dimensions
from db_mcp_knowledge.metrics.store import (
    add_dimension,
    add_metric,
    delete_dimension,
    delete_metric,
    load_dimensions,
    load_metric_bindings,
    load_metrics,
    upsert_metric_binding,
)
from db_mcp_models import MetricBinding, MetricDimensionBinding

from db_mcp.tools.utils import resolve_connection


def _serialize_metric_binding(binding: MetricBinding) -> dict:
    """Convert a binding model to a JSON-safe payload."""
    return {
        "metric_name": binding.metric_name,
        "sql": binding.sql,
        "tables": binding.tables,
        "dimensions": [
            {
                "dimension_name": dimension_binding.dimension_name,
                "projection_sql": dimension_binding.projection_sql,
                "filter_sql": dimension_binding.filter_sql,
                "group_by_sql": dimension_binding.group_by_sql,
                "tables": dimension_binding.tables,
            }
            for _, dimension_binding in sorted(binding.dimensions.items())
        ],
    }


def _validate_metric_binding(
    *,
    provider_id: str,
    connection_path: Path,
    metric_name: str,
    sql: str,
    tables: list[str] | None = None,
    dimensions: list[dict] | None = None,
) -> dict:
    """Validate a metric binding against the approved logical catalogs."""
    metrics_catalog = load_metrics(provider_id, connection_path=connection_path)
    dimensions_catalog = load_dimensions(provider_id, connection_path=connection_path)

    errors: list[str] = []
    warnings: list[str] = []

    metric = metrics_catalog.get_metric(metric_name)
    if metric is None:
        errors.append(f"Metric '{metric_name}' not found in the approved catalog.")
    if not sql.strip():
        errors.append("Binding SQL is required.")

    binding_tables = tables or []
    binding_dimensions = dimensions or []
    seen_dimensions: set[str] = set()

    for raw_dimension in binding_dimensions:
        dimension_name = raw_dimension.get("dimension_name")
        if not isinstance(dimension_name, str) or not dimension_name:
            errors.append("Each binding dimension must include a non-empty dimension_name.")
            continue
        if dimension_name in seen_dimensions:
            errors.append(f"Duplicate binding dimension '{dimension_name}'.")
            continue
        seen_dimensions.add(dimension_name)

        dimension = dimensions_catalog.get_dimension(dimension_name)
        if dimension is None:
            errors.append(f"Dimension '{dimension_name}' not found in the approved catalog.")
            continue
        if metric is not None and metric.dimensions and dimension_name not in metric.dimensions:
            errors.append(
                f"Metric '{metric_name}' is not approved for dimension '{dimension_name}'."
            )

        projection_sql = raw_dimension.get("projection_sql")
        if not isinstance(projection_sql, str) or not projection_sql.strip():
            errors.append(f"Binding dimension '{dimension_name}' requires projection_sql.")

        dimension_tables = raw_dimension.get("tables") or []
        if (
            binding_tables
            and dimension_tables
            and not set(binding_tables).intersection(dimension_tables)
        ):
            errors.append(
                f"Binding dimension '{dimension_name}' does not share a table with metric "
                f"'{metric_name}'."
            )

    if metric is not None and metric.dimensions:
        missing_dimensions = sorted(set(metric.dimensions) - seen_dimensions)
        if missing_dimensions:
            warnings.append(
                "Metric binding does not define projections for approved dimensions: "
                + ", ".join(missing_dimensions)
            )

    return {"valid": not errors, "errors": errors, "warnings": warnings}


async def _metrics_discover(connection: str) -> dict:
    """Mine the knowledge vault for metric and dimension candidates.

    Analyzes training examples (SQL patterns), business rules, and schema
    descriptions to find potential metrics (aggregations) and dimensions
    (GROUP BY columns, categorical/temporal/geographic fields).

    Results are grouped by semantic category (Location, Time, Device, etc.)
    and ranked by confidence score.

    Returns:
        Dict with metric_candidates, dimension_candidates grouped by category,
        and a summary.
    """
    # Use resolve_connection for proper validation
    _, _, connection_path = resolve_connection(connection)
    result = await mine_metrics_and_dimensions(connection_path)

    metric_candidates = result.get("metric_candidates", [])
    dimension_candidates = result.get("dimension_candidates", [])

    # Group dimension candidates by semantic category
    by_category: dict[str, list[dict]] = {}
    for c in dimension_candidates:
        cat = c.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(
            {
                "name": c.dimension.name,
                "display_name": c.dimension.display_name,
                "description": c.dimension.description,
                "type": c.dimension.type.value,
                "column": c.dimension.column,
                "tables": c.dimension.tables,
                "confidence": c.confidence,
                "source": c.source,
            }
        )

    # Sort categories by count (largest first)
    sorted_categories = dict(sorted(by_category.items(), key=lambda x: len(x[1]), reverse=True))

    return {
        "metric_candidates": [
            {
                "name": c.metric.name,
                "display_name": c.metric.display_name,
                "description": c.metric.description,
                "sql": c.metric.sql,
                "tables": c.metric.tables,
                "tags": c.metric.tags,
                "confidence": c.confidence,
                "source": c.source,
                "evidence": c.evidence,
            }
            for c in metric_candidates
        ],
        "dimension_candidates_by_category": sorted_categories,
        "summary": (
            f"Found {len(metric_candidates)} metric candidate(s) and "
            f"{len(dimension_candidates)} dimension candidate(s) "
            f"across {len(sorted_categories)} categories."
        ),
        "guidance": {
            "next_steps": [
                "Review candidates and approve the ones that are useful with metrics_approve.",
                "Use metrics_add to manually define metrics not found by mining.",
                "Use metrics_list to see the current approved catalog.",
            ],
        },
    }


async def _metrics_bindings_list(connection: str) -> dict:
    """List metric execution bindings configured for the connection."""
    _, provider_id, connection_path = resolve_connection(connection)
    bindings_catalog = load_metric_bindings(provider_id, connection_path=connection_path)

    return {
        "bindings": [
            _serialize_metric_binding(binding)
            for _, binding in sorted(bindings_catalog.bindings.items())
        ],
        "summary": f"{len(bindings_catalog.bindings)} binding(s) in catalog.",
        "guidance": {
            "next_steps": [
                "Use metrics_bindings_validate before saving or editing a binding.",
                "Use metrics_bindings_set to add or update a metric binding.",
            ],
        },
    }


async def _metrics_bindings_validate(
    connection: str,
    metric_name: str,
    sql: str,
    tables: list[str] | None = None,
    dimensions: list[dict] | None = None,
) -> dict:
    """Validate a metric binding against approved metrics and dimensions."""
    _, provider_id, connection_path = resolve_connection(connection)
    validation = _validate_metric_binding(
        provider_id=provider_id,
        connection_path=connection_path,
        metric_name=metric_name,
        sql=sql,
        tables=tables,
        dimensions=dimensions,
    )
    return {
        "metric_name": metric_name,
        **validation,
    }


async def _metrics_bindings_set(
    connection: str,
    metric_name: str,
    sql: str,
    tables: list[str] | None = None,
    dimensions: list[dict] | None = None,
) -> dict:
    """Create or update a connection-bound metric binding."""
    _, provider_id, connection_path = resolve_connection(connection)
    validation = _validate_metric_binding(
        provider_id=provider_id,
        connection_path=connection_path,
        metric_name=metric_name,
        sql=sql,
        tables=tables,
        dimensions=dimensions,
    )
    if not validation["valid"]:
        return {
            "saved": False,
            "metric_name": metric_name,
            "validation": validation,
        }

    dimension_bindings = {}
    for raw_dimension in dimensions or []:
        dimension_binding = MetricDimensionBinding(
            dimension_name=raw_dimension["dimension_name"],
            projection_sql=raw_dimension["projection_sql"],
            filter_sql=raw_dimension.get("filter_sql"),
            group_by_sql=raw_dimension.get("group_by_sql"),
            tables=raw_dimension.get("tables", []),
        )
        dimension_bindings[dimension_binding.dimension_name] = dimension_binding

    binding = MetricBinding(
        metric_name=metric_name,
        sql=sql,
        tables=tables or [],
        dimensions=dimension_bindings,
    )
    result = upsert_metric_binding(provider_id, binding, connection_path=connection_path)
    return {
        "saved": result.get("saved", False),
        "metric_name": metric_name,
        "binding": _serialize_metric_binding(binding),
        "validation": validation,
        "file_path": result.get("file_path"),
        "error": result.get("error"),
    }


async def _metrics_list(connection: str) -> dict:
    """List all approved metrics and dimensions in the catalog.

    Returns the full catalog of business metrics and dimensions that have
    been approved or manually added.

    Args:
        connection: Connection name for multi-connection support.

    Returns:
        Dict with metrics list, dimensions list, and summary.
    """
    # Resolve connection for validation and provider_id
    _, provider_id, connection_path = resolve_connection(connection)

    metrics_catalog = load_metrics(provider_id, connection_path=connection_path)
    dimensions_catalog = load_dimensions(provider_id, connection_path=connection_path)
    bindings_catalog = load_metric_bindings(provider_id, connection_path=connection_path)

    return {
        "metrics": [
            {
                "name": m.name,
                "display_name": m.display_name,
                "description": m.description,
                "sql": m.sql,
                "tables": m.tables,
                "tags": m.tags,
                "dimensions": m.dimensions,
                "has_binding": m.name in bindings_catalog.bindings,
                "binding_dimensions": sorted(
                    bindings_catalog.bindings[m.name].dimensions.keys()
                )
                if m.name in bindings_catalog.bindings
                else [],
                "notes": m.notes,
            }
            for m in metrics_catalog.metrics
        ],
        "dimensions": [
            {
                "name": d.name,
                "display_name": d.display_name,
                "description": d.description,
                "type": d.type.value,
                "column": d.column,
                "tables": d.tables,
                "values": d.values,
            }
            for d in dimensions_catalog.dimensions
        ],
        "summary": (
            f"{metrics_catalog.count()} metric(s) and "
            f"{dimensions_catalog.count()} dimension(s) in catalog."
        ),
        "guidance": {
            "next_steps": [
                "Use metrics_discover to mine the vault for new candidates.",
                "Use metrics_add to define new metrics or dimensions manually.",
            ],
        },
    }


async def _metrics_approve(
    type: str,
    name: str,
    connection: str,
    description: str = "",
    sql: str = "",
    column: str = "",
    display_name: str | None = None,
    tables: list[str] | None = None,
    tags: list[str] | None = None,
    dimensions: list[str] | None = None,
    dim_type: str = "categorical",
    values: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Approve a discovered candidate into the metrics catalog.

    Use this after metrics_discover to approve candidates.

    Args:
        type: Either "metric" or "dimension"
        name: Identifier for the metric/dimension
        connection: Connection name for multi-connection support.
        description: What it measures (required for metrics)
        sql: Optional legacy SQL template for direct execution
        column: Column reference like "table.column" (required for dimensions)
        display_name: Human-readable name
        tables: Tables involved
        tags: Categorization tags (metrics only)
        dimensions: Dimension names this metric can be sliced by (metrics only)
        dim_type: Dimension type — temporal, categorical, geographic, entity
        values: Known values for the dimension
        notes: Additional notes (metrics only)

    Returns:
        Dict with approval status.
    """
    # Resolve connection for validation and provider_id
    _, provider_id, connection_path = resolve_connection(connection)

    if type == "metric":
        if not description:
            return {
                "error": "description is required for metrics",
                "approved": False,
            }
        result = add_metric(
            provider_id=provider_id,
            name=name,
            description=description,
            sql=sql,
            connection_path=connection_path,
            display_name=display_name,
            tables=tables,
            tags=tags,
            dimensions=dimensions,
            notes=notes,
            status="approved",
        )
        return {
            "approved": result.get("added", False),
            "type": "metric",
            "name": name,
            "warnings": (
                ["Metric was saved without embedded SQL; add a binding before execution."]
                if not sql
                else []
            ),
            "guidance": {
                "next_steps": [
                    f"Metric '{name}' approved. Use metrics_list to see the catalog.",
                    "Use metrics_bindings_set to attach connection-specific execution SQL.",
                    "Continue approving more candidates with metrics_approve.",
                ],
            },
        }

    elif type == "dimension":
        if not column:
            return {
                "error": "column is required for dimensions",
                "approved": False,
            }
        result = add_dimension(
            provider_id=provider_id,
            name=name,
            column=column,
            connection_path=connection_path,
            description=description,
            display_name=display_name,
            dim_type=dim_type,
            tables=tables,
            values=values,
            status="approved",
        )
        return {
            "approved": result.get("added", False),
            "type": "dimension",
            "name": name,
            "guidance": {
                "next_steps": [
                    f"Dimension '{name}' approved. Use metrics_list to see the catalog.",
                    "Continue approving more candidates with metrics_approve.",
                ],
            },
        }

    return {"error": f"Invalid type '{type}'. Use 'metric' or 'dimension'.", "approved": False}


async def _metrics_add(
    type: str,
    name: str,
    connection: str,
    description: str = "",
    sql: str = "",
    column: str = "",
    display_name: str | None = None,
    tables: list[str] | None = None,
    tags: list[str] | None = None,
    dimensions: list[str] | None = None,
    dim_type: str = "categorical",
    values: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Manually add a metric or dimension to the catalog.

    Use this to define metrics/dimensions that weren't found by mining.

    Args:
        type: Either "metric" or "dimension"
        name: Identifier for the metric/dimension
        connection: Connection name for multi-connection support.
        description: What it measures (required for metrics)
        sql: Optional legacy SQL template for direct execution
        column: Column reference like "table.column" (required for dimensions)
        display_name: Human-readable name
        tables: Tables involved
        tags: Categorization tags (metrics only)
        dimensions: Dimension names this metric can be sliced by (metrics only)
        dim_type: Dimension type — temporal, categorical, geographic, entity
        values: Known values for the dimension
        notes: Additional notes (metrics only)

    Returns:
        Dict with add status.
    """
    # Delegate to _metrics_approve — same logic, different framing
    result = await _metrics_approve(
        type=type,
        name=name,
        connection=connection,
        description=description,
        sql=sql,
        column=column,
        display_name=display_name,
        tables=tables,
        tags=tags,
        dimensions=dimensions,
        dim_type=dim_type,
        values=values,
        notes=notes,
    )

    # Rename key for clarity
    if "approved" in result:
        result["added"] = result.pop("approved")

    return result


async def _metrics_remove(type: str, name: str, connection: str) -> dict:
    """Remove a metric or dimension from the catalog.

    Args:
        type: Either "metric" or "dimension"
        name: Name of the metric/dimension to remove
        connection: Connection name for multi-connection support.

    Returns:
        Dict with removal status.
    """
    # Resolve connection for validation and provider_id
    _, provider_id, connection_path = resolve_connection(connection)

    if type == "metric":
        result = delete_metric(provider_id, name, connection_path=connection_path)
        return {
            "removed": result.get("deleted", False),
            "type": "metric",
            "name": name,
            "error": result.get("error"),
        }
    elif type == "dimension":
        result = delete_dimension(provider_id, name, connection_path=connection_path)
        return {
            "removed": result.get("deleted", False),
            "type": "dimension",
            "name": name,
            "error": result.get("error"),
        }

    return {"error": f"Invalid type '{type}'. Use 'metric' or 'dimension'.", "removed": False}
