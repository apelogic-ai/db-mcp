"""JSONL trace reader and analysis for historical trace data.

Reads JSONL files written by JSONLSpanExporter and converts them
into the same trace format used by SpanCollector.get_traces().
Also provides trace analysis for semantic layer insights.
"""

import json
import logging
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)


def list_trace_dates(connection_path: Path, user_id: str) -> list[str]:
    """List available YYYY-MM-DD dates from JSONL trace files.

    Args:
        connection_path: Path to the connection directory
        user_id: User identifier for trace subdirectory

    Returns:
        Sorted list of date strings (most recent first)
    """
    traces_dir = connection_path / "traces" / user_id
    if not traces_dir.exists():
        return []

    dates = []
    for f in traces_dir.iterdir():
        if f.suffix == ".jsonl" and f.stem.count("-") == 2:
            dates.append(f.stem)

    dates.sort(reverse=True)
    return dates


def read_traces_from_jsonl(file_path: Path, limit: int = 50) -> list[dict]:
    """Read and parse a JSONL trace file, grouping spans into traces.

    Normalizes the JSONL format to match SpanCollector.get_traces() output:
    - ts (nanoseconds) → start_time (seconds)
    - attrs → attributes
    - parent_id → parent_span_id
    - duration_ms preserved as-is

    Args:
        file_path: Path to the JSONL file
        limit: Maximum number of traces to return

    Returns:
        List of trace dicts matching SpanCollector.get_traces() format
    """
    if not file_path.exists():
        return []

    # Read all spans from JSONL
    spans_by_trace: dict[str, list[dict]] = {}

    try:
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Normalize JSONL format to collector format
                start_time = record.get("ts", 0)
                # ts is in nanoseconds from OTel, convert to seconds
                if start_time > 1e15:
                    start_time = start_time / 1e9

                duration_ms = record.get("duration_ms", 0)
                end_time = start_time + (duration_ms / 1000) if duration_ms else None

                span = {
                    "trace_id": record.get("trace_id", ""),
                    "span_id": record.get("span_id", ""),
                    "parent_span_id": record.get("parent_id"),
                    "name": record.get("name", ""),
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_ms": duration_ms,
                    "status": record.get("status", "OK").lower(),
                    "attributes": record.get("attrs", {}),
                    "events": record.get("events", []),
                }

                trace_id = span["trace_id"]
                if trace_id not in spans_by_trace:
                    spans_by_trace[trace_id] = []
                spans_by_trace[trace_id].append(span)

    except Exception as e:
        logger.error(f"Failed to read JSONL file {file_path}: {e}")
        return []

    # Build trace objects (same shape as SpanCollector.get_traces())
    traces = []
    for trace_id, spans in spans_by_trace.items():
        spans.sort(key=lambda s: s["start_time"])

        start = min(s["start_time"] for s in spans)
        end = max(s["end_time"] or s["start_time"] for s in spans)

        traces.append(
            {
                "trace_id": trace_id,
                "start_time": start,
                "end_time": end,
                "duration_ms": (end - start) * 1000,
                "span_count": len(spans),
                "root_span": spans[0]["name"] if spans else None,
                "spans": spans,
            }
        )

    # Sort by start_time descending (most recent first)
    traces.sort(key=lambda t: t["start_time"], reverse=True)

    return traces[:limit]


# ── Trace analysis for insights ────────────────────────────────────────


def _is_protocol_noise(trace: dict) -> bool:
    """Check if a trace is MCP protocol housekeeping (not user-initiated)."""
    noise = {
        "prompts/list",
        "tools/list",
        "resources/list",
        "initialize",
        "notifications/initialized",
        "ping",
    }
    if trace.get("span_count", 0) > 1:
        return False
    root = (trace.get("root_span") or "").lower()
    return any(p in root for p in noise)


def _extract_sql(span: dict) -> str | None:
    """Extract SQL text from a span's attributes."""
    attrs = span.get("attributes", {})
    return attrs.get("sql") or attrs.get("sql.preview") or None


def _normalize_sql(sql: str) -> str:
    """Normalize SQL for deduplication (strip whitespace, lowercase keywords)."""
    return " ".join(sql.split()).strip()


