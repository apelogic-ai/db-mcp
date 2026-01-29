"""Knowledge gaps persistence — load, save, merge, resolve.

Follows the same pattern as training/store.py for consistency.
Gaps are stored in a single YAML file per connection.
"""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from db_mcp_models import GapSource, GapStatus, KnowledgeGap, KnowledgeGaps

logger = logging.getLogger(__name__)


def _get_connection_dir(provider_id: str) -> Path:
    """Resolve connection directory from provider_id (connection name)."""
    return Path.home() / ".db-mcp" / "connections" / provider_id


def get_gaps_file_path(provider_id: str) -> Path:
    """Get path to knowledge_gaps.yaml."""
    return _get_connection_dir(provider_id) / "knowledge_gaps.yaml"


def load_gaps(provider_id: str) -> KnowledgeGaps:
    """Load knowledge gaps from YAML file.

    Args:
        provider_id: Provider identifier

    Returns:
        KnowledgeGaps (empty if file doesn't exist)
    """
    gaps_file = get_gaps_file_path(provider_id)

    if not gaps_file.exists():
        return KnowledgeGaps(provider_id=provider_id)

    try:
        with open(gaps_file) as f:
            data = yaml.safe_load(f)
        return KnowledgeGaps.model_validate(data)
    except Exception:
        return KnowledgeGaps(provider_id=provider_id)


