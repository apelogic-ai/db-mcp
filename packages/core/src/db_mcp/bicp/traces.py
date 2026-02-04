"""JSONL trace reader and analysis for historical trace data.

Reads JSONL files written by JSONLSpanExporter and converts them
into the same trace format used by SpanCollector.get_traces().
Also provides trace analysis for semantic layer insights.
"""

import json
import logging
import re
from collections import Counter, defaultdict
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
    """Extract SQL text from a span's attributes.

    Checks multiple attribute keys where SQL may be stored:
    - attrs.sql / attrs.sql.preview (standard instrumentation)
    - attrs.args (JSON-encoded tool arguments, e.g. {"sql": "SELECT ..."})
    """
    attrs = span.get("attributes", {})
    sql = attrs.get("sql") or attrs.get("sql.preview")
    if sql:
        return sql

    # Try extracting from args JSON (e.g. api_execute_sql stores SQL in args)
    args_str = attrs.get("args")
    if args_str and isinstance(args_str, str):
        try:
            args_data = json.loads(args_str)
            if isinstance(args_data, dict):
                sql = args_data.get("sql")
                if sql:
                    return sql
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def _normalize_sql(sql: str) -> str:
    """Normalize SQL for deduplication (strip whitespace, lowercase keywords)."""
    return " ".join(sql.split()).strip()


def _summarize_sql(sql: str) -> str:
    """Generate a short human-readable summary of a SQL query.

    Extracts the main operation, tables, and key clauses to produce
    a natural-language hint like "Count records from users grouped by status".
    """
    import re

    upper = sql.upper()
    parts: list[str] = []

    # Detect main operation
    if re.search(r"\bCOUNT\s*\(", upper):
        parts.append("Count")
    elif re.search(r"\bAVG\s*\(", upper):
        parts.append("Average")
    elif re.search(r"\bSUM\s*\(", upper):
        parts.append("Sum")
    elif re.search(r"\bMAX\s*\(", upper):
        parts.append("Max")
    elif re.search(r"\bMIN\s*\(", upper):
        parts.append("Min")
    elif upper.lstrip().startswith("SELECT"):
        parts.append("Select")
    elif upper.lstrip().startswith("WITH"):
        parts.append("Query")

    # Extract tables from FROM clause
    from_match = re.search(r"\bFROM\s+([^\s,(]+)", sql, re.IGNORECASE)
    if from_match:
        table = from_match.group(1).split(".")[-1]  # last part of dotted name
        parts.append(f"from {table}")

    # JOIN tables
    joins = re.findall(r"\bJOIN\s+([^\s,(]+)", sql, re.IGNORECASE)
    if joins:
        join_tables = [j.split(".")[-1] for j in joins[:2]]
        parts.append(f"joining {', '.join(join_tables)}")

    # WHERE hint
    if re.search(r"\bWHERE\b", upper):
        parts.append("with filters")

    # GROUP BY hint
    if re.search(r"\bGROUP\s+BY\b", upper):
        parts.append("grouped")

    # ORDER BY / LIMIT hint
    if re.search(r"\bORDER\s+BY\b", upper):
        parts.append("ordered")
    if re.search(r"\bLIMIT\b", upper):
        parts.append("limited")

    return " ".join(parts) if parts else "SQL query"


# Words too generic to be meaningful business terms — filter these out
_STOP_WORDS = frozenset(
    {
        # Vault structure words
        "table",
        "tables",
        "column",
        "columns",
        "schema",
        "schemas",
        "domain",
        "example",
        "examples",
        "instruction",
        "instructions",
        "rule",
        "rules",
        "training",
        "metrics",
        "learnings",
        "vault",
        "connection",
        # File types / extensions
        "yaml",
        "yml",
        "md",
        "json",
        "csv",
        "txt",
        # Common grep noise
        "description",
        "descriptions",
        "name",
        "type",
        "id",
        "key",
        "value",
        "select",
        "from",
        "where",
        "join",
        "order",
        "group",
        "limit",
        "having",
        "insert",
        "update",
        "delete",
        "create",
        "drop",
        "alter",
        "index",
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "distinct",
        "between",
        "like",
        "null",
        "true",
        "false",
        "case",
        "when",
        "then",
        "else",
        "end",
        "duration",
        "timestamp",
        "date",
        "time",
        "interval",
        "cast",
        # Single characters and very short tokens
        "a",
        "an",
        "the",
        "is",
        "in",
        "on",
        "of",
        "to",
        "for",
        "and",
        "or",
    }
)


