"""Vault schema registry — central validation and side-effect layer for knowledge writes.

Each named MCP tool (query_approve, query_add_rule, metrics_add, …) stays on the
public surface unchanged.  This module is the shared *implementation* layer those
tools delegate to.

Usage::

    result = vault_write_typed(
        schema_key="approved_example",
        content={"id": "abc", "natural_language": "...", "sql": "..."},
        provider_id="my-conn",
        connection_path=Path("/home/user/.db-mcp/connections/my-conn"),
    )

Flow for vault_write_typed():
    1. Look up the schema key (KeyError if unknown)
    2. Validate ``content`` against the registered Pydantic model (ValidationError on failure)
    3. Run pre_hooks — any hook can raise to abort the write
    4. Call writer — performs the atomic primary write; returns result dict
    5. Run post_hooks — side effects (dual-writes, log appends, …)
    6. Return writer result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# SchemaEntry
# ---------------------------------------------------------------------------

type WriterFn = Callable[[BaseModel, str, Path], dict]
type HookFn = Callable[[BaseModel, str, Path], None]
type DeleterFn = Callable[[str, str, Path], dict]
type DeleteHookFn = Callable[[str, str, Path], None]


@dataclass
class SchemaEntry:
    """Registry entry describing how to validate and write one schema type."""

    model: type[BaseModel]
    writer: WriterFn
    pre_hooks: list[HookFn] = field(default_factory=list)
    post_hooks: list[HookFn] = field(default_factory=list)


@dataclass
class DeleteEntry:
    """Registry entry describing how to delete one schema type by identifier."""

    deleter: DeleterFn
    pre_hooks: list[DeleteHookFn] = field(default_factory=list)
    post_hooks: list[DeleteHookFn] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, SchemaEntry] = {}
_DELETE_REGISTRY: dict[str, DeleteEntry] = {}


def register(key: str, entry: SchemaEntry) -> None:
    """Register (or replace) a schema entry."""
    _REGISTRY[key] = entry


def lookup(key: str) -> SchemaEntry:
    """Return the entry for *key*, raising KeyError if unknown."""
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(f"Unknown vault schema key: {key!r}") from None


def register_delete(key: str, entry: DeleteEntry) -> None:
    """Register (or replace) a delete entry."""
    _DELETE_REGISTRY[key] = entry


def lookup_delete(key: str) -> DeleteEntry:
    """Return the delete entry for *key*, raising KeyError if unknown."""
    try:
        return _DELETE_REGISTRY[key]
    except KeyError:
        raise KeyError(f"Unknown vault delete schema key: {key!r}") from None


# ---------------------------------------------------------------------------
# vault_write_typed
# ---------------------------------------------------------------------------


def vault_write_typed(
    schema_key: str,
    content: dict,
    provider_id: str,
    connection_path: Path,
) -> dict:
    """Write vault content through the schema registry.

    Args:
        schema_key: Registry key (e.g. "approved_example", "business_rule").
        content: Raw dict that will be validated against the schema's Pydantic model.
        provider_id: Connection / provider identifier.
        connection_path: Absolute path to the connection directory.

    Returns:
        Result dict returned by the writer function.

    Raises:
        KeyError: If *schema_key* is not registered.
        pydantic.ValidationError: If *content* fails model validation.
        Any exception raised by a pre-hook aborts the write.
    """
    entry = lookup(schema_key)
    validated = entry.model.model_validate(content)

    for hook in entry.pre_hooks:
        hook(validated, provider_id, connection_path)

    result = entry.writer(validated, provider_id, connection_path)

    for hook in entry.post_hooks:
        hook(validated, provider_id, connection_path)

    return result


def vault_delete_typed(
    schema_key: str,
    identifier: str,
    provider_id: str,
    connection_path: Path,
) -> dict:
    """Delete a vault item through the schema registry.

    Args:
        schema_key: Delete registry key (e.g. "metric_deletion", "dimension_deletion").
        identifier: Name or ID of the item to delete.
        provider_id: Connection / provider identifier.
        connection_path: Absolute path to the connection directory.

    Returns:
        Result dict returned by the deleter function.

    Raises:
        KeyError: If *schema_key* is not registered.
        Any exception raised by a pre-hook aborts the delete.
    """
    entry = lookup_delete(schema_key)

    for hook in entry.pre_hooks:
        hook(identifier, provider_id, connection_path)

    result = entry.deleter(identifier, provider_id, connection_path)

    for hook in entry.post_hooks:
        hook(identifier, provider_id, connection_path)

    return result


# ---------------------------------------------------------------------------
# Local payload models (not in db_mcp_models — only used inside the registry)
# ---------------------------------------------------------------------------


class BusinessRuleEntry(BaseModel):
    """Payload model for business_rule schema writes."""

    rule: str

    @field_validator("rule")
    @classmethod
    def rule_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rule must not be empty")
        return v


class GapDismissalEntry(BaseModel):
    """Payload model for gap_dismissal schema writes."""

    gap_id: str
    reason: str | None = None


# ---------------------------------------------------------------------------
# Built-in entries
# ---------------------------------------------------------------------------


def _register_approved_example() -> None:
    from db_mcp_models import FeedbackType, QueryExample

    from db_mcp_knowledge.training.store import add_feedback, save_example

    def writer(example: QueryExample, provider_id: str, connection_path: Path) -> dict:
        return save_example(provider_id, example)

    def post_hook(example: QueryExample, provider_id: str, connection_path: Path) -> None:
        add_feedback(
            provider_id=provider_id,
            natural_language=example.natural_language,
            generated_sql=example.sql,
            feedback_type=FeedbackType.APPROVED,
            tables_involved=example.tables_used,
        )

    register(
        "approved_example",
        SchemaEntry(model=QueryExample, writer=writer, post_hooks=[post_hook]),
    )


def _register_corrected_feedback() -> None:
    from db_mcp_models import FeedbackType, QueryFeedback

    from db_mcp_knowledge.training.store import add_example, add_feedback

    def writer(fb: QueryFeedback, provider_id: str, connection_path: Path) -> dict:
        return add_feedback(
            provider_id=provider_id,
            natural_language=fb.natural_language,
            generated_sql=fb.generated_sql,
            feedback_type=fb.feedback_type,
            corrected_sql=fb.corrected_sql,
            feedback_text=fb.feedback_text,
            tables_involved=fb.tables_involved,
        )

    def post_hook(fb: QueryFeedback, provider_id: str, connection_path: Path) -> None:
        if fb.feedback_type == FeedbackType.CORRECTED and fb.corrected_sql:
            add_example(
                provider_id=provider_id,
                natural_language=fb.natural_language,
                sql=fb.corrected_sql,
                tables_used=fb.tables_involved,
                notes=f"Corrected from: {fb.generated_sql[:100]}...",
            )

    register(
        "corrected_feedback",
        SchemaEntry(model=QueryFeedback, writer=writer, post_hooks=[post_hook]),
    )


def _register_business_rule() -> None:
    from db_mcp_knowledge.training.store import add_rule, load_instructions

    def pre_hook(entry: BusinessRuleEntry, provider_id: str, connection_path: Path) -> None:
        instructions = load_instructions(provider_id)
        if entry.rule in instructions.rules:
            raise ValueError(f"Rule already exists: {entry.rule!r}")

    def writer(entry: BusinessRuleEntry, provider_id: str, connection_path: Path) -> dict:
        return add_rule(provider_id, entry.rule)

    register(
        "business_rule",
        SchemaEntry(model=BusinessRuleEntry, writer=writer, pre_hooks=[pre_hook]),
    )


def _register_metric() -> None:
    from db_mcp_models import Metric

    from db_mcp_knowledge.metrics.store import load_metrics, save_metrics

    def writer(metric: Metric, provider_id: str, connection_path: Path) -> dict:
        catalog = load_metrics(provider_id, connection_path=connection_path)
        catalog.add_metric(metric)
        return save_metrics(catalog, connection_path=connection_path)

    register("metric", SchemaEntry(model=Metric, writer=writer))


def _register_dimension() -> None:
    from db_mcp_models import Dimension

    from db_mcp_knowledge.metrics.store import load_dimensions, save_dimensions

    def writer(dimension: Dimension, provider_id: str, connection_path: Path) -> dict:
        catalog = load_dimensions(provider_id, connection_path=connection_path)
        catalog.add_dimension(dimension)
        return save_dimensions(catalog, connection_path=connection_path)

    register("dimension", SchemaEntry(model=Dimension, writer=writer))


def _register_metric_binding() -> None:
    from db_mcp_models import MetricBinding

    from db_mcp_knowledge.metrics.store import load_dimensions, load_metrics, upsert_metric_binding

    def pre_hook(binding: MetricBinding, provider_id: str, connection_path: Path) -> None:
        metrics_catalog = load_metrics(provider_id, connection_path=connection_path)
        if not metrics_catalog.get_metric(binding.metric_name):
            raise ValueError(
                f"Metric '{binding.metric_name}' not found in catalog"
            )
        if binding.dimensions:
            dims_catalog = load_dimensions(provider_id, connection_path=connection_path)
            for dim_name in binding.dimensions:
                if not dims_catalog.get_dimension(dim_name):
                    raise ValueError(
                        f"Dimension '{dim_name}' not found in catalog"
                    )

    def writer(binding: MetricBinding, provider_id: str, connection_path: Path) -> dict:
        return upsert_metric_binding(provider_id, binding, connection_path=connection_path)

    register(
        "metric_binding",
        SchemaEntry(model=MetricBinding, writer=writer, pre_hooks=[pre_hook]),
    )


def _register_gap_dismissal() -> None:
    from db_mcp_models import GapStatus

    from db_mcp_knowledge.gaps.store import dismiss_gap, load_gaps

    def pre_hook(entry: GapDismissalEntry, provider_id: str, connection_path: Path) -> None:
        gaps = load_gaps(provider_id)
        target = gaps.get_gap(entry.gap_id)
        if not target or target.status != GapStatus.OPEN:
            raise ValueError(f"Gap {entry.gap_id!r} not found or not open")

    def writer(entry: GapDismissalEntry, provider_id: str, connection_path: Path) -> dict:
        return dismiss_gap(provider_id, entry.gap_id, entry.reason)

    register(
        "gap_dismissal",
        SchemaEntry(model=GapDismissalEntry, writer=writer, pre_hooks=[pre_hook]),
    )


def _register_metric_deletion() -> None:
    from db_mcp_knowledge.metrics.store import delete_metric, load_metrics

    def pre_hook(identifier: str, provider_id: str, connection_path: Path) -> None:
        catalog = load_metrics(provider_id, connection_path=connection_path)
        if not catalog.get_metric(identifier):
            raise ValueError(f"Metric '{identifier}' not found in catalog")

    def deleter(identifier: str, provider_id: str, connection_path: Path) -> dict:
        return delete_metric(provider_id, identifier, connection_path=connection_path)

    register_delete(
        "metric_deletion",
        DeleteEntry(deleter=deleter, pre_hooks=[pre_hook]),
    )


def _register_dimension_deletion() -> None:
    from db_mcp_knowledge.metrics.store import delete_dimension, load_dimensions

    def pre_hook(identifier: str, provider_id: str, connection_path: Path) -> None:
        catalog = load_dimensions(provider_id, connection_path=connection_path)
        if not catalog.get_dimension(identifier):
            raise ValueError(f"Dimension '{identifier}' not found in catalog")

    def deleter(identifier: str, provider_id: str, connection_path: Path) -> dict:
        return delete_dimension(provider_id, identifier, connection_path=connection_path)

    register_delete(
        "dimension_deletion",
        DeleteEntry(deleter=deleter, pre_hooks=[pre_hook]),
    )


# ---------------------------------------------------------------------------
# Bootstrap all built-in entries at import time
# ---------------------------------------------------------------------------

_register_approved_example()
_register_corrected_feedback()
_register_business_rule()
_register_metric()
_register_dimension()
_register_metric_binding()
_register_gap_dismissal()
_register_metric_deletion()
_register_dimension_deletion()
