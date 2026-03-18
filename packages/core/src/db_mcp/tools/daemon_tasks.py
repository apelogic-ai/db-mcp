"""Executor-like daemon task tools."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from db_mcp.code_runtime.backend import HostDbMcpRuntime, _normalize_text, _score_text_match
from db_mcp.registry import ConnectionRegistry
from db_mcp.tools.generation import _run_sql, _validate_sql


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


def _candidate_tables(
    runtime: HostDbMcpRuntime,
    question: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for table in runtime._schema_tables():  # internal cached schema helper
        identifier = _table_identifier(table)
        columns = [column for column in table.get("columns", []) if isinstance(column, dict)]
        score = _score_text_match(
            question,
            identifier,
            table.get("description"),
            " ".join(str(column.get("name", "")) for column in columns),
            " ".join(str(column.get("description", "")) for column in columns),
        )
        if score <= 0:
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
                "score": score,
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
    candidate_tables = _candidate_tables(runtime, question)
    candidate_columns = runtime.find_columns(question, limit=10)
    examples = [_example_payload(item) for item in runtime.relevant_examples(question, limit=3)]
    rules = [_rule_payload(item) for item in runtime.relevant_rules(question, limit=5)]
    domain_context = _select_relevant_blocks(
        _safe_read_text(runtime.connection_path / "domain" / "model.md"),
        question,
    )
    sql_rules_context = _select_relevant_blocks(
        _safe_read_text(runtime.connection_path / "instructions" / "sql_rules.md"),
        question,
    )
    suggested_sql = runtime.plan(question).get("suggested_sql")

    return _json_safe(
        {
        "question": question,
        "connection": runtime.connection,
        "dialect": schema.get("dialect") if isinstance(schema, dict) else None,
        "connector": runtime.connector(),
        "candidate_tables": candidate_tables,
        "candidate_columns": candidate_columns,
        "candidate_joins": _infer_join_paths(candidate_tables),
        "examples": examples,
        "rules": rules,
        "domain_context": domain_context or None,
        "sql_rules_context": sql_rules_context or None,
        "suggested_sql": suggested_sql,
        "client_context": extra_context or {},
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


async def _prepare_task(
    question: str,
    connection: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble compact structured query context for the external agent."""
    resolved_connection = _resolve_connection_name(connection)
    runtime = HostDbMcpRuntime(resolved_connection)
    prepared_context = _build_prepare_context(runtime, question, context)
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
        "next_step": (
            "Write SQL using the prepared context, then call "
            "execute_task(task_id=..., sql=..., confirmed=False)."
        ),
    }


async def _execute_task(
    task_id: str,
    sql: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Validate and execute SQL for a prepared task."""
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
    validation = _unwrap_tool_payload(await _validate_sql(sql=sql, connection=task.connection))
    task.validation = validation

    if not validation.get("valid", False):
        if "Validation is not supported" in str(validation.get("error", "")):
            execution = _unwrap_tool_payload(
                await _run_sql(
                    connection=task.connection,
                    sql=sql,
                    confirmed=confirmed,
                )
            )
            task.execution = execution
            task.status = "completed" if execution.get("status") == "success" else str(
                execution.get("status") or "failed"
            )
            _update_task(task)
            return {
                "status": task.status,
                "task_id": task.task_id,
                "connection": task.connection,
                "sql": sql,
                "validation": validation,
                "execution": execution,
            }

        task.status = "validation_error"
        _update_task(task)
        return {
            "status": "validation_error",
            "task_id": task.task_id,
            "connection": task.connection,
            "sql": sql,
            "validation": validation,
        }

    if validation.get("write_confirmation_required") and not confirmed:
        task.status = "confirmation_required"
        _update_task(task)
        return {
            "status": "confirmation_required",
            "task_id": task.task_id,
            "connection": task.connection,
            "sql": sql,
            "validation": validation,
            "message": validation.get("tier_reason")
            or "This statement requires explicit confirmation.",
        }

    execution = _unwrap_tool_payload(
        await _run_sql(
            connection=task.connection,
            query_id=str(validation.get("query_id")),
            confirmed=confirmed,
        )
    )
    task.execution = execution
    task.status = "completed" if execution.get("status") == "success" else str(
        execution.get("status") or "failed"
    )
    _update_task(task)
    return {
        "status": task.status,
        "task_id": task.task_id,
        "connection": task.connection,
        "sql": sql,
        "validation": validation,
        "execution": execution,
    }


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
