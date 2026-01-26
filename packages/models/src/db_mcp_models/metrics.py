"""Metrics layer models for db-mcp.

Metrics provide canonical definitions for business KPIs like DAU, revenue, retention.
They enable consistent SQL generation across sessions.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class MetricParameter(BaseModel):
    """A parameter for a metric SQL template."""

    name: str = Field(..., description="Parameter name (e.g., 'start_date')")
    type: str = Field(default="string", description="Parameter type: string, date, number")
    required: bool = Field(default=True, description="Whether the parameter is required")
    default: str | None = Field(default=None, description="Default value if not provided")
    description: str | None = Field(default=None, description="Description of the parameter")


class Metric(BaseModel):
    """A single metric definition."""

    name: str = Field(..., description="Metric identifier (e.g., 'daily_active_users')")
    display_name: str | None = Field(default=None, description="Human-readable name")
    description: str = Field(..., description="What this metric measures")
    sql: str = Field(..., description="SQL template with {parameter} placeholders")
    tables: list[str] = Field(default_factory=list, description="Tables used by this metric")
    parameters: list[MetricParameter] = Field(
        default_factory=list, description="SQL template parameters"
    )
    tags: list[str] = Field(
        default_factory=list, description="Tags for categorization (e.g., 'engagement', 'kpi')"
    )
    notes: str | None = Field(default=None, description="Additional notes or gotchas")
    created_at: datetime | None = Field(default=None, description="When the metric was created")
    created_by: str | None = Field(default=None, description="Who created the metric")


class MetricsCatalog(BaseModel):
    """Collection of metrics for a connection (metrics/catalog.yaml)."""

    version: str = Field(default="1.0.0", description="Catalog version")
    provider_id: str = Field(..., description="Connection/provider identifier")
    metrics: list[Metric] = Field(default_factory=list, description="List of metrics")

    def get_metric(self, name: str) -> Metric | None:
        """Get a metric by name."""
        for m in self.metrics:
            if m.name == name:
                return m
        return None

    def add_metric(self, metric: Metric) -> None:
        """Add or update a metric."""
        # Remove existing with same name
        self.metrics = [m for m in self.metrics if m.name != metric.name]
        self.metrics.append(metric)

    def remove_metric(self, name: str) -> bool:
        """Remove a metric by name. Returns True if removed."""
        original_count = len(self.metrics)
        self.metrics = [m for m in self.metrics if m.name != name]
        return len(self.metrics) < original_count

    def count(self) -> int:
        """Return number of metrics."""
        return len(self.metrics)

    def list_names(self) -> list[str]:
        """Return list of metric names."""
        return [m.name for m in self.metrics]

    def search(self, query: str) -> list[Metric]:
        """Search metrics by name, description, or tags."""
        query_lower = query.lower()
        results = []
        for m in self.metrics:
            if (
                query_lower in m.name.lower()
                or query_lower in m.description.lower()
                or (m.display_name and query_lower in m.display_name.lower())
                or any(query_lower in tag.lower() for tag in m.tags)
            ):
                results.append(m)
        return results
