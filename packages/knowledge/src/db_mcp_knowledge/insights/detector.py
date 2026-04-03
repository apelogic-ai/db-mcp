"""Lightweight insight detector.

Runs after trace writes to flag noteworthy patterns.
Results are stored as pending insights for MCP resource exposure.

Design: deterministic and cheap. The agent does the deep thinking.
We just flag what's worth thinking about.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    """A single pending insight for the agent to review."""

    id: str
    category: str  # error, pattern, gap, performance, knowledge
    severity: str  # info, warning, action
    title: str
    summary: str
    details: dict = field(default_factory=dict)
    detected_at: float = field(default_factory=time.time)
    dismissed: bool = False


@dataclass
class InsightStore:
    """Pending insights awaiting agent review."""

    insights: list[Insight] = field(default_factory=list)
    last_scan_at: float = 0.0
    last_processed_at: float = 0.0  # When insights were last reviewed/processed

    def add(self, insight: Insight) -> bool:
        """Add insight if not duplicate. Returns True if added."""
        for existing in self.insights:
            if existing.id == insight.id or (
                existing.category == insight.category
                and existing.title == insight.title
                and not existing.dismissed
            ):
                return False
        self.insights.append(insight)
        return True

    def dismiss(self, insight_id: str) -> bool:
        """Mark an insight as dismissed."""
        for i in self.insights:
            if i.id == insight_id:
                i.dismissed = True
                return True
        return False

    def pending(self) -> list[Insight]:
        """Get non-dismissed insights."""
        return [i for i in self.insights if not i.dismissed]

    def clear_dismissed(self) -> int:
        """Remove dismissed insights. Returns count removed."""
        before = len(self.insights)
        self.insights = [i for i in self.insights if not i.dismissed]
        return before - len(self.insights)


def _insights_path(connection_path: Path) -> Path:
    return connection_path / ".insights.json"


def load_insights(connection_path: Path) -> InsightStore:
    """Load pending insights from disk."""
    path = _insights_path(connection_path)
    if not path.exists():
        return InsightStore()
    try:
        data = json.loads(path.read_text())
        insights = [Insight(**i) for i in data.get("insights", [])]
        return InsightStore(
            insights=insights,
            last_scan_at=data.get("last_scan_at", 0.0),
            last_processed_at=data.get("last_processed_at", 0.0),
        )
    except Exception as e:
        logger.warning(f"Failed to load insights: {e}")
        return InsightStore()


def save_insights(connection_path: Path, store: InsightStore) -> None:
    """Save pending insights to disk."""
    path = _insights_path(connection_path)
    data = {
        "insights": [asdict(i) for i in store.insights],
        "last_scan_at": store.last_scan_at,
        "last_processed_at": store.last_processed_at,
    }
    path.write_text(json.dumps(data, indent=2))


def detect_insights(
    analysis: dict,
    connection_path: Path,
) -> list[Insight]:
    """Run lightweight detection on trace analysis results.

    Takes the output of analyze_traces() and produces insights.
    Deterministic and cheap -- no LLM calls.

    Args:
        analysis: Output from bicp.traces.analyze_traces()
        connection_path: Path to connection directory

    Returns:
        List of new insights detected
    """
    insights: list[Insight] = []
    ts = time.time()

    # 1. Repeated SQL -- agent is struggling
    for rq in analysis.get("repeatedQueries", []):
        if rq.get("is_example"):
            continue  # Already saved, not actionable
        count = rq.get("count", 0)
        if count >= 3:
            insights.append(
                Insight(
                    id=f"repeated-{hash(rq.get('full_sql', '')) % 10**8}",
                    category="pattern",
                    severity="action",
                    title=f"Query repeated {count} times",
                    summary=(
                        f"The same query has been generated {count} times "
                        f"across sessions. Saving it as an example would "
                        f"let the agent reuse it directly."
                    ),
                    details={
                        "sql_preview": rq.get("sql_preview", ""),
                        "suggested_intent": rq.get("suggested_intent", ""),
                        "count": count,
                    },
                    detected_at=ts,
                )
            )

    # 2. Validation failures -- knowledge gaps
    fail_rate = analysis.get("insights", {}).get("validateFailRate")
    fail_count = analysis.get("validationFailureCount", 0)
    if fail_rate is not None and fail_rate > 30 and fail_count >= 3:
        insights.append(
            Insight(
                id=f"high-fail-rate-{int(ts)}",
                category="error",
                severity="warning",
                title=f"High SQL validation failure rate ({fail_rate}%)",
                summary=(
                    f"{fail_count} validation failures detected. "
                    f"The agent may be missing schema context or "
                    f"business rules for common query patterns."
                ),
                details={
                    "fail_rate": fail_rate,
                    "fail_count": fail_count,
                    "sample_errors": [
                        e.get("error_message", "")
                        for e in analysis.get("validationFailures", [])[:3]
                    ],
                },
                detected_at=ts,
            )
        )

    # 3. Vocabulary gaps detected
    open_gaps = [g for g in analysis.get("vocabularyGaps", []) if g.get("status") == "open"]
    if open_gaps:
        terms = [t.get("term", "") for g in open_gaps for t in g.get("terms", [])][:5]
        insights.append(
            Insight(
                id=f"vocab-gaps-{len(open_gaps)}",
                category="gap",
                severity="action",
                title=f"{len(open_gaps)} unmapped business terms",
                summary=(
                    f"Terms like {', '.join(repr(t) for t in terms)} "
                    f"appeared in queries but aren't mapped to schema. "
                    f"Adding business rules would improve accuracy."
                ),
                details={
                    "gap_count": len(open_gaps),
                    "sample_terms": terms,
                },
                detected_at=ts,
            )
        )

    # 4. Low example hit rate -- agent not using knowledge
    hit_rate = analysis.get("insights", {}).get("exampleHitRate")
    gen_calls = analysis.get("insights", {}).get("generationCalls", 0)
    if hit_rate is not None and hit_rate < 30 and gen_calls >= 5:
        insights.append(
            Insight(
                id=f"low-hit-rate-{int(ts)}",
                category="knowledge",
                severity="info",
                title=f"Low example reuse ({hit_rate}%)",
                summary=(
                    f"Only {hit_rate}% of SQL generation calls found "
                    f"relevant examples. The knowledge vault may need "
                    f"more examples for common query patterns."
                ),
                details={
                    "hit_rate": hit_rate,
                    "generation_calls": gen_calls,
                },
                detected_at=ts,
            )
        )

    # 5. Errors with saveable SQL -- learning opportunities
    unsaved_errors = [
        e for e in analysis.get("errors", []) if e.get("sql") and not e.get("is_saved")
    ]
    if len(unsaved_errors) >= 3:
        insights.append(
            Insight(
                id=f"unsaved-errors-{len(unsaved_errors)}",
                category="knowledge",
                severity="action",
                title=f"{len(unsaved_errors)} failed queries not saved",
                summary=(
                    f"There are {len(unsaved_errors)} failed queries "
                    f"with SQL that could be saved as learnings to "
                    f"prevent the agent from repeating the same mistakes."
                ),
                details={
                    "count": len(unsaved_errors),
                    "sample_errors": [
                        {
                            "sql": e.get("sql", "")[:100],
                            "error": e.get("error", "")[:100],
                        }
                        for e in unsaved_errors[:3]
                    ],
                },
                detected_at=ts,
            )
        )

    # 6. No knowledge captures in recent traces
    capture_count = analysis.get("knowledgeCaptureCount", 0)
    trace_count = analysis.get("traceCount", 0)
    if trace_count >= 10 and capture_count == 0:
        insights.append(
            Insight(
                id=f"no-captures-{int(ts)}",
                category="knowledge",
                severity="info",
                title="No knowledge captured recently",
                summary=(
                    f"{trace_count} queries analyzed but no examples, "
                    f"rules, or feedback saved. The knowledge vault "
                    f"isn't growing from usage."
                ),
                details={
                    "trace_count": trace_count,
                },
                detected_at=ts,
            )
        )

    return insights


def should_suggest_insights(connection_path: Path, threshold_hours: float = 24.0) -> bool:
    """Check if agent should suggest insights processing based on time threshold.

    Args:
        connection_path: Path to connection directory
        threshold_hours: Hours since last processing to trigger suggestion (default 24)

    Returns:
        True if insights should be suggested (time threshold passed and insights exist)
    """
    store = load_insights(connection_path)

    # No pending insights = no suggestion needed
    if not store.pending():
        return False

    # Check if enough time has passed since last processing
    current_time = time.time()
    hours_since_processed = (current_time - store.last_processed_at) / 3600

    return hours_since_processed >= threshold_hours


def mark_insights_processed(connection_path: Path) -> None:
    """Mark insights as processed (updates timestamp).

    Call this when the agent has reviewed insights, either through
    the review-insights prompt or conversational suggestion.
    """
    store = load_insights(connection_path)
    store.last_processed_at = time.time()
    save_insights(connection_path, store)


def scan_and_update(connection_path: Path, analysis: dict) -> InsightStore:
    """Run detection and update the insight store.

    Returns the updated store with any new insights added.
    """
    store = load_insights(connection_path)
    new_insights = detect_insights(analysis, connection_path)

    added = 0
    for insight in new_insights:
        if store.add(insight):
            added += 1

    store.last_scan_at = time.time()
    store.clear_dismissed()

    if added > 0:
        save_insights(connection_path, store)
        logger.info(f"Added {added} new insight(s), total pending: {len(store.pending())}")

    return store
