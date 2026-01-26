"""Metrics persistence - catalog storage and retrieval.

Metrics are stored in metrics/catalog.yaml within each connection directory.
"""

from datetime import UTC, datetime
from pathlib import Path

import yaml
from db_mcp_models import Metric, MetricParameter, MetricsCatalog

from db_mcp.onboarding.state import get_provider_dir


def get_metrics_dir(provider_id: str) -> Path:
    """Get path to metrics directory."""
    return get_provider_dir(provider_id) / "metrics"


def get_catalog_file_path(provider_id: str) -> Path:
    """Get path to metrics catalog file."""
    return get_metrics_dir(provider_id) / "catalog.yaml"


# =============================================================================
# Load / Save
# =============================================================================


def _metric_from_dict(data: dict) -> Metric:
    """Convert dict to Metric model."""
    # Handle parameters
    parameters = []
    for p in data.get("parameters", []):
        if isinstance(p, dict):
            parameters.append(MetricParameter(**p))
        elif isinstance(p, MetricParameter):
            parameters.append(p)

    # Handle created_at
    created_at = None
    if data.get("created_at"):
        try:
            if isinstance(data["created_at"], datetime):
                created_at = data["created_at"]
            else:
                created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = None

    return Metric(
        name=data.get("name", ""),
        display_name=data.get("display_name"),
        description=data.get("description", ""),
        sql=data.get("sql", ""),
        tables=data.get("tables", []),
        parameters=parameters,
        tags=data.get("tags", []),
        notes=data.get("notes"),
        created_at=created_at,
        created_by=data.get("created_by"),
    )


def _metric_to_dict(metric: Metric) -> dict:
    """Convert Metric to dict for YAML storage."""
    result = {
        "name": metric.name,
        "description": metric.description,
        "sql": metric.sql,
    }

    if metric.display_name:
        result["display_name"] = metric.display_name

    if metric.tables:
        result["tables"] = metric.tables

    if metric.parameters:
        result["parameters"] = [
            {
                "name": p.name,
                "type": p.type,
                "required": p.required,
                **({"default": p.default} if p.default else {}),
                **({"description": p.description} if p.description else {}),
            }
            for p in metric.parameters
        ]

    if metric.tags:
        result["tags"] = metric.tags

    if metric.notes:
        result["notes"] = metric.notes

    if metric.created_at:
        result["created_at"] = metric.created_at.isoformat()

    if metric.created_by:
        result["created_by"] = metric.created_by

    return result


def load_metrics(provider_id: str) -> MetricsCatalog:
    """Load metrics catalog from YAML file.

    Args:
        provider_id: Provider identifier

    Returns:
        MetricsCatalog (empty if file doesn't exist)
    """
    catalog_file = get_catalog_file_path(provider_id)

    if not catalog_file.exists():
        return MetricsCatalog(provider_id=provider_id)

    try:
        with open(catalog_file) as f:
            data = yaml.safe_load(f)

        if not data:
            return MetricsCatalog(provider_id=provider_id)

        metrics = [_metric_from_dict(m) for m in data.get("metrics", [])]

        return MetricsCatalog(
            version=data.get("version", "1.0.0"),
            provider_id=provider_id,
            metrics=metrics,
        )
    except Exception:
        return MetricsCatalog(provider_id=provider_id)


def save_metrics(catalog: MetricsCatalog) -> dict:
    """Save metrics catalog to YAML file.

    Args:
        catalog: MetricsCatalog to save

    Returns:
        Dict with save status
    """
    try:
        metrics_dir = get_metrics_dir(catalog.provider_id)
        metrics_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": catalog.version,
            "provider_id": catalog.provider_id,
            "metrics": [_metric_to_dict(m) for m in catalog.metrics],
        }

        catalog_file = get_catalog_file_path(catalog.provider_id)
        with open(catalog_file, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        return {"saved": True, "file_path": str(catalog_file), "error": None}
    except Exception as e:
        return {"saved": False, "file_path": None, "error": str(e)}


# =============================================================================
# CRUD Operations
# =============================================================================


def get_metric(provider_id: str, name: str) -> Metric | None:
    """Get a metric by name.

    Args:
        provider_id: Provider identifier
        name: Metric name

    Returns:
        Metric if found, None otherwise
    """
    catalog = load_metrics(provider_id)
    return catalog.get_metric(name)


def add_metric(
    provider_id: str,
    name: str,
    description: str,
    sql: str,
    display_name: str | None = None,
    tables: list[str] | None = None,
    parameters: list[dict] | None = None,
    tags: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Add a new metric to the catalog.

    Args:
        provider_id: Provider identifier
        name: Metric identifier
        description: What the metric measures
        sql: SQL template
        display_name: Human-readable name
        tables: Tables used
        parameters: SQL template parameters
        tags: Categorization tags
        notes: Additional notes

    Returns:
        Dict with status
    """
    catalog = load_metrics(provider_id)

    # Convert parameter dicts to MetricParameter
    params = []
    if parameters:
        for p in parameters:
            if isinstance(p, dict):
                params.append(MetricParameter(**p))
            elif isinstance(p, MetricParameter):
                params.append(p)

    metric = Metric(
        name=name,
        display_name=display_name,
        description=description,
        sql=sql,
        tables=tables or [],
        parameters=params,
        tags=tags or [],
        notes=notes,
        created_at=datetime.now(UTC),
    )

    catalog.add_metric(metric)
    result = save_metrics(catalog)

    if result["saved"]:
        return {
            "added": True,
            "metric_name": name,
            "total_metrics": catalog.count(),
            "file_path": result["file_path"],
        }
    else:
        return {"added": False, "error": result["error"]}


def delete_metric(provider_id: str, name: str) -> dict:
    """Delete a metric from the catalog.

    Args:
        provider_id: Provider identifier
        name: Metric name to delete

    Returns:
        Dict with status
    """
    catalog = load_metrics(provider_id)

    if not catalog.remove_metric(name):
        return {"deleted": False, "error": f"Metric '{name}' not found"}

    result = save_metrics(catalog)

    if result["saved"]:
        return {
            "deleted": True,
            "metric_name": name,
            "total_metrics": catalog.count(),
        }
    else:
        return {"deleted": False, "error": result["error"]}


def search_metrics(provider_id: str, query: str) -> list[Metric]:
    """Search metrics by name, description, or tags.

    Args:
        provider_id: Provider identifier
        query: Search query

    Returns:
        List of matching metrics
    """
    catalog = load_metrics(provider_id)
    return catalog.search(query)
