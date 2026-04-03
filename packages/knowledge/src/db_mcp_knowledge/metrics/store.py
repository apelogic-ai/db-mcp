"""Metrics and dimensions persistence - catalog storage and retrieval.

Metrics are stored in metrics/catalog.yaml within each connection directory.
Dimensions are stored in metrics/dimensions.yaml.
"""

from datetime import UTC, datetime
from pathlib import Path

import yaml
from db_mcp_models import (
    Dimension,
    DimensionsCatalog,
    DimensionType,
    Metric,
    MetricBinding,
    MetricBindingsCatalog,
    MetricDimensionBinding,
    MetricParameter,
    MetricsCatalog,
)


def get_metrics_dir(provider_id: str, *, connection_path: Path) -> Path:
    """Get path to metrics directory."""
    return Path(connection_path) / "metrics"


def get_catalog_file_path(provider_id: str, *, connection_path: Path) -> Path:
    """Get path to metrics catalog file."""
    return get_metrics_dir(provider_id, connection_path=connection_path) / "catalog.yaml"


def get_bindings_file_path(provider_id: str, *, connection_path: Path) -> Path:
    """Get path to metrics bindings file."""
    return get_metrics_dir(provider_id, connection_path=connection_path) / "bindings.yaml"


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
        dimensions=data.get("dimensions", []),
        notes=data.get("notes"),
        status=data.get("status", "approved"),
        created_at=created_at,
        created_by=data.get("created_by"),
    )


def _metric_to_dict(metric: Metric) -> dict:
    """Convert Metric to dict for YAML storage."""
    result = {
        "name": metric.name,
        "description": metric.description,
    }

    if metric.sql:
        result["sql"] = metric.sql

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

    if metric.dimensions:
        result["dimensions"] = metric.dimensions

    if metric.notes:
        result["notes"] = metric.notes

    if metric.created_at:
        result["created_at"] = metric.created_at.isoformat()

    if metric.status and metric.status != "approved":
        result["status"] = metric.status

    if metric.created_by:
        result["created_by"] = metric.created_by

    return result


def load_metrics(
    provider_id: str,
    *,
    connection_path: Path,
) -> MetricsCatalog:
    """Load metrics catalog from YAML file.

    Args:
        provider_id: Provider identifier
        connection_path: Connection directory path (required, keyword-only).

    Returns:
        MetricsCatalog (empty if file doesn't exist)
    """
    catalog_file = get_catalog_file_path(provider_id, connection_path=connection_path)

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


def _metric_dimension_binding_from_dict(name: str, data: dict) -> MetricDimensionBinding:
    """Convert dict to MetricDimensionBinding model."""
    return MetricDimensionBinding(
        dimension_name=data.get("dimension_name", name),
        projection_sql=data.get("projection_sql", data.get("column", "")),
        filter_sql=data.get("filter_sql"),
        group_by_sql=data.get("group_by_sql"),
        tables=data.get("tables", []),
    )


def _metric_binding_from_dict(metric_name: str, data: dict) -> MetricBinding:
    """Convert dict to MetricBinding model."""
    dimensions = {
        name: _metric_dimension_binding_from_dict(name, binding_data)
        for name, binding_data in data.get("dimensions", {}).items()
        if isinstance(binding_data, dict)
    }

    tables = data.get("tables")
    if tables is None:
        single_table = data.get("table")
        tables = [single_table] if single_table else []

    return MetricBinding(
        metric_name=data.get("metric_name", metric_name),
        sql=data.get("sql", data.get("dialect_sql", "")),
        tables=tables,
        dimensions=dimensions,
    )


