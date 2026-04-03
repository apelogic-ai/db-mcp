"""Shared backend for Python-native code execution."""

from __future__ import annotations

import json
import re
import shlex
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from db_mcp_knowledge.business_rules import extract_business_rule_texts

from db_mcp.exec_runtime import ExecRuntimeError, ExecSandboxSpec, ExecSessionManager
from db_mcp.tools.utils import require_connection, resolve_connection

_CODE_RUNTIME_MODULE = """\
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from sqlalchemy import create_engine, inspect, text


class CodeModeConfirmationRequired(RuntimeError):
    pass


def _read_yaml(path: Path):
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _extract_rule_texts(value):
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        rules = []
        for item in value:
            rules.extend(_extract_rule_texts(item))
        return rules
    if isinstance(value, dict):
        if "rules" in value:
            return _extract_rule_texts(value.get("rules"))
        for key in ("rule", "rule_text", "text", "description", "summary", "note"):
            if key in value:
                return _extract_rule_texts(value.get(key))
    return []


def _camel_case_words(value: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\\1 \\2", value)


def _normalize_text(value: object) -> str:
    text_value = _camel_case_words(str(value or ""))
    return " ".join(part for part in re.split(r"[^a-z0-9]+", text_value.lower()) if part)


def _tokenize(value: object) -> set[str]:
    tokens = set()
    for token in _normalize_text(value).split():
        tokens.add(token)
        if token.endswith("s") and len(token) > 3:
            tokens.add(token[:-1])
    return tokens


def _score_text_match(query: str, *values: object) -> int:
    query_norm = _normalize_text(query)
    query_tokens = _tokenize(query)
    if not query_tokens and not query_norm:
        return 0

    score = 0
    for value in values:
        value_norm = _normalize_text(value)
        value_tokens = _tokenize(value)
        if not value_norm and not value_tokens:
            continue
        overlap = query_tokens & value_tokens
        if overlap:
            score += len(overlap) * 10
        if query_norm and value_norm:
            if query_norm in value_norm:
                score += 15
            if value_norm in query_norm:
                score += 8
    return score


def _leading_keyword(sql: str) -> str:
    stripped = sql.lstrip()
    while stripped.startswith("--"):
        _, _, stripped = stripped.partition("\\n")
        stripped = stripped.lstrip()
    while stripped.startswith("/*"):
        _, _, stripped = stripped.partition("*/")
        stripped = stripped.lstrip()
    token = stripped.split(None, 1)[0] if stripped else ""
    return token.upper()


def _is_write_sql(sql: str) -> bool:
    first = _leading_keyword(sql)
    return first not in {"", "SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA"}


class DbMcpRuntime:
    def __init__(self, workspace: Path, *, confirmed: bool = False):
        self.workspace = workspace
        self.confirmed = confirmed
        self._connector = None
        self._engine = None

    def read_text(self, relative_path: str) -> str:
        return (self.workspace / relative_path).read_text()

    def read_yaml(self, relative_path: str):
        return _read_yaml(self.workspace / relative_path)

    def read_protocol(self) -> str:
        return self.read_text("PROTOCOL.md")

    def ack_protocol(self) -> str:
        return self.read_protocol()

    def protocol_text(self) -> str:
        return self.read_protocol()

    def connector(self):
        if self._connector is None:
            self._connector = _read_yaml(self.workspace / "connector.yaml")
        return self._connector

    def schema_descriptions(self):
        return self.read_yaml("schema/descriptions.yaml")

    def _schema_tables(self):
        schema = self.schema_descriptions()
        if isinstance(schema, dict):
            tables = schema.get("tables", {})
            if isinstance(tables, list):
                return [table for table in tables if isinstance(table, dict)]
            if isinstance(tables, dict):
                rows = []
                for name, payload in tables.items():
                    if isinstance(payload, dict):
                        row = dict(payload)
                        row.setdefault("name", name)
                        rows.append(row)
                    else:
                        rows.append({"name": name})
                return rows
        return []

    def table_names(self):
        tables = self._schema_tables()
        names = sorted(
            str(table.get("name") or table.get("table_name"))
            for table in tables
            if table.get("name") or table.get("table_name")
        )
        if names:
            return names
        return sorted(inspect(self.engine()).get_table_names())

    def describe_table(self, name: str):
        query_norm = _normalize_text(name)
        best_match = None
        best_score = -1
        for table in self._schema_tables():
            table_name = table.get("name") or table.get("table_name") or ""
            score = _score_text_match(query_norm, table_name, table.get("full_name"))
            if query_norm == _normalize_text(table_name):
                score += 100
            if score > best_score:
                best_score = score
                best_match = table
        if best_match is not None and best_score > 0:
            payload = dict(best_match)
            payload["name"] = payload.get("name") or payload.get("table_name")
            payload["columns"] = [
                dict(column) for column in payload.get("columns", []) if isinstance(column, dict)
            ]
            return payload

        inspector = inspect(self.engine())
        for table_name in inspector.get_table_names():
            if _normalize_text(table_name) == query_norm:
                return {
                    "name": table_name,
                    "schema": None,
                    "catalog": None,
                    "full_name": table_name,
                    "description": None,
                    "status": "live",
                    "columns": [
                        {
                            "name": column.get("name"),
                            "type": str(column.get("type")),
                            "description": None,
                        }
                        for column in inspector.get_columns(table_name)
                    ],
                }
        return None

    def find_tables(self, query: str, limit: int = 5):
        matches = []
        for table in self._schema_tables():
            name = table.get("name") or table.get("table_name") or ""
            columns = [column.get("name", "") for column in table.get("columns", [])]
            score = _score_text_match(
                query,
                name,
                table.get("full_name"),
                table.get("description"),
                " ".join(columns),
            )
            if score <= 0:
                continue
            matches.append(
                {
                    "name": name,
                    "full_name": table.get("full_name") or name,
                    "description": table.get("description"),
                    "columns": columns,
                    "score": score,
                }
            )
        matches.sort(key=lambda item: (-item["score"], item["name"]))
        return matches[:limit]

    def find_table(self, query: str):
        matches = self.find_tables(query, limit=1)
        return matches[0] if matches else None

    def find_columns(self, query: str, limit: int = 10):
        matches = []
        for table in self._schema_tables():
            table_name = table.get("name") or table.get("table_name") or ""
            for column in table.get("columns", []):
                if not isinstance(column, dict):
                    continue
                score = _score_text_match(
                    query,
                    column.get("name"),
                    column.get("description"),
                    column.get("type"),
                    table_name,
                )
                if score <= 0:
                    continue
                matches.append(
                    {
                        "table": table_name,
                        "name": column.get("name"),
                        "type": column.get("type"),
                        "description": column.get("description"),
                        "score": score,
                    }
                )
        matches.sort(key=lambda item: (-item["score"], item["table"], item["name"]))
        return matches[:limit]

    def _load_examples(self):
        examples_dir = self.workspace / "examples"
        if not examples_dir.exists():
            return []
        records = []
        for path in sorted(examples_dir.glob("*.yaml")):
            payload = _read_yaml(path)
            if isinstance(payload, dict):
                payload = dict(payload)
                payload.setdefault("id", path.stem)
                records.append(payload)
        return records

    def relevant_examples(self, query: str, limit: int = 5):
        matches = []
        for example in self._load_examples():
            score = _score_text_match(
                query,
                example.get("id"),
                example.get("intent"),
                example.get("notes"),
                " ".join(example.get("tables", []) or []),
                " ".join(example.get("keywords", []) or []),
                example.get("sql"),
            )
            if score <= 0:
                continue
            payload = dict(example)
            payload["score"] = score
            matches.append(payload)
        matches.sort(key=lambda item: (-item["score"], str(item.get("id", ""))))
        return matches[:limit]

    def _load_rule_entries(self):
        entries = []

        rules_path = self.workspace / "instructions" / "business_rules.yaml"
        rules_payload = _read_yaml(rules_path)
        source = str(rules_path.relative_to(self.workspace))
        for text_value in _extract_rule_texts(rules_payload):
            entries.append({"source": source, "text": text_value})
        if isinstance(rules_payload, dict):
            for text_value in _extract_rule_texts(rules_payload.get("candidate_rules", [])):
                entries.append({"source": source, "text": text_value})

        learnings_dir = self.workspace / "learnings"
        if learnings_dir.exists():
            for path in sorted(learnings_dir.glob("*.md")):
                for line in path.read_text().splitlines():
                    stripped = line.strip()
                    if stripped.startswith("- "):
                        entries.append(
                            {
                                "source": str(path.relative_to(self.workspace)),
                                "text": stripped[2:].strip(),
                            }
                        )
        return entries

    def relevant_rules(self, query: str, limit: int = 5):
        matches = []
        for entry in self._load_rule_entries():
            score = _score_text_match(query, entry.get("text"), entry.get("source"))
            if score <= 0:
                continue
            payload = dict(entry)
            payload["score"] = score
            matches.append(payload)
        matches.sort(key=lambda item: (-item["score"], item["source"], item["text"]))
        return matches[:limit]

    def plan(self, question: str):
        table = self.find_table(question)
        columns = self.find_columns(question, limit=5)
        examples = self.relevant_examples(question, limit=3)
        rules = self.relevant_rules(question, limit=3)
        suggested_sql = None
        if table:
            question_norm = _normalize_text(question)
            if any(token in question_norm for token in ("how many", "count", "number", "total")):
                suggested_sql = f"SELECT COUNT(*) AS answer FROM {table['name']}"
        return {
            "question": question,
            "table": table,
            "columns": columns,
            "examples": examples,
            "rules": rules,
            "suggested_sql": suggested_sql,
        }

    def answer_intent(self, intent: str, options: dict | None = None):
        from db_mcp.orchestrator.engine import preview_answer_intent as _preview_answer_intent

        connection_name = os.environ.get("CONNECTION_NAME") or self.workspace.name
        payload = _preview_answer_intent(
            intent=intent,
            connection=connection_name,
            provider_id=connection_name,
            connection_path=self.workspace,
            options=options,
        ).model_dump(mode="json")
        if payload.get("status") != "ready":
            return payload

        resolved_plan = payload.get("resolved_plan") or {}
        rows = self.query(str(resolved_plan.get("sql") or ""))
        payload["status"] = "success"
        payload["records"] = rows
        payload["answer"] = (
            f"Executed metric '{resolved_plan.get('metric_name')}' on connection "
            f"'{connection_name}' and returned {len(rows)} "
            f"{'row' if len(rows) == 1 else 'rows'}."
        )
        return payload

    def domain_model(self) -> str:
        return self.read_text("domain/model.md")

    def sql_rules(self) -> str:
        return self.read_text("instructions/sql_rules.md")

    def database_url(self) -> str:
        return (self.connector().get("database_url") or "").strip()

    def connect_args(self):
        raw = self.connector().get("capabilities", {}).get("connect_args", {})
        return raw if isinstance(raw, dict) else {}

    def engine(self):
        if self._engine is None:
            database_url = self.database_url()
            if not database_url:
                raise RuntimeError("connector.yaml does not define a database_url for code mode")
            self._engine = create_engine(database_url, connect_args=self.connect_args())
        return self._engine

    def query(self, sql: str, params: dict | None = None):
        if _is_write_sql(sql):
            raise CodeModeConfirmationRequired(
                "Write statement requires confirmation. Re-run code(..., confirmed=True)."
            )
        with self.engine().connect() as conn:
            result = conn.execute(text(sql), params or {})
            if not result.returns_rows:
                return []
            return [dict(row._mapping) for row in result]

    def scalar(self, sql: str, params: dict | None = None):
        rows = self.query(sql, params=params)
        if not rows:
            return None
        first_row = rows[0]
        return next(iter(first_row.values())) if first_row else None

    def execute(self, sql: str, params: dict | None = None):
        is_write = _is_write_sql(sql)
        if is_write and not self.confirmed:
            raise CodeModeConfirmationRequired(
                "Write statement requires confirmation. Re-run code(..., confirmed=True)."
            )
        with self.engine().begin() as conn:
            result = conn.execute(text(sql), params or {})
            if result.returns_rows:
                return {
                    "rows": [dict(row._mapping) for row in result],
                    "statement_type": _leading_keyword(sql),
                    "is_write": is_write,
                }
            return {
                "rowcount": result.rowcount,
                "statement_type": _leading_keyword(sql),
                "is_write": is_write,
            }

    def finalize_answer(
        self,
        *,
        task_id: str,
        answer_value=None,
        answer_text: str | None = None,
        evidence_sql: str | None = None,
        confidence: float | None = 1.0,
        failure_reason: str | None = None,
        status: str | None = None,
    ):
        resolved_status = status or ("failed" if failure_reason else "answered")
        resolved_text = answer_text
        if resolved_text is None:
            if answer_value is None:
                resolved_text = failure_reason or ""
            else:
                resolved_text = str(answer_value)
        return {
            "task_id": task_id,
            "status": resolved_status,
            "answer_value": answer_value,
            "answer_text": resolved_text,
            "evidence_sql": evidence_sql,
            "confidence": confidence,
            "failure_reason": failure_reason,
        }


def create_runtime(workspace: Path, *, confirmed: bool = False) -> DbMcpRuntime:
    return DbMcpRuntime(workspace=workspace, confirmed=confirmed)
"""

