"""Tests for collaboration manifest model and persistence."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from db_mcp.collab.manifest import (
    MANIFEST_FILENAME,
    CollabManifest,
    CollabMember,
    CollabSyncConfig,
    add_member,
    get_member,
    get_role,
    load_manifest,
    save_manifest,
)


def _make_manifest(**kwargs) -> CollabManifest:
    defaults = {"created_at": datetime.now(timezone.utc)}
    defaults.update(kwargs)
    return CollabManifest(**defaults)


class TestCollabManifestModel:
    """Test Pydantic model validation."""

    def test_defaults(self):
        m = _make_manifest()
        assert m.version == "1"
        assert m.members == []
        assert m.sync.auto_sync is True
        assert m.sync.sync_interval_minutes == 60

    def test_with_members(self):
        member = CollabMember(
            user_name="alice",
            user_id="abcd1234",
            role="master",
            joined_at=datetime.now(timezone.utc),
        )
        m = _make_manifest(members=[member])
        assert len(m.members) == 1
        assert m.members[0].user_name == "alice"
        assert m.members[0].role == "master"

    def test_custom_sync_config(self):
        m = _make_manifest(sync=CollabSyncConfig(auto_sync=False, sync_interval_minutes=30))
        assert m.sync.auto_sync is False
        assert m.sync.sync_interval_minutes == 30


class TestManifestPersistence:
    """Test load/save round-trip."""

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            manifest = _make_manifest()
            manifest = add_member(manifest, "alice", "abcd1234", "master")
            manifest = add_member(manifest, "bob", "efgh5678", "collaborator")

            save_manifest(path, manifest)
            loaded = load_manifest(path)

            assert loaded is not None
            assert len(loaded.members) == 2
            assert loaded.members[0].user_name == "alice"
            assert loaded.members[1].user_name == "bob"
            assert loaded.version == "1"

    def test_load_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert load_manifest(Path(tmpdir)) is None

    def test_load_empty_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / MANIFEST_FILENAME).write_text("")
            assert load_manifest(path) is None

    def test_load_corrupt_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / MANIFEST_FILENAME).write_text("not: valid: yaml: [[[")
            assert load_manifest(path) is None


class TestMemberLookup:
    """Test member lookup helpers."""

    def test_get_member_found(self):
        m = _make_manifest()
        m = add_member(m, "alice", "abcd1234", "master")
        member = get_member(m, "abcd1234")
        assert member is not None
        assert member.user_name == "alice"

    def test_get_member_not_found(self):
        m = _make_manifest()
        assert get_member(m, "nonexistent") is None

    def test_get_role(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            manifest = _make_manifest()
            manifest = add_member(manifest, "alice", "abcd1234", "master")
            save_manifest(path, manifest)

            assert get_role(path, "abcd1234") == "master"
            assert get_role(path, "unknown") is None

    def test_get_role_no_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert get_role(Path(tmpdir), "abcd1234") is None


class TestAddMember:
    """Test add_member helper."""

    def test_add_new_member(self):
        m = _make_manifest()
        m = add_member(m, "alice", "abcd1234", "master")
        assert len(m.members) == 1

    def test_add_duplicate_is_noop(self):
        m = _make_manifest()
        m = add_member(m, "alice", "abcd1234", "master")
        m = add_member(m, "alice", "abcd1234", "collaborator")
        assert len(m.members) == 1
        assert m.members[0].role == "master"  # unchanged

    def test_add_multiple_members(self):
        m = _make_manifest()
        m = add_member(m, "alice", "abcd1234", "master")
        m = add_member(m, "bob", "efgh5678", "collaborator")
        m = add_member(m, "carol", "ijkl9012", "collaborator")
        assert len(m.members) == 3
