"""MCP tools for knowledge gaps inspection, resolution, and dismissal."""

from db_mcp.config import get_settings
from db_mcp.gaps.store import auto_resolve_gaps, dismiss_gap, load_gaps


def _gap_to_entry(gap) -> dict:
    """Convert a KnowledgeGap to a serializable dict."""
    return {
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


async def _get_knowledge_gaps() -> dict:
    """Get current knowledge gaps for the active connection.

    Returns open gaps with suggested rules, plus summary stats.
    Use this to review unmapped business terms that the agent
    couldn't find in schema, examples, or rules.

    Analysts can work through gaps conversationally:
    1. Review each gap and confirm/correct the suggested rule
    2. Use query_add_rule to add confirmed rules
    3. Gaps will be auto-resolved when matching rules are added
    4. Use dismiss_knowledge_gap to dismiss false positives
    """
    settings = get_settings()
    provider_id = settings.provider_id

    # Auto-resolve first so stats are current
    auto_resolve_gaps(provider_id)

    gaps = load_gaps(provider_id)
    stats = gaps.stats()

    open_gaps = [_gap_to_entry(g) for g in gaps.get_open()]
    resolved_gaps = [_gap_to_entry(g) for g in gaps.get_resolved()]

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
                "Use dismiss_knowledge_gap to dismiss false positives",
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


async def _dismiss_knowledge_gap(gap_id: str, reason: str = "") -> dict:
    """Dismiss a knowledge gap as a false positive.

    Use this when a detected gap is not a real business term —
    e.g., it was triggered by grepping for common words like "intent".

    Dismissed gaps are preserved so they won't be re-detected from
    future traces, but they are hidden from the gaps list.

    If the gap belongs to a group, all gaps in the group are dismissed.

    Args:
        gap_id: The ID of the gap to dismiss (from get_knowledge_gaps output).
        reason: Optional reason for dismissal (e.g., "not a domain term").

    Returns:
        Status dict with count of dismissed gaps.
    """
    settings = get_settings()
    provider_id = settings.provider_id

    result = dismiss_gap(provider_id, gap_id, reason or None)

    if result.get("dismissed"):
        return {
            "status": "success",
            "message": f"Dismissed {result['count']} gap(s)",
            "gap_id": gap_id,
            "count": result["count"],
        }
    else:
        return {
            "status": "error",
            "message": result.get("error", "Failed to dismiss gap"),
            "gap_id": gap_id,
        }
