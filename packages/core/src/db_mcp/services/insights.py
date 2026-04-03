"""Insights and gaps services."""

from datetime import datetime, timedelta
from pathlib import Path


def dismiss_gap(connection: str, gap_id: str, reason: str | None = None) -> dict:
    """Dismiss a knowledge gap for a connection."""
    from db_mcp_knowledge.gaps.store import dismiss_gap as dismiss_gap_store

    result = dismiss_gap_store(connection, gap_id, reason)
    if result.get("dismissed"):
        return {
            "success": True,
            "count": result["count"],
        }
    return {
        "success": False,
        "error": result.get("error", "Failed to dismiss gap"),
    }


def save_example(connection: str, sql: str, intent: str) -> dict:
    """Save a repeated query as a training example."""
    from db_mcp_knowledge.training.store import add_example

    result = add_example(
        provider_id=connection,
        natural_language=intent,
        sql=sql,
    )

    if result.get("added"):
        return {
            "success": True,
            "example_id": result["example_id"],
            "total_examples": result["total_examples"],
            "file_path": result.get("file_path"),
        }

    return {
        "success": False,
        "error": result.get("error", "Failed to save example"),
    }


def analyze_insights(connection_path: Path | None, days: int = 7) -> dict:
    """Analyze live and historical traces and refresh derived insights."""
    from db_mcp.bicp.traces import analyze_traces, read_traces_from_jsonl
    from db_mcp.console.collector import get_collector

    all_traces: list[dict] = []

    try:
        live = get_collector().get_traces(limit=500)
        all_traces.extend(live)
    except Exception:
        pass

    if connection_path:
        try:
            from db_mcp.traces import get_traces_dir, get_user_id_from_config, is_traces_enabled

            if is_traces_enabled():
                user_id = get_user_id_from_config()
                if user_id:
                    traces_dir = get_traces_dir(connection_path, user_id)
                    today = datetime.now()
                    for i in range(days):
                        date = today - timedelta(days=i)
                        date_str = date.strftime("%Y-%m-%d")
                        file_path = traces_dir / f"{date_str}.jsonl"
                        if file_path.exists():
                            day_traces = read_traces_from_jsonl(file_path, limit=500)
                            all_traces.extend(day_traces)
        except Exception:
            pass

    seen_ids: set[str] = set()
    unique_traces: list[dict] = []
    for trace in all_traces:
        trace_id = trace.get("trace_id", "")
        if trace_id not in seen_ids:
            seen_ids.add(trace_id)
            unique_traces.append(trace)

    analysis = analyze_traces(unique_traces, connection_path, days=days)

    if connection_path:
        try:
            from db_mcp_knowledge.insights.detector import scan_and_update

            scan_and_update(connection_path, analysis)
        except Exception:
            pass

        try:
            from db_mcp_knowledge.gaps.store import auto_resolve_gaps, load_gaps_from_path

            provider_id = connection_path.name
            resolved = auto_resolve_gaps(provider_id)
            if resolved > 0:
                all_gaps = load_gaps_from_path(connection_path)
                groups: dict[str, list] = {}
                ungrouped: list = []
                for gap in all_gaps.gaps:
                    if gap.group_id:
                        groups.setdefault(gap.group_id, []).append(gap)
                    else:
                        ungrouped.append(gap)

                def _gap_to_entry(gap_list: list) -> dict:
                    terms = []
                    all_cols: list[str] = []
                    suggested = None
                    earliest = float("inf")
                    status = "resolved"
                    source = gap_list[0].source.value if gap_list else "traces"
                    for gap in gap_list:
                        terms.append(
                            {
                                "term": gap.term,
                                "searchCount": 0,
                                "session": "",
                                "timestamp": gap.detected_at.timestamp(),
                            }
                        )
                        all_cols.extend(gap.related_columns)
                        if gap.suggested_rule:
                            suggested = gap.suggested_rule
                        earliest = min(earliest, gap.detected_at.timestamp())
                        if gap.status.value == "open":
                            status = "open"
                        source = gap.source.value

                    seen: set[str] = set()
                    unique: list[str] = []
                    for column in all_cols:
                        if column not in seen:
                            seen.add(column)
                            unique.append(column)

                    return {
                        "id": gap_list[0].id,
                        "terms": terms,
                        "totalSearches": 0,
                        "timestamp": earliest,
                        "schemaMatches": [
                            {
                                "name": column.split(".")[-1],
                                "table": column,
                                "type": "column",
                            }
                            for column in unique[:10]
                        ],
                        "suggestedRule": suggested,
                        "status": status,
                        "source": source,
                    }

                persisted_gaps = [_gap_to_entry(gaps) for gaps in groups.values()]
                persisted_gaps.extend(_gap_to_entry([gap]) for gap in ungrouped)
                analysis["vocabularyGaps"] = persisted_gaps
        except Exception:
            pass

    return analysis
