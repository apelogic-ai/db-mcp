"""SQLite-backed metadata store for the insider agent."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from db_mcp.insider.config import get_insider_db_path
from db_mcp.insider.models import AgentEvent, utc_now


class InsiderStore:
    """Small SQLite-backed store for insider-agent metadata."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_insider_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS insider_events (
                    event_id TEXT PRIMARY KEY,
                    connection TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    schema_digest TEXT,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    batched_at TEXT,
                    completed_at TEXT,
                    superseded_by_batch_id TEXT
                );
                CREATE TABLE IF NOT EXISTS insider_batches (
                    batch_id TEXT PRIMARY KEY,
                    connection TEXT NOT NULL,
                    event_ids_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_text TEXT
                );
                CREATE TABLE IF NOT EXISTS insider_runs (
                    run_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    connection TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    estimated_cost_usd REAL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_text TEXT,
                    proposal_summary_json TEXT
                );
                CREATE TABLE IF NOT EXISTS insider_reviews (
                    review_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    connection TEXT NOT NULL,
                    status TEXT NOT NULL,
                    review_kind TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    diff_path TEXT NOT NULL,
                    reasoning_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    decision_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS insider_budget_usage (
                    usage_id TEXT PRIMARY KEY,
                    connection TEXT,
                    run_id TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_insider_events_connection_status
                    ON insider_events(connection, status);
                CREATE INDEX IF NOT EXISTS idx_insider_batches_connection_status
                    ON insider_batches(connection, status);
                CREATE INDEX IF NOT EXISTS idx_insider_runs_connection_status
                    ON insider_runs(connection, status);
                CREATE INDEX IF NOT EXISTS idx_insider_reviews_connection_status
                    ON insider_reviews(connection, status);
                CREATE INDEX IF NOT EXISTS idx_insider_events_created_at
                    ON insider_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_insider_batches_created_at
                    ON insider_batches(created_at);
                CREATE INDEX IF NOT EXISTS idx_insider_runs_created_at
                    ON insider_runs(started_at);
                CREATE INDEX IF NOT EXISTS idx_insider_reviews_created_at
                    ON insider_reviews(created_at);
                CREATE INDEX IF NOT EXISTS idx_insider_budget_created_at
                    ON insider_budget_usage(created_at);
                """
            )

    def create_event(self, event: AgentEvent, *, force: bool = False) -> bool:
        """Persist one event if it is not a duplicate."""
        with self._connect() as conn:
            if not force:
                row = conn.execute(
                    """
                    SELECT event_id FROM insider_events
                    WHERE connection = ? AND event_type = ? AND schema_digest = ?
                    AND status IN ('pending', 'batched', 'running', 'completed')
                    LIMIT 1
                    """,
                    (event.connection, event.event_type, event.schema_digest),
                ).fetchone()
                if row is not None:
                    return False
            conn.execute(
                """
                INSERT INTO insider_events (
                    event_id, connection, event_type, schema_digest, payload_json,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.connection,
                    event.event_type,
                    event.schema_digest,
                    json.dumps(event.payload),
                    event.status,
                    event.created_at,
                ),
            )
            return True

    def pending_events(self, connection: str | None = None) -> list[dict[str, Any]]:
        """List pending events."""
        query = """
            SELECT * FROM insider_events
            WHERE status = 'pending'
        """
        params: tuple[Any, ...] = ()
        if connection:
            query += " AND connection = ?"
            params = (connection,)
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_events(self, connection: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List recent insider events."""
        query = "SELECT * FROM insider_events"
        params: tuple[Any, ...] = ()
        if connection:
            query += " WHERE connection = ?"
            params = (connection,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params += (limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def create_batch(self, connection: str, event_ids: list[str]) -> str:
        """Create one batch record and mark events as batched."""
        batch_id = uuid.uuid4().hex
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO insider_batches (
                    batch_id, connection, event_ids_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (batch_id, connection, json.dumps(event_ids), "pending", now),
            )
            conn.executemany(
                """
                UPDATE insider_events
                SET status = 'batched', batched_at = ?, superseded_by_batch_id = ?
                WHERE event_id = ?
                """,
                [(now, batch_id, event_id) for event_id in event_ids],
            )
        return batch_id

    def mark_batch_started(self, batch_id: str) -> None:
        """Mark a batch as running."""
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE insider_batches SET status = 'running', started_at = ? WHERE batch_id = ?",
                (now, batch_id),
            )
            row = conn.execute(
                "SELECT event_ids_json FROM insider_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if row is not None:
                event_ids = json.loads(row["event_ids_json"])
                conn.executemany(
                    "UPDATE insider_events SET status = 'running' WHERE event_id = ?",
                    [(event_id,) for event_id in event_ids],
                )

    def mark_batch_completed(
        self,
        batch_id: str,
        *,
        success: bool,
        error_text: str | None = None,
    ) -> None:
        """Finalize a batch and its events."""
        now = utc_now()
        status = "completed" if success else "failed"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE insider_batches
                SET status = ?, completed_at = ?, error_text = ?
                WHERE batch_id = ?
                """,
                (status, now, error_text, batch_id),
            )
            row = conn.execute(
                "SELECT event_ids_json FROM insider_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if row is not None:
                event_ids = json.loads(row["event_ids_json"])
                conn.executemany(
                    """
                    UPDATE insider_events
                    SET status = ?, completed_at = ?
                    WHERE event_id = ?
                    """,
                    [(status, now, event_id) for event_id in event_ids],
                )

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM insider_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_batches(self, connection: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM insider_batches"
        params: tuple[Any, ...] = ()
        if connection:
            query += " WHERE connection = ?"
            params = (connection,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params += (limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def create_run(
        self,
        *,
        batch_id: str,
        connection: str,
        provider: str,
        model: str,
    ) -> str:
        run_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO insider_runs (
                    run_id, batch_id, connection, provider, model, status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, batch_id, connection, provider, model, "running", utc_now()),
            )
        return run_id

    def complete_run(
        self,
        run_id: str,
        *,
        success: bool,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        estimated_cost_usd: float | None = None,
        proposal_summary: dict[str, Any] | None = None,
        error_text: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE insider_runs
                SET status = ?, input_tokens = ?, output_tokens = ?, estimated_cost_usd = ?,
                    completed_at = ?, proposal_summary_json = ?, error_text = ?
                WHERE run_id = ?
                """,
                (
                    "completed" if success else "failed",
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    utc_now(),
                    json.dumps(proposal_summary or {}),
                    error_text,
                    run_id,
                ),
            )

    def list_runs(self, connection: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM insider_runs"
        params: tuple[Any, ...] = ()
        if connection:
            query += " WHERE connection = ?"
            params = (connection,)
        query += " ORDER BY started_at DESC LIMIT ?"
        params += (limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def record_budget_usage(
        self,
        *,
        connection: str,
        run_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO insider_budget_usage (
                    usage_id, connection, run_id, provider, model,
                    input_tokens, output_tokens, estimated_cost_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    connection,
                    run_id,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    utc_now(),
                ),
            )

    def get_budget_summary(self, connection: str | None = None) -> dict[str, Any]:
        where = ""
        params: tuple[Any, ...] = ()
        if connection:
            where = " WHERE connection = ?"
            params = (connection,)
        with self._connect() as conn:
            total = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
                    COUNT(*) AS runs
                FROM insider_budget_usage
                {where}
                """,
                params,
            ).fetchone()
        return dict(total) if total else {
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "runs": 0,
        }

    def runs_last_hour(self, connection: str | None = None) -> int:
        query = """
            SELECT COUNT(*) AS count
            FROM insider_runs
            WHERE status = 'completed'
              AND started_at >= datetime('now', '-1 hour')
        """
        params: tuple[Any, ...] = ()
        if connection:
            query += " AND connection = ?"
            params = (connection,)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row["count"]) if row else 0

    def monthly_spend(self, connection: str | None = None) -> float:
        query = """
            SELECT COALESCE(SUM(estimated_cost_usd), 0) AS total
            FROM insider_budget_usage
            WHERE created_at >= datetime('now', 'start of month')
        """
        params: tuple[Any, ...] = ()
        if connection:
            query += " AND connection = ?"
            params = (connection,)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return float(row["total"]) if row else 0.0

    def create_review(
        self,
        *,
        review_id: str,
        run_id: str,
        connection: str,
        review_kind: str,
        manifest_path: Path,
        diff_path: Path,
        reasoning_path: Path,
    ) -> str:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO insider_reviews (
                    review_id, run_id, connection, status, review_kind,
                    manifest_path, diff_path, reasoning_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    run_id,
                    connection,
                    "pending",
                    review_kind,
                    str(manifest_path),
                    str(diff_path),
                    str(reasoning_path),
                    utc_now(),
                ),
            )
        return review_id

    def set_review_status(self, review_id: str, status: str, reason: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE insider_reviews
                SET status = ?, decided_at = ?, decision_reason = ?
                WHERE review_id = ?
                """,
                (status, utc_now(), reason, review_id),
            )

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM insider_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_reviews(self, connection: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM insider_reviews"
        params: tuple[Any, ...] = ()
        if connection:
            query += " WHERE connection = ?"
            params = (connection,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params += (limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
