"""Schema scanner for detecting knowledge gaps.

Two modes:
1. Deterministic scan — heuristic detection of abbreviations and short names.
   Used during onboarding (no LLM context available).
2. LLM-based scan — uses MCPSamplingModel for deeper analysis.
   Used when an MCP session is available.
"""

import logging
import re
import uuid
from datetime import UTC, datetime

from db_mcp_models import GapSource, KnowledgeGap
from pydantic import BaseModel, Field
from pydantic_ai import Agent

logger = logging.getLogger(__name__)

# Common column name parts that are NOT abbreviations
_COMMON_NAMES = frozenset(
    {
        "id",
        "name",
        "type",
        "key",
        "code",
        "date",
        "time",
        "at",
        "by",
        "url",
        "uri",
        "ip",
        "is",
        "has",
        "no",
        "to",
        "on",
        "in",
        "of",
        "min",
        "max",
        "avg",
        "sum",
        "cnt",
        "num",
        "qty",
        "amt",
        "pct",
        "src",
        "dst",
        "ref",
        "idx",
        "seq",
        "ver",
        "row",
        "col",
        "val",
        "msg",
        "err",
        "log",
        "tag",
        "ttl",
        "lat",
        "lon",
        "geo",
        "utc",
        "day",
        "hr",
        "sec",
        "ms",
        "ts",
        "tz",
        "asc",
        "desc",
        "cpu",
        "ram",
        "pid",
        "uid",
        "gid",
        "env",
        "api",
        "sdk",
        "email",
        "phone",
        "status",
        "state",
        "flag",
        "level",
        "mode",
        "count",
        "total",
        "amount",
        "price",
        "cost",
        "rate",
        "ratio",
        "start",
        "end",
        "begin",
        "first",
        "last",
        "next",
        "prev",
        "created",
        "updated",
        "deleted",
        "modified",
        "timestamp",
        "user",
        "role",
        "group",
        "org",
        "team",
        "account",
        "session",
        "order",
        "item",
        "product",
        "category",
        "label",
        "title",
        "description",
        "comment",
        "note",
        "text",
        "body",
        "content",
        "path",
        "file",
        "dir",
        "size",
        "length",
        "width",
        "height",
        "color",
        "image",
        "icon",
        "avatar",
        "version",
        "active",
        "enabled",
        "visible",
        "public",
        "private",
        "default",
        "source",
        "target",
        "parent",
        "child",
        "owner",
        "author",
        "address",
        "city",
        "country",
        "region",
        "locale",
        "language",
        "currency",
        "unit",
        "format",
        "encoding",
        "hash",
        "token",
        "password",
        "secret",
        "salt",
        "config",
        "setting",
        "option",
        "priority",
        "weight",
        "score",
        "rank",
        "index",
        "position",
    }
)


class DetectedGap(BaseModel):
    """A single gap detected by the schema scanner."""

    term: str = Field(description="The abbreviation, jargon, or non-obvious term")
    columns: list[str] = Field(
        description="Full column references (table.column) where it appears"
    )
    explanation: str = Field(description="Best guess at what the term means")


class SchemaGapScanResult(BaseModel):
    """Structured output from the schema gap scanner."""

    gaps: list[DetectedGap] = Field(
        default_factory=list,
        description="List of detected abbreviations, jargon, and non-obvious terms",
    )


_SCAN_SYSTEM_PROMPT = """\
You are a database schema analyst. Your job is to identify abbreviations, \
jargon, and non-obvious terms in database column and table names that would \
be confusing to someone unfamiliar with the domain.

Focus on:
- Abbreviations (e.g. "bh_d", "hmh", "nas_id", "cui", "cdr")
- Domain jargon (e.g. "greenfield", "brownfield", "hotspot", "churn")
- Non-obvious names where the column name alone doesn't explain what it stores
- Code names or internal terms used as business identifiers

Do NOT flag:
- Common, self-explanatory names (id, name, email, created_at, updated_at, etc.)
- Standard SQL/database terms (primary_key, index, sequence)
- Common prefixes/suffixes (is_, has_, _count, _total, _date, _at)
- Terms that are obvious from context (user_id, order_total, product_name)

For each term, provide:
1. The term itself (lowercase, as it appears in the schema)
2. Which columns it appears in (use full table.column format)
3. Your best guess at what it means based on context
"""

_scan_agent = Agent(
    system_prompt=_SCAN_SYSTEM_PROMPT,
    output_type=SchemaGapScanResult,
)


