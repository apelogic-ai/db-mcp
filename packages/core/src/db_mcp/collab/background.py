"""Background sync loop for collaborators.

Runs periodic full_sync() in the MCP server's async event loop,
following the same pattern as the task store cleanup loop.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CollabSyncLoop:
    """Periodic background sync for collaborators."""

    def __init__(
        self,
        connection_path: Path,
        user_name: str,
        interval_minutes: int = 60,
    ):
        self._connection_path = connection_path
        self._user_name = user_name
        self._interval_seconds = interval_minutes * 60
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the periodic sync task."""
        if self._task is not None:
            return

        async def sync_loop():
            while True:
                try:
                    await asyncio.sleep(self._interval_seconds)
                    await asyncio.to_thread(self._run_sync)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception("Collab sync loop error: %s", e)

        self._task = asyncio.create_task(sync_loop())
        logger.info(
            "Started collab sync loop (interval: %dm, user: %s)",
            self._interval_seconds // 60,
            self._user_name,
        )

    async def stop(self) -> None:
        """Stop the periodic sync task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Stopped collab sync loop")

    def _run_sync(self) -> None:
        """Run full_sync in a thread (blocking git operations)."""
        from db_mcp.collab.sync import full_sync

        try:
            result = full_sync(self._connection_path, self._user_name)
            if result.additive_merged or result.shared_state_files:
                logger.info(
                    "Collab sync: %d additive merged, %d shared-state pending",
                    result.additive_merged,
                    len(result.shared_state_files),
                )
        except Exception as e:
            logger.warning("Collab sync failed: %s", e)
