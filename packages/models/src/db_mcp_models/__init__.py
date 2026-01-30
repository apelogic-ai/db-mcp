"""Shared Pydantic models for db-mcp."""

from db_mcp_models.gaps import GapSource, GapStatus, KnowledgeGap, KnowledgeGaps
from db_mcp_models.metrics import (
    Dimension,
    DimensionCandidate,
    DimensionsCatalog,
    DimensionType,
    Metric,
    MetricCandidate,
    MetricParameter,
    MetricsCatalog,
)
from db_mcp_models.onboarding import (
    ColumnDescription,
    OnboardingPhase,
    OnboardingState,
    SchemaDescriptions,
    TableDescription,
    TableDescriptionStatus,
)
from db_mcp_models.plan import PlanStep, QueryPlan
from db_mcp_models.query import QueryMetadata, QueryResult
from db_mcp_models.task import Task, TaskStatus
from db_mcp_models.training import (
    CandidateRule,
    FeedbackLog,
    FeedbackType,
    PromptInstructions,
    QueryExample,
    QueryExamples,
    QueryFeedback,
)
from db_mcp_models.ui import ChartSpec, ColumnSpec, GridSpec

__version__ = "0.1.0"

__all__ = [
    # Knowledge Gaps
    "KnowledgeGap",
    "KnowledgeGaps",
    "GapStatus",
    "GapSource",
    # Task
    "Task",
    "TaskStatus",
    # Plan
    "QueryPlan",
    "PlanStep",
    # Query
    "QueryResult",
    "QueryMetadata",
    # UI
    "GridSpec",
    "ColumnSpec",
    "ChartSpec",
    # Onboarding
    "OnboardingState",
    "OnboardingPhase",
    # Schema Descriptions
    "SchemaDescriptions",
    "TableDescription",
    "TableDescriptionStatus",
    "ColumnDescription",
    # Training
    "QueryExample",
    "QueryExamples",
    "QueryFeedback",
    "FeedbackLog",
    "FeedbackType",
    "CandidateRule",
    "PromptInstructions",
    # Metrics
    "Metric",
    "MetricParameter",
    "MetricsCatalog",
    # Dimensions
    "Dimension",
    "DimensionType",
    "DimensionsCatalog",
    # Candidates
    "MetricCandidate",
    "DimensionCandidate",
]