def load_metric_bindings(
    provider_id: str,
    *,
    connection_path: Path,
) -> MetricBindingsCatalog:
    """Load connection-specific metric bindings from YAML file."""
    bindings_file = get_bindings_file_path(provider_id, connection_path=connection_path)

    if not bindings_file.exists():
        return MetricBindingsCatalog(provider_id=provider_id)

    try:
        with open(bindings_file) as f:
            data = yaml.safe_load(f)

        if not data:
            return MetricBindingsCatalog(provider_id=provider_id)

        bindings = {
            metric_name: _metric_binding_from_dict(metric_name, binding_data)
            for metric_name, binding_data in data.get("bindings", {}).items()
            if isinstance(binding_data, dict)
        }

        return MetricBindingsCatalog(
            version=data.get("version", "1.0.0"),
            provider_id=provider_id,
            bindings=bindings,
        )
    except Exception:
        return MetricBindingsCatalog(provider_id=provider_id)


def _metric_dimension_binding_to_dict(binding: MetricDimensionBinding) -> dict:
    """Convert MetricDimensionBinding to dict for YAML storage."""
    result = {
        "dimension_name": binding.dimension_name,
        "projection_sql": binding.projection_sql,
    }
    if binding.filter_sql:
        result["filter_sql"] = binding.filter_sql
    if binding.group_by_sql:
        result["group_by_sql"] = binding.group_by_sql
    if binding.tables:
        result["tables"] = binding.tables
    return result


def _metric_binding_to_dict(binding: MetricBinding) -> dict:
    """Convert MetricBinding to dict for YAML storage."""
    result = {
        "metric_name": binding.metric_name,
        "sql": binding.sql,
    }
    if binding.tables:
        result["tables"] = binding.tables
    if binding.dimensions:
        result["dimensions"] = {
            name: _metric_dimension_binding_to_dict(dimension_binding)
            for name, dimension_binding in binding.dimensions.items()
        }
    return result


def save_metric_bindings(catalog: MetricBindingsCatalog, *, connection_path: Path) -> dict:
    """Save connection-specific metric bindings to YAML file."""
    try:
        metrics_dir = get_metrics_dir(catalog.provider_id, connection_path=connection_path)
        metrics_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": catalog.version,
            "provider_id": catalog.provider_id,
            "bindings": {
                metric_name: _metric_binding_to_dict(binding)
                for metric_name, binding in catalog.bindings.items()
            },
        }

        bindings_file = get_bindings_file_path(
            catalog.provider_id, connection_path=connection_path
        )
        with open(bindings_file, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        return {"saved": True, "file_path": str(bindings_file), "error": None}
    except Exception as e:
        return {"saved": False, "file_path": None, "error": str(e)}


def upsert_metric_binding(
    provider_id: str, binding: MetricBinding, *, connection_path: Path
) -> dict:
    """Add or update a metric binding for a connection."""
    catalog = load_metric_bindings(provider_id, connection_path=connection_path)
    catalog.bindings[binding.metric_name] = binding
    result = save_metric_bindings(catalog, connection_path=connection_path)
    if result["saved"]:
        return {
            "saved": True,
            "metric_name": binding.metric_name,
            "file_path": result["file_path"],
        }
    return {"saved": False, "metric_name": binding.metric_name, "error": result["error"]}


def save_metrics(catalog: MetricsCatalog, *, connection_path: Path) -> dict:
    """Save metrics catalog to YAML file.

    Args:
        catalog: MetricsCatalog to save
        connection_path: Connection directory path (required, keyword-only).

    Returns:
        Dict with save status
    """
    try:
        metrics_dir = get_metrics_dir(catalog.provider_id, connection_path=connection_path)
        metrics_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": catalog.version,
            "provider_id": catalog.provider_id,
            "metrics": [_metric_to_dict(m) for m in catalog.metrics],
        }

        catalog_file = get_catalog_file_path(
            catalog.provider_id, connection_path=connection_path
        )
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


def get_metric(provider_id: str, name: str, *, connection_path: Path) -> Metric | None:
    """Get a metric by name.

    Args:
        provider_id: Provider identifier
        name: Metric name
        connection_path: Connection directory path (required, keyword-only).

    Returns:
        Metric if found, None otherwise
    """
    catalog = load_metrics(provider_id, connection_path=connection_path)
    return catalog.get_metric(name)


