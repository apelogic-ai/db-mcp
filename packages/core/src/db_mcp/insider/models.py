"""Core insider-agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


EventType = Literal["new_connection"]
ReviewKind = Literal["schema_descriptions", "canonical_examples", "canonical_domain_model"]


class ExampleCandidate(BaseModel):
    """Structured example proposal from the insider provider."""

    slug: str = Field(..., description="Stable filename slug")
    natural_language: str = Field(..., description="Human question or intent")
    sql: str = Field(..., description="SQL text")
    tables: list[str] = Field(default_factory=list, description="Tables referenced by the query")
    notes: str | None = Field(default=None, description="Optional notes")
    tags: list[str] = Field(default_factory=list, description="Optional tags")


class ColumnDescriptionUpdate(BaseModel):
    """Column description update proposal."""

    name: str
    description: str


class TableDescriptionUpdate(BaseModel):
    """Table description proposal."""

    table_full_name: str
    description: str
    columns: list[ColumnDescriptionUpdate] = Field(default_factory=list)


class ReviewItemProposal(BaseModel):
    """Proposal that affects canonical serving artifacts."""

    kind: ReviewKind
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)


class InsiderProposalBundle(BaseModel):
    """Structured output returned by the insider model provider."""

    draft_domain_model_markdown: str | None = None
    description_updates: list[TableDescriptionUpdate] = Field(default_factory=list)
    example_candidates: list[ExampleCandidate] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    review_items: list[ReviewItemProposal] = Field(default_factory=list)


class ProviderRequest(BaseModel):
    """Prepared request for a concrete provider."""

    system_prompt: str
    user_prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    """Normalized provider response."""

    raw_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InsiderRunRequest(BaseModel):
    """Deterministic context passed to the provider layer."""

    connection: str
    connection_path: str
    schema_digest: str
    event_type: EventType
    event_payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class AgentEvent:
    """Pending insider-agent observation."""

    event_id: str
    connection: str
    event_type: EventType
    schema_digest: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now)
    status: str = "pending"


@dataclass(slots=True)
class ReviewDecision:
    """Review action taken by an operator."""

    review_id: str
    status: Literal["approved", "rejected", "stale"]
    reason: str | None = None

