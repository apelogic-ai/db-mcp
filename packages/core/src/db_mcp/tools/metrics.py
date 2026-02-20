"""Metrics and dimensions MCP tools — discover, manage, and catalog business metrics."""

from db_mcp.metrics.mining import mine_metrics_and_dimensions
from db_mcp.metrics.store import (
    add_dimension,
    add_metric,
    delete_dimension,
    delete_metric,
    load_dimensions,
    load_metrics,
)
from db_mcp.onboarding.state import get_connection_path
from db_mcp.tools.utils import get_resolved_provider_id


async def _metrics_discover(connection: str | None = None) -> dict:
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
    from db_mcp.tools.utils import resolve_connection

    if connection is not None:
        # Use resolve_connection for proper validation
        _, _, connection_path = resolve_connection(connection)
    else:
        # Legacy fallback when no connection specified
        connection_path = get_connection_path()
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


async def _metrics_list(connection: str | None = None) -> dict:
    """List all approved metrics and dimensions in the catalog.

    Returns the full catalog of business metrics and dimensions that have
    been approved or manually added.

    Args:
        connection: Optional connection name for multi-connection support.

    Returns:
        Dict with metrics list, dimensions list, and summary.
    """
    from db_mcp.tools.utils import resolve_connection

    if connection is not None:
        # Use resolve_connection for proper validation, then use connection name as provider_id
        resolve_connection(connection)  # Validates connection exists
        provider_id = connection
    else:
        # Legacy fallback when no connection specified
        provider_id = get_resolved_provider_id(None)

    metrics_catalog = load_metrics(provider_id)
    dimensions_catalog = load_dimensions(provider_id)

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
    connection: str | None = None,
) -> dict:
    """Approve a discovered candidate into the metrics catalog.

    Use this after metrics_discover to approve candidates.

    Args:
        type: Either "metric" or "dimension"
        name: Identifier for the metric/dimension
        description: What it measures (required for metrics)
        sql: SQL template (required for metrics)
        column: Column reference like "table.column" (required for dimensions)
        display_name: Human-readable name
        tables: Tables involved
        tags: Categorization tags (metrics only)
        dimensions: Dimension names this metric can be sliced by (metrics only)
        dim_type: Dimension type — temporal, categorical, geographic, entity
        values: Known values for the dimension
        notes: Additional notes (metrics only)
        connection: Optional connection name for multi-connection support.

    Returns:
        Dict with approval status.
    """
    from db_mcp.tools.utils import resolve_connection

    if connection is not None:
        # Use resolve_connection for proper validation, then use connection name as provider_id
        resolve_connection(connection)  # Validates connection exists
        provider_id = connection
    else:
        # Legacy fallback when no connection specified
        provider_id = get_resolved_provider_id(None)

    if type == "metric":
        if not description or not sql:
            return {
                "error": "description and sql are required for metrics",
                "approved": False,
            }
        result = add_metric(
            provider_id=provider_id,
            name=name,
            description=description,
            sql=sql,
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
            "guidance": {
                "next_steps": [
                    f"Metric '{name}' approved. Use metrics_list to see the catalog.",
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
    connection: str | None = None,
) -> dict:
    """Manually add a metric or dimension to the catalog.

    Use this to define metrics/dimensions that weren't found by mining.

    Args:
        type: Either "metric" or "dimension"
        name: Identifier for the metric/dimension
        description: What it measures (required for metrics)
        sql: SQL template (required for metrics)
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
        connection=connection,
    )

    # Rename key for clarity
    if "approved" in result:
        result["added"] = result.pop("approved")

    return result


async def _metrics_remove(type: str, name: str, connection: str | None = None) -> dict:
    """Remove a metric or dimension from the catalog.

    Args:
        type: Either "metric" or "dimension"
        name: Name of the metric/dimension to remove
        connection: Optional connection name for multi-connection support.

    Returns:
        Dict with removal status.
    """
    from db_mcp.tools.utils import resolve_connection

    if connection is not None:
        # Use resolve_connection for proper validation, then use connection name as provider_id
        resolve_connection(connection)  # Validates connection exists
        provider_id = connection
    else:
        # Legacy fallback when no connection specified
        provider_id = get_resolved_provider_id(None)

    if type == "metric":
        result = delete_metric(provider_id, name)
        return {
            "removed": result.get("deleted", False),
            "type": "metric",
            "name": name,
            "error": result.get("error"),
        }
    elif type == "dimension":
        result = delete_dimension(provider_id, name)
        return {
            "removed": result.get("deleted", False),
            "type": "dimension",
            "name": name,
            "error": result.get("error"),
        }

    return {"error": f"Invalid type '{type}'. Use 'metric' or 'dimension'.", "removed": False}