def add_metric(
    provider_id: str,
    name: str,
    description: str,
    sql: str,
    *,
    connection_path: Path,
    display_name: str | None = None,
    tables: list[str] | None = None,
    parameters: list[dict] | None = None,
    tags: list[str] | None = None,
    dimensions: list[str] | None = None,
    notes: str | None = None,
    status: str = "approved",
) -> dict:
    """Add a new metric to the catalog.

    Args:
        provider_id: Provider identifier
        name: Metric identifier
        description: What the metric measures
        sql: SQL template
        connection_path: Connection directory path (required, keyword-only).
        display_name: Human-readable name
        tables: Tables used
        parameters: SQL template parameters
        tags: Categorization tags
        dimensions: Dimension names this metric can be sliced by
        notes: Additional notes

    Returns:
        Dict with status
    """
    catalog = load_metrics(provider_id, connection_path=connection_path)

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
        dimensions=dimensions or [],
        notes=notes,
        status=status,
        created_at=datetime.now(UTC),
    )

    catalog.add_metric(metric)
    result = save_metrics(catalog, connection_path=connection_path)

    if result["saved"]:
        return {
            "added": True,
            "metric_name": name,
            "total_metrics": catalog.count(),
            "file_path": result["file_path"],
        }
    else:
        return {"added": False, "error": result["error"]}


def delete_metric(provider_id: str, name: str, *, connection_path: Path) -> dict:
    """Delete a metric from the catalog.

    Args:
        provider_id: Provider identifier
        name: Metric name to delete
        connection_path: Connection directory path (required, keyword-only).

    Returns:
        Dict with status
    """
    catalog = load_metrics(provider_id, connection_path=connection_path)

    if not catalog.remove_metric(name):
        return {"deleted": False, "error": f"Metric '{name}' not found"}

    result = save_metrics(catalog, connection_path=connection_path)

    if result["saved"]:
        return {
            "deleted": True,
            "metric_name": name,
            "total_metrics": catalog.count(),
        }
    else:
        return {"deleted": False, "error": result["error"]}


def search_metrics(provider_id: str, query: str, *, connection_path: Path) -> list[Metric]:
    """Search metrics by name, description, or tags.

    Args:
        provider_id: Provider identifier
        query: Search query
        connection_path: Connection directory path (required, keyword-only).

    Returns:
        List of matching metrics
    """
    catalog = load_metrics(provider_id, connection_path=connection_path)
    return catalog.search(query)


# =============================================================================
# Dimensions — Load / Save
# =============================================================================


def get_dimensions_file_path(provider_id: str, *, connection_path: Path) -> Path:
    """Get path to dimensions catalog file."""
    return get_metrics_dir(provider_id, connection_path=connection_path) / "dimensions.yaml"


def _dimension_from_dict(data: dict) -> Dimension:
    """Convert dict to Dimension model."""
    created_at = None
    if data.get("created_at"):
        try:
            if isinstance(data["created_at"], datetime):
                created_at = data["created_at"]
            else:
                created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = None

    dim_type = DimensionType.CATEGORICAL
    raw_type = data.get("type")
    if raw_type:
        try:
            dim_type = DimensionType(raw_type)
        except ValueError:
            pass

    return Dimension(
        name=data.get("name", ""),
        display_name=data.get("display_name"),
        description=data.get("description", ""),
        type=dim_type,
        column=data.get("column", ""),
        tables=data.get("tables", []),
        values=data.get("values", []),
        synonyms=data.get("synonyms", []),
        status=data.get("status", "approved"),
        created_at=created_at,
        created_by=data.get("created_by"),
    )


def _dimension_to_dict(dimension: Dimension) -> dict:
    """Convert Dimension to dict for YAML storage."""
    result: dict = {
        "name": dimension.name,
        "description": dimension.description,
        "type": dimension.type.value,
        "column": dimension.column,
    }

    if dimension.display_name:
        result["display_name"] = dimension.display_name

    if dimension.tables:
        result["tables"] = dimension.tables

    if dimension.values:
        result["values"] = dimension.values

    if dimension.synonyms:
        result["synonyms"] = dimension.synonyms

    if dimension.status and dimension.status != "approved":
        result["status"] = dimension.status

    if dimension.created_at:
        result["created_at"] = dimension.created_at.isoformat()

    if dimension.created_by:
        result["created_by"] = dimension.created_by

    return result


