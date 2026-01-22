"""Shared Pydantic models for db-mcp."""

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
]
