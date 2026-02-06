"""Tests for collaborator sync engine."""

from pathlib import Path
from unittest.mock import patch

from db_mcp.collab.sync import (
    SyncResult,
    _branch_name,
    collaborator_pull,
    collaborator_push,
    full_sync,
)


class TestBranchName:
    def test_branch_name(self):
        assert _branch_name("alice") == "collaborator/alice"

    def test_branch_name_with_special_chars(self):
        assert _branch_name("bob-smith") == "collaborator/bob-smith"


class TestCollaboratorPull:
    @patch("db_mcp.collab.sync.git")
    def test_pull_fetches_and_merges(self, mock_git):
        mock_git.current_branch.return_value = "collaborator/alice"
        path = Path("/fake/connection")

        collaborator_pull(path, "alice")

        mock_git.fetch.assert_called_once_with(path)
        mock_git.merge.assert_called_once_with(path, "origin/main")

    @patch("db_mcp.collab.sync.git")
    def test_pull_switches_branch_if_needed(self, mock_git):
        mock_git.current_branch.return_value = "main"
        path = Path("/fake/connection")

        collaborator_pull(path, "alice")

        mock_git.checkout.assert_called_once_with(path, "collaborator/alice")


class TestCollaboratorPush:
    @patch("db_mcp.collab.sync.gh_available", return_value=False)
    @patch("db_mcp.collab.sync.git")
    def test_no_changes_returns_empty_result(self, mock_git, _gh):
        mock_git.current_branch.return_value = "collaborator/alice"
        mock_git.status.return_value = []
        path = Path("/fake/connection")

        result = collaborator_push(path, "alice")

        assert result.additive_merged == 0
        assert result.shared_state_files == []
        mock_git.add.assert_not_called()

    @patch("db_mcp.collab.sync.gh_available", return_value=False)
    @patch("db_mcp.collab.sync.git")
    def test_additive_only_merges_to_main(self, mock_git, _gh):
        mock_git.current_branch.return_value = "collaborator/alice"
        mock_git.status.return_value = ["examples/abc.yaml"]
        mock_git.commit.return_value = "abc1234"
        mock_git.diff_names.return_value = ["examples/abc.yaml"]
        path = Path("/fake/connection")

        result = collaborator_push(path, "alice")

        assert result.additive_merged == 1
        assert result.shared_state_files == []
        # Should merge to main and switch back
        mock_git.checkout.assert_any_call(path, "main")
        mock_git.merge.assert_called_once_with(path, "collaborator/alice")
        mock_git.push.assert_called_once_with(path)

    @patch("db_mcp.collab.sync.open_pr", return_value="https://github.com/org/repo/pull/1")
    @patch("db_mcp.collab.sync.gh_available", return_value=True)
    @patch("db_mcp.collab.sync.git")
    def test_shared_state_opens_pr(self, mock_git, _gh, mock_pr):
        mock_git.current_branch.return_value = "collaborator/alice"
        mock_git.status.return_value = ["schema/descriptions.yaml"]
        mock_git.commit.return_value = "abc1234"
        mock_git.diff_names.return_value = [
            "examples/abc.yaml",
            "schema/descriptions.yaml",
        ]
        path = Path("/fake/connection")

        result = collaborator_push(path, "alice")

        assert result.additive_merged == 1
        assert result.shared_state_files == ["schema/descriptions.yaml"]
        assert result.pr_opened is True
        assert result.pr_url == "https://github.com/org/repo/pull/1"
        mock_git.push_branch.assert_called_once_with(path, "collaborator/alice")

    @patch("db_mcp.collab.sync.gh_available", return_value=False)
    @patch("db_mcp.collab.sync.git")
    def test_shared_state_without_gh_pushes_branch(self, mock_git, _gh):
        mock_git.current_branch.return_value = "collaborator/alice"
        mock_git.status.return_value = ["domain/model.md"]
        mock_git.commit.return_value = "abc1234"
        mock_git.diff_names.return_value = ["domain/model.md"]
        path = Path("/fake/connection")

        result = collaborator_push(path, "alice")

        assert result.shared_state_files == ["domain/model.md"]
        assert result.pr_opened is False
        mock_git.push_branch.assert_called_once()


class TestFullSync:
    @patch("db_mcp.collab.sync.collaborator_push")
    @patch("db_mcp.collab.sync.collaborator_pull")
    def test_calls_pull_then_push(self, mock_pull, mock_push):
        mock_push.return_value = SyncResult(additive_merged=2)
        path = Path("/fake/connection")

        result = full_sync(path, "alice")

        mock_pull.assert_called_once_with(path, "alice")
        mock_push.assert_called_once_with(path, "alice")
        assert result.additive_merged == 2

    @patch("db_mcp.collab.sync.collaborator_push")
    @patch("db_mcp.collab.sync.collaborator_pull", side_effect=Exception("network error"))
    def test_continues_push_if_pull_fails(self, mock_pull, mock_push):
        mock_push.return_value = SyncResult()
        path = Path("/fake/connection")

        full_sync(path, "alice")

        mock_push.assert_called_once()
