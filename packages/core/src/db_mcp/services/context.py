"""Context-building services for query generation."""

from pathlib import Path
from typing import Any

from db_mcp_knowledge.onboarding.schema_store import load_schema_descriptions
from db_mcp_knowledge.training.store import load_examples, load_instructions
from db_mcp_knowledge.vault.paths import BUSINESS_RULES_FILE, DESCRIPTIONS_FILE, EXAMPLES_DIR
from opentelemetry import trace


def build_schema_context(
    provider_id: str,
    tables_hint: list[str] | None = None,
    connection_path: Path | None = None,
) -> str:
    """Build schema context string for LLM prompts."""
    schema = load_schema_descriptions(provider_id, connection_path=connection_path)
    if not schema:
        return ""

    current_span = trace.get_current_span()
    files_used = current_span.get_attribute("knowledge.files_used") or []
    files_used.append(DESCRIPTIONS_FILE)
    current_span.set_attribute("knowledge.files_used", files_used)

    lines = ["## Available Tables\n"]

    for table in schema.tables:
        if tables_hint and table.full_name not in tables_hint:
            continue

        desc = f" - {table.description}" if table.description else ""
        lines.append(f"### {table.full_name}{desc}\n")
        lines.append("Columns:")

        for col in table.columns:
            col_desc = f" -- {col.description}" if col.description else ""
            lines.append(f"  - {col.name}: {col.type or 'unknown'}{col_desc}")

        lines.append("")

    return "\n".join(lines)


def build_examples_context(provider_id: str, limit: int = 5) -> str:
    """Build examples context for few-shot learning."""
    examples = load_examples(provider_id)
    if not examples.examples:
        return ""

    current_span = trace.get_current_span()
    files_used = list(current_span.get_attribute("knowledge.files_used") or [])

    for example in examples.examples[:limit]:
        files_used.append(f"{EXAMPLES_DIR}/{example.id}.yaml")

    current_span.set_attribute("knowledge.files_used", files_used)

    lines = ["## Query Examples\n"]

    for example in examples.examples[:limit]:
        lines.append(f"Question: {example.natural_language}")
        lines.append(f"SQL: {example.sql}")
        lines.append("")

    return "\n".join(lines)


def build_rules_context(provider_id: str) -> str:
    """Build business rules context."""
    instructions = load_instructions(provider_id)
    if not instructions.rules:
        return ""

    current_span = trace.get_current_span()
    files_used = list(current_span.get_attribute("knowledge.files_used") or [])
    files_used.append(BUSINESS_RULES_FILE)
    current_span.set_attribute("knowledge.files_used", files_used)

    lines = ["## Business Rules\n"]
    for rule in instructions.rules:
        lines.append(f"- {rule}")

    return "\n".join(lines)


def load_semantic_context(
    provider_id: str, connection_path: Path | None = None
) -> tuple[Any, Any]:
    """Load schema descriptions and query examples for semantic workflows."""
    schema = load_schema_descriptions(provider_id, connection_path=connection_path)
    examples = load_examples(provider_id)
    return schema, examples


def load_schema_knowledge(provider_id: str, connection_path: Path | None = None) -> Any:
    """Load schema descriptions for semantic read/enrichment flows."""
    return load_schema_descriptions(provider_id, connection_path=connection_path)


__all__ = [
    "build_examples_context",
    "build_rules_context",
    "build_schema_context",
    "load_schema_knowledge",
    "load_semantic_context",
]