def _extract_search_terms(command: str) -> list[str]:
    """Extract search terms from grep/find commands.

    Parses patterns like:
        grep -ri "venue" examples/       → ["venue"]
        grep -i 'CUI' schema/            → ["CUI"]
        find examples -name "*cui*"       → ["cui"]
        grep -rn "nas_id" schema/ examples/  → ["nas_id"]

    Filters out structural/generic words that aren't real business terms.
    """
    terms: list[str] = []
    cmd_lower = command.lower().strip()

    if cmd_lower.startswith("grep"):
        # Extract quoted arguments from grep commands
        quoted = re.findall(r"""['"]([^'"]+)['"]""", command)
        for q in quoted:
            # Skip file paths and glob patterns
            if "/" in q or q.startswith(".") or q.startswith("*"):
                continue
            # Split on regex alternation (\|) first, then clean each part
            # e.g. "cui\b\|CUI\b" → ["cui\b", "CUI\b"] → ["cui", "CUI"]
            parts = re.split(r"\\?\|", q)
            for part in parts:
                # Strip regex metacharacters: \b \w \d anchors etc.
                cleaned = re.sub(r"\\[bBwWdDsS]", "", part)
                cleaned = re.sub(r"[\\^$.*+?{}()\[\]:\-]+", "", cleaned)
                cleaned = cleaned.strip().lower()
                if cleaned and len(cleaned) >= 2 and cleaned not in _STOP_WORDS:
                    terms.append(cleaned)

    elif cmd_lower.startswith("find"):
        # find ... -name "*pattern*" or -iname "*pattern*"
        name_matches = re.findall(r'-i?name\s+["\']?\*?([^"\'*\s]+)\*?["\']?', command, re.I)
        for t in name_matches:
            cleaned = t.lower().strip()
            if cleaned and len(cleaned) >= 2 and cleaned not in _STOP_WORDS:
                terms.append(cleaned)

    return terms


def _are_similar(a: str, b: str) -> bool:
    """Check if two terms are similar enough to group together.

    Uses substring matching and underscore-stripped comparison.
    e.g. "nas_id" and "nasid" → True, "cui" and "nasid" → False
    """
    a_stripped = a.replace("_", "").replace("-", "")
    b_stripped = b.replace("_", "").replace("-", "")

    # One is substring of other (min length 2)
    if len(a) >= 2 and len(b) >= 2:
        if a_stripped in b_stripped or b_stripped in a_stripped:
            return True

    return False


def _find_schema_matches(terms: list[str], connection_path: Path | None) -> list[dict]:
    """Find schema columns/tables whose names contain any of the given terms.

    Returns list of {name, table, type} matches.
    """
    if not connection_path:
        return []

    schema_file = connection_path / "schema" / "descriptions.yaml"
    if not schema_file.exists() or schema_file.stat().st_size < 10:
        return []

    try:
        import yaml

        with open(schema_file) as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []

    matches: list[dict] = []
    seen: set[str] = set()
    tables = data.get("tables", [])

    for table in tables:
        table_name = (table.get("full_name") or table.get("name", "")).lower()
        for term in terms:
            if term in table_name.replace("_", "") or term in table_name:
                key = f"table:{table_name}"
                if key not in seen:
                    seen.add(key)
                    matches.append(
                        {
                            "name": table.get("full_name") or table.get("name", ""),
                            "description": table.get("description", ""),
                            "type": "table",
                        }
                    )

        for col in table.get("columns", []):
            col_name = col.get("name", "").lower()
            for term in terms:
                if term in col_name.replace("_", "") or term in col_name:
                    key = f"col:{table_name}.{col_name}"
                    if key not in seen:
                        seen.add(key)
                        matches.append(
                            {
                                "name": col.get("name", ""),
                                "table": table.get("full_name") or table.get("name", ""),
                                "description": col.get("description", ""),
                                "type": "column",
                            }
                        )

    return matches[:5]  # Limit to top 5 matches