async def scan_schema_for_gaps(
    schema_data: dict,
    provider_id: str,
    model: object,
) -> list[KnowledgeGap]:
    """Analyze schema column/table names for jargon and abbreviations.

    Args:
        schema_data: Parsed schema descriptions (from descriptions.yaml)
        provider_id: Provider identifier for gap metadata
        model: LLM model instance (e.g. MCPSamplingModel)

    Returns:
        List of KnowledgeGap objects to be saved
    """
    tables = schema_data.get("tables", [])
    if not tables:
        return []

    # Build a compact schema listing for the LLM
    lines = ["# Database Schema\n"]
    for table in tables:
        table_name = table.get("full_name") or table.get("name", "unknown")
        desc = table.get("description", "")
        lines.append(f"## {table_name}")
        if desc:
            lines.append(f"  Description: {desc}")

        columns = table.get("columns", [])
        for col in columns:
            col_name = col.get("name", "")
            col_desc = col.get("description", "")
            col_type = col.get("type", "")
            parts = [f"  - {col_name}"]
            if col_type:
                parts.append(f"({col_type})")
            if col_desc:
                parts.append(f"-- {col_desc}")
            lines.append(" ".join(parts))

        lines.append("")

    schema_text = "\n".join(lines)

    prompt = (
        f"Analyze the following database schema and identify abbreviations, "
        f"jargon, and non-obvious terms in the table and column names.\n\n"
        f"{schema_text}"
    )

    try:
        result = await _scan_agent.run(prompt, model=model)
        scan_result = result.output
    except Exception as e:
        logger.warning(f"Schema gap scan failed: {e}")
        return []

    # Convert to KnowledgeGap objects
    gaps: list[KnowledgeGap] = []
    now = datetime.now(UTC)

    for detected in scan_result.gaps:
        gap = KnowledgeGap(
            id=str(uuid.uuid4())[:8],
            term=detected.term.lower(),
            source=GapSource.SCHEMA_SCAN,
            detected_at=now,
            context="abbreviation detected in schema column names",
            related_columns=detected.columns,
            suggested_rule=(
                f"{detected.term} means {detected.explanation}" if detected.explanation else None
            ),
        )
        gaps.append(gap)

    logger.info(f"Schema scan detected {len(gaps)} potential knowledge gaps")
    return gaps


def _is_abbreviation(part: str) -> bool:
    """Check if a column name part looks like an abbreviation.

    Heuristics:
    - All consonants (no vowels), length 2-5: likely abbreviation (e.g. "bh", "cdr")
    - Very short (2-3 chars) and not in common names list
    - All uppercase in original (before lowering)
    """
    if part in _COMMON_NAMES:
        return False
    if len(part) < 2:
        return False

    # Short token not in common list
    if len(part) <= 3:
        return True

    # No vowels (consonant-only abbreviation like "cdr", "hmh", "bh")
    vowels = set("aeiou")
    if len(part) <= 5 and not vowels.intersection(part):
        return True

    return False


def scan_schema_deterministic(schema_data: dict) -> list[KnowledgeGap]:
    """Deterministic schema scan for abbreviations and short names.

    This is a fast, no-LLM scan that flags column name parts that look
    like abbreviations or jargon. Used during onboarding when no MCP
    session is available for LLM-based analysis.

    Args:
        schema_data: Parsed schema descriptions (from descriptions.yaml)

    Returns:
        List of KnowledgeGap objects
    """
    tables = schema_data.get("tables", [])
    if not tables:
        return []

    # Collect potential abbreviations: term -> list of table.column references
    term_refs: dict[str, list[str]] = {}

    for table in tables:
        table_name = table.get("full_name") or table.get("name", "unknown")

        for col in table.get("columns", []):
            col_name = col.get("name", "")
            if not col_name:
                continue

            # Split column name into parts
            parts = re.split(r"[_\-]+", col_name.lower())
            for part in parts:
                if _is_abbreviation(part):
                    ref = f"{table_name}.{col_name}"
                    if part not in term_refs:
                        term_refs[part] = []
                    if ref not in term_refs[part]:
                        term_refs[part].append(ref)

    # Convert to KnowledgeGap objects
    gaps: list[KnowledgeGap] = []
    now = datetime.now(UTC)

    for term, refs in sorted(term_refs.items()):
        gap = KnowledgeGap(
            id=str(uuid.uuid4())[:8],
            term=term,
            source=GapSource.SCHEMA_SCAN,
            detected_at=now,
            context=f"abbreviation detected in {len(refs)} column{'s' if len(refs) != 1 else ''}",
            related_columns=refs[:10],  # Limit to 10 refs
            suggested_rule=None,
        )
        gaps.append(gap)

    logger.info(f"Deterministic scan detected {len(gaps)} potential abbreviations")
    return gaps
