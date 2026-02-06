"""Tests for GitHub PR helper."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from db_mcp.collab.github import gh_available, list_prs, open_pr


class TestGhAvailable:
    @patch("shutil.which", return_value="/usr/local/bin/gh")
    def test_available(self, _):
        assert gh_available() is True

    @patch("shutil.which", return_value=None)
    def test_not_available(self, _):
        assert gh_available() is False


class TestOpenPr:
    @patch("db_mcp.collab.github.gh_available", return_value=False)
    def test_returns_none_without_gh(self, _):
        result = open_pr(Path("/fake"), "branch", "title", "body")
        assert result is None

    @patch("subprocess.run")
    @patch("db_mcp.collab.github.gh_available", return_value=True)
    def test_returns_url_on_success(self, _, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/org/repo/pull/42\n",
        )
        result = open_pr(Path("/fake"), "collaborator/alice", "title", "body")
        assert result == "https://github.com/org/repo/pull/42"

    @patch("subprocess.run")
    @patch("db_mcp.collab.github.gh_available", return_value=True)
    def test_returns_none_when_pr_exists(self, _, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="a pull request for branch already exists",
        )
        result = open_pr(Path("/fake"), "collaborator/alice", "title", "body")
        assert result is None

    @patch("subprocess.run", side_effect=Exception("boom"))
    @patch("db_mcp.collab.github.gh_available", return_value=True)
    def test_returns_none_on_exception(self, _, __):
        result = open_pr(Path("/fake"), "branch", "title", "body")
        assert result is None


class TestListPrs:
    @patch("db_mcp.collab.github.gh_available", return_value=False)
    def test_returns_empty_without_gh(self, _):
        assert list_prs(Path("/fake")) == []

    @patch("subprocess.run")
    @patch("db_mcp.collab.github.gh_available", return_value=True)
    def test_returns_parsed_prs(self, _, mock_run):
        pr_json = (
            '[{"number": 42, "title": "test PR", "url": "https://...",'
            ' "headRefName": "collaborator/alice", "state": "OPEN"}]'
        )
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=pr_json,
        )
        prs = list_prs(Path("/fake"))
        assert len(prs) == 1
        assert prs[0]["number"] == 42

    @patch("subprocess.run")
    @patch("db_mcp.collab.github.gh_available", return_value=True)
    def test_returns_empty_on_error(self, _, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert list_prs(Path("/fake")) == []