def _detect_vocabulary_gaps(traces: list[dict], connection_path: Path | None = None) -> list[dict]:
    """Detect vocabulary gap patterns and group related terms.

    A vocabulary gap occurs when the agent can't map a user's business term
    to the schema, causing a burst of grep/find shell commands all searching
    for the same term with no results.

    Detection heuristic:
    - Group shell traces by session.id
    - Within each session, extract search terms from grep/find commands
    - If a term appears in 3+ search commands, flag it as an unmapped term
    - Group related terms (same session + substring similarity)
    - Find potential schema column matches for each group
    - Suggest a business rule synonym string

    Returns:
        List of grouped gap dicts:
        [{
            terms: [{term, searchCount, session, timestamp}],
            totalSearches: int,
            timestamp: float,
            schemaMatches: [{name, table?, description, type}],
            suggestedRule: str | None,
        }]
    """
    # Group shell search commands by session
    session_searches: dict[str, list[dict]] = defaultdict(list)

    for trace_data in traces:
        for span in trace_data.get("spans", []):
            attrs = span.get("attributes", {})
            tool_name = attrs.get("tool.name", "")
            command = attrs.get("command", "")
            session_id = attrs.get("session.id", "unknown")

            if tool_name != "shell" or not command:
                continue

            terms = _extract_search_terms(command)
            for term in terms:
                session_searches[session_id].append(
                    {
                        "term": term,
                        "command": command[:200],
                        "timestamp": span.get("start_time", 0),
                        "trace_id": trace_data.get("trace_id", ""),
                    }
                )

    # Find terms searched 3+ times within a session
    raw_gaps: list[dict] = []
    seen_terms: set[str] = set()

    for session_id, searches in session_searches.items():
        term_counts: Counter[str] = Counter(s["term"] for s in searches)
        for term, count in term_counts.items():
            if count >= 3 and term not in seen_terms:
                first = min(s["timestamp"] for s in searches if s["term"] == term)
                raw_gaps.append(
                    {
                        "term": term,
                        "searchCount": count,
                        "session": session_id[:8],
                        "timestamp": first,
                    }
                )
                seen_terms.add(term)

    if not raw_gaps:
        return []

    # ── Group related terms ─────────────────────────────────────────
    # Two terms are grouped if they share a session OR are substring-similar.
    # Use union-find to merge groups.
    parent: dict[int, int] = {i: i for i in range(len(raw_gaps))}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pa] = pb

    for i in range(len(raw_gaps)):
        for j in range(i + 1, len(raw_gaps)):
            # Only group by substring similarity — same session alone
            # is not enough (user may search multiple unrelated terms)
            if _are_similar(raw_gaps[i]["term"], raw_gaps[j]["term"]):
                union(i, j)

    # Build groups
    groups_map: dict[int, list[int]] = defaultdict(list)
    for i in range(len(raw_gaps)):
        groups_map[find(i)].append(i)

    # Build final grouped output
    grouped_gaps: list[dict] = []
    for indices in groups_map.values():
        group_terms = [raw_gaps[i] for i in indices]
        group_terms.sort(key=lambda g: g["searchCount"], reverse=True)
        total_searches = sum(g["searchCount"] for g in group_terms)
        earliest = min(g["timestamp"] for g in group_terms)

        # Find schema matches for this group
        term_strings = [g["term"] for g in group_terms]
        schema_matches = _find_schema_matches(term_strings, connection_path)

        # Build suggested rule
        suggested_rule = _build_suggested_rule(term_strings, schema_matches)

        grouped_gaps.append(
            {
                "terms": group_terms,
                "totalSearches": total_searches,
                "timestamp": earliest,
                "schemaMatches": schema_matches,
                "suggestedRule": suggested_rule,
            }
        )

    grouped_gaps.sort(key=lambda g: g["totalSearches"], reverse=True)
    return grouped_gaps


