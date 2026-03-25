"""Shared Pydantic models for db-mcp."""

from db_mcp_models.gaps import GapSource, GapStatus, KnowledgeGap, KnowledgeGaps
from db_mcp_models.meta_query import (
    ExpectedCardinality,
    MetaDimension,
    MetaFilter,
    MetaMeasure,
    MetaQueryPlan,
    MetaTimeContext,
    ObservedCardinality,
)
from db_mcp_models.metrics import (
    Dimension,
    DimensionCandidate,
    DimensionsCatalog,
    DimensionType,
    Metric,
    MetricBinding,
    MetricBindingsCatalog,
    MetricCandidate,
    MetricDimensionBinding,
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
from db_mcp_models.orchestration import (
    AnswerIntentResponse,
    ConfidenceVector,
    MetricExecutionPlan,
    ResultShape,
)
from db_mcp_models.plan import PlanStep, QueryPlan
from db_mcp_models.policy import (
    BoundaryMode,
    SemanticPolicy,
    TimeWindowPolicy,
    UnitConversionPolicy,
)
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
    "MetricBinding",
    "MetricBindingsCatalog",
    "MetricDimensionBinding",
    "MetricParameter",
    "MetricsCatalog",
    # Dimensions
    "Dimension",
    "DimensionType",
    "DimensionsCatalog",
    # Candidates
    "MetricCandidate",
    "DimensionCandidate",
    # Meta query
    "ExpectedCardinality",
    "ObservedCardinality",
    "MetaMeasure",
    "MetaDimension",
    "MetaFilter",
    "MetaTimeContext",
    "MetaQueryPlan",
    # Orchestration
    "MetricExecutionPlan",
    "ConfidenceVector",
    "ResultShape",
    "AnswerIntentResponse",
    # Policy
    "BoundaryMode",
    "TimeWindowPolicy",
    "UnitConversionPolicy",
    "SemanticPolicy",
]