def save_gaps(gaps: KnowledgeGaps) -> dict:
    """Save knowledge gaps to YAML file.

    Args:
        gaps: KnowledgeGaps to save

    Returns:
        Dict with save status
    """
    try:
        gaps_file = get_gaps_file_path(gaps.provider_id)
        gaps_file.parent.mkdir(parents=True, exist_ok=True)

        gaps_dict = gaps.model_dump(mode="json")

        with open(gaps_file, "w") as f:
            yaml.dump(
                gaps_dict,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        return {"saved": True, "file_path": str(gaps_file), "error": None}
    except Exception as e:
        return {"saved": False, "file_path": None, "error": str(e)}


def add_gap(
    provider_id: str,
    term: str,
    source: GapSource,
    context: str | None = None,
    related_columns: list[str] | None = None,
    suggested_rule: str | None = None,
) -> KnowledgeGap | None:
    """Add a single gap, deduplicating by term. Returns the gap or None if duplicate."""
    gaps = load_gaps(provider_id)

    if gaps.has_term(term):
        return None

    gap = KnowledgeGap(
        id=str(uuid.uuid4())[:8],
        term=term,
        source=source,
        context=context,
        related_columns=related_columns or [],
        suggested_rule=suggested_rule,
    )
    gaps.add_gap(gap)
    save_gaps(gaps)
    return gap


def resolve_gap(provider_id: str, gap_id: str, resolved_by: str) -> dict:
    """Mark a gap (and all gaps in its group) as resolved.

    Args:
        provider_id: Provider identifier
        gap_id: Gap ID to resolve
        resolved_by: How it was resolved (business_rules, schema_description, manual)

    Returns:
        Dict with status and count of resolved gaps
    """
    gaps = load_gaps(provider_id)
    target = gaps.get_gap(gap_id)
    if not target or target.status != GapStatus.OPEN:
        return {
            "resolved": False,
            "error": f"Gap {gap_id} not found or already resolved",
        }

    # Resolve the target and all siblings in the same group
    resolved_count = 0
    if target.group_id:
        for g in gaps.gaps:
            if g.group_id == target.group_id and g.status == GapStatus.OPEN:
                gaps.resolve(g.id, resolved_by)
                resolved_count += 1
    else:
        gaps.resolve(gap_id, resolved_by)
        resolved_count = 1

    save_gaps(gaps)
    return {"resolved": True, "gap_id": gap_id, "count": resolved_count}


def merge_trace_gaps(provider_id: str, trace_gaps: list[dict]) -> int:
    """Merge vocabulary gaps detected from traces into the persistent file.

    Takes the grouped output from _detect_vocabulary_gaps() and adds new gaps,
    skipping terms that already exist.

    Args:
        provider_id: Provider identifier
        trace_gaps: List of grouped gap dicts from _detect_vocabulary_gaps()
            Each has: terms, totalSearches, timestamp, schemaMatches, suggestedRule

    Returns:
        Count of new gaps added
    """
    gaps = load_gaps(provider_id)
    added = 0

    for group in trace_gaps:
        suggested_rule = group.get("suggestedRule")
        schema_matches = group.get("schemaMatches", [])
        related_columns = [
            f"{m.get('table', '')}.{m['name']}" if m.get("table") else m["name"]
            for m in schema_matches
            if m.get("type") == "column"
        ]

        # All terms in a group share the same group_id
        terms_in_group = group.get("terms", [])
        if len(terms_in_group) <= 1:
            grp_id = None
        else:
            # Check if any existing gap already has a group_id for a term in this group
            grp_id = None
            for term_info in terms_in_group:
                for existing in gaps.gaps:
                    if existing.term.lower() == term_info["term"].lower() and existing.group_id:
                        grp_id = existing.group_id
                        break
                if grp_id:
                    break
            if not grp_id:
                grp_id = str(uuid.uuid4())[:8]

        for term_info in terms_in_group:
            term = term_info["term"]
            if gaps.has_term(term):
                # Update group_id on existing gap if it was ungrouped
                if grp_id:
                    for existing in gaps.gaps:
                        if existing.term.lower() == term.lower() and not existing.group_id:
                            existing.group_id = grp_id
                continue

            gap = KnowledgeGap(
                id=str(uuid.uuid4())[:8],
                term=term,
                group_id=grp_id,
                source=GapSource.TRACES,
                detected_at=datetime.fromtimestamp(term_info.get("timestamp", 0), tz=UTC),
                context=f"searched {term_info['searchCount']}x in session {term_info['session']}",
                related_columns=related_columns,
                suggested_rule=suggested_rule,
            )
            gaps.add_gap(gap)
            added += 1

    if added > 0:
        save_gaps(gaps)
        logger.info(f"Merged {added} new knowledge gaps from traces")

    return added


def auto_resolve_gaps(provider_id: str) -> int:
    """Check if any open gaps have been addressed by business rules.

    Scans business_rules.yaml for terms matching open gaps.
    Marks matching gaps as resolved with resolved_by="business_rules".

    Returns:
        Count of newly resolved gaps
    """
    gaps = load_gaps(provider_id)
    open_gaps = gaps.get_open()
    if not open_gaps:
        return 0

    # Read business rules directly from the connection directory
    rules_file = _get_connection_dir(provider_id) / "instructions" / "business_rules.yaml"
    if not rules_file.exists():
        return 0

    try:
        with open(rules_file) as f:
            data = yaml.safe_load(f) or {}
        rules = data.get("rules", [])
        if not rules or not isinstance(rules, list):
            return 0
    except Exception:
        return 0

    # Build a lowercase version of all rules for matching
    rules_text = "\n".join(str(r).lower() for r in rules)

    resolved_count = 0
    for gap in open_gaps:
        term_lower = gap.term.lower()
        # Check if the term appears in any business rule
        if term_lower in rules_text:
            gap.status = GapStatus.RESOLVED
            gap.resolved_at = datetime.now(UTC)
            gap.resolved_by = "business_rules"
            resolved_count += 1

    if resolved_count > 0:
        save_gaps(gaps)
        logger.info(f"Auto-resolved {resolved_count} knowledge gaps")

    return resolved_count


def load_gaps_from_path(connection_path: Path) -> KnowledgeGaps:
    """Load knowledge gaps directly from a connection path.

    Used by BICP agent which has the path but not necessarily the provider_id.
    """
    gaps_file = connection_path / "knowledge_gaps.yaml"
    if not gaps_file.exists():
        return KnowledgeGaps(provider_id="unknown")

    try:
        with open(gaps_file) as f:
            data = yaml.safe_load(f)
        return KnowledgeGaps.model_validate(data)
    except Exception:
        return KnowledgeGaps(provider_id="unknown")
