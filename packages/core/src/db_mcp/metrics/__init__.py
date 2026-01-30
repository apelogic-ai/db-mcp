"""Metrics and dimensions layer for db-mcp.

Provides storage and retrieval of business metric and dimension definitions.
"""

from db_mcp.metrics.store import (
    add_dimension,
    add_metric,
    delete_dimension,
    delete_metric,
    get_dimension,
    get_metric,
    get_metrics_dir,
    load_dimensions,
    load_metrics,
    save_dimensions,
    save_metrics,
    search_dimensions,
    search_metrics,
)

__all__ = [
    "get_metrics_dir",
    # Metrics
    "load_metrics",
    "save_metrics",
    "get_metric",
    "add_metric",
    "delete_metric",
    "search_metrics",
    # Dimensions
    "load_dimensions",
    "save_dimensions",
    "get_dimension",
    "add_dimension",
    "delete_dimension",
    "search_dimensions",
]
