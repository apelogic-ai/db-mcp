from pathlib import Path

from db_mcp_knowledge.metrics.mining import mine_metrics_and_dimensions
from db_mcp_knowledge.metrics.store import (
    add_dimension,
    add_metric,
    delete_dimension,
    delete_metric,
    load_dimensions,
    load_metrics,
)


async def discover_metric_candidates(connection: str, connection_path: Path) -> dict:
    result = await mine_metrics_and_dimensions(connection_path)

    mined_metric_names = {c.metric.name for c in result.get("metric_candidates", [])}
    mined_dim_names = {c.dimension.name for c in result.get("dimension_candidates", [])}

    metric_candidates_out = [
        {
            "metric": c.metric.model_dump(mode="json"),
            "confidence": c.confidence,
            "source": c.source,
            "evidence": c.evidence,
        }
        for c in result.get("metric_candidates", [])
    ]
    dimension_candidates_out = [
        {
            "dimension": c.dimension.model_dump(mode="json"),
            "confidence": c.confidence,
            "source": c.source,
            "evidence": c.evidence,
            "category": c.category,
        }
        for c in result.get("dimension_candidates", [])
    ]

    metrics_catalog = load_metrics(connection, connection_path=connection_path)
    for metric in metrics_catalog.candidates():
        if metric.name not in mined_metric_names:
            metric_candidates_out.append(
                {
                    "metric": metric.model_dump(mode="json"),
                    "confidence": 0.6,
                    "source": "catalog",
                    "evidence": [],
                }
            )

    dimensions_catalog = load_dimensions(connection, connection_path=connection_path)
    for dimension in dimensions_catalog.candidates():
        if dimension.name not in mined_dim_names:
            dimension_candidates_out.append(
                {
                    "dimension": dimension.model_dump(mode="json"),
                    "confidence": 0.6,
                    "source": "catalog",
                    "evidence": [],
                    "category": "Other",
                }
            )

    return {
        "metricCandidates": metric_candidates_out,
        "dimensionCandidates": dimension_candidates_out,
    }


def list_approved_metrics(connection: str, *, connection_path: Path) -> dict:
    metrics_catalog = load_metrics(connection, connection_path=connection_path)
    dimensions_catalog = load_dimensions(connection, connection_path=connection_path)

    approved_metrics = metrics_catalog.approved()
    approved_dimensions = dimensions_catalog.approved()

    return {
        "metrics": [metric.model_dump(mode="json") for metric in approved_metrics],
        "dimensions": [dimension.model_dump(mode="json") for dimension in approved_dimensions],
        "metricCount": len(approved_metrics),
        "dimensionCount": len(approved_dimensions),
    }


def add_metric_definition(connection: str, data: dict, *, connection_path: Path) -> dict:
    result = add_metric(
        provider_id=connection,
        name=data["name"],
        description=data.get("description", ""),
        sql=data.get("sql", ""),
        connection_path=connection_path,
        display_name=data.get("display_name"),
        tables=data.get("tables", []),
        parameters=data.get("parameters", []),
        tags=data.get("tags", []),
        dimensions=data.get("dimensions", []),
        notes=data.get("notes"),
        status=data.get("status", "approved"),
    )

    if result.get("added"):
        return {
            "success": True,
            "name": data["name"],
            "type": "metric",
            "filePath": result.get("file_path", ""),
        }

    return {"success": False, "error": result.get("error", "Failed to add")}


def add_dimension_definition(connection: str, data: dict, *, connection_path: Path) -> dict:
    result = add_dimension(
        provider_id=connection,
        name=data["name"],
        column=data.get("column", ""),
        connection_path=connection_path,
        description=data.get("description", ""),
        display_name=data.get("display_name"),
        dim_type=data.get("type", "categorical"),
        tables=data.get("tables", []),
        values=data.get("values", []),
        synonyms=data.get("synonyms", []),
        status=data.get("status", "approved"),
    )

    if result.get("added"):
        return {
            "success": True,
            "name": data["name"],
            "type": "dimension",
            "filePath": result.get("file_path", ""),
        }

    return {"success": False, "error": result.get("error", "Failed to add")}


def update_metric_definition(
    connection: str, name: str, data: dict, *, connection_path: Path
) -> dict:
    delete_metric(connection, name, connection_path=connection_path)
    new_name = data.get("name", name)
    result = add_metric(
        provider_id=connection,
        name=new_name,
        description=data.get("description", ""),
        sql=data.get("sql", ""),
        connection_path=connection_path,
        display_name=data.get("display_name"),
        tables=data.get("tables", []),
        parameters=data.get("parameters", []),
        tags=data.get("tags", []),
        dimensions=data.get("dimensions", []),
        notes=data.get("notes"),
        status=data.get("status", "approved"),
    )

    if result.get("added"):
        return {"success": True, "name": new_name, "type": "metric"}

    return {"success": False, "error": result.get("error", "Failed to update")}


def update_dimension_definition(
    connection: str, name: str, data: dict, *, connection_path: Path
) -> dict:
    delete_dimension(connection, name, connection_path=connection_path)
    new_name = data.get("name", name)
    result = add_dimension(
        provider_id=connection,
        name=new_name,
        column=data.get("column", ""),
        connection_path=connection_path,
        description=data.get("description", ""),
        display_name=data.get("display_name"),
        dim_type=data.get("type", "categorical"),
        tables=data.get("tables", []),
        values=data.get("values", []),
        synonyms=data.get("synonyms", []),
    )

    if result.get("added"):
        return {"success": True, "name": new_name, "type": "dimension"}

    return {"success": False, "error": result.get("error", "Failed to update")}


def delete_metric_definition(connection: str, name: str, *, connection_path: Path) -> dict:
    result = delete_metric(connection, name, connection_path=connection_path)
    if result.get("deleted"):
        return {"success": True, "name": name, "type": "metric"}
    return {"success": False, "error": result.get("error", "Not found")}


def delete_dimension_definition(connection: str, name: str, *, connection_path: Path) -> dict:
    result = delete_dimension(connection, name, connection_path=connection_path)
    if result.get("deleted"):
        return {"success": True, "name": name, "type": "dimension"}
    return {"success": False, "error": result.get("error", "Not found")}


def approve_metric_candidate(connection: str, data: dict, *, connection_path: Path) -> dict:
    approved_data = dict(data)
    approved_data["created_by"] = "approved"
    approved_data["status"] = "approved"
    return add_metric_definition(connection, approved_data, connection_path=connection_path)


def approve_dimension_candidate(connection: str, data: dict, *, connection_path: Path) -> dict:
    approved_data = dict(data)
    approved_data["created_by"] = "approved"
    approved_data["status"] = "approved"
    return add_dimension_definition(connection, approved_data, connection_path=connection_path)
