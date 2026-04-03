"""Thin MCP tool wrappers for metrics tools (step 3.06).

Calls db_mcp.services.metrics and underlying knowledge-layer stores directly.
Does not import from db_mcp.tools.metrics.
"""

from __future__ import annotations

from db_mcp.services.connection import resolve_connection
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

# ---------------------------------------------------------------------------
# Helpers (inlined from db_mcp.tools.metrics — no import from tools.metrics)
# ---------------------------------------------------------------------------

def _serialize_metric_binding(binding: MetricBinding) -> dict:
    return {
        "metric_name": binding.metric_name,
        "sql": binding.sql,
        "tables": binding.tables,
        "dimensions": [
            {
                "dimension_name": d.dimension_name,
                "projection_sql": d.projection_sql,
                "filter_sql": d.filter_sql,
                "group_by_sql": d.group_by_sql,
                "tables": d.tables,
            }
            for _, d in sorted(binding.dimensions.items())
        ],
    }


def _validate_metric_binding(
    *,
    provider_id: str,
    connection_path,
    metric_name: str,
    sql: str,
    tables: list[str] | None = None,
    dimensions: list[dict] | None = None,
) -> dict:
    metrics_catalog = load_metrics(provider_id, connection_path=connection_path)
    dimensions_catalog = load_dimensions(provider_id, connection_path=connection_path)

    errors: list[str] = []
    warnings: list[str] = []

    metric = metrics_catalog.get_metric(metric_name)
    if metric is None:
        errors.append(f"Metric '{metric_name}' not found in the approved catalog.")
    if not sql.strip():
        errors.append("Binding SQL is required.")

    seen_dimensions: set[str] = set()
    for raw_dimension in dimensions or []:
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

    if metric is not None and metric.dimensions:
        missing = [d for d in metric.dimensions if d not in seen_dimensions]
        if missing:
            warnings.append(
                "Metric binding does not define projections for approved dimensions: "
                + ", ".join(missing)
            )

    return {"valid": not errors, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

async def _metrics_discover(connection: str) -> dict:
    """Mine the knowledge vault for metric and dimension candidates."""
    _, _, connection_path = resolve_connection(connection)
    result = await mine_metrics_and_dimensions(connection_path)

    metric_candidates = result.get("metric_candidates", [])
    dimension_candidates = result.get("dimension_candidates", [])

    by_category: dict[str, list[dict]] = {}
    for c in dimension_candidates:
        cat = c.category
        by_category.setdefault(cat, []).append(
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
    }


async def _metrics_bindings_list(connection: str) -> dict:
    """List metric execution bindings configured for the connection."""
    _, provider_id, connection_path = resolve_connection(connection)
    bindings_catalog = load_metric_bindings(provider_id, connection_path=connection_path)
    return {
        "bindings": [
            _serialize_metric_binding(b) for _, b in sorted(bindings_catalog.bindings.items())
        ],
        "summary": f"{len(bindings_catalog.bindings)} binding(s) in catalog.",
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
    return {"metric_name": metric_name, **validation}


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
        return {"saved": False, "metric_name": metric_name, "validation": validation}

    dimension_bindings = {
        raw["dimension_name"]: MetricDimensionBinding(
            dimension_name=raw["dimension_name"],
            projection_sql=raw["projection_sql"],
            filter_sql=raw.get("filter_sql"),
            group_by_sql=raw.get("group_by_sql"),
            tables=raw.get("tables", []),
        )
        for raw in (dimensions or [])
    }
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
    """List all approved metrics and dimensions in the catalog."""
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
                "binding_dimensions": sorted(bindings_catalog.bindings[m.name].dimensions.keys())
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
    """Approve a discovered candidate into the metrics catalog."""
    _, provider_id, connection_path = resolve_connection(connection)

    if type == "metric":
        if not description:
            return {"error": "description is required for metrics", "approved": False}
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
        }

    if type == "dimension":
        if not column:
            return {"error": "column is required for dimensions", "approved": False}
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
        return {"approved": result.get("added", False), "type": "dimension", "name": name}

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
    """Manually add a metric or dimension to the catalog."""
    result = await _metrics_approve(
        type=type, name=name, connection=connection, description=description, sql=sql,
        column=column, display_name=display_name, tables=tables, tags=tags,
        dimensions=dimensions, dim_type=dim_type, values=values, notes=notes,
    )
    if "approved" in result:
        result["added"] = result.pop("approved")
    return result


async def _metrics_remove(type: str, name: str, connection: str) -> dict:
    """Remove a metric or dimension from the catalog."""
    _, provider_id, connection_path = resolve_connection(connection)

    if type == "metric":
        result = delete_metric(provider_id, name, connection_path=connection_path)
        return {"removed": result.get("deleted", False), "type": "metric", "name": name,
                "error": result.get("error")}
    if type == "dimension":
        result = delete_dimension(provider_id, name, connection_path=connection_path)
        return {"removed": result.get("deleted", False), "type": "dimension", "name": name,
                "error": result.get("error")}

    return {"error": f"Invalid type '{type}'. Use 'metric' or 'dimension'.", "removed": False}