_WRAPPER_SENTINEL = "db_mcp_code_mode_error"
_CONFIRM_REQUIRED_EXIT_CODE = 40
_PROTOCOL_CALL_RE = re.compile(r"dbmcp\.(?:read_protocol|ack_protocol)\s*\(")
_DISCOVERY_CALL_RE = re.compile(
    r"dbmcp\.(?:"
    r"connector|schema_descriptions|table_names|describe_table|find_table|find_tables|"
    r"find_columns|relevant_examples|relevant_rules|plan|domain_model|sql_rules"
    r")\s*\("
)
_SEMANTIC_QUERY_CALL_RE = re.compile(r"dbmcp\.answer_intent\s*\(")
_QUERY_CALL_RE = re.compile(r"dbmcp\.(?:query|scalar|execute|answer_intent)\s*\(")
_FINALIZE_CALL_RE = re.compile(r"dbmcp\.finalize_answer\s*\(")
_PHASE_PROTOCOL_UNREAD = "protocol_unread"
_PHASE_SCHEMA_RESOLUTION = "schema_resolution"
_PHASE_QUERY_READY = "query_ready"
_PHASE_QUERY_EXECUTED = "query_executed"
_PHASE_ANSWERED = "answered"
_REPEATED_SCRIPT_LIMIT = 3