def analyze_traces(traces: list[dict], connection_path: Path | None = None) -> dict:
    """Analyze traces for semantic layer gaps and inefficiencies.

    Examines tool call patterns to surface:
    - Failed validations and their error patterns
    - Repeated similar queries (AI struggling)
    - Knowledge capture activity (examples saved, feedback given)
    - Tool usage distribution
    - Cost tier distribution
    - Tables referenced

    Args:
        traces: List of trace dicts (from get_traces() or read_traces_from_jsonl)
        connection_path: Path to connection dir for checking knowledge files

    Returns:
        Dict with analysis results for the Insights page
    """
    # Filter out protocol noise
    user_traces = [t for t in traces if not _is_protocol_noise(t)]

    # Counters
    tool_counts: Counter[str] = Counter()
    error_traces: list[dict] = []
    sql_seen: dict[str, list[dict]] = {}  # normalized_sql -> traces
    validation_errors: list[dict] = []
    cost_tiers: Counter[str] = Counter()
    tables_referenced: Counter[str] = Counter()
    knowledge_events: list[dict] = []
    shell_commands: list[dict] = []
    total_duration_ms = 0.0

    for trace in user_traces:
        total_duration_ms += trace.get("duration_ms", 0)

        for span in trace.get("spans", []):
            attrs = span.get("attributes", {})
            name = span.get("name", "")
            tool_name = attrs.get("tool.name", "")

            # Count tool usage
            if tool_name:
                tool_counts[tool_name] += 1

            # Track errors
            is_error = (
                span.get("status") == "error"
                or attrs.get("tool.success") is False
                or str(attrs.get("tool.success", "")).lower() == "false"
            )
            if is_error:
                error_traces.append(
                    {
                        "trace_id": trace.get("trace_id", ""),
                        "span_name": name,
                        "tool": tool_name,
                        "error": attrs.get("tool.error", attrs.get("error.message", "")),
                        "timestamp": span.get("start_time", 0),
                    }
                )

            # Track SQL for dedup analysis
            sql = _extract_sql(span)
            if sql:
                norm = _normalize_sql(sql)
                if norm not in sql_seen:
                    sql_seen[norm] = []
                sql_seen[norm].append(
                    {
                        "trace_id": trace.get("trace_id", ""),
                        "tool": tool_name or name,
                        "timestamp": span.get("start_time", 0),
                    }
                )

            # Validation failures
            if tool_name in ("validate_sql", "explain_sql") or "validate" in name.lower():
                rejected = attrs.get("validation.rejected")
                error_type = attrs.get("error.type")
                if rejected or error_type or is_error:
                    validation_errors.append(
                        {
                            "sql_preview": (sql or "")[:100],
                            "rejected_keyword": rejected,
                            "error_type": error_type,
                            "error_message": attrs.get("error.message", ""),
                            "timestamp": span.get("start_time", 0),
                        }
                    )

            # Cost tiers
            cost_tier = attrs.get("cost_tier")
            if cost_tier:
                cost_tiers[str(cost_tier)] += 1

            # Tables referenced
            for key in ("table_name", "tables_hint"):
                table_val = attrs.get(key)
                if table_val:
                    for t in str(table_val).split(","):
                        t = t.strip()
                        if t:
                            tables_referenced[t] += 1

            # Knowledge capture events
            if tool_name in (
                "query_approve",
                "query_feedback",
                "import_examples",
                "import_instructions",
            ):
                knowledge_events.append(
                    {
                        "tool": tool_name,
                        "feedback_type": attrs.get("feedback_type", ""),
                        "examples_added": attrs.get("examples_added"),
                        "rules_added": attrs.get("rules_added"),
                        "timestamp": span.get("start_time", 0),
                    }
                )

            # Shell commands
            command = attrs.get("command")
            if command or tool_name == "shell":
                shell_commands.append(
                    {
                        "command": str(command or "")[:200],
                        "timestamp": span.get("start_time", 0),
                        "success": not is_error,
                    }
                )

    # Identify repeated SQL (same query executed multiple times)
    repeated_queries = []
    for norm_sql, occurrences in sql_seen.items():
        if len(occurrences) >= 2:
            repeated_queries.append(
                {
                    "sql_preview": norm_sql[:100],
                    "count": len(occurrences),
                    "first_seen": min(o["timestamp"] for o in occurrences),
                    "last_seen": max(o["timestamp"] for o in occurrences),
                }
            )
    repeated_queries.sort(key=lambda r: r["count"], reverse=True)

    # Check knowledge layer completeness
    knowledge_status = _check_knowledge_status(connection_path) if connection_path else {}

    return {
        "traceCount": len(user_traces),
        "protocolTracesFiltered": len(traces) - len(user_traces),
        "totalDurationMs": round(total_duration_ms, 1),
        "toolUsage": dict(tool_counts.most_common(20)),
        "errors": error_traces[:20],
        "errorCount": len(error_traces),
        "validationFailures": validation_errors[:20],
        "validationFailureCount": len(validation_errors),
        "costTiers": dict(cost_tiers),
        "repeatedQueries": repeated_queries[:10],
        "tablesReferenced": dict(tables_referenced.most_common(20)),
        "knowledgeEvents": knowledge_events[:20],
        "knowledgeCaptureCount": len(knowledge_events),
        "shellCommands": shell_commands[:10],
        "knowledgeStatus": knowledge_status,
    }


def _check_knowledge_status(connection_path: Path) -> dict:
    """Check the state of the semantic layer for a connection.

    Returns counts of examples, rules, schema descriptions, etc.
    """
    status: dict[str, object] = {
        "hasSchema": False,
        "hasDomain": False,
        "exampleCount": 0,
        "ruleCount": 0,
    }

    if not connection_path or not connection_path.exists():
        return status

    # Schema descriptions
    schema_file = connection_path / "schema" / "descriptions.yaml"
    status["hasSchema"] = schema_file.exists() and schema_file.stat().st_size > 10

    # Domain model
    domain_file = connection_path / "domain" / "model.md"
    if not domain_file.exists():
        domain_file = connection_path / "domain" / "model.yaml"
    status["hasDomain"] = domain_file.exists() and domain_file.stat().st_size > 10

    # Training examples
    examples_dir = connection_path / "examples"
    if not examples_dir.exists():
        examples_dir = connection_path / "training" / "examples"
    if examples_dir.exists():
        status["exampleCount"] = sum(
            1 for f in examples_dir.iterdir() if f.suffix in (".yaml", ".yml") and f.is_file()
        )

    # Business rules
    rules_file = connection_path / "instructions" / "business_rules.yaml"
    if rules_file.exists():
        try:
            import yaml

            with open(rules_file) as f:
                data = yaml.safe_load(f) or {}
            rules = data.get("rules", [])
            status["ruleCount"] = len(rules) if isinstance(rules, list) else 0
        except Exception:
            pass

    return status
