"""Tests for background collab sync loop."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from db_mcp.collab.background import CollabSyncLoop


class TestCollabSyncLoop:
    @pytest.fixture
    def loop(self):
        return CollabSyncLoop(
            connection_path=Path("/fake/connection"),
            user_name="alice",
            interval_minutes=1,
        )

    @pytest.mark.asyncio
    async def test_start_creates_task(self, loop):
        await loop.start()
        assert loop._task is not None
        await loop.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, loop):
        await loop.start()
        assert loop._task is not None
        await loop.stop()
        assert loop._task is None

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self, loop):
        await loop.start()
        first_task = loop._task
        await loop.start()
        assert loop._task is first_task
        await loop.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self, loop):
        await loop.stop()  # Should not raise

    @pytest.mark.asyncio
    @patch("db_mcp.collab.background.CollabSyncLoop._run_sync")
    async def test_run_sync_called(self, mock_sync):
        """Test that sync is called after the interval."""
        # Use a very short interval
        loop = CollabSyncLoop(
            connection_path=Path("/fake"),
            user_name="alice",
            interval_minutes=1,
        )
        # Override interval to be very short for testing
        loop._interval_seconds = 0.05

        await loop.start()
        await asyncio.sleep(0.15)  # Wait for ~3 intervals
        await loop.stop()

        assert mock_sync.call_count >= 1
