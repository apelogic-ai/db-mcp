"""Metrics layer models for db-mcp.

Metrics provide canonical definitions for business KPIs like DAU, revenue, retention.
Dimensions provide the axes along which metrics can be sliced (time, category, geography).
They enable consistent SQL generation across sessions.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# =============================================================================
# Enums
# =============================================================================


class DimensionType(str, Enum):
    """Classification of dimension columns."""

    TEMPORAL = "temporal"  # date, timestamp
    CATEGORICAL = "categorical"  # carrier, venue_type
    GEOGRAPHIC = "geographic"  # city, state, zip
    ENTITY = "entity"  # subscriber_id, nas_id


# =============================================================================
# Metric models
# =============================================================================


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
    dimensions: list[str] = Field(
        default_factory=list, description="Dimension names this metric can be sliced by"
    )
    notes: str | None = Field(default=None, description="Additional notes or gotchas")
    status: str = Field(
        default="approved",
        description="Lifecycle status: 'candidate' (discovered, needs review) or 'approved' (verified, in catalog)",
    )
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

    def approved(self) -> list[Metric]:
        """Return only approved metrics (status != 'candidate')."""
        return [m for m in self.metrics if m.status != "candidate"]

    def candidates(self) -> list[Metric]:
        """Return only candidate metrics (status == 'candidate')."""
        return [m for m in self.metrics if m.status == "candidate"]

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


# =============================================================================
# Dimension models
# =============================================================================


class Dimension(BaseModel):
    """A single dimension definition — an axis for slicing metrics."""

    name: str = Field(..., description="Dimension identifier (e.g., 'carrier')")
    display_name: str | None = Field(default=None, description="Human-readable name")
    description: str = Field(default="", description="What this dimension represents")
    type: DimensionType = Field(
        default=DimensionType.CATEGORICAL, description="Dimension classification"
    )
    column: str = Field(..., description="Column reference (e.g., 'cdr_agg_day.carrier')")
    tables: list[str] = Field(
        default_factory=list, description="Tables where this dimension exists"
    )
    values: list[str] = Field(
        default_factory=list, description="Known values (e.g., ['tmo', 'helium_mobile'])"
    )
    synonyms: list[str] = Field(
        default_factory=list, description="Alternative names from business rules"
    )
    status: str = Field(
        default="approved",
        description="Lifecycle status: 'candidate' (discovered, needs review) or 'approved' (verified, in catalog)",
    )
    created_at: datetime | None = Field(default=None, description="When the dimension was created")
    created_by: str | None = Field(
        default=None, description="Origin: 'mined', 'manual', or 'approved'"
    )


class DimensionsCatalog(BaseModel):
    """Collection of dimensions for a connection (metrics/dimensions.yaml)."""

    version: str = Field(default="1.0.0", description="Catalog version")
    provider_id: str = Field(..., description="Connection/provider identifier")
    dimensions: list[Dimension] = Field(default_factory=list, description="List of dimensions")

    def get_dimension(self, name: str) -> Dimension | None:
        """Get a dimension by name."""
        for d in self.dimensions:
            if d.name == name:
                return d
        return None

    def add_dimension(self, dimension: Dimension) -> None:
        """Add or update a dimension."""
        self.dimensions = [d for d in self.dimensions if d.name != dimension.name]
        self.dimensions.append(dimension)

    def remove_dimension(self, name: str) -> bool:
        """Remove a dimension by name. Returns True if removed."""
        original_count = len(self.dimensions)
        self.dimensions = [d for d in self.dimensions if d.name != name]
        return len(self.dimensions) < original_count

    def approved(self) -> list[Dimension]:
        """Return only approved dimensions (status != 'candidate')."""
        return [d for d in self.dimensions if d.status != "candidate"]

    def candidates(self) -> list[Dimension]:
        """Return only candidate dimensions (status == 'candidate')."""
        return [d for d in self.dimensions if d.status == "candidate"]

    def count(self) -> int:
        """Return number of dimensions."""
        return len(self.dimensions)

    def list_names(self) -> list[str]:
        """Return list of dimension names."""
        return [d.name for d in self.dimensions]

    def search(self, query: str) -> list[Dimension]:
        """Search dimensions by name, description, or synonyms."""
        query_lower = query.lower()
        results = []
        for d in self.dimensions:
            if (
                query_lower in d.name.lower()
                or query_lower in d.description.lower()
                or (d.display_name and query_lower in d.display_name.lower())
                or any(query_lower in s.lower() for s in d.synonyms)
            ):
                results.append(d)
        return results


# =============================================================================
# Candidate wrappers (for mining results)
# =============================================================================


class MetricCandidate(BaseModel):
    """A metric candidate extracted from vault material."""

    metric: Metric
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score (0-1)")
    source: str = Field(
        default="examples", description="Where it was found: 'examples', 'rules', 'schema'"
    )
    evidence: list[str] = Field(
        default_factory=list, description="Example IDs or rule text supporting this"
    )


class DimensionCandidate(BaseModel):
    """A dimension candidate extracted from vault material."""

    dimension: Dimension
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score (0-1)")
    source: str = Field(
        default="schema", description="Where it was found: 'examples', 'rules', 'schema'"
    )
    evidence: list[str] = Field(
        default_factory=list, description="Column references or rule text supporting this"
    )
    category: str = Field(
        default="Other", description="Semantic category: Location, Time, Device, User, etc."
    )
