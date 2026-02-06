"""Tests for git backend branch operations."""

import subprocess

import pytest

from db_mcp.git_utils import NativeGitBackend


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    backend = NativeGitBackend()
    backend.init(tmp_path)
    # Configure git user for commits
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    # Initial commit
    (tmp_path / "README.md").write_text("# test\n")
    backend.add(tmp_path, ["."])
    backend.commit(tmp_path, "initial commit")
    return tmp_path, backend


class TestCurrentBranch:
    """Test current_branch operation."""

    def test_returns_default_branch(self, git_repo):
        path, backend = git_repo
        branch = backend.current_branch(path)
        assert branch in ("main", "master")

    def test_returns_feature_branch(self, git_repo):
        path, backend = git_repo
        backend.checkout(path, "feature/test", create=True)
        assert backend.current_branch(path) == "feature/test"


class TestCheckout:
    """Test checkout operation."""

    def test_create_and_switch_branch(self, git_repo):
        path, backend = git_repo
        backend.checkout(path, "collaborator/alice", create=True)
        assert backend.current_branch(path) == "collaborator/alice"

    def test_switch_to_existing_branch(self, git_repo):
        path, backend = git_repo
        backend.checkout(path, "collaborator/alice", create=True)
        # Switch back to main/master
        default_branch = "main" if backend.branch_exists(path, "main") else "master"
        backend.checkout(path, default_branch)
        assert backend.current_branch(path) == default_branch
        # Switch back
        backend.checkout(path, "collaborator/alice")
        assert backend.current_branch(path) == "collaborator/alice"

    def test_create_fails_if_exists(self, git_repo):
        path, backend = git_repo
        backend.checkout(path, "test-branch", create=True)
        default_branch = "main" if backend.branch_exists(path, "main") else "master"
        backend.checkout(path, default_branch)
        with pytest.raises(subprocess.CalledProcessError):
            backend.checkout(path, "test-branch", create=True)


class TestBranchExists:
    """Test branch_exists operation."""

    def test_default_branch_exists(self, git_repo):
        path, backend = git_repo
        default_branch = "main" if backend.branch_exists(path, "main") else "master"
        assert backend.branch_exists(path, default_branch)

    def test_nonexistent_branch(self, git_repo):
        path, backend = git_repo
        assert not backend.branch_exists(path, "nonexistent")

    def test_created_branch_exists(self, git_repo):
        path, backend = git_repo
        backend.checkout(path, "collaborator/bob", create=True)
        assert backend.branch_exists(path, "collaborator/bob")


class TestMerge:
    """Test merge operation."""

    def test_merge_branch(self, git_repo):
        path, backend = git_repo
        default_branch = backend.current_branch(path)

        # Create feature branch with a new file
        backend.checkout(path, "feature", create=True)
        (path / "new_file.txt").write_text("hello\n")
        backend.add(path, ["new_file.txt"])
        backend.commit(path, "add new file")

        # Switch back and merge
        backend.checkout(path, default_branch)
        assert not (path / "new_file.txt").exists()
        backend.merge(path, "feature")
        assert (path / "new_file.txt").exists()


class TestDiffNames:
    """Test diff_names operation."""

    def test_shows_changed_files(self, git_repo):
        path, backend = git_repo
        default_branch = backend.current_branch(path)

        # Create branch with changes
        backend.checkout(path, "collaborator/alice", create=True)
        (path / "examples").mkdir(exist_ok=True)
        (path / "examples" / "ex1.yaml").write_text("intent: test\n")
        (path / "schema").mkdir(exist_ok=True)
        (path / "schema" / "descriptions.yaml").write_text("tables: []\n")
        backend.add(path, ["."])
        backend.commit(path, "add files")

        changed = backend.diff_names(path, default_branch, "collaborator/alice")
        assert "examples/ex1.yaml" in changed
        assert "schema/descriptions.yaml" in changed

    def test_empty_diff(self, git_repo):
        path, backend = git_repo
        default_branch = backend.current_branch(path)
        backend.checkout(path, "empty-branch", create=True)
        changed = backend.diff_names(path, default_branch, "empty-branch")
        assert changed == []


class TestPushBranch:
    """Test push_branch operation."""

    def test_push_branch_to_remote(self, tmp_path):
        """Test pushing a specific branch to a remote (bare repo)."""
        backend = NativeGitBackend()

        # Create a bare remote repo
        remote_path = tmp_path / "remote.git"
        remote_path.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=remote_path, check=True)

        # Create local repo
        local_path = tmp_path / "local"
        backend.init(local_path)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=local_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=local_path,
            check=True,
        )
        (local_path / "README.md").write_text("# test\n")
        backend.add(local_path, ["."])
        backend.commit(local_path, "initial")
        backend.remote_add(local_path, "origin", str(remote_path))
        backend.push(local_path)

        # Create a branch and push it
        backend.checkout(local_path, "collaborator/alice", create=True)
        (local_path / "test.txt").write_text("hello\n")
        backend.add(local_path, ["test.txt"])
        backend.commit(local_path, "branch commit")
        backend.push_branch(local_path, "collaborator/alice")

        # Verify remote has the branch
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=local_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "origin/collaborator/alice" in result.stdout


class TestFetch:
    """Test fetch operation."""

    def test_fetch_from_remote(self, tmp_path):
        backend = NativeGitBackend()

        # Create a bare remote
        remote_path = tmp_path / "remote.git"
        remote_path.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=remote_path, check=True)

        # Create local repo and push
        local_path = tmp_path / "local"
        backend.init(local_path)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=local_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=local_path,
            check=True,
        )
        (local_path / "README.md").write_text("# test\n")
        backend.add(local_path, ["."])
        backend.commit(local_path, "initial")
        backend.remote_add(local_path, "origin", str(remote_path))
        backend.push(local_path)

        # Fetch should succeed without errors
        backend.fetch(local_path)
