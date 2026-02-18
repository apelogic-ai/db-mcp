"""Tests for db_mcp.cli.git_ops module.

Tests is_git_url, git_init, git_clone using mocked subprocess / git_utils.
No real git operations are performed.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db_mcp.cli.git_ops import (
    GITIGNORE_CONTENT,
    git_clone,
    git_init,
    git_pull,
    git_sync,
    is_git_installed,
    is_git_url,
)


class TestIsGitInstalled:
    def test_always_true(self):
        """Always True — dulwich provides a fallback."""
        assert is_git_installed() is True


class TestIsGitUrl:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("git@github.com:org/repo.git", True),
            ("https://github.com/org/repo", True),
            ("https://gitlab.com/org/repo.git", True),
            ("https://bitbucket.org/org/repo", True),
            ("https://github.com/user/repo", True),  # github.com in url
            ("repo.git", True),  # ends with .git
            ("", False),
            ("not-a-url", False),
            ("https://example.com/something", False),
            ("/local/path/to/repo", False),
            ("just-a-name", False),
        ],
    )
    def test_url_detection(self, url, expected):
        assert is_git_url(url) == expected

    def test_none_returns_false(self):
        assert is_git_url(None) is False  # type: ignore

    def test_gitlab_url(self):
        assert is_git_url("https://gitlab.com/group/project") is True

    def test_ssh_url(self):
        assert is_git_url("git@gitlab.com:group/project.git") is True


class TestGitInit:
    def test_success_without_remote(self, tmp_path):
        """git_init returns True on success with no remote."""
        mock_git = MagicMock()

        with patch("db_mcp.cli.git_ops.console"), patch(
            "db_mcp.git_utils.git", mock_git
        ):
            result = git_init(tmp_path)

        assert result is True
        mock_git.init.assert_called_once_with(tmp_path)
        mock_git.add.assert_called_once_with(tmp_path, ["."])
        mock_git.commit.assert_called_once()
        mock_git.remote_add.assert_not_called()

    def test_success_with_remote(self, tmp_path):
        """git_init sets remote when url provided."""
        mock_git = MagicMock()

        with patch("db_mcp.cli.git_ops.console"), patch(
            "db_mcp.git_utils.git", mock_git
        ):
            result = git_init(tmp_path, remote_url="git@github.com:org/repo.git")

        assert result is True
        mock_git.remote_add.assert_called_once_with(
            tmp_path, "origin", "git@github.com:org/repo.git"
        )

    def test_creates_gitignore_when_missing(self, tmp_path):
        """git_init writes .gitignore if not present."""
        mock_git = MagicMock()

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            git_init(tmp_path)

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".*" in gitignore.read_text()

    def test_does_not_overwrite_existing_gitignore(self, tmp_path):
        """git_init preserves existing .gitignore."""
        existing = tmp_path / ".gitignore"
        existing.write_text("custom content\n")
        mock_git = MagicMock()

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            git_init(tmp_path)

        assert existing.read_text() == "custom content\n"

    def test_returns_false_on_exception(self, tmp_path):
        """git_init returns False when git raises."""
        mock_git = MagicMock()
        mock_git.init.side_effect = RuntimeError("git broke")

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_init(tmp_path)

        assert result is False


class TestGitClone:
    def test_success(self, tmp_path):
        """git_clone returns True on success."""
        mock_git = MagicMock()

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_clone("git@github.com:org/repo.git", tmp_path / "dest")

        assert result is True
        mock_git.clone.assert_called_once_with(
            "git@github.com:org/repo.git", tmp_path / "dest"
        )

    def test_returns_false_on_not_implemented(self, tmp_path):
        """Returns False when native git not available for clone."""
        mock_git = MagicMock()
        mock_git.clone.side_effect = NotImplementedError("need native git")

        with patch("db_mcp.cli.git_ops.console") as mock_console, patch(
            "db_mcp.git_utils.git", mock_git
        ):
            result = git_clone("git@github.com:org/repo.git", tmp_path / "dest")

        assert result is False
        mock_console.print.assert_called()

    def test_returns_false_on_exception(self, tmp_path):
        """Returns False when clone raises."""
        mock_git = MagicMock()
        mock_git.clone.side_effect = RuntimeError("network error")

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_clone("git@github.com:org/repo.git", tmp_path / "dest")

        assert result is False


class TestGitSync:
    def test_commits_and_pushes_when_changes_exist(self, tmp_path):
        """git_sync commits, pulls, then pushes when there are changes."""
        mock_git = MagicMock()
        mock_git.status.return_value = ["modified: foo.yaml"]
        mock_git.has_remote.return_value = True

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_sync(tmp_path)

        assert result is True
        mock_git.add.assert_called_once_with(tmp_path, ["."])
        mock_git.commit.assert_called_once()
        mock_git.pull.assert_called_once()
        mock_git.push.assert_called_once()

    def test_skips_commit_when_no_changes(self, tmp_path):
        """git_sync skips commit when working tree is clean."""
        mock_git = MagicMock()
        mock_git.status.return_value = []
        mock_git.has_remote.return_value = True

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_sync(tmp_path)

        assert result is True
        mock_git.add.assert_not_called()
        mock_git.commit.assert_not_called()

    def test_returns_true_when_no_remote(self, tmp_path):
        """git_sync returns True (no-op) when no remote configured."""
        mock_git = MagicMock()
        mock_git.status.return_value = []
        mock_git.has_remote.return_value = False

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_sync(tmp_path)

        assert result is True
        mock_git.push.assert_not_called()

    def test_returns_false_on_push_rejected(self, tmp_path):
        """Returns False when push is rejected."""
        mock_git = MagicMock()
        mock_git.status.return_value = []
        mock_git.has_remote.return_value = True
        mock_git.push.side_effect = Exception("rejected: non-fast-forward")

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_sync(tmp_path)

        assert result is False


class TestGitPull:
    def test_pulls_cleanly(self, tmp_path):
        """git_pull succeeds on clean working tree."""
        mock_git = MagicMock()
        mock_git.status.return_value = []

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_pull(tmp_path)

        assert result is True
        mock_git.pull.assert_called_once()

    def test_stashes_and_pops_when_changes(self, tmp_path):
        """git_pull stashes local changes, pulls, then restores them."""
        mock_git = MagicMock()
        mock_git.status.return_value = ["modified: foo.yaml"]

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_pull(tmp_path)

        assert result is True
        mock_git.stash.assert_called_once()
        mock_git.stash_pop.assert_called_once()

    def test_returns_false_when_stash_not_supported(self, tmp_path):
        """Returns False when stash not available (dulwich fallback)."""
        mock_git = MagicMock()
        mock_git.status.return_value = ["modified: foo.yaml"]
        mock_git.stash.side_effect = NotImplementedError("need native git")

        with patch("db_mcp.cli.git_ops.console"), patch("db_mcp.git_utils.git", mock_git):
            result = git_pull(tmp_path)

        assert result is False
