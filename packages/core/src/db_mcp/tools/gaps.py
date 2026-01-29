"""MCP tool for knowledge gaps inspection and resolution."""

from db_mcp.config import get_settings
from db_mcp.gaps.store import auto_resolve_gaps, load_gaps


async def _get_knowledge_gaps() -> dict:
    """Get current knowledge gaps for the active connection.

    Returns open gaps with suggested rules, plus summary stats.
    Use this to review unmapped business terms that the agent
    couldn't find in schema, examples, or rules.

    Analysts can work through gaps conversationally:
    1. Review each gap and confirm/correct the suggested rule
    2. Use query_add_rule to add confirmed rules
    3. Gaps will be auto-resolved when matching rules are added
    """
    settings = get_settings()
    provider_id = settings.provider_id

    # Auto-resolve first so stats are current
    auto_resolve_gaps(provider_id)

    gaps = load_gaps(provider_id)
    stats = gaps.stats()

    open_gaps = []
    resolved_gaps = []
    for gap in gaps.gaps:
        entry = {
            "id": gap.id,
            "term": gap.term,
            "status": gap.status.value,
            "source": gap.source.value,
            "context": gap.context,
            "related_columns": gap.related_columns,
            "suggested_rule": gap.suggested_rule,
            "detected_at": gap.detected_at.isoformat(),
            "resolved_by": gap.resolved_by,
        }
        if gap.status.value == "open":
            open_gaps.append(entry)
        else:
            resolved_gaps.append(entry)

    guidance: dict = {}
    if stats["open"] > 0:
        guidance = {
            "summary": (
                f"{stats['open']} open knowledge gap{'s' if stats['open'] != 1 else ''} found."
            ),
            "next_steps": [
                "Review each gap and confirm/correct the suggested rule",
                "Use query_add_rule to add confirmed rules as business rules",
                "Gaps will be auto-resolved when matching rules are added",
            ],
        }
    else:
        guidance = {
            "summary": "No open knowledge gaps.",
            "next_steps": ["All detected gaps have been resolved."],
        }

    return {
        "status": "success",
        "provider_id": provider_id,
        "gaps": open_gaps,
        "resolved": resolved_gaps,
        "stats": stats,
        "guidance": guidance,
    }