def _build_suggested_rule(terms: list[str], schema_matches: list[dict]) -> str | None:
    """Build a suggested business rule synonym string.

    e.g. "CUI, chargeable_user_identity, nas_id are synonyms."
    Includes the best schema column match if found.
    """
    # Collect unique names: user terms + matched column names
    all_names: list[str] = []
    seen: set[str] = set()

    # Add schema column matches first (canonical names)
    for m in schema_matches:
        if m["type"] == "column":
            name = m["name"]
            if name.lower() not in seen:
                seen.add(name.lower())
                all_names.append(name)

    # Add user search terms
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            all_names.append(t)

    if len(all_names) < 2:
        return None

    return ", ".join(all_names) + " are synonyms."


def _detect_filesystem_captures(connection_path: Path | None, days: int = 7) -> list[dict]:
    """Detect knowledge captures by checking example file modification times.

    This is a fallback for when span instrumentation isn't present (e.g. the
    MCP server hasn't been restarted after adding training.py spans). It checks
    the examples/ directory for files created/modified within the analysis window.

    Args:
        connection_path: Path to the connection directory
        days: Number of days to look back

    Returns:
        List of capture dicts: [{type, filename, timestamp}]
    """
    if not connection_path or not connection_path.exists():
        return []

    import time as _time

    cutoff = _time.time() - (days * 86400)
    captures: list[dict] = []

    # Check examples directory
    examples_dir = connection_path / "examples"
    if not examples_dir.exists():
        examples_dir = connection_path / "training" / "examples"

    if examples_dir.exists():
        for f in examples_dir.iterdir():
            if f.suffix in (".yaml", ".yml") and f.is_file():
                mtime = f.stat().st_mtime
                if mtime >= cutoff:
                    # Read intent from example file
                    intent = None
                    try:
                        import yaml

                        with open(f) as fh:
                            data = yaml.safe_load(fh)
                        if isinstance(data, dict):
                            intent = data.get("intent")
                    except Exception:
                        pass
                    captures.append(
                        {
                            "type": "example_saved",
                            "filename": f.name,
                            "intent": intent,
                            "timestamp": mtime,
                        }
                    )

    # Check feedback file
    feedback_file = connection_path / "training" / "feedback.yaml"
    if feedback_file.exists():
        mtime = feedback_file.stat().st_mtime
        if mtime >= cutoff:
            captures.append(
                {
                    "type": "feedback_given",
                    "filename": feedback_file.name,
                    "timestamp": mtime,
                }
            )

    captures.sort(key=lambda c: c["timestamp"], reverse=True)
    return captures


