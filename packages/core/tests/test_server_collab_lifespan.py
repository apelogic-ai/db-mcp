"""Tests for collab pull-on-start / push-on-stop in server lifespan."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db_mcp.collab.manifest import CollabManifest, CollabMember, CollabSyncConfig
from db_mcp.collab.sync import SyncResult


class TestServerCollabLifespan:
    """Test that server_lifespan pulls on start and pushes on stop."""

    def _make_manifest(self, role="collaborator"):
        return CollabManifest(
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            members=[
                CollabMember(
                    user_name="alice",
                    user_id="alice001",
                    role=role,
                    joined_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                )
            ],
            sync=CollabSyncConfig(auto_sync=True, sync_interval_minutes=60),
        )

    @pytest.mark.asyncio
    async def test_pulls_on_startup_for_collaborator(self):
        """Collaborator gets a pull on server startup."""
        manifest = self._make_manifest("collaborator")

        mock_settings = MagicMock()
        mock_settings.get_effective_connection_path.return_value = Path("/fake/conn")

        with (
            patch("db_mcp.server.get_task_store") as mock_store,
            patch("db_mcp.server.get_settings", return_value=mock_settings),
            patch("db_mcp.collab.manifest.load_manifest", return_value=manifest),
            patch(
                "db_mcp.collab.manifest.get_member",
                return_value=manifest.members[0],
            ),
            patch(
                "db_mcp.traces.get_user_id_from_config",
                return_value="alice001",
            ),
            patch("db_mcp.collab.sync.collaborator_pull") as mock_pull,
            patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            mock_store.return_value.start_cleanup_loop = AsyncMock()
            mock_store.return_value.stop_cleanup_loop = AsyncMock()

            # Make asyncio.to_thread call the function
            async def call_fn(fn, *args, **kwargs):
                return fn(*args, **kwargs)

            mock_thread.side_effect = call_fn

            from db_mcp.server import server_lifespan

            mock_server = MagicMock()
            async with server_lifespan(mock_server):
                pass

            mock_pull.assert_called_once_with(Path("/fake/conn"), "alice")

    @pytest.mark.asyncio
    async def test_pushes_on_shutdown_for_collaborator(self):
        """Collaborator gets a push on server shutdown."""
        manifest = self._make_manifest("collaborator")

        mock_settings = MagicMock()
        mock_settings.get_effective_connection_path.return_value = Path("/fake/conn")

        with (
            patch("db_mcp.server.get_task_store") as mock_store,
            patch("db_mcp.server.get_settings", return_value=mock_settings),
            patch("db_mcp.collab.manifest.load_manifest", return_value=manifest),
            patch(
                "db_mcp.collab.manifest.get_member",
                return_value=manifest.members[0],
            ),
            patch(
                "db_mcp.traces.get_user_id_from_config",
                return_value="alice001",
            ),
            patch("db_mcp.collab.sync.collaborator_pull"),
            patch(
                "db_mcp.collab.sync.collaborator_push",
                return_value=SyncResult(additive_merged=3),
            ) as mock_push,
            patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            mock_store.return_value.start_cleanup_loop = AsyncMock()
            mock_store.return_value.stop_cleanup_loop = AsyncMock()

            async def call_fn(fn, *args, **kwargs):
                return fn(*args, **kwargs)

            mock_thread.side_effect = call_fn

            from db_mcp.server import server_lifespan

            mock_server = MagicMock()
            async with server_lifespan(mock_server):
                pass

            mock_push.assert_called_once_with(Path("/fake/conn"), "alice")

    @pytest.mark.asyncio
    async def test_no_manifest_skips_collab(self):
        """No manifest means no pull/push."""
        mock_settings = MagicMock()
        mock_settings.get_effective_connection_path.return_value = Path("/fake/conn")

        with (
            patch("db_mcp.server.get_task_store") as mock_store,
            patch("db_mcp.server.get_settings", return_value=mock_settings),
            patch("db_mcp.collab.manifest.load_manifest", return_value=None),
            patch("db_mcp.collab.sync.collaborator_pull") as mock_pull,
            patch("db_mcp.collab.sync.collaborator_push") as mock_push,
        ):
            mock_store.return_value.start_cleanup_loop = AsyncMock()
            mock_store.return_value.stop_cleanup_loop = AsyncMock()

            from db_mcp.server import server_lifespan

            mock_server = MagicMock()
            async with server_lifespan(mock_server):
                pass

            mock_pull.assert_not_called()
            mock_push.assert_not_called()

    @pytest.mark.asyncio
    async def test_master_role_skips_collab(self):
        """Master role does not trigger pull/push."""
        manifest = self._make_manifest("master")

        mock_settings = MagicMock()
        mock_settings.get_effective_connection_path.return_value = Path("/fake/conn")

        with (
            patch("db_mcp.server.get_task_store") as mock_store,
            patch("db_mcp.server.get_settings", return_value=mock_settings),
            patch("db_mcp.collab.manifest.load_manifest", return_value=manifest),
            patch(
                "db_mcp.collab.manifest.get_member",
                return_value=manifest.members[0],
            ),
            patch(
                "db_mcp.traces.get_user_id_from_config",
                return_value="alice001",
            ),
            patch("db_mcp.collab.sync.collaborator_pull") as mock_pull,
            patch("db_mcp.collab.sync.collaborator_push") as mock_push,
        ):
            mock_store.return_value.start_cleanup_loop = AsyncMock()
            mock_store.return_value.stop_cleanup_loop = AsyncMock()

            from db_mcp.server import server_lifespan

            mock_server = MagicMock()
            async with server_lifespan(mock_server):
                pass

            mock_pull.assert_not_called()
            mock_push.assert_not_called()

    @pytest.mark.asyncio
    async def test_pull_failure_does_not_crash_server(self):
        """If pull fails on startup, server still starts normally."""
        manifest = self._make_manifest("collaborator")

        mock_settings = MagicMock()
        mock_settings.get_effective_connection_path.return_value = Path("/fake/conn")

        with (
            patch("db_mcp.server.get_task_store") as mock_store,
            patch("db_mcp.server.get_settings", return_value=mock_settings),
            patch("db_mcp.collab.manifest.load_manifest", return_value=manifest),
            patch(
                "db_mcp.collab.manifest.get_member",
                return_value=manifest.members[0],
            ),
            patch(
                "db_mcp.traces.get_user_id_from_config",
                return_value="alice001",
            ),
            patch(
                "db_mcp.collab.sync.collaborator_pull",
                side_effect=Exception("network error"),
            ),
            patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            mock_store.return_value.start_cleanup_loop = AsyncMock()
            mock_store.return_value.stop_cleanup_loop = AsyncMock()

            async def call_fn(fn, *args, **kwargs):
                return fn(*args, **kwargs)

            mock_thread.side_effect = call_fn

            from db_mcp.server import server_lifespan

            mock_server = MagicMock()
            # Should not raise
            async with server_lifespan(mock_server):
                pass
