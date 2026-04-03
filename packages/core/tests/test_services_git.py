"""Tests for services/git.py — git history/show/revert service functions.

Step 4.06: Replace git handlers with service calls (3 methods).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# get_git_history
# ---------------------------------------------------------------------------


class TestGetGitHistory:
    def test_returns_commit_list(self, tmp_path):
        from db_mcp.services.git import get_git_history

        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        target_file = tmp_path / "schema" / "descriptions.yaml"
        target_file.parent.mkdir()
        target_file.touch()

        fake_commit = MagicMock()
        fake_commit.hash = "abc1234"
        fake_commit.full_hash = "abc1234567890abcdef"
        fake_commit.message = "Initial commit"
        fake_commit.date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fake_commit.author = "Alice"

        mock_git = MagicMock()
        mock_git.log.return_value = [fake_commit]

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = get_git_history(tmp_path, "schema/descriptions.yaml", limit=10)

        assert result["success"] is True
        assert len(result["commits"]) == 1
        commit = result["commits"][0]
        assert commit["hash"] == "abc1234"
        assert commit["fullHash"] == "abc1234567890abcdef"
        assert commit["message"] == "Initial commit"
        assert commit["author"] == "Alice"
        assert commit["date"] == "2026-01-01T00:00:00+00:00"
        mock_git.log.assert_called_once_with(tmp_path, "schema/descriptions.yaml", limit=10)

    def test_uses_default_limit_50(self, tmp_path):
        from db_mcp.services.git import get_git_history

        (tmp_path / ".git").mkdir()
        target = tmp_path / "file.yaml"
        target.touch()

        mock_git = MagicMock()
        mock_git.log.return_value = []

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            get_git_history(tmp_path, "file.yaml")

        mock_git.log.assert_called_once_with(tmp_path, "file.yaml", limit=50)

    def test_error_when_git_not_enabled(self, tmp_path):
        from db_mcp.services.git import get_git_history

        target = tmp_path / "file.yaml"
        target.touch()

        result = get_git_history(tmp_path, "file.yaml")

        assert result["success"] is False
        assert "git" in result["error"].lower()

    def test_error_when_file_not_found(self, tmp_path):
        from db_mcp.services.git import get_git_history

        (tmp_path / ".git").mkdir()

        result = get_git_history(tmp_path, "nonexistent.yaml")

        assert result["success"] is False
        assert result["error"] is not None

    def test_error_on_git_exception(self, tmp_path):
        from db_mcp.services.git import get_git_history

        (tmp_path / ".git").mkdir()
        target = tmp_path / "file.yaml"
        target.touch()

        mock_git = MagicMock()
        mock_git.log.side_effect = RuntimeError("git exploded")

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = get_git_history(tmp_path, "file.yaml")

        assert result["success"] is False
        assert "git exploded" in result["error"]

    def test_error_on_path_traversal(self, tmp_path):
        from db_mcp.services.git import get_git_history

        (tmp_path / ".git").mkdir()

        result = get_git_history(tmp_path, "../etc/passwd")

        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    def test_error_on_absolute_path(self, tmp_path):
        from db_mcp.services.git import get_git_history

        (tmp_path / ".git").mkdir()

        result = get_git_history(tmp_path, "/etc/passwd")

        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    def test_error_when_connection_dir_missing(self, tmp_path):
        from db_mcp.services.git import get_git_history

        missing = tmp_path / "nonexistent"

        result = get_git_history(missing, "file.yaml")

        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# get_git_content
# ---------------------------------------------------------------------------


class TestGetGitContent:
    def test_returns_file_content_at_commit(self, tmp_path):
        from db_mcp.services.git import get_git_content

        (tmp_path / ".git").mkdir()

        mock_git = MagicMock()
        mock_git.show.return_value = "column: orders\n"

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = get_git_content(tmp_path, "schema/descriptions.yaml", "abc1234")

        assert result["success"] is True
        assert result["content"] == "column: orders\n"
        assert result["commit"] == "abc1234"
        mock_git.show.assert_called_once_with(tmp_path, "schema/descriptions.yaml", "abc1234")

    def test_error_when_git_not_enabled(self, tmp_path):
        from db_mcp.services.git import get_git_content

        result = get_git_content(tmp_path, "file.yaml", "abc1234")

        assert result["success"] is False
        assert "git" in result["error"].lower()

    def test_error_on_file_not_found_in_history(self, tmp_path):
        from db_mcp.services.git import get_git_content

        (tmp_path / ".git").mkdir()

        mock_git = MagicMock()
        mock_git.show.side_effect = FileNotFoundError("not in history")

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = get_git_content(tmp_path, "file.yaml", "abc1234")

        assert result["success"] is False
        assert "not in history" in result["error"]

    def test_error_on_git_exception(self, tmp_path):
        from db_mcp.services.git import get_git_content

        (tmp_path / ".git").mkdir()

        mock_git = MagicMock()
        mock_git.show.side_effect = RuntimeError("git exploded")

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = get_git_content(tmp_path, "file.yaml", "abc1234")

        assert result["success"] is False
        assert "git exploded" in result["error"]

    def test_error_on_path_traversal(self, tmp_path):
        from db_mcp.services.git import get_git_content

        (tmp_path / ".git").mkdir()

        result = get_git_content(tmp_path, "../etc/passwd", "abc1234")

        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    def test_error_on_invalid_commit_hash(self, tmp_path):
        from db_mcp.services.git import get_git_content

        (tmp_path / ".git").mkdir()

        result = get_git_content(tmp_path, "file.yaml", "../../bad")

        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    def test_error_when_connection_dir_missing(self, tmp_path):
        from db_mcp.services.git import get_git_content

        missing = tmp_path / "nonexistent"

        result = get_git_content(missing, "file.yaml", "abc1234")

        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# revert_git_file
# ---------------------------------------------------------------------------


class TestRevertGitFile:
    def test_reverts_file_and_commits(self, tmp_path):
        from db_mcp.services.git import revert_git_file

        (tmp_path / ".git").mkdir()
        target = tmp_path / "schema" / "descriptions.yaml"
        target.parent.mkdir()
        target.write_text("old content")

        mock_git = MagicMock()
        mock_git.show.return_value = "reverted content\n"
        mock_git.add.return_value = None
        mock_git.commit.return_value = "newcommit"

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = revert_git_file(tmp_path, "schema/descriptions.yaml", "abc1234")

        assert result["success"] is True
        assert "abc1234" in result["message"]
        assert target.read_text() == "reverted content\n"
        mock_git.show.assert_called_once_with(tmp_path, "schema/descriptions.yaml", "abc1234")
        mock_git.add.assert_called_once_with(tmp_path, ["schema/descriptions.yaml"])
        mock_git.commit.assert_called_once()

    def test_error_when_git_not_enabled(self, tmp_path):
        from db_mcp.services.git import revert_git_file

        result = revert_git_file(tmp_path, "file.yaml", "abc1234")

        assert result["success"] is False
        assert "git" in result["error"].lower()

    def test_error_on_file_not_found_in_history(self, tmp_path):
        from db_mcp.services.git import revert_git_file

        (tmp_path / ".git").mkdir()

        mock_git = MagicMock()
        mock_git.show.side_effect = FileNotFoundError("not in history")

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = revert_git_file(tmp_path, "file.yaml", "abc1234")

        assert result["success"] is False
        assert "not in history" in result["error"]

    def test_error_on_git_exception(self, tmp_path):
        from db_mcp.services.git import revert_git_file

        (tmp_path / ".git").mkdir()

        mock_git = MagicMock()
        mock_git.show.side_effect = RuntimeError("git exploded")

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = revert_git_file(tmp_path, "file.yaml", "abc1234")

        assert result["success"] is False
        assert "git exploded" in result["error"]

    def test_creates_parent_directory_for_new_file(self, tmp_path):
        """Revert can restore a deleted file — parent dir may not exist."""
        from db_mcp.services.git import revert_git_file

        (tmp_path / ".git").mkdir()
        # Target dir does not exist yet
        assert not (tmp_path / "new_dir").exists()

        mock_git = MagicMock()
        mock_git.show.return_value = "restored content\n"
        mock_git.commit.return_value = "newcommit"

        with patch("db_mcp.services.git._get_git", return_value=mock_git):
            result = revert_git_file(tmp_path, "new_dir/file.yaml", "abc1234")

        assert result["success"] is True
        assert (tmp_path / "new_dir" / "file.yaml").read_text() == "restored content\n"

    def test_error_on_path_traversal(self, tmp_path):
        from db_mcp.services.git import revert_git_file

        (tmp_path / ".git").mkdir()

        result = revert_git_file(tmp_path, "../etc/passwd", "abc1234")

        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    def test_error_on_invalid_commit_hash(self, tmp_path):
        from db_mcp.services.git import revert_git_file

        (tmp_path / ".git").mkdir()

        result = revert_git_file(tmp_path, "file.yaml", "../../bad")

        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    def test_error_when_connection_dir_missing(self, tmp_path):
        from db_mcp.services.git import revert_git_file

        missing = tmp_path / "nonexistent"

        result = revert_git_file(missing, "file.yaml", "abc1234")

        assert result["success"] is False
        assert "not found" in result["error"].lower()



# ---------------------------------------------------------------------------
# try_git_commit (4.09)
# ---------------------------------------------------------------------------


def test_try_git_commit_returns_false_when_no_git_dir(tmp_path):
    from db_mcp.services.git import try_git_commit

    result = try_git_commit(tmp_path, "test commit", ["file.yaml"])
    assert result is False


def test_try_git_commit_returns_true_on_success(tmp_path):
    from db_mcp.services.git import try_git_commit

    (tmp_path / ".git").mkdir()
    fake_git = MagicMock()
    fake_git.commit.return_value = "abc1234 test commit"

    with patch("db_mcp.services.git._get_git", return_value=fake_git):
        result = try_git_commit(tmp_path, "test commit", ["file.yaml"])

    assert result is True
    fake_git.add.assert_called_once_with(tmp_path, ["file.yaml"])
    fake_git.commit.assert_called_once_with(tmp_path, "test commit")


def test_try_git_commit_returns_false_when_commit_is_none(tmp_path):
    from db_mcp.services.git import try_git_commit

    (tmp_path / ".git").mkdir()
    fake_git = MagicMock()
    fake_git.commit.return_value = None

    with patch("db_mcp.services.git._get_git", return_value=fake_git):
        result = try_git_commit(tmp_path, "nothing to commit", ["file.yaml"])

    assert result is False


def test_try_git_commit_returns_false_on_exception(tmp_path):
    from db_mcp.services.git import try_git_commit

    (tmp_path / ".git").mkdir()
    fake_git = MagicMock()
    fake_git.add.side_effect = RuntimeError("git not found")

    with patch("db_mcp.services.git._get_git", return_value=fake_git):
        result = try_git_commit(tmp_path, "test commit", ["file.yaml"])

    assert result is False
