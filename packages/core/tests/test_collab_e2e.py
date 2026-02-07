"""End-to-end integration tests for the collaborative git sync flow.

These tests use real local git repos (bare remote + working clones)
to verify the full collaborator_pull -> collaborator_push -> master_merge_all
lifecycle without mocking the git backend.

Run separately:  uv run pytest -m e2e -v
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from db_mcp.collab.manifest import CollabManifest, add_member, save_manifest
from db_mcp.collab.merge import master_merge_all
from db_mcp.collab.sync import collaborator_pull, collaborator_push, full_sync
from db_mcp.git_utils import NativeGitBackend

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

backend = NativeGitBackend()


def _git_config(path: Path, name: str, email: str) -> None:
    """Configure git user for a repo (required for commits)."""
    subprocess.run(["git", "config", "user.email", email], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", name], cwd=path, check=True)


def _create_additive_file(
    repo: Path, filename: str = "ex1.yaml", content: str = "intent: test query\n"
) -> None:
    """Create a file under examples/ (classifies as additive)."""
    (repo / "examples").mkdir(exist_ok=True)
    (repo / "examples" / filename).write_text(content)


def _create_shared_state_file(
    repo: Path,
    subdir: str = "schema",
    filename: str = "descriptions.yaml",
    content: str = "tables: []\n",
) -> None:
    """Create a file under schema/ or similar (classifies as shared-state)."""
    (repo / subdir).mkdir(exist_ok=True)
    (repo / subdir / filename).write_text(content)


def _refresh_master(master_path: Path) -> None:
    """Pull latest from origin into master's working directory."""
    backend.fetch(master_path)
    backend.merge(master_path, "origin/main")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bare_remote(tmp_path):
    """Create a bare git repository acting as the shared remote."""
    remote_path = tmp_path / "remote.git"
    remote_path.mkdir()
    subprocess.run(["git", "init", "--bare", "-b", "main"], cwd=remote_path, check=True)
    return remote_path


@pytest.fixture
def master_repo(tmp_path, bare_remote):
    """Create the master's working repo with collab initialized."""
    master_path = tmp_path / "master"
    backend.init(master_path)
    # Force main branch (system default might be 'master')
    subprocess.run(
        ["git", "checkout", "-b", "main"],
        cwd=master_path,
        capture_output=True,
        check=False,
    )
    _git_config(master_path, "Master", "master@test.com")

    # Seed: README + collab manifest with master member
    (master_path / "README.md").write_text("# Test Vault\n")
    manifest = CollabManifest(created_at=datetime.now(timezone.utc))
    manifest = add_member(manifest, "master", "master-001", "master")
    save_manifest(master_path, manifest)

    backend.add(master_path, ["."])
    backend.commit(master_path, "Initial commit with collab manifest")
    backend.remote_add(master_path, "origin", str(bare_remote))
    backend.push(master_path)
    return master_path


@pytest.fixture
def make_collaborator(tmp_path, bare_remote):
    """Factory fixture: make_collaborator('alice') → cloned repo Path."""

    def _make(name: str) -> Path:
        collab_path = tmp_path / name
        backend.clone(str(bare_remote), collab_path)
        _git_config(collab_path, name.title(), f"{name}@test.com")
        return collab_path

    return _make


# ---------------------------------------------------------------------------
# TestCollaboratorPullE2E
# ---------------------------------------------------------------------------


