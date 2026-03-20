"""Executor-like daemon task tools."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from db_mcp.code_runtime.backend import HostDbMcpRuntime, _normalize_text, _score_text_match
from db_mcp.registry import ConnectionRegistry
from db_mcp.tools.generation import _get_result, _run_sql, _validate_sql

_INLINE_RESULT_TIMEOUT_SECONDS = 30.0
_INLINE_RESULT_POLL_SECONDS = 1.0
_PREPARE_TASK_TIMEOUT_SECONDS = 15.0
_EXECUTE_TASK_TIMEOUT_SECONDS = 45.0


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_connection_name(connection: str | None) -> str:
    if connection:
        return connection
    registry = ConnectionRegistry.get_instance()
    return registry.get_default_name()


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def _unwrap_tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    if isinstance(result, dict):
        return result
    raise TypeError(f"Unsupported tool payload type: {type(result)!r}")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _split_text_blocks(text: str) -> list[str]:
    return [block.strip() for block in text.split("\n\n") if block.strip()]


def _select_relevant_blocks(
    text: str,
    query: str,
    *,
    limit: int = 3,
    max_chars: int = 1500,
) -> str:
    blocks = _split_text_blocks(text)
    if not blocks:
        return ""

    scored: list[tuple[int, str]] = []
    for block in blocks:
        score = _score_text_match(query, block)
        if score <= 0:
            continue
        scored.append((score, block))
    if not scored:
        scored = [(1, blocks[0])]

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected: list[str] = []
    total = 0
    for _, block in scored[:limit]:
        if total and total + len(block) + 2 > max_chars:
            break
        selected.append(block)
        total += len(block) + 2
    return "\n\n".join(selected)


def _table_identifier(table: dict[str, Any]) -> str:
    return str(table.get("full_name") or table.get("name") or table.get("table_name") or "")


def _table_display_name(table: dict[str, Any]) -> str:
    return str(table.get("name") or table.get("table_name") or table.get("full_name") or "")


def _table_aliases(table: dict[str, Any]) -> set[str]:
    aliases = {
        _normalize_text(_table_identifier(table)),
        _normalize_text(_table_display_name(table)),
    }
    aliases.update(
        {
            _normalize_text(str(table.get("full_name") or "")),
            _normalize_text(str(table.get("name") or "")),
            _normalize_text(str(table.get("table_name") or "")),
        }
    )
    aliases.discard("")
    return aliases


def _matches_table_name(raw_value: Any, aliases: set[str]) -> bool:
    value = _normalize_text(str(raw_value))
    return bool(value) and any(
        value == alias or value.endswith(alias) or alias.endswith(value) for alias in aliases
    )


def _context_list(extra_context: dict[str, Any] | None, key: str) -> list[str]:
    if not isinstance(extra_context, dict):
        return []
    value = extra_context.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _context_text(extra_context: dict[str, Any] | None) -> str:
    if not isinstance(extra_context, dict):
        return ""
    return " ".join(str(value) for value in extra_context.values() if value is not None)


def _is_expanded_profile(
    *,
    extra_context: dict[str, Any] | None,
    candidate_scores: list[float],
) -> bool:
    if extra_context:
        return True
    if len(candidate_scores) < 2:
        return False
    return abs(candidate_scores[0] - candidate_scores[1]) <= 20


def _build_table_signals(
    table: dict[str, Any],
    *,
    examples: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    domain_text: str,
    business_rules_text: str,
    sql_rules_text: str,
    extra_context: dict[str, Any] | None,
) -> tuple[int, list[str]]:
    aliases = _table_aliases(table)
    reasons: list[str] = []
    score = 0

    example_hits = 0
    for example in examples:
        for table_name in example.get("tables", []) or []:
            if _matches_table_name(table_name, aliases):
                example_hits += int(example.get("score") or 1)
                break
    if example_hits:
        score += example_hits * 4
        reasons.append(f"matched examples (+{example_hits * 4})")

    rule_hits = 0
    for rule in rules:
        text = str(rule.get("text") or "")
        if any(alias and alias in _normalize_text(text) for alias in aliases):
            rule_hits += int(rule.get("score") or 1)
    if rule_hits:
        score += rule_hits * 3
        reasons.append(f"matched rules (+{rule_hits * 3})")

    domain_hits = _score_text_match(domain_text, *aliases) if domain_text else 0
    if domain_hits:
        score += domain_hits * 2
        reasons.append(f"matched domain model (+{domain_hits * 2})")

    business_rule_hits = (
        _score_text_match(business_rules_text, *aliases) if business_rules_text else 0
    )
    if business_rule_hits:
        score += business_rule_hits * 3
        reasons.append(f"matched business rules (+{business_rule_hits * 3})")

    sql_rule_hits = _score_text_match(sql_rules_text, *aliases) if sql_rules_text else 0
    if sql_rule_hits:
        score += sql_rule_hits * 2
        reasons.append(f"matched SQL rules (+{sql_rule_hits * 2})")

    avoid_tables = {_normalize_text(item) for item in _context_list(extra_context, "avoid_tables")}
    if any(
        alias in avoid_tables or any(avoid.endswith(alias) for avoid in avoid_tables)
        for alias in aliases
    ):
        score -= 1000
        reasons.append("explicitly avoided in refinement context (-1000)")

    must_include_tables = {
        _normalize_text(item) for item in _context_list(extra_context, "must_include_tables")
    }
    if must_include_tables and any(
        alias in must_include_tables
        or any(include.endswith(alias) for include in must_include_tables)
        for alias in aliases
    ):
        score += 200
        reasons.append("explicitly preferred in refinement context (+200)")

    context_hits = _score_text_match(_context_text(extra_context), *aliases)
    if context_hits:
        score += context_hits
        reasons.append(f"matched refinement context (+{context_hits})")

    return score, reasons


def _candidate_tables(
    runtime: HostDbMcpRuntime,
    question: str,
    *,
    extra_context: dict[str, Any] | None = None,
    limit: int = 5,
    examples: list[dict[str, Any]] | None = None,
    rules: list[dict[str, Any]] | None = None,
    domain_text: str = "",
    business_rules_text: str = "",
    sql_rules_text: str = "",
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    examples = examples or []
    rules = rules or []
    for table in runtime._schema_tables():  # internal cached schema helper
        identifier = _table_identifier(table)
        columns = [column for column in table.get("columns", []) if isinstance(column, dict)]
        lexical_score = _score_text_match(
            question,
            identifier,
            table.get("description"),
            " ".join(str(column.get("name", "")) for column in columns),
            " ".join(str(column.get("description", "")) for column in columns),
        )
        signal_score, reasons = _build_table_signals(
            table,
            examples=examples,
            rules=rules,
            domain_text=domain_text,
            business_rules_text=business_rules_text,
            sql_rules_text=sql_rules_text,
            extra_context=extra_context,
        )
        score = lexical_score + signal_score
        if score <= 0 and lexical_score <= 0 and signal_score <= 0:
            continue
        matches.append(
            {
                "identifier": identifier,
                "name": _table_display_name(table),
                "description": table.get("description"),
                "columns": [
                    {
                        "name": column.get("name"),
                        "type": column.get("type"),
                        "description": column.get("description"),
                    }
                    for column in columns
                ],
                "lexical_score": lexical_score,
                "signal_score": signal_score,
                "score": score,
                "reasons": reasons,
            }
        )
    matches.sort(key=lambda item: (-int(item["score"]), str(item["identifier"])))
    return matches[:limit]


def _join_score(left_col: str, right_col: str, right_table: str) -> tuple[int, str] | None:
    left_norm = _normalize_text(left_col)
    right_norm = _normalize_text(right_col)
    right_table_norm = _normalize_text(right_table.split(".")[-1])
    if not left_norm or not right_norm:
        return None
    if left_norm == right_norm and (
        left_norm.endswith("id") or left_norm in {"address", "mint", "symbol"}
    ):
        return 80, "matching identifier columns"
    if right_table_norm and left_norm == f"{right_table_norm}id" and right_norm.endswith("id"):
        return 90, "foreign-key style id match"
    if left_norm.endswith("mint") and right_norm in {"mint", "address"}:
        return 85, "token mint/address match"
    if left_norm.endswith("address") and right_norm in {"address", "mint"}:
        return 75, "address-style identifier match"
    return None


def _infer_join_paths(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    join_paths: list[dict[str, Any]] = []
    for index, left in enumerate(tables):
        for right in tables[index + 1 :]:
            best: tuple[int, dict[str, Any]] | None = None
            for left_col in left.get("columns", []):
                for right_col in right.get("columns", []):
                    score_reason = _join_score(
                        str(left_col.get("name", "")),
                        str(right_col.get("name", "")),
                        str(right.get("identifier", "")),
                    )
                    if score_reason is None:
                        score_reason = _join_score(
                            str(right_col.get("name", "")),
                            str(left_col.get("name", "")),
                            str(left.get("identifier", "")),
                        )
                        if score_reason is not None:
                            score, reason = score_reason
                            candidate = {
                                "left_table": right["identifier"],
                                "left_column": right_col.get("name"),
                                "right_table": left["identifier"],
                                "right_column": left_col.get("name"),
                                "reason": reason,
                                "score": score,
                            }
                            if best is None or score > best[0]:
                                best = (score, candidate)
                            continue
                    if score_reason is not None:
                        score, reason = score_reason
                        candidate = {
                            "left_table": left["identifier"],
                            "left_column": left_col.get("name"),
                            "right_table": right["identifier"],
                            "right_column": right_col.get("name"),
                            "reason": reason,
                            "score": score,
                        }
                        if best is None or score > best[0]:
                            best = (score, candidate)
            if best is not None:
                join_paths.append(best[1])
    join_paths.sort(
        key=lambda item: (
            -int(item["score"]),
            str(item["left_table"]),
            str(item["right_table"]),
        )
    )
    return join_paths[:5]


def _example_payload(example: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(
        {
        "id": example.get("id"),
        "intent": example.get("intent"),
        "sql": example.get("sql"),
        "tables": example.get("tables"),
        "keywords": example.get("keywords"),
        "notes": example.get("notes"),
        "score": example.get("score"),
        }
    )


def _rule_payload(rule: dict[str, Any]) -> dict[str, Any]:
    return _json_safe(
        {
        "source": rule.get("source"),
        "text": rule.get("text"),
        "score": rule.get("score"),
        }
    )


def _build_prepare_context(
    runtime: HostDbMcpRuntime,
    question: str,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema = runtime.schema_descriptions()
    domain_text = _safe_read_text(runtime.connection_path / "domain" / "model.md")
    business_rules_text = _safe_read_text(
        runtime.connection_path / "instructions" / "business_rules.yaml"
    )
    sql_rules_text = _safe_read_text(runtime.connection_path / "instructions" / "sql_rules.md")
    examples = [_example_payload(item) for item in runtime.relevant_examples(question, limit=8)]
    rules = [_rule_payload(item) for item in runtime.relevant_rules(question, limit=8)]
    initial_candidate_tables = _candidate_tables(
        runtime,
        question,
        extra_context=extra_context,
        limit=8,
        examples=examples,
        rules=rules,
        domain_text=domain_text,
        business_rules_text=business_rules_text,
        sql_rules_text=sql_rules_text,
    )
    context_profile = "expanded" if _is_expanded_profile(
        extra_context=extra_context,
        candidate_scores=[float(item.get("score") or 0) for item in initial_candidate_tables[:2]],
    ) else "compact"
    table_limit = 8 if context_profile == "expanded" else 5
    column_limit = 15 if context_profile == "expanded" else 10
    example_limit = 5 if context_profile == "expanded" else 3
    rule_limit = 8 if context_profile == "expanded" else 5
    block_limit = 5 if context_profile == "expanded" else 3
    max_chars = 3000 if context_profile == "expanded" else 1500
    candidate_tables = initial_candidate_tables[:table_limit]
    candidate_columns = runtime.find_columns(question, limit=column_limit)
    domain_context = domain_text.strip()
    business_rules_context = business_rules_text.strip()
    sql_rules_context = _select_relevant_blocks(
        sql_rules_text,
        question,
        limit=block_limit,
        max_chars=max_chars,
    )
    avoid_tables = _context_list(extra_context, "avoid_tables")
    must_apply_filters = _context_list(extra_context, "must_apply_filters")
    recommended_tables = candidate_tables[:2]
    competing_tables = candidate_tables[1:4]
    ambiguous = bool(competing_tables) and (
        context_profile == "expanded"
        or abs(
            float(candidate_tables[0].get("score") or 0)
            - float(candidate_tables[1].get("score") or 0)
        )
        <= 20
    )

    return _json_safe(
        {
            "question": question,
            "connection": runtime.connection,
            "dialect": schema.get("dialect") if isinstance(schema, dict) else None,
            "connector": runtime.connector(),
            "disambiguation": {
                "ambiguous": ambiguous,
                "recommended_tables": recommended_tables,
                "competing_tables": competing_tables,
                "avoid_tables": avoid_tables,
                "must_apply_filters": must_apply_filters,
            },
            "business_rules_context": business_rules_context or None,
            "domain_context": domain_context or None,
            "sql_rules_context": sql_rules_context or None,
            "examples": examples[:example_limit],
            "rules": rules[:rule_limit],
            "candidate_tables": candidate_tables,
            "candidate_columns": candidate_columns,
            "candidate_joins": _infer_join_paths(candidate_tables),
            "client_context": extra_context or {},
            "context_profile": context_profile,
        }
    )


@dataclass
class PreparedTask:
    task_id: str
    connection: str
    question: str
    context: dict[str, Any]
    status: str = "context_ready"
    sql: str | None = None
    validation: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    canceled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "connection": self.connection,
            "question": self.question,
            "status": self.status,
            "sql": self.sql,
            "validation": self.validation,
            "execution": self.execution,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "canceled": self.canceled,
            "context": self.context,
        }


_TASKS: dict[str, PreparedTask] = {}
_TASKS_LOCK = threading.Lock()


def _register_task(task: PreparedTask) -> PreparedTask:
    with _TASKS_LOCK:
        _TASKS[task.task_id] = task
    return task


def _get_task_state(task_id: str) -> PreparedTask | None:
    with _TASKS_LOCK:
        return _TASKS.get(task_id)


def _update_task(task: PreparedTask) -> None:
    task.updated_at = _utc_now()
    with _TASKS_LOCK:
        _TASKS[task.task_id] = task


def _is_async_read_execution(
    *,
    validation: dict[str, Any] | None,
    execution: dict[str, Any],
) -> bool:
    status = str(execution.get("status") or "").lower()
    if status not in {"submitted", "running", "pending"}:
        return False
    if validation and bool(validation.get("is_write")):
        return False
    if bool(execution.get("is_write")):
        return False
    execution_id = execution.get("execution_id") or execution.get("query_id")
    return bool(execution_id)


def _normalize_async_completion(execution: dict[str, Any]) -> dict[str, Any]:
    if str(execution.get("status") or "").lower() != "complete":
        return execution
    normalized = dict(execution)
    normalized["status"] = "success"
    normalized.setdefault("mode", "async_inline")
    return normalized


async def _resolve_inline_execution(
    *,
    connection: str,
    validation: dict[str, Any] | None,
    execution: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    if not _is_async_read_execution(validation=validation, execution=execution):
        return execution, 0

    execution_id = str(execution.get("execution_id") or execution.get("query_id"))
    attempts = max(1, int(_INLINE_RESULT_TIMEOUT_SECONDS / _INLINE_RESULT_POLL_SECONDS))
    latest = execution
    poll_attempts = 0

    for _ in range(attempts):
        poll_attempts += 1
        polled = _unwrap_tool_payload(
            await _get_result(query_id=execution_id, connection=connection)
        )
        status = str(polled.get("status") or "").lower()
        if status == "complete":
            return _normalize_async_completion(polled), poll_attempts
        if status == "error":
            return polled, poll_attempts
        latest = polled
        if status not in {"running", "pending", "submitted"}:
            return polled, poll_attempts
        await asyncio.sleep(_INLINE_RESULT_POLL_SECONDS)

    return latest, poll_attempts


def _observability(
    *,
    stage: str,
    started_at: float,
    timed_out: bool,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "stage": stage,
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 1),
        "timed_out": timed_out,
    }
    payload.update(extra)
    return _json_safe(payload)


async def _prepare_task(
    question: str,
    connection: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble compact structured query context for the external agent."""
    started_at = time.monotonic()
    resolved_connection = _resolve_connection_name(connection)
    runtime = HostDbMcpRuntime(resolved_connection)
    try:
        prepared_context = await asyncio.wait_for(
            asyncio.to_thread(_build_prepare_context, runtime, question, context),
            timeout=_PREPARE_TASK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {
            "status": "timeout",
            "connection": resolved_connection,
            "question": question,
            "error": "prepare_task exceeded its deadline while assembling context.",
            "observability": _observability(
                stage="prepare_task",
                started_at=started_at,
                timed_out=True,
                deadline_seconds=_PREPARE_TASK_TIMEOUT_SECONDS,
            ),
        }
    task = _register_task(
        PreparedTask(
            task_id=uuid.uuid4().hex[:12],
            connection=resolved_connection,
            question=question,
            context=prepared_context,
        )
    )
    return {
        "status": "context_ready",
        "task_id": task.task_id,
        "connection": task.connection,
        "question": task.question,
        "context": task.context,
        "observability": _observability(
            stage="prepare_task",
            started_at=started_at,
            timed_out=False,
            deadline_seconds=_PREPARE_TASK_TIMEOUT_SECONDS,
            context_profile=task.context.get("context_profile", "compact"),
            candidate_table_count=len(task.context.get("candidate_tables", [])),
            ambiguous=bool(task.context.get("disambiguation", {}).get("ambiguous")),
        ),
        "next_step": (
            "Write SQL using the prepared context, then call "
            "execute_task(task_id=..., sql=..., confirmed=False)."
        ),
    }


async def _execute_task_inner(
    task: PreparedTask,
    sql: str,
    confirmed: bool,
) -> tuple[str, dict[str, Any] | None, dict[str, Any], int]:
    validation = _unwrap_tool_payload(await _validate_sql(sql=sql, connection=task.connection))

    if not validation.get("valid", False):
        if "Validation is not supported" in str(validation.get("error", "")):
            execution = _unwrap_tool_payload(
                await _run_sql(
                    connection=task.connection,
                    sql=sql,
                    confirmed=confirmed,
                )
            )
            execution, poll_attempts = await _resolve_inline_execution(
                connection=task.connection,
                validation=validation,
                execution=execution,
            )
            status = "completed" if execution.get("status") == "success" else str(
                execution.get("status") or "failed"
            )
            return status, validation, execution, poll_attempts

        return "validation_error", validation, {}, 0

    if validation.get("write_confirmation_required") and not confirmed:
        return "confirmation_required", validation, {}, 0

    execution = _unwrap_tool_payload(
        await _run_sql(
            connection=task.connection,
            query_id=str(validation.get("query_id")),
            confirmed=confirmed,
        )
    )
    execution, poll_attempts = await _resolve_inline_execution(
        connection=task.connection,
        validation=validation,
        execution=execution,
    )
    status = "completed" if execution.get("status") == "success" else str(
        execution.get("status") or "failed"
    )
    return status, validation, execution, poll_attempts


async def _execute_task(
    task_id: str,
    sql: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Validate and execute SQL for a prepared task."""
    started_at = time.monotonic()
    task = _get_task_state(task_id)
    if task is None:
        return {"status": "error", "error": f"Task {task_id!r} was not found.", "task_id": task_id}
    if task.canceled:
        return {
            "status": "canceled",
            "error": f"Task {task_id!r} has been canceled.",
            "task_id": task_id,
        }

    task.sql = sql
    try:
        status, validation, execution, poll_attempts = await asyncio.wait_for(
            _execute_task_inner(task, sql, confirmed),
            timeout=_EXECUTE_TASK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        task.status = "timeout"
        _update_task(task)
        return {
            "status": "timeout",
            "task_id": task.task_id,
            "connection": task.connection,
            "sql": sql,
            "error": "execute_task exceeded its deadline while validating or executing SQL.",
            "observability": _observability(
                stage="execute_task",
                started_at=started_at,
                timed_out=True,
                deadline_seconds=_EXECUTE_TASK_TIMEOUT_SECONDS,
                inline_resolution_attempts=0,
            ),
        }

    task.validation = validation
    task.execution = execution or None
    task.status = status
    _update_task(task)
    payload = {
        "status": task.status,
        "task_id": task.task_id,
        "connection": task.connection,
        "sql": sql,
        "validation": validation,
        "observability": _observability(
            stage="execute_task",
            started_at=started_at,
            timed_out=False,
            deadline_seconds=_EXECUTE_TASK_TIMEOUT_SECONDS,
            inline_resolution_attempts=poll_attempts,
        ),
    }
    if execution:
        payload["execution"] = execution
    if status == "confirmation_required":
        payload["message"] = (
            validation.get("tier_reason") or "This statement requires explicit confirmation."
        )
    return payload


async def _get_task(task_id: str) -> dict[str, Any]:
    """Return prepared task state and artifacts."""
    task = _get_task_state(task_id)
    if task is None:
        return {"status": "error", "error": f"Task {task_id!r} was not found.", "task_id": task_id}
    return task.to_dict()


async def _cancel_task(task_id: str) -> dict[str, Any]:
    """Cancel a prepared task."""
    task = _get_task_state(task_id)
    if task is None:
        return {"status": "error", "error": f"Task {task_id!r} was not found.", "task_id": task_id}
    task.canceled = True
    task.status = "canceled"
    _update_task(task)
    return {"status": "canceled", "task_id": task_id}