def analyze_traces(traces: list[dict], connection_path: Path | None = None, days: int = 7) -> dict:
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

    # Knowledge-flow tracking
    knowledge_usage_snapshots: list[dict] = []  # per-get_data call
    knowledge_captures: list[dict] = []  # per-approve/feedback/import call
    sessions_seen: set[str] = set()

    for trace in user_traces:
        total_duration_ms += trace.get("duration_ms", 0)

        for span in trace.get("spans", []):
            attrs = span.get("attributes", {})
            name = span.get("name", "")
            tool_name = attrs.get("tool.name", "")

            # Count tool usage
            if tool_name:
                tool_counts[tool_name] += 1

            # Track errors (hard failures: exceptions, and soft failures: error results)
            is_error = (
                span.get("status") == "error"
                or attrs.get("tool.success") is False
                or str(attrs.get("tool.success", "")).lower() == "false"
            )
            is_soft_failure = (
                attrs.get("tool.soft_failure") is True
                or str(attrs.get("tool.soft_failure", "")).lower() == "true"
            )
            if is_error or is_soft_failure:
                # Extract SQL if available for this error
                error_sql = _extract_sql(span)
                error_traces.append(
                    {
                        "trace_id": trace.get("trace_id", ""),
                        "span_name": name,
                        "tool": tool_name,
                        "error": attrs.get("tool.error")
                        or attrs.get("tool.failure_detail")
                        or attrs.get("error.message", ""),
                        "error_type": "hard" if is_error else "soft",
                        "timestamp": span.get("start_time", 0),
                        "sql": error_sql,  # Include SQL for save-as-learning feature
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
            if (
                tool_name in ("validate_sql", "explain_sql", "get_data")
                or "validate" in name.lower()
            ):
                rejected = attrs.get("validation.rejected")
                error_type = attrs.get("error.type")
                failure_detail = attrs.get("tool.failure_detail")
                if rejected or error_type or is_error or (is_soft_failure and sql):
                    validation_errors.append(
                        {
                            "sql_preview": (sql or "")[:100],
                            "rejected_keyword": rejected,
                            "error_type": error_type
                            or ("soft_failure" if is_soft_failure else None),
                            "error_message": failure_detail or attrs.get("error.message", ""),
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

            # Session tracking
            session_id = attrs.get("session.id")
            if session_id:
                sessions_seen.add(str(session_id))

            # Knowledge usage (from get_data spans instrumented in generation.py)
            examples_avail = attrs.get("knowledge.examples_available")
            if examples_avail is not None:
                knowledge_usage_snapshots.append(
                    {
                        "tool": tool_name or name,
                        "schema_tables": attrs.get("knowledge.schema_tables", 0),
                        "examples_available": examples_avail,
                        "examples_in_context": attrs.get("knowledge.examples_in_context", 0),
                        "rules_available": attrs.get("knowledge.rules_available", 0),
                        "timestamp": span.get("start_time", 0),
                    }
                )

            # Knowledge capture (from training.py instrumentation)
            capture_type = attrs.get("knowledge.capture")
            if capture_type:
                knowledge_captures.append(
                    {
                        "type": str(capture_type),
                        "total_examples": attrs.get("knowledge.total_examples"),
                        "total_rules": attrs.get("knowledge.total_rules"),
                        "total_feedback": attrs.get("knowledge.total_feedback"),
                        "feedback_type": attrs.get("knowledge.feedback_type"),
                        "timestamp": span.get("start_time", 0),
                    }
                )

    # Identify repeated SQL (same query executed multiple times)
    repeated_queries = []
    for norm_sql, occurrences in sql_seen.items():
        if len(occurrences) >= 2:
            repeated_queries.append(
                {
                    "sql_preview": norm_sql[:100],
                    "full_sql": norm_sql,
                    "suggested_intent": _summarize_sql(norm_sql),
                    "count": len(occurrences),
                    "first_seen": min(o["timestamp"] for o in occurrences),
                    "last_seen": max(o["timestamp"] for o in occurrences),
                    "is_example": False,
                    "example_id": None,
                }
            )
    repeated_queries.sort(key=lambda r: r["count"], reverse=True)

    # Check which repeated queries / errors are already saved as training examples
    if connection_path and (repeated_queries or error_traces):
        try:
            from db_mcp.training.store import load_examples

            provider_id = connection_path.name
            examples = load_examples(provider_id)
            example_sqls: dict[str, str] = {}
            for ex in examples.examples:
                example_sqls[_normalize_sql(ex.sql)] = ex.id
            for rq in repeated_queries:
                ex_id = example_sqls.get(rq["full_sql"])
                if ex_id:
                    rq["is_example"] = True
                    rq["example_id"] = ex_id
            for et in error_traces:
                if et.get("sql"):
                    ex_id = example_sqls.get(_normalize_sql(et["sql"]))
                    if ex_id:
                        et["is_saved"] = True
                        et["example_id"] = ex_id
        except Exception:
            pass

    # Check knowledge layer completeness
    knowledge_status = _check_knowledge_status(connection_path) if connection_path else {}

    # ── Compute real insights ───────────────────────────────────────────

    # 1. "Is the agent finding what it needs?"
    #    Look at knowledge usage snapshots — were examples/rules available?
    generation_calls = len(knowledge_usage_snapshots)
    calls_with_examples = sum(
        1 for s in knowledge_usage_snapshots if s.get("examples_in_context", 0) > 0
    )
    calls_with_rules = sum(1 for s in knowledge_usage_snapshots if s.get("rules_available", 0) > 0)
    calls_without_examples = generation_calls - calls_with_examples

    # 2. "Is it using prior knowledge to cut the line?"
    #    Ratio of generation calls that had examples in context
    example_hit_rate = (
        round(calls_with_examples / generation_calls * 100) if generation_calls > 0 else None
    )

    # 3. "Are there SQL generation mistakes?"
    #    Already captured in error_traces and validation_errors
    #    Add: ratio of validate_sql calls that failed
    validate_calls = tool_counts.get("validate_sql", 0)
    validate_fail_rate = (
        round(len(validation_errors) / validate_calls * 100) if validate_calls > 0 else None
    )

    # 4. "Are we capturing new knowledge?"
    #    Compare knowledge capture events to total tool traces
    #    Use filesystem fallback when spans lack instrumentation
    capture_by_type: Counter[str] = Counter()
    for kc in knowledge_captures:
        capture_by_type[kc["type"]] += 1

    # Filesystem-based fallback: detect captures from file modification times
    fs_captures = _detect_filesystem_captures(connection_path, days=days)
    if fs_captures and not knowledge_captures:
        # No span-based captures found — use filesystem detection instead
        for fc in fs_captures:
            capture_by_type[fc["type"]] += 1
            knowledge_captures.append(
                {
                    "type": fc["type"],
                    "total_examples": None,
                    "total_rules": None,
                    "total_feedback": None,
                    "feedback_type": None,
                    "timestamp": fc["timestamp"],
                    "filename": fc.get("filename"),
                    "intent": fc.get("intent"),
                    "source": "filesystem",
                }
            )

    insights = {
        "generationCalls": generation_calls,
        "callsWithExamples": calls_with_examples,
        "callsWithRules": calls_with_rules,
        "callsWithoutExamples": calls_without_examples,
        "exampleHitRate": example_hit_rate,
        "validateCalls": validate_calls,
        "validateFailRate": validate_fail_rate,
        "knowledgeCapturesByType": dict(capture_by_type),
        "sessionCount": len(sessions_seen),
    }

    # ── Vocabulary gap detection ──────────────────────────────────────
    # Detect new gaps from traces
    trace_detected_gaps = _detect_vocabulary_gaps(user_traces, connection_path)

    # Persist newly detected gaps and read back the full persisted list
    persisted_gaps: list[dict] = []
    if connection_path:
        try:
            from db_mcp.gaps.store import load_gaps_from_path, merge_trace_gaps

            # Persist any newly detected trace gaps
            if trace_detected_gaps:
                provider_id_for_gaps = connection_path.name
                merge_trace_gaps(provider_id_for_gaps, trace_detected_gaps)

            # Read back all persisted gaps, rebuilding groups by group_id
            all_gaps = load_gaps_from_path(connection_path)

            # Group gaps by group_id (ungrouped gaps get their own entry)
            groups: dict[str, list] = {}  # group_id -> list of gaps
            ungrouped: list = []
            for gap in all_gaps.gaps:
                if gap.group_id:
                    groups.setdefault(gap.group_id, []).append(gap)
                else:
                    ungrouped.append(gap)

            def _gap_to_entry(gap_list: list) -> dict:
                terms = []
                all_columns: list[str] = []
                suggested = None
                earliest = float("inf")
                status = "resolved"  # resolved unless any is open
                source = gap_list[0].source.value if gap_list else "traces"
                for g in gap_list:
                    terms.append(
                        {
                            "term": g.term,
                            "searchCount": 0,
                            "session": "",
                            "timestamp": g.detected_at.timestamp(),
                        }
                    )
                    all_columns.extend(g.related_columns)
                    if g.suggested_rule:
                        suggested = g.suggested_rule
                    earliest = min(earliest, g.detected_at.timestamp())
                    if g.status.value == "open":
                        status = "open"
                    source = g.source.value
                # Deduplicate columns
                seen_cols: set[str] = set()
                unique_cols: list[str] = []
                for c in all_columns:
                    if c not in seen_cols:
                        seen_cols.add(c)
                        unique_cols.append(c)
                return {
                    "id": gap_list[0].id,
                    "terms": terms,
                    "totalSearches": 0,
                    "timestamp": earliest,
                    "schemaMatches": [
                        {"name": c.split(".")[-1], "table": c, "type": "column"}
                        for c in unique_cols[:10]
                    ],
                    "suggestedRule": suggested,
                    "status": status,
                    "source": source,
                }

            for gap_list in groups.values():
                persisted_gaps.append(_gap_to_entry(gap_list))
            for gap in ungrouped:
                persisted_gaps.append(_gap_to_entry([gap]))
        except Exception as e:
            logger.warning(f"Failed to persist knowledge gaps: {e}")
            persisted_gaps = trace_detected_gaps
    else:
        persisted_gaps = trace_detected_gaps

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
        "knowledgeEvents": _merge_knowledge_events(knowledge_events, knowledge_captures)[:20],
        "knowledgeCaptureCount": len(knowledge_events) or len(knowledge_captures),
        "shellCommands": shell_commands[:10],
        "knowledgeStatus": knowledge_status,
        "insights": insights,
        "vocabularyGaps": persisted_gaps,
    }


def _merge_knowledge_events(events: list[dict], captures: list[dict]) -> list[dict]:
    """Merge span-based knowledge events with filesystem-detected captures.

    If there are explicit tool events (query_approve, etc.), use those.
    Otherwise fall back to filesystem captures, converting them to the
    same format so the UI can display detail rows.
    """
    if events:
        return sorted(events, key=lambda e: e.get("timestamp", 0), reverse=True)

    # Convert filesystem captures to event format
    merged = []
    for cap in captures:
        merged.append(
            {
                "tool": cap.get("type", "unknown"),
                "feedback_type": cap.get("feedback_type"),
                "examples_added": cap.get("total_examples"),
                "rules_added": cap.get("total_rules"),
                "filename": cap.get("filename"),
                "intent": cap.get("intent"),
                "timestamp": cap.get("timestamp", 0),
            }
        )
    return sorted(merged, key=lambda e: e.get("timestamp", 0), reverse=True)


def _check_knowledge_status(connection_path: Path) -> dict:
    """Check the state of the semantic layer for a connection.

    Returns counts of examples, rules, schema descriptions, etc.
    """
    status: dict[str, object] = {
        "hasSchema": False,
        "hasDomain": False,
        "exampleCount": 0,
        "ruleCount": 0,
        "metricCount": 0,
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

    # Metrics catalog (count only approved metrics)
    catalog_file = connection_path / "metrics" / "catalog.yaml"
    if catalog_file.exists():
        try:
            import yaml

            with open(catalog_file) as f:
                data = yaml.safe_load(f) or {}
            metrics = data.get("metrics", [])
            if isinstance(metrics, list):
                status["metricCount"] = sum(
                    1 for m in metrics if isinstance(m, dict) and m.get("status") != "candidate"
                )
        except Exception:
            pass

    return status
