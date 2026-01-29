"""Knowledge gap models for tracking unmapped business terms."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class GapStatus(str, Enum):
    """Status of a knowledge gap."""

    OPEN = "open"
    RESOLVED = "resolved"


class GapSource(str, Enum):
    """How the gap was detected."""

    SCHEMA_SCAN = "schema_scan"
    TRACES = "traces"


class KnowledgeGap(BaseModel):
    """A single knowledge gap — an unmapped business term or abbreviation."""

    id: str = Field(..., description="Unique gap ID")
    term: str = Field(..., description="The unmapped term")
    group_id: str | None = Field(default=None, description="Groups related terms together")
    status: GapStatus = Field(default=GapStatus.OPEN, description="open or resolved")
    source: GapSource = Field(..., description="How this gap was detected")
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    context: str | None = Field(default=None, description="How the gap was detected")
    related_columns: list[str] = Field(
        default_factory=list, description="Schema columns related to this term"
    )
    suggested_rule: str | None = Field(
        default=None, description="Suggested business rule synonym string"
    )
    resolved_at: datetime | None = Field(default=None)
    resolved_by: str | None = Field(
        default=None, description="How it was resolved: business_rules, schema_description, manual"
    )


class KnowledgeGaps(BaseModel):
    """Collection of knowledge gaps (knowledge_gaps.yaml)."""

    version: str = Field(default="1.0.0")
    provider_id: str = Field(..., description="Provider identifier")
    gaps: list[KnowledgeGap] = Field(default_factory=list)

    def get_gap(self, gap_id: str) -> KnowledgeGap | None:
        """Get gap by ID."""
        for g in self.gaps:
            if g.id == gap_id:
                return g
        return None

    def get_open(self) -> list[KnowledgeGap]:
        """Get all open gaps."""
        return [g for g in self.gaps if g.status == GapStatus.OPEN]

    def get_resolved(self) -> list[KnowledgeGap]:
        """Get all resolved gaps."""
        return [g for g in self.gaps if g.status == GapStatus.RESOLVED]

    def has_term(self, term: str) -> bool:
        """Check if a term already exists (case-insensitive)."""
        term_lower = term.lower()
        return any(g.term.lower() == term_lower for g in self.gaps)

    def add_gap(self, gap: KnowledgeGap) -> None:
        """Add a gap, deduplicating by term (case-insensitive)."""
        if not self.has_term(gap.term):
            self.gaps.append(gap)

    def resolve(self, gap_id: str, resolved_by: str) -> bool:
        """Mark a gap as resolved. Returns True if found and updated."""
        gap = self.get_gap(gap_id)
        if gap and gap.status == GapStatus.OPEN:
            gap.status = GapStatus.RESOLVED
            gap.resolved_at = datetime.now(UTC)
            gap.resolved_by = resolved_by
            return True
        return False

    def stats(self) -> dict[str, int]:
        """Return summary stats."""
        open_count = len(self.get_open())
        resolved_count = len(self.get_resolved())
        return {
            "total": len(self.gaps),
            "open": open_count,
            "resolved": resolved_count,
        }