@dataclass(frozen=True)
class CodeSession:
    """A resolved code session bound to one connection and MCP session."""

    session_id: str
    connection: str
    spec: ExecSandboxSpec


@dataclass(frozen=True)
class CodeResult:
    """Normalized code execution result."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    truncated: bool
    status: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 3),
            "truncated": self.truncated,
        }
        if self.status is not None:
            payload["status"] = self.status
        if self.message is not None:
            payload["message"] = self.message
        return payload


@dataclass
class _RuntimeSessionState:
    fingerprint: tuple[int, int]
    phase: str
    last_script_hash: str | None = None
    repeated_script_count: int = 0
    last_success_phase: str | None = None


_runtime_session_states: dict[tuple[str, str], _RuntimeSessionState] = {}


def _read_yaml_file(path: Path) -> object:
    import yaml

    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _camel_case_words(value: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)


def _normalize_text(value: object) -> str:
    text_value = _camel_case_words(str(value or ""))
    return " ".join(part for part in re.split(r"[^a-z0-9]+", text_value.lower()) if part)


def _tokenize(value: object) -> set[str]:
    tokens = set()
    for token in _normalize_text(value).split():
        tokens.add(token)
        if token.endswith("s") and len(token) > 3:
            tokens.add(token[:-1])
    return tokens


def _score_text_match(query: str, *values: object) -> int:
    query_norm = _normalize_text(query)
    query_tokens = _tokenize(query)
    if not query_tokens and not query_norm:
        return 0

    score = 0
    for value in values:
        value_norm = _normalize_text(value)
        value_tokens = _tokenize(value)
        if not value_norm and not value_tokens:
            continue
        overlap = query_tokens & value_tokens
        if overlap:
            score += len(overlap) * 10
        if query_norm and value_norm:
            if query_norm in value_norm:
                score += 15
            if value_norm in query_norm:
                score += 8
    return score


def _leading_keyword(sql: str) -> str:
    stripped = sql.lstrip()
    while stripped.startswith("--"):
        _, _, stripped = stripped.partition("\n")
        stripped = stripped.lstrip()
    while stripped.startswith("/*"):
        _, _, stripped = stripped.partition("*/")
        stripped = stripped.lstrip()
    token = stripped.split(None, 1)[0] if stripped else ""
    return token.upper()


def _is_write_sql(sql: str) -> bool:
    first = _leading_keyword(sql)
    return first not in {"", "SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA"}


class HostDbMcpRuntime:
    """Main-process runtime SDK for host-managed sessions."""

    def __init__(self, connection: str, *, confirmed: bool = False):
        connector, connection_name, connection_path = resolve_connection(
            require_connection(connection)
        )
        self.connection = connection_name
        self.connection_path = Path(connection_path)
        self.connector_impl = connector
        self.confirmed = confirmed
        self._connector_payload: dict[str, object] | None = None

    def read_text(self, relative_path: str) -> str:
        return (self.connection_path / relative_path).read_text()

    def read_yaml(self, relative_path: str) -> object:
        return _read_yaml_file(self.connection_path / relative_path)

    def read_protocol(self) -> str:
        return self.read_text("PROTOCOL.md")

    def ack_protocol(self) -> str:
        return self.read_protocol()

    def protocol_text(self) -> str:
        return self.read_protocol()

    def connector(self) -> dict[str, object]:
        if self._connector_payload is None:
            payload = _read_yaml_file(self.connection_path / "connector.yaml")
            self._connector_payload = payload if isinstance(payload, dict) else {}
        return self._connector_payload

    def schema_descriptions(self) -> dict[str, object]:
        payload = self.read_yaml("schema/descriptions.yaml")
        return payload if isinstance(payload, dict) else {}

    def _schema_tables(self) -> list[dict[str, Any]]:
        schema = self.schema_descriptions()
        tables = schema.get("tables", {}) if isinstance(schema, dict) else {}
        if isinstance(tables, list):
            return [table for table in tables if isinstance(table, dict)]
        if isinstance(tables, dict):
            rows: list[dict[str, Any]] = []
            for name, payload in tables.items():
                if isinstance(payload, dict):
                    row = dict(payload)
                    row.setdefault("name", name)
                    rows.append(row)
                else:
                    rows.append({"name": name})
            return rows
        return []

    def table_names(self) -> list[str]:
        return sorted(
            str(table.get("name") or table.get("table_name"))
            for table in self._schema_tables()
            if table.get("name") or table.get("table_name")
        )

    def describe_table(self, name: str) -> dict[str, object] | None:
        query_norm = _normalize_text(name)
        best_match: dict[str, Any] | None = None
        best_score = -1
        for table in self._schema_tables():
            table_name = table.get("name") or table.get("table_name") or ""
            score = _score_text_match(query_norm, table_name, table.get("full_name"))
            if query_norm == _normalize_text(table_name):
                score += 100
            if score > best_score:
                best_score = score
                best_match = table
        if best_match is not None and best_score > 0:
            payload = dict(best_match)
            payload["name"] = payload.get("name") or payload.get("table_name")
            payload["columns"] = [
                dict(column) for column in payload.get("columns", []) if isinstance(column, dict)
            ]
            return payload
        return None

    def find_tables(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        matches = []
        for table in self._schema_tables():
            name = table.get("name") or table.get("table_name") or ""
            columns = [column.get("name", "") for column in table.get("columns", [])]
            score = _score_text_match(
                query,
                name,
                table.get("full_name"),
                table.get("description"),
                " ".join(columns),
            )
            if score <= 0:
                continue
            matches.append(
                {
                    "name": name,
                    "full_name": table.get("full_name") or name,
                    "description": table.get("description"),
                    "columns": columns,
                    "score": score,
                }
            )
        matches.sort(key=lambda item: (-int(item["score"]), str(item["name"])))
        return matches[:limit]

    def find_table(self, query: str) -> dict[str, object] | None:
        matches = self.find_tables(query, limit=1)
        return matches[0] if matches else None

    def find_columns(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        matches = []
        for table in self._schema_tables():
            table_name = table.get("name") or table.get("table_name") or ""
            for column in table.get("columns", []):
                if not isinstance(column, dict):
                    continue
                score = _score_text_match(
                    query,
                    column.get("name"),
                    column.get("description"),
                    column.get("type"),
                    table_name,
                )
                if score <= 0:
                    continue
                matches.append(
                    {
                        "table": table_name,
                        "name": column.get("name"),
                        "type": column.get("type"),
                        "description": column.get("description"),
                        "score": score,
                    }
                )
        matches.sort(key=lambda item: (-int(item["score"]), str(item["table"]), str(item["name"])))
        return matches[:limit]

    def _load_examples(self) -> list[dict[str, object]]:
        examples_dir = self.connection_path / "examples"
        if not examples_dir.exists():
            return []
        records: list[dict[str, object]] = []
        for path in sorted(examples_dir.glob("*.yaml")):
            payload = _read_yaml_file(path)
            if isinstance(payload, dict):
                row = dict(payload)
                row.setdefault("id", path.stem)
                records.append(row)
        return records

    def relevant_examples(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        matches = []
        for example in self._load_examples():
            score = _score_text_match(
                query,
                example.get("id"),
                example.get("intent"),
                example.get("notes"),
                " ".join(str(value) for value in (example.get("tables", []) or [])),
                " ".join(str(value) for value in (example.get("keywords", []) or [])),
                example.get("sql"),
            )
            if score <= 0:
                continue
            payload = dict(example)
            payload["score"] = score
            matches.append(payload)
        matches.sort(key=lambda item: (-int(item["score"]), str(item.get("id", ""))))
        return matches[:limit]

    def _load_rule_entries(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        rules_path = self.connection_path / "instructions" / "business_rules.yaml"
        rules_payload = _read_yaml_file(rules_path)
        source = str(rules_path.relative_to(self.connection_path))
        for text_value in extract_business_rule_texts(rules_payload):
            entries.append({"source": source, "text": str(text_value)})
        if isinstance(rules_payload, dict):
            candidate_texts = extract_business_rule_texts(
                rules_payload.get("candidate_rules", [])
            )
            for text_value in candidate_texts:
                entries.append({"source": source, "text": str(text_value)})
        learnings_dir = self.connection_path / "learnings"
        if learnings_dir.exists():
            for path in sorted(learnings_dir.glob("*.md")):
                for line in path.read_text().splitlines():
                    stripped = line.strip()
                    if stripped.startswith("- "):
                        entries.append(
                            {
                                "source": str(path.relative_to(self.connection_path)),
                                "text": stripped[2:].strip(),
                            }
                        )
        return entries

    def relevant_rules(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        matches = []
        for entry in self._load_rule_entries():
            score = _score_text_match(query, entry.get("text"), entry.get("source"))
            if score <= 0:
                continue
            payload = dict(entry)
            payload["score"] = score
            matches.append(payload)
        matches.sort(
            key=lambda item: (
                -int(item["score"]),
                str(item["source"]),
                str(item["text"]),
            )
        )
        return matches[:limit]

    def plan(self, question: str) -> dict[str, object]:
        table = self.find_table(question)
        columns = self.find_columns(question, limit=5)
        examples = self.relevant_examples(question, limit=3)
        rules = self.relevant_rules(question, limit=3)
        suggested_sql = None
        if table:
            question_norm = _normalize_text(question)
            if any(token in question_norm for token in ("how many", "count", "number", "total")):
                suggested_sql = f"SELECT COUNT(*) AS answer FROM {table['name']}"
        return {
            "question": question,
            "table": table,
            "columns": columns,
            "examples": examples,
            "rules": rules,
            "suggested_sql": suggested_sql,
        }

    def answer_intent(
        self,
        intent: str,
        options: dict[str, object] | None = None,
    ) -> dict[str, object]:
        from db_mcp.orchestrator.engine import preview_answer_intent as _preview_answer_intent

        payload = _preview_answer_intent(
            intent=intent,
            connection=self.connection,
            provider_id=self.connection,
            connection_path=self.connection_path,
            options=options,
        ).model_dump(mode="json")
        if payload.get("status") != "ready":
            return payload

        resolved_plan = payload.get("resolved_plan") or {}
        rows = self.query(str(resolved_plan.get("sql") or ""))
        payload["status"] = "success"
        payload["records"] = rows
        payload["answer"] = (
            f"Executed metric '{resolved_plan.get('metric_name')}' on connection "
            f"'{self.connection}' and returned {len(rows)} "
            f"{'row' if len(rows) == 1 else 'rows'}."
        )
        return payload

    def domain_model(self) -> str:
        return self.read_text("domain/model.md")

    def sql_rules(self) -> str:
        return self.read_text("instructions/sql_rules.md")

    def query(self, sql: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        if _is_write_sql(sql):
            raise RuntimeError(
                "Write statement requires confirmation. Re-run with confirmed=True."
            )
        rows = self.connector_impl.execute_sql(sql, params)
        return [dict(row) for row in rows]

    def scalar(self, sql: str, params: dict[str, object] | None = None) -> object:
        rows = self.query(sql, params=params)
        if not rows:
            return None
        first_row = rows[0]
        return next(iter(first_row.values())) if first_row else None

    def execute(self, sql: str, params: dict[str, object] | None = None) -> dict[str, object]:
        is_write = _is_write_sql(sql)
        if is_write and not self.confirmed:
            raise RuntimeError(
                "Write statement requires confirmation. Re-run with confirmed=True."
            )
        rows = self.connector_impl.execute_sql(sql, params)
        return {
            "rows": [dict(row) for row in rows],
            "statement_type": _leading_keyword(sql),
            "is_write": is_write,
        }

    def finalize_answer(
        self,
        *,
        task_id: str,
        answer_value: object = None,
        answer_text: str | None = None,
        evidence_sql: str | None = None,
        confidence: float | None = 1.0,
        failure_reason: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        resolved_status = status or ("failed" if failure_reason else "answered")
        resolved_text = answer_text
        if resolved_text is None:
            resolved_text = failure_reason or "" if answer_value is None else str(answer_value)
        return {
            "task_id": task_id,
            "status": resolved_status,
            "answer_value": answer_value,
            "answer_text": resolved_text,
            "evidence_sql": evidence_sql,
            "confidence": confidence,
            "failure_reason": failure_reason,
        }


def _load_connection_env(connection_path: Path) -> dict[str, str]:
    env_path = connection_path / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip("\"'")
    return values


def _build_environment(
    connection_name: str,
    connection_path: Path,
    connector: object,
) -> dict[str, str]:
    config = getattr(connector, "config", None)
    api_config = getattr(connector, "api_config", None)
    database_url = getattr(config, "database_url", "") or ""
    base_url = getattr(config, "base_url", "") or getattr(api_config, "base_url", "") or ""
    capabilities = getattr(config, "capabilities", {}) or {}

    env = _load_connection_env(connection_path)
    if database_url:
        env["DATABASE_URL"] = database_url
    if base_url:
        env["BASE_URL"] = base_url
    if isinstance(capabilities.get("connect_args"), dict):
        env["DB_MCP_CONNECT_ARGS_JSON"] = json.dumps(capabilities["connect_args"])

    env["CONNECTION_NAME"] = connection_name
    env["CONNECTION_PATH"] = "/workspace"
    env["VAULT_PATH"] = "/workspace"
    env["HOME"] = "/workspace"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _build_spec(connection: str, *, session_id: str) -> ExecSandboxSpec:
    from db_mcp.exec_runtime import derive_allowed_endpoint

    connector, connection_name, connection_path = resolve_connection(
        require_connection(connection)
    )
    config = getattr(connector, "config", None)
    api_config = getattr(connector, "api_config", None)
    database_url = getattr(config, "database_url", "") or ""
    base_url = getattr(config, "base_url", "") or getattr(api_config, "base_url", "") or ""
    connection_path = Path(connection_path)
    return ExecSandboxSpec(
        session_id=session_id,
        connection=connection_name,
        connection_path=connection_path,
        allowed_endpoint=derive_allowed_endpoint(database_url, base_url=base_url),
        environment=_build_environment(connection_name, connection_path, connector),
    )


def create_code_session(connection: str, session_id: str) -> CodeSession:
    """Create a code session for one connection."""
    spec = _build_spec(connection, session_id=session_id)
    return CodeSession(session_id=session_id, connection=spec.connection, spec=spec)


def _protocol_fingerprint(connection_path: Path) -> tuple[int, int]:
    stat = (connection_path / "PROTOCOL.md").stat()
    return (stat.st_mtime_ns, stat.st_size)


def _is_protocol_read_code(code: str) -> bool:
    return bool(_PROTOCOL_CALL_RE.search(code))


def _has_discovery_calls(code: str) -> bool:
    return bool(_DISCOVERY_CALL_RE.search(code))


def _has_query_calls(code: str) -> bool:
    return bool(_QUERY_CALL_RE.search(code))


def _has_semantic_query_calls(code: str) -> bool:
    return bool(_SEMANTIC_QUERY_CALL_RE.search(code))


def _has_finalize_calls(code: str) -> bool:
    return bool(_FINALIZE_CALL_RE.search(code))


def _protocol_gate_result() -> CodeResult:
    return CodeResult(
        stdout="",
        stderr=(
            "Read PROTOCOL.md first with "
            "code(connection=..., code='print(dbmcp.read_protocol())')"
        ),
        exit_code=1,
        duration_ms=0.0,
        truncated=False,
    )


def _schema_gate_result() -> CodeResult:
    return CodeResult(
        stdout="",
        stderr=(
            "Resolve schema first with dbmcp.find_tables(...), dbmcp.describe_table(...), "
            "dbmcp.find_columns(...), dbmcp.relevant_examples(...), or "
            "dbmcp.relevant_rules(...), then run the query."
        ),
        exit_code=1,
        duration_ms=0.0,
        truncated=False,
    )


def _query_gate_result() -> CodeResult:
    return CodeResult(
        stdout="",
        stderr=(
            "Schema is already resolved in this session. Run the final query next with "
            "dbmcp.scalar(...), dbmcp.query(...), or dbmcp.execute(...)."
        ),
        exit_code=1,
        duration_ms=0.0,
        truncated=False,
    )


def _finalize_gate_result() -> CodeResult:
    return CodeResult(
        stdout="",
        stderr=(
            "Run the final query first with dbmcp.scalar(...), dbmcp.query(...), or "
            "dbmcp.execute(...), then call dbmcp.finalize_answer(...)."
        ),
        exit_code=1,
        duration_ms=0.0,
        truncated=False,
    )


def _answered_gate_result() -> CodeResult:
    return CodeResult(
        stdout="",
        stderr=(
            "This session already finalized an answer. Start a new session for a new question."
        ),
        exit_code=1,
        duration_ms=0.0,
        truncated=False,
    )


def _stuck_result(*, phase: str, last_success_phase: str | None) -> CodeResult:
    guidance = {
        _PHASE_PROTOCOL_UNREAD: "Read PROTOCOL.md with `dbmcp.read_protocol()`.",
        _PHASE_SCHEMA_RESOLUTION: (
            "Resolve schema with `dbmcp.find_table(...)`, `dbmcp.find_tables(...)`, "
            "`dbmcp.describe_table(...)`, or `dbmcp.plan(...)`."
        ),
        _PHASE_QUERY_READY: (
            "Run the final query next with `dbmcp.scalar(...)`, `dbmcp.query(...)`, or "
            "`dbmcp.execute(...)`."
        ),
        _PHASE_QUERY_EXECUTED: "Finalize the answer with `dbmcp.finalize_answer(...)`.",
        _PHASE_ANSWERED: "Start a new session for a new question.",
    }.get(phase, "Take the next state-appropriate action.")
    message = f"Session is stuck in phase `{phase}`. {guidance}"
    if last_success_phase:
        message += f" Last successful phase: `{last_success_phase}`."
    return CodeResult(
        stdout="",
        stderr=message,
        exit_code=1,
        duration_ms=0.0,
        truncated=False,
        status="stuck",
        message=message,
    )


def _get_runtime_state(
    session: CodeSession,
) -> tuple[_RuntimeSessionState | None, tuple[int, int]]:
    key = (session.session_id, session.connection)
    current_fingerprint = _protocol_fingerprint(session.spec.connection_path)
    state = _runtime_session_states.get(key)
    if state is not None and state.fingerprint != current_fingerprint:
        _runtime_session_states.pop(key, None)
        state = None
    return state, current_fingerprint


def _current_phase(session: CodeSession, code: str) -> str:
    state, _ = _get_runtime_state(session)
    if state is None:
        return (
            _PHASE_SCHEMA_RESOLUTION if _is_protocol_read_code(code) else _PHASE_PROTOCOL_UNREAD
        )
    return state.phase


def _update_submission_state(session: CodeSession, code: str) -> _RuntimeSessionState:
    key = (session.session_id, session.connection)
    state, fingerprint = _get_runtime_state(session)
    if state is None:
        state = _RuntimeSessionState(
            fingerprint=fingerprint,
            phase=_current_phase(session, code),
        )
        _runtime_session_states[key] = state
    content_hash = sha256(code.encode("utf-8")).hexdigest()
    if state.last_script_hash == content_hash:
        state.repeated_script_count += 1
    else:
        state.last_script_hash = content_hash
        state.repeated_script_count = 1
    return state


def _stuck_submission_result(session: CodeSession, code: str) -> CodeResult | None:
    state = _update_submission_state(session, code)
    if state.repeated_script_count < _REPEATED_SCRIPT_LIMIT:
        return None
    return _stuck_result(phase=state.phase, last_success_phase=state.last_success_phase)


def _gate_runtime_flow(session: CodeSession, code: str) -> CodeResult | None:
    phase = _current_phase(session, code)
    has_discovery = _has_discovery_calls(code)
    has_query = _has_query_calls(code)
    has_semantic_query = _has_semantic_query_calls(code)
    has_finalize = _has_finalize_calls(code)

    if phase == _PHASE_PROTOCOL_UNREAD and not _is_protocol_read_code(code):
        return _protocol_gate_result()
    if (
        phase == _PHASE_SCHEMA_RESOLUTION
        and has_query
        and not has_discovery
        and not has_semantic_query
    ):
        return _schema_gate_result()
    if phase in {_PHASE_SCHEMA_RESOLUTION, _PHASE_QUERY_READY} and has_finalize and not has_query:
        return _finalize_gate_result()
    if phase == _PHASE_QUERY_READY and has_discovery and not has_query:
        return _query_gate_result()
    if phase == _PHASE_ANSWERED and not has_finalize:
        return _answered_gate_result()
    return None


def _record_runtime_state(session: CodeSession, code: str, result: CodeResult) -> None:
    key = (session.session_id, session.connection)
    if result.exit_code != 0:
        return

    state, fingerprint = _get_runtime_state(session)
    phase = _current_phase(session, code)
    if _has_finalize_calls(code):
        phase = _PHASE_ANSWERED
    elif _has_query_calls(code):
        phase = _PHASE_QUERY_EXECUTED
    elif _has_discovery_calls(code):
        phase = _PHASE_QUERY_READY
    elif _is_protocol_read_code(code):
        phase = _PHASE_SCHEMA_RESOLUTION

    if state is None:
        state = _RuntimeSessionState(fingerprint=fingerprint, phase=phase)
        _runtime_session_states[key] = state
    state.fingerprint = fingerprint
    state.phase = phase
    state.last_success_phase = phase


def _ensure_support_files(connection_path: Path) -> tuple[Path, Path]:
    state_dir = connection_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    runtime_module_path = state_dir / "db_mcp_code_runtime.py"
    if not runtime_module_path.exists() or runtime_module_path.read_text() != _CODE_RUNTIME_MODULE:
        runtime_module_path.write_text(_CODE_RUNTIME_MODULE)
    scripts_dir = state_dir / "code_mode_runs"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    return runtime_module_path, scripts_dir


def _build_wrapper_script(*, session: CodeSession, code: str, confirmed: bool) -> Path:
    _, scripts_dir = _ensure_support_files(session.spec.connection_path)
    script_path = scripts_dir / f"{uuid.uuid4().hex}.py"
    user_code_literal = json.dumps(code)
    script_path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import json",
                "import sys",
                "from pathlib import Path",
                "",
                "workspace = Path.cwd()",
                'sys.path.insert(0, str(workspace / "state"))',
                "from db_mcp_code_runtime import CodeModeConfirmationRequired, create_runtime",
                "",
                f"USER_CODE = {user_code_literal}",
                f"dbmcp = create_runtime(workspace=workspace, confirmed={confirmed})",
                "globals_dict = {'__name__': '__main__', 'dbmcp': dbmcp}",
                "try:",
                "    exec(compile(USER_CODE, '<db-mcp-code>', 'exec'), globals_dict)",
                "except CodeModeConfirmationRequired as exc:",
                "    print(",
                "        json.dumps(",
                "            {",
                f"                'type': '{_WRAPPER_SENTINEL}',",
                "                'kind': 'confirm_required',",
                "                'message': str(exc),",
                "            }",
                "        ),",
                "        file=sys.stderr,",
                "    )",
                f"    raise SystemExit({_CONFIRM_REQUIRED_EXIT_CODE})",
            ]
        )
        + "\n"
    )
    return script_path


def _parse_wrapper_error(result: dict[str, object]) -> CodeResult | None:
    if int(result.get("exit_code", 0)) != _CONFIRM_REQUIRED_EXIT_CODE:
        return None
    stderr = str(result.get("stderr", "") or "").strip()
    if not stderr:
        return None
    try:
        payload = json.loads(stderr.splitlines()[-1])
    except json.JSONDecodeError:
        return None
    if payload.get("type") != _WRAPPER_SENTINEL or payload.get("kind") != "confirm_required":
        return None
    return CodeResult(
        stdout="",
        stderr="",
        exit_code=1,
        duration_ms=float(result.get("duration_ms", 0.0) or 0.0),
        truncated=bool(result.get("truncated", False)),
        status="confirm_required",
        message=str(
            payload.get(
                "message",
                "Write statement requires confirmation. Re-run code(..., confirmed=True).",
            )
        ),
    )


def run_code(
    session: CodeSession,
    code: str,
    *,
    timeout_seconds: int = 30,
    confirmed: bool = False,
    manager: ExecSessionManager,
) -> CodeResult:
    """Run Python code for a code session."""
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1")
    if timeout_seconds > 600:
        raise ValueError("timeout_seconds must be at most 600")
    if stuck_result := _stuck_submission_result(session, code):
        return stuck_result
    if gate_result := _gate_runtime_flow(session, code):
        return gate_result

    script_path = _build_wrapper_script(session=session, code=code, confirmed=confirmed)
    command = f"python3 {shlex.quote(str(script_path.relative_to(session.spec.connection_path)))}"
    try:
        raw_result = manager.execute(
            session_id=session.session_id,
            spec=session.spec,
            command=command,
            timeout_seconds=timeout_seconds,
        )
    except ExecRuntimeError as exc:
        return CodeResult(
            stdout="",
            stderr=str(exc),
            exit_code=1,
            duration_ms=0.0,
            truncated=False,
        )
    finally:
        script_path.unlink(missing_ok=True)

    wrapped = _parse_wrapper_error(raw_result)
    if wrapped is not None:
        return wrapped

    result = CodeResult(
        stdout=str(raw_result.get("stdout", "") or ""),
        stderr=str(raw_result.get("stderr", "") or ""),
        exit_code=int(raw_result.get("exit_code", 1) or 0),
        duration_ms=float(raw_result.get("duration_ms", 0.0) or 0.0),
        truncated=bool(raw_result.get("truncated", False)),
    )
    _record_runtime_state(session, code, result)
    return result
