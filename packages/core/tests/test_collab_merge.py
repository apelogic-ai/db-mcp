"""Tests for master merge logic."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from db_mcp.collab.merge import (
    CollaboratorMergeResult,
    MergeResult,
    _list_remote_collaborator_branches,
    master_merge_all,
    prune_merged_branches,
)


class TestListRemoteCollaboratorBranches:
    @patch("db_mcp.collab.merge.git")
    def test_lists_collaborator_branches(self, mock_git):
        mock_result = MagicMock()
        mock_result.stdout = (
            "  origin/collaborator/alice\n  origin/collaborator/bob\n  origin/main\n"
        )
        mock_git._run.return_value = mock_result
        path = Path("/fake/connection")

        branches = _list_remote_collaborator_branches(path)

        assert branches == [
            "origin/collaborator/alice",
            "origin/collaborator/bob",
        ]

    @patch("db_mcp.collab.merge.git")
    def test_empty_when_no_branches(self, mock_git):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_git._run.return_value = mock_result
        path = Path("/fake/connection")

        branches = _list_remote_collaborator_branches(path)
        assert branches == []

    @patch("db_mcp.collab.merge.git")
    def test_handles_git_error(self, mock_git):
        mock_git._run.side_effect = subprocess.CalledProcessError(1, "git")
        path = Path("/fake/connection")

        branches = _list_remote_collaborator_branches(path)
        assert branches == []


class TestMasterMergeAll:
    @patch("db_mcp.collab.merge.prune_merged_branches", return_value=[])
    @patch("db_mcp.collab.merge._list_remote_collaborator_branches", return_value=[])
    @patch("db_mcp.collab.merge.git")
    def test_no_collaborator_branches(self, mock_git, _list_fn, _prune):
        mock_git.current_branch.return_value = "main"
        path = Path("/fake/connection")

        result = master_merge_all(path)

        assert result.collaborators == []
        assert result.total_additive == 0

    @patch("db_mcp.collab.merge.prune_merged_branches", return_value=[])
    @patch("db_mcp.collab.merge.gh_available", return_value=False)
    @patch(
        "db_mcp.collab.merge._list_remote_collaborator_branches",
        return_value=["origin/collaborator/alice"],
    )
    @patch("db_mcp.collab.merge.git")
    def test_auto_merges_additive(self, mock_git, _list_fn, _gh, _prune):
        mock_git.current_branch.return_value = "main"
        mock_git.diff_names.return_value = ["examples/abc.yaml", "examples/def.yaml"]
        path = Path("/fake/connection")

        result = master_merge_all(path)

        assert len(result.collaborators) == 1
        assert result.collaborators[0].user_name == "alice"
        assert result.collaborators[0].additive_merged == 2
        assert result.collaborators[0].shared_state_files == []
        mock_git.merge.assert_called_once_with(path, "origin/collaborator/alice")
        mock_git.push.assert_called_once_with(path)

    @patch("db_mcp.collab.merge.prune_merged_branches", return_value=[])
    @patch(
        "db_mcp.collab.merge.open_pr",
        return_value="https://github.com/org/repo/pull/5",
    )
    @patch("db_mcp.collab.merge.gh_available", return_value=True)
    @patch(
        "db_mcp.collab.merge._list_remote_collaborator_branches",
        return_value=["origin/collaborator/bob"],
    )
    @patch("db_mcp.collab.merge.git")
    def test_opens_pr_for_shared_state(self, mock_git, _list_fn, _gh, mock_pr, _prune):
        mock_git.current_branch.return_value = "main"
        mock_git.diff_names.return_value = [
            "examples/abc.yaml",
            "schema/descriptions.yaml",
        ]
        path = Path("/fake/connection")

        result = master_merge_all(path)

        assert len(result.collaborators) == 1
        assert result.collaborators[0].shared_state_files == ["schema/descriptions.yaml"]
        assert result.collaborators[0].pr_opened is True
        # Should NOT auto-merge when shared state is present
        mock_git.merge.assert_not_called()

    @patch("db_mcp.collab.merge.prune_merged_branches", return_value=[])
    @patch("db_mcp.collab.merge.gh_available", return_value=False)
    @patch(
        "db_mcp.collab.merge._list_remote_collaborator_branches",
        return_value=[
            "origin/collaborator/alice",
            "origin/collaborator/bob",
        ],
    )
    @patch("db_mcp.collab.merge.git")
    def test_processes_multiple_collaborators(self, mock_git, _list_fn, _gh, _prune):
        mock_git.current_branch.return_value = "main"
        mock_git.diff_names.side_effect = [
            ["examples/a.yaml"],  # alice: additive only
            ["examples/b.yaml", "domain/model.md"],  # bob: mixed
        ]
        path = Path("/fake/connection")

        result = master_merge_all(path)

        assert len(result.collaborators) == 2
        assert result.total_additive == 2
        assert result.total_prs == 0  # gh not available


class TestMergeConflictFallback:
    @patch("db_mcp.collab.merge.prune_merged_branches", return_value=[])
    @patch("db_mcp.collab.merge.open_pr", return_value="https://github.com/org/repo/pull/10")
    @patch("db_mcp.collab.merge.gh_available", return_value=True)
    @patch(
        "db_mcp.collab.merge._list_remote_collaborator_branches",
        return_value=["origin/collaborator/alice"],
    )
    @patch("db_mcp.collab.merge.git")
    def test_merge_conflict_falls_back_to_pr(self, mock_git, _list_fn, _gh, mock_pr, _prune):
        mock_git.current_branch.return_value = "main"
        mock_git.diff_names.return_value = ["examples/abc.yaml"]
        mock_git.merge.side_effect = Exception("conflict")
        path = Path("/fake/connection")

        result = master_merge_all(path)

        mock_git.merge_abort.assert_called_once_with(path)
        assert result.collaborators[0].pr_opened is True
        assert result.collaborators[0].additive_merged == 0


class TestCollabYamlAutoMerge:
    @patch("db_mcp.collab.merge.prune_merged_branches", return_value=[])
    @patch("db_mcp.collab.merge.gh_available", return_value=False)
    @patch(
        "db_mcp.collab.merge._list_remote_collaborator_branches",
        return_value=["origin/collaborator/alice"],
    )
    @patch("db_mcp.collab.merge.git")
    def test_collab_yaml_only_auto_merges(self, mock_git, _list_fn, _gh, _prune):
        mock_git.current_branch.return_value = "main"
        mock_git.diff_names.return_value = [".collab.yaml"]
        path = Path("/fake/connection")

        result = master_merge_all(path)

        mock_git.merge.assert_called_once_with(path, "origin/collaborator/alice")
        assert result.collaborators[0].additive_merged == 1  # .collab.yaml auto-merged
        assert result.collaborators[0].shared_state_files == [".collab.yaml"]


class TestPruneMergedBranches:
    @patch("db_mcp.collab.merge.git")
    def test_prunes_merged_branches(self, mock_git):
        mock_git.list_merged_remote_branches.return_value = [
            "origin/collaborator/alice",
            "origin/collaborator/bob",
        ]
        path = Path("/fake/connection")

        pruned = prune_merged_branches(path)

        assert pruned == ["collaborator/alice", "collaborator/bob"]
        assert mock_git.delete_remote_branch.call_count == 2

    @patch("db_mcp.collab.merge.git")
    def test_no_branches_to_prune(self, mock_git):
        mock_git.list_merged_remote_branches.return_value = []
        path = Path("/fake/connection")

        pruned = prune_merged_branches(path)
        assert pruned == []

    @patch("db_mcp.collab.merge.git")
    def test_handles_delete_failure(self, mock_git):
        mock_git.list_merged_remote_branches.return_value = [
            "origin/collaborator/alice",
        ]
        mock_git.delete_remote_branch.side_effect = Exception("permission denied")
        path = Path("/fake/connection")

        pruned = prune_merged_branches(path)
        assert pruned == []  # failed to delete


class TestMergeResult:
    def test_total_additive(self):
        r = MergeResult(
            collaborators=[
                CollaboratorMergeResult(user_name="a", additive_merged=3),
                CollaboratorMergeResult(user_name="b", additive_merged=5),
            ]
        )
        assert r.total_additive == 8

    def test_total_prs(self):
        r = MergeResult(
            collaborators=[
                CollaboratorMergeResult(user_name="a", pr_opened=True),
                CollaboratorMergeResult(user_name="b", pr_opened=False),
                CollaboratorMergeResult(user_name="c", pr_opened=True),
            ]
        )
        assert r.total_prs == 2
