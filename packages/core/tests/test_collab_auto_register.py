"""Tests for _auto_register_collaborator in brownfield init."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from db_mcp.cli import _auto_register_collaborator
from db_mcp.collab.manifest import CollabManifest, CollabMember


def _create_manifest(tmp_path: Path, members=None) -> CollabManifest:
    """Helper to create and save a manifest to disk."""
    manifest = CollabManifest(
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        members=members or [],
    )
    manifest_path = tmp_path / ".collab.yaml"
    data = manifest.model_dump(mode="json")
    with open(manifest_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return manifest


class TestAutoRegisterCollaborator:
    def test_no_manifest_is_noop(self, tmp_path):
        """When there's no .collab.yaml, does nothing."""
        _auto_register_collaborator(tmp_path)
        # No crash, no .collab.yaml created
        assert not (tmp_path / ".collab.yaml").exists()

    def test_registers_new_collaborator(self, tmp_path):
        """When manifest exists and user is not a member, registers them."""
        _create_manifest(
            tmp_path,
            members=[
                CollabMember(
                    user_name="master",
                    user_id="master01",
                    role="master",
                    joined_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                )
            ],
        )

        mock_git = MagicMock()

        with (
            patch("db_mcp.git_utils.git", mock_git),
            patch("db_mcp.collab.manifest.get_user_name_from_config", return_value=None),
            patch("db_mcp.collab.manifest.set_user_name_in_config") as mock_set_name,
            patch("db_mcp.traces.get_user_id_from_config", return_value=None),
            patch("db_mcp.traces.generate_user_id", return_value="alice001"),
            patch("db_mcp.cli.load_config", return_value={"active_connection": "test"}),
            patch("db_mcp.cli.save_config"),
            patch("db_mcp.cli.click.prompt", return_value="alice"),
            patch("db_mcp.cli.console"),
        ):
            _auto_register_collaborator(tmp_path)

        # Should have set user_name
        mock_set_name.assert_called_once_with("alice")

        # Should have created branch and committed
        mock_git.checkout.assert_called_once_with(tmp_path, "collaborator/alice", create=True)
        mock_git.add.assert_called_once_with(tmp_path, [".collab.yaml"])
        mock_git.commit.assert_called_once()
        mock_git.push_branch.assert_called_once_with(tmp_path, "collaborator/alice")

        # Manifest should now include alice
        from db_mcp.collab.manifest import load_manifest

        updated = load_manifest(tmp_path)
        assert updated is not None
        assert len(updated.members) == 2
        assert updated.members[1].user_name == "alice"
        assert updated.members[1].user_id == "alice001"
        assert updated.members[1].role == "collaborator"

    def test_already_registered_is_noop(self, tmp_path):
        """When user is already a member, skips registration."""
        _create_manifest(
            tmp_path,
            members=[
                CollabMember(
                    user_name="alice",
                    user_id="alice001",
                    role="collaborator",
                    joined_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                )
            ],
        )

        mock_git = MagicMock()

        with (
            patch("db_mcp.git_utils.git", mock_git),
            patch(
                "db_mcp.collab.manifest.get_user_name_from_config",
                return_value="alice",
            ),
            patch("db_mcp.traces.get_user_id_from_config", return_value="alice001"),
            patch("db_mcp.cli.console"),
        ):
            _auto_register_collaborator(tmp_path)

        # Should not have created a branch
        mock_git.checkout.assert_not_called()
        mock_git.add.assert_not_called()

    def test_push_failure_logs_warning(self, tmp_path):
        """When push fails, registers locally and warns user."""
        _create_manifest(tmp_path, members=[])

        mock_git = MagicMock()
        mock_git.push_branch.side_effect = Exception("auth failed")

        with (
            patch("db_mcp.git_utils.git", mock_git),
            patch(
                "db_mcp.collab.manifest.get_user_name_from_config",
                return_value="bob",
            ),
            patch("db_mcp.traces.get_user_id_from_config", return_value="bob00001"),
            patch("db_mcp.cli.console"),
        ):
            _auto_register_collaborator(tmp_path)

        # Should have registered locally
        mock_git.checkout.assert_called_once()
        mock_git.add.assert_called_once()
        mock_git.commit.assert_called_once()

        # Manifest should have bob
        from db_mcp.collab.manifest import load_manifest

        updated = load_manifest(tmp_path)
        assert updated is not None
        assert len(updated.members) == 1
        assert updated.members[0].user_name == "bob"
