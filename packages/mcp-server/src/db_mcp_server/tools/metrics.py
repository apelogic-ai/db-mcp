"""Thin MCP tool wrappers for metrics tools (step 3.06).

All write and delete operations delegate to the vault schema registry.
Read and validation operations call the knowledge layer directly.
"""

from __future__ import annotations

from db_mcp.services.connection import resolve_connection
from db_mcp.services.metrics import (
    serialize_metric_binding as _serialize_metric_binding,
)
from db_mcp.services.metrics import (
    validate_metric_binding as _validate_metric_binding,
)
from db_mcp_knowledge.metrics.mining import mine_metrics_and_dimensions
from db_mcp_knowledge.metrics.store import (
    load_dimensions,
    load_metric_bindings,
    load_metrics,
)
from db_mcp_knowledge.vault.schema_registry import vault_delete_typed, vault_write_typed
from db_mcp_models import MetricDimensionBinding

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

    result = vault_write_typed(
        "metric_binding",
        {
            "metric_name": metric_name,
            "sql": sql,
            "tables": tables or [],
            "dimensions": {
                name: {
                    "dimension_name": db.dimension_name,
                    "projection_sql": db.projection_sql,
                    "filter_sql": db.filter_sql,
                    "group_by_sql": db.group_by_sql,
                    "tables": db.tables,
                }
                for name, db in dimension_bindings.items()
            },
        },
        provider_id,
        connection_path,
    )
    from db_mcp_models import MetricBinding

    binding = MetricBinding(
        metric_name=metric_name,
        sql=sql,
        tables=tables or [],
        dimensions=dimension_bindings,
    )
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
        result = vault_write_typed(
            "metric",
            {
                "name": name,
                "description": description,
                "sql": sql,
                "display_name": display_name,
                "tables": tables or [],
                "tags": tags or [],
                "dimensions": dimensions or [],
                "notes": notes,
                "status": "approved",
            },
            provider_id,
            connection_path,
        )
        return {
            "approved": result.get("saved", False),
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
        result = vault_write_typed(
            "dimension",
            {
                "name": name,
                "description": description,
                "column": column,
                "display_name": display_name,
                "type": dim_type,
                "tables": tables or [],
                "values": values or [],
                "status": "approved",
            },
            provider_id,
            connection_path,
        )
        return {"approved": result.get("saved", False), "type": "dimension", "name": name}

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
        try:
            result = vault_delete_typed("metric_deletion", name, provider_id, connection_path)
        except ValueError as e:
            return {"removed": False, "type": "metric", "name": name, "error": str(e)}
        return {"removed": result.get("deleted", False), "type": "metric", "name": name,
                "error": result.get("error")}

    if type == "dimension":
        try:
            result = vault_delete_typed("dimension_deletion", name, provider_id, connection_path)
        except ValueError as e:
            return {"removed": False, "type": "dimension", "name": name, "error": str(e)}
        return {"removed": result.get("deleted", False), "type": "dimension", "name": name,
                "error": result.get("error")}

    return {"error": f"Invalid type '{type}'. Use 'metric' or 'dimension'.", "removed": False}