class TestCollaboratorPullE2E:
    def test_pull_fetches_main_changes(self, master_repo, make_collaborator):
        # Master pushes a new file
        _create_additive_file(master_repo, "master_hint.yaml", "hint: use JOIN\n")
        backend.add(master_repo, ["."])
        backend.commit(master_repo, "Add master hint")
        backend.push(master_repo)

        # Collaborator clones and pulls
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")

        assert backend.current_branch(alice) == "collaborator/alice"
        assert (alice / "examples" / "master_hint.yaml").exists()
        assert (alice / "examples" / "master_hint.yaml").read_text() == "hint: use JOIN\n"

    def test_pull_creates_branch_if_missing(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        # Alice starts on main, no collaborator branch exists
        assert backend.current_branch(alice) == "main"

        collaborator_pull(alice, "alice")

        assert backend.current_branch(alice) == "collaborator/alice"


# ---------------------------------------------------------------------------
# TestCollaboratorPushAdditiveE2E
# ---------------------------------------------------------------------------


class TestCollaboratorPushAdditiveE2E:
    def test_additive_auto_merges_to_main(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")

        _create_additive_file(alice, "alice_q1.yaml", "intent: count users\n")
        result = collaborator_push(alice, "alice")

        assert result.additive_merged == 1
        assert result.shared_state_files == []
        assert result.pr_opened is False

        # Verify file reached master's main
        _refresh_master(master_repo)
        assert (master_repo / "examples" / "alice_q1.yaml").exists()

    def test_multiple_additive_files(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")

        _create_additive_file(alice, "q1.yaml", "intent: query 1\n")
        _create_additive_file(alice, "q2.yaml", "intent: query 2\n")
        # Also add a learnings file
        (alice / "learnings" / "failures").mkdir(parents=True, exist_ok=True)
        (alice / "learnings" / "failures" / "f1.yaml").write_text("error: timeout\n")

        result = collaborator_push(alice, "alice")

        assert result.additive_merged == 3
        assert result.shared_state_files == []

        _refresh_master(master_repo)
        assert (master_repo / "examples" / "q1.yaml").exists()
        assert (master_repo / "examples" / "q2.yaml").exists()
        assert (master_repo / "learnings" / "failures" / "f1.yaml").exists()

    def test_no_changes_returns_empty(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")

        result = collaborator_push(alice, "alice")

        assert result.additive_merged == 0
        assert result.shared_state_files == []


# ---------------------------------------------------------------------------
# TestCollaboratorPushSharedStateE2E
# ---------------------------------------------------------------------------


class TestCollaboratorPushSharedStateE2E:
    @patch("db_mcp.collab.sync.gh_available", return_value=False)
    def test_shared_state_pushes_branch_only(self, _mock_gh, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")

        _create_shared_state_file(alice)
        result = collaborator_push(alice, "alice")

        assert "schema/descriptions.yaml" in result.shared_state_files
        assert result.pr_opened is False

        # Main should NOT have the file
        _refresh_master(master_repo)
        assert not (master_repo / "schema" / "descriptions.yaml").exists()

    @patch("db_mcp.collab.sync.gh_available", return_value=False)
    def test_mixed_files_pushes_branch(self, _mock_gh, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")

        _create_additive_file(alice, "ex1.yaml")
        _create_shared_state_file(alice)
        result = collaborator_push(alice, "alice")

        # Additive counted but NOT merged to main (shared-state triggers branch-only)
        assert result.additive_merged == 1
        assert "schema/descriptions.yaml" in result.shared_state_files

        _refresh_master(master_repo)
        assert not (master_repo / "examples" / "ex1.yaml").exists()
        assert not (master_repo / "schema" / "descriptions.yaml").exists()

    @patch("db_mcp.collab.sync.open_pr", return_value="https://fake/pr/1")
    @patch("db_mcp.collab.sync.gh_available", return_value=True)
    def test_shared_state_opens_pr(self, _mock_gh, mock_pr, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")

        _create_shared_state_file(alice, "domain", "model.yaml", "entities: []\n")
        result = collaborator_push(alice, "alice")

        assert result.pr_opened is True
        assert result.pr_url == "https://fake/pr/1"
        mock_pr.assert_called_once()


# ---------------------------------------------------------------------------
# TestMasterMergeAllE2E
# ---------------------------------------------------------------------------


class TestMasterMergeAllE2E:
    def _push_collab_branch(self, collab_path: Path, name: str) -> None:
        """Manually push a collaborator branch (bypassing collaborator_push auto-merge)."""
        backend.checkout(collab_path, f"collaborator/{name}", create=True)
        backend.add(collab_path, ["."])
        backend.commit(collab_path, f"changes from {name}")
        backend.push_branch(collab_path, f"collaborator/{name}")

    def test_merge_additive_from_collaborator(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        _create_additive_file(alice, "alice_q.yaml", "intent: alice query\n")
        self._push_collab_branch(alice, "alice")

        result = master_merge_all(master_repo)

        assert len(result.collaborators) == 1
        assert result.collaborators[0].user_name == "alice"
        assert result.collaborators[0].additive_merged == 1
        assert result.collaborators[0].shared_state_files == []
        assert (master_repo / "examples" / "alice_q.yaml").exists()

    @patch("db_mcp.collab.merge.gh_available", return_value=False)
    def test_flags_shared_state(self, _mock_gh, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        _create_shared_state_file(alice)
        self._push_collab_branch(alice, "alice")

        result = master_merge_all(master_repo)

        assert len(result.collaborators) == 1
        assert "schema/descriptions.yaml" in result.collaborators[0].shared_state_files
        assert not (master_repo / "schema" / "descriptions.yaml").exists()

    def test_multiple_collaborators(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        _create_additive_file(alice, "alice_q.yaml", "intent: alice\n")
        self._push_collab_branch(alice, "alice")

        bob = make_collaborator("bob")
        _create_additive_file(bob, "bob_q.yaml", "intent: bob\n")
        self._push_collab_branch(bob, "bob")

        result = master_merge_all(master_repo)

        assert len(result.collaborators) == 2
        # Bob's clone includes alice's file (from shared remote), so after
        # alice is merged first, bob's diff against main shows only bob's file.
        # Total depends on merge order but both files end up on main.
        assert result.total_additive >= 2
        assert (master_repo / "examples" / "alice_q.yaml").exists()
        assert (master_repo / "examples" / "bob_q.yaml").exists()

    def test_no_collaborator_branches(self, master_repo):
        result = master_merge_all(master_repo)

        assert result.collaborators == []
        assert result.total_additive == 0


# ---------------------------------------------------------------------------
# TestFullSyncE2E
# ---------------------------------------------------------------------------


class TestFullSyncE2E:
    def test_full_sync_pull_and_push(self, master_repo, make_collaborator):
        # Master pushes a hint file
        _create_additive_file(master_repo, "master_hint.yaml", "hint: join tables\n")
        backend.add(master_repo, ["."])
        backend.commit(master_repo, "Add master hint")
        backend.push(master_repo)

        # Alice clones and creates her own file
        alice = make_collaborator("alice")
        _create_additive_file(alice, "alice_q.yaml", "intent: count users\n")

        result = full_sync(alice, "alice")

        # Pull brought master's hint
        assert (alice / "examples" / "master_hint.yaml").exists()
        # Push merged alice's file to main
        assert result.additive_merged == 1
        _refresh_master(master_repo)
        assert (master_repo / "examples" / "alice_q.yaml").exists()


# ---------------------------------------------------------------------------
# TestTwoCollaboratorsE2E
# ---------------------------------------------------------------------------


class TestTwoCollaboratorsE2E:
    def test_sequential_additive_no_conflict(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")
        _create_additive_file(alice, "alice_q.yaml", "intent: alice\n")
        collaborator_push(alice, "alice")

        bob = make_collaborator("bob")
        # Bob's clone picks up alice's merge on main
        result = full_sync(bob, "bob")
        # Bob should have alice's file (from pull)
        assert (bob / "examples" / "alice_q.yaml").exists()

        # Now bob adds his own
        _create_additive_file(bob, "bob_q.yaml", "intent: bob\n")
        result = collaborator_push(bob, "bob")
        assert result.additive_merged == 1

        _refresh_master(master_repo)
        assert (master_repo / "examples" / "alice_q.yaml").exists()
        assert (master_repo / "examples" / "bob_q.yaml").exists()

    def test_concurrent_via_full_sync(self, master_repo, make_collaborator):
        # Both clone at the same state
        alice = make_collaborator("alice")
        bob = make_collaborator("bob")

        _create_additive_file(alice, "alice_q.yaml", "intent: alice\n")
        result_alice = full_sync(alice, "alice")
        assert result_alice.additive_merged == 1

        _create_additive_file(bob, "bob_q.yaml", "intent: bob\n")
        result_bob = full_sync(bob, "bob")
        # Bob's pull merges alice's file into bob's branch; diff against main
        # may include alice's file if it arrived via the merge commit path.
        assert result_bob.additive_merged >= 1

        _refresh_master(master_repo)
        assert (master_repo / "examples" / "alice_q.yaml").exists()
        assert (master_repo / "examples" / "bob_q.yaml").exists()


# ---------------------------------------------------------------------------
# TestEdgeCasesE2E
# ---------------------------------------------------------------------------


class TestEdgeCasesE2E:
    def test_multiple_push_cycles(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")

        # First push
        _create_additive_file(alice, "q1.yaml", "intent: first\n")
        result1 = collaborator_push(alice, "alice")
        assert result1.additive_merged == 1

        # Second push — first file was already merged to main,
        # so diff only shows the new file
        _create_additive_file(alice, "q2.yaml", "intent: second\n")
        result2 = collaborator_push(alice, "alice")
        assert result2.additive_merged == 1

        _refresh_master(master_repo)
        assert (master_repo / "examples" / "q1.yaml").exists()
        assert (master_repo / "examples" / "q2.yaml").exists()

    def test_pull_when_already_on_branch(self, master_repo, make_collaborator):
        alice = make_collaborator("alice")
        collaborator_pull(alice, "alice")
        assert backend.current_branch(alice) == "collaborator/alice"

        # Pull again — should not crash
        collaborator_pull(alice, "alice")
        assert backend.current_branch(alice) == "collaborator/alice"