def load_dimensions(
    provider_id: str,
    *,
    connection_path: Path,
) -> DimensionsCatalog:
    """Load dimensions catalog from YAML file."""
    dim_file = get_dimensions_file_path(provider_id, connection_path=connection_path)

    if not dim_file.exists():
        return DimensionsCatalog(provider_id=provider_id)

    try:
        with open(dim_file) as f:
            data = yaml.safe_load(f)

        if not data:
            return DimensionsCatalog(provider_id=provider_id)

        dimensions = [_dimension_from_dict(d) for d in data.get("dimensions", [])]

        return DimensionsCatalog(
            version=data.get("version", "1.0.0"),
            provider_id=provider_id,
            dimensions=dimensions,
        )
    except Exception:
        return DimensionsCatalog(provider_id=provider_id)


def save_dimensions(catalog: DimensionsCatalog, *, connection_path: Path) -> dict:
    """Save dimensions catalog to YAML file."""
    try:
        metrics_dir = get_metrics_dir(catalog.provider_id, connection_path=connection_path)
        metrics_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": catalog.version,
            "provider_id": catalog.provider_id,
            "dimensions": [_dimension_to_dict(d) for d in catalog.dimensions],
        }

        dim_file = get_dimensions_file_path(
            catalog.provider_id, connection_path=connection_path
        )
        with open(dim_file, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        return {"saved": True, "file_path": str(dim_file), "error": None}
    except Exception as e:
        return {"saved": False, "file_path": None, "error": str(e)}


# =============================================================================
# Dimensions — CRUD Operations
# =============================================================================


def get_dimension(provider_id: str, name: str, *, connection_path: Path) -> Dimension | None:
    """Get a dimension by name."""
    catalog = load_dimensions(provider_id, connection_path=connection_path)
    return catalog.get_dimension(name)


def add_dimension(
    provider_id: str,
    name: str,
    column: str,
    *,
    connection_path: Path,
    description: str = "",
    display_name: str | None = None,
    dim_type: str = "categorical",
    tables: list[str] | None = None,
    values: list[str] | None = None,
    synonyms: list[str] | None = None,
    status: str = "approved",
) -> dict:
    """Add a new dimension to the catalog."""
    catalog = load_dimensions(provider_id, connection_path=connection_path)

    try:
        dtype = DimensionType(dim_type)
    except ValueError:
        dtype = DimensionType.CATEGORICAL

    dimension = Dimension(
        name=name,
        display_name=display_name,
        description=description,
        type=dtype,
        column=column,
        tables=tables or [],
        values=values or [],
        synonyms=synonyms or [],
        status=status,
        created_at=datetime.now(UTC),
        created_by="manual",
    )

    catalog.add_dimension(dimension)
    result = save_dimensions(catalog, connection_path=connection_path)

    if result["saved"]:
        return {
            "added": True,
            "dimension_name": name,
            "total_dimensions": catalog.count(),
            "file_path": result["file_path"],
        }
    else:
        return {"added": False, "error": result["error"]}


def delete_dimension(provider_id: str, name: str, *, connection_path: Path) -> dict:
    """Delete a dimension from the catalog."""
    catalog = load_dimensions(provider_id, connection_path=connection_path)

    if not catalog.remove_dimension(name):
        return {"deleted": False, "error": f"Dimension '{name}' not found"}

    result = save_dimensions(catalog, connection_path=connection_path)

    if result["saved"]:
        return {
            "deleted": True,
            "dimension_name": name,
            "total_dimensions": catalog.count(),
        }
    else:
        return {"deleted": False, "error": result["error"]}


def search_dimensions(provider_id: str, query: str, *, connection_path: Path) -> list[Dimension]:
    """Search dimensions by name, description, or synonyms."""
    catalog = load_dimensions(provider_id, connection_path=connection_path)
    return catalog.search(query)
