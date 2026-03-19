"""Async supervisor for insider-agent event processing."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from db_mcp.insider.config import InsiderConfig
from db_mcp.insider.logging import log_event
from db_mcp.insider.models import InsiderProposalBundle
from db_mcp.insider.provider import build_provider
from db_mcp.insider.services import InsiderService
from db_mcp.insider.store import InsiderStore


class InsiderSupervisor:
    """Owns pending insider work and background processing tasks."""

    def __init__(
        self,
        *,
        config: InsiderConfig,
        store: InsiderStore | None = None,
        service: InsiderService | None = None,
    ):
        self.config = config
        self.service = service or InsiderService(store=store, config=config)
        self.store = self.service.store
        self._pending: dict[str, list[str]] = {}
        self._timers: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._global_semaphore = asyncio.Semaphore(max(1, self.config.max_concurrent_runs))
        self._connection_locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        """Resume any pending work after process start."""
        self._running = True
        for connection in self.service.pending_connections():
            rows = self.service.pending_events(connection)
            self._pending[connection] = [row["event_id"] for row in rows]
            self._schedule_flush(connection, delay_seconds=0.1)

    async def stop(self) -> None:
        """Stop background timers."""
        self._running = False
        for timer in list(self._timers.values()):
            timer.cancel()
        self._timers.clear()

    async def emit_new_connection(
        self,
        connection: str,
        *,
        payload: dict[str, Any] | None = None,
        force: bool = False,
    ) -> str | None:
        """Emit one new-connection bootstrap event."""
        event_id = self.service.queue_new_connection(
            connection,
            payload=payload,
            force=force,
        )
        if event_id is None:
            return None

        self._pending.setdefault(connection, []).append(event_id)
        self._schedule_flush(connection, delay_seconds=self.config.debounce_seconds)
        return event_id

    def _schedule_flush(self, connection: str, *, delay_seconds: float) -> None:
        prior = self._timers.get(connection)
        if prior is not None:
            prior.cancel()
        self._timers[connection] = asyncio.create_task(
            self._flush_after(connection, delay_seconds)
        )

    async def _flush_after(self, connection: str, delay_seconds: float) -> None:
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        await self._run_pending(connection)
        self._timers.pop(connection, None)

    def _connection_lock(self, connection: str) -> asyncio.Lock:
        lock = self._connection_locks.get(connection)
        if lock is None:
            lock = asyncio.Lock()
            self._connection_locks[connection] = lock
        return lock

    async def _run_pending(self, connection: str) -> None:
        if not self._running:
            return
        async with self._connection_lock(connection):
            pending_ids = list(self._pending.get(connection, []))
            if not pending_ids:
                rows = self.service.pending_events(connection)
                pending_ids = [row["event_id"] for row in rows]
            if not pending_ids:
                return

            self._pending[connection] = []
            batch_id = self.service.create_batch(connection, pending_ids)
            log_event(
                "insider_batch_scheduled",
                connection=connection,
                batch_id=batch_id,
                event_ids=pending_ids,
                status="pending",
            )
            asyncio.create_task(self._run_batch(connection, batch_id))

    async def _run_batch(self, connection: str, batch_id: str) -> None:
        async with self._global_semaphore:
            self.store.mark_batch_started(batch_id)
            conn_path = self.service.resolve_connection_path(connection)
            provider = build_provider(
                provider=self.config.provider,
                model=self.config.model,
                api_key_env=self.config.api_key_env,
            )
            run_id = self.store.create_run(
                batch_id=batch_id,
                connection=connection,
                provider=self.config.provider,
                model=self.config.model,
            )
            log_event(
                "insider_run_started",
                connection=connection,
                batch_id=batch_id,
                run_id=run_id,
                provider=self.config.provider,
                model=self.config.model,
                status="running",
            )

            try:
                started_at = time.monotonic()
                if self.store.runs_last_hour(connection) >= self.config.budgets.max_runs_per_hour:
                    raise RuntimeError("Hourly insider run limit exceeded")
                if (
                    self.store.monthly_spend(connection)
                    >= self.config.budgets.max_monthly_spend_usd
                ):
                    raise RuntimeError("Monthly insider spend limit exceeded")

                request = self.service.build_run_request(connection, conn_path)
                run_dir = conn_path / ".insider" / "runs" / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "input-summary.json").write_text(
                    json.dumps(request.model_dump(mode="json"), indent=2)
                )
                provider_request = provider.prepare(request)
                response = await asyncio.to_thread(provider.run, provider_request)
                input_tokens = response.input_tokens or 0
                output_tokens = response.output_tokens or 0
                if input_tokens + output_tokens > self.config.budgets.max_tokens_per_run:
                    raise RuntimeError("Per-run insider token budget exceeded")
                bundle = provider.parse(response)
                applied_paths, review_count = self.service.apply_bundle(
                    run_id=run_id,
                    connection=connection,
                    connection_path=conn_path,
                    schema_digest=request.schema_digest,
                    bundle=bundle,
                )

                estimated_cost = response.estimated_cost_usd or 0.0
                self.store.complete_run(
                    run_id,
                    success=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimated_cost,
                    proposal_summary={
                        "findings": len(bundle.findings),
                        "description_updates": len(bundle.description_updates),
                        "example_candidates": len(bundle.example_candidates),
                        "review_items": len(bundle.review_items),
                    },
                )
                self.store.record_budget_usage(
                    connection=connection,
                    run_id=run_id,
                    provider=self.config.provider,
                    model=self.config.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimated_cost,
                )
                self.store.mark_batch_completed(batch_id, success=True)
                log_event(
                    "insider_run_completed",
                    connection=connection,
                    batch_id=batch_id,
                    run_id=run_id,
                    provider=self.config.provider,
                    model=self.config.model,
                    status="completed",
                    duration_ms=round((time.monotonic() - started_at) * 1000, 2),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimated_cost,
                    staged_file_count=review_count,
                    applied_file_count=len(applied_paths),
                )
            except Exception as exc:
                error_text = str(exc)
                duration_ms = (
                    round((time.monotonic() - started_at) * 1000, 2)
                    if "started_at" in locals()
                    else None
                )
                if "budget" in error_text.lower() or "limit exceeded" in error_text.lower():
                    log_event(
                        "insider_budget_blocked",
                        connection=connection,
                        batch_id=batch_id,
                        run_id=run_id,
                        provider=self.config.provider,
                        model=self.config.model,
                        status="blocked",
                        duration_ms=duration_ms,
                        error=error_text,
                    )
                else:
                    log_event(
                        "insider_run_failed",
                        connection=connection,
                        batch_id=batch_id,
                        run_id=run_id,
                        provider=self.config.provider,
                        model=self.config.model,
                        status="failed",
                        duration_ms=duration_ms,
                        error=error_text,
                    )
                self.store.complete_run(run_id, success=False, error_text=error_text)
                self.store.mark_batch_completed(batch_id, success=False, error_text=error_text)

    def _apply_bundle(
        self,
        *,
        run_id: str,
        connection: str,
        conn_path,
        schema_digest: str,
        bundle: InsiderProposalBundle,
    ) -> tuple[list, int]:
        """Compatibility wrapper for tests while service boundary settles."""
        return self.service.apply_bundle(
            run_id=run_id,
            connection=connection,
            connection_path=conn_path,
            schema_digest=schema_digest,
            bundle=bundle,
        )
