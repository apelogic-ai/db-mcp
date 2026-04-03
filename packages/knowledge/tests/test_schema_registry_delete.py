"""TDD tests for vault_delete_typed (Phase 2, step 6 — delete semantics)."""

from pathlib import Path

import pytest


def _provider_dir(tmp: Path) -> Path:
    d = tmp / "connections" / "test"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# DeleteEntry / registry API
# ---------------------------------------------------------------------------


class TestDeleteRegistryAPI:
    def test_register_and_lookup_delete_entry(self):
        from db_mcp_knowledge.vault.schema_registry import (
            DeleteEntry,
            lookup_delete,
            register_delete,
        )

        def deleter(identifier, pid, cp):
            return {"deleted": True}

        register_delete("test_deletion", DeleteEntry(deleter=deleter))
        entry = lookup_delete("test_deletion")
        assert entry.deleter is deleter

    def test_lookup_unknown_delete_key_raises(self):
        from db_mcp_knowledge.vault.schema_registry import lookup_delete

        with pytest.raises(KeyError):
            lookup_delete("__no_such_delete_key__")


# ---------------------------------------------------------------------------
# vault_delete_typed — core flow
# ---------------------------------------------------------------------------


class TestVaultDeleteTyped:
    def test_unknown_key_raises_keyerror(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import vault_delete_typed

        with pytest.raises(KeyError):
            vault_delete_typed("__nope__", "some_id", "p", tmp_path)

    def test_pre_hook_raising_aborts_delete(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import (
            DeleteEntry,
            register_delete,
            vault_delete_typed,
        )

        deleted: list[str] = []

        def aborting_hook(identifier, pid, cp):
            raise ValueError("pre-hook abort")

        def deleter(identifier, pid, cp):
            deleted.append(identifier)
            return {"deleted": True}

        register_delete(
            "abort_delete_test",
            DeleteEntry(deleter=deleter, pre_hooks=[aborting_hook]),
        )

        with pytest.raises(ValueError, match="pre-hook abort"):
            vault_delete_typed("abort_delete_test", "x", "p", tmp_path)

        assert deleted == []

    def test_post_hooks_fire_after_delete(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import (
            DeleteEntry,
            register_delete,
            vault_delete_typed,
        )

        fired: list[str] = []

        def deleter(identifier, pid, cp):
            return {"deleted": True}

        def post_hook(identifier, pid, cp):
            fired.append(identifier)

        register_delete(
            "post_delete_test",
            DeleteEntry(deleter=deleter, post_hooks=[post_hook]),
        )
        vault_delete_typed("post_delete_test", "my_item", "p", tmp_path)
        assert fired == ["my_item"]

    def test_deleter_return_value_is_returned(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import (
            DeleteEntry,
            register_delete,
            vault_delete_typed,
        )

        def deleter(identifier, pid, cp):
            return {"deleted": True, "name": identifier}

        register_delete("return_delete_test", DeleteEntry(deleter=deleter))
        result = vault_delete_typed("return_delete_test", "dau", "p", tmp_path)
        assert result == {"deleted": True, "name": "dau"}


# ---------------------------------------------------------------------------
# metric_deletion built-in entry
# ---------------------------------------------------------------------------


class TestMetricDeletionEntry:
    def test_deletes_existing_metric(self, tmp_path):
        from db_mcp_knowledge.metrics.store import add_metric, load_metrics
        from db_mcp_knowledge.vault.schema_registry import vault_delete_typed

        add_metric("test", "dau", "Daily active users", "SELECT 1", connection_path=tmp_path)
        result = vault_delete_typed("metric_deletion", "dau", "test", tmp_path)

        assert result.get("deleted") is True
        catalog = load_metrics("test", connection_path=tmp_path)
        assert catalog.get_metric("dau") is None

    def test_pre_hook_rejects_missing_metric(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import vault_delete_typed

        with pytest.raises(ValueError, match="not found"):
            vault_delete_typed("metric_deletion", "nonexistent", "test", tmp_path)


# ---------------------------------------------------------------------------
# dimension_deletion built-in entry
# ---------------------------------------------------------------------------


class TestDimensionDeletionEntry:
    def test_deletes_existing_dimension(self, tmp_path):
        from db_mcp_knowledge.metrics.store import add_dimension, load_dimensions
        from db_mcp_knowledge.vault.schema_registry import vault_delete_typed

        add_dimension("test", "country", "users.country", connection_path=tmp_path)
        result = vault_delete_typed("dimension_deletion", "country", "test", tmp_path)

        assert result.get("deleted") is True
        catalog = load_dimensions("test", connection_path=tmp_path)
        assert catalog.get_dimension("country") is None

    def test_pre_hook_rejects_missing_dimension(self, tmp_path):
        from db_mcp_knowledge.vault.schema_registry import vault_delete_typed

        with pytest.raises(ValueError, match="not found"):
            vault_delete_typed("dimension_deletion", "nonexistent", "test", tmp_path)
