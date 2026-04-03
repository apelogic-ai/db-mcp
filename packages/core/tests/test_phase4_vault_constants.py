"""RED tests — Phase 4 step 4.03: vault_service must own the folder-metadata constants.

The FOLDER_IMPORTANCE, EXPECTED_FOLDERS, and STOCK_READMES dictionaries are
semantic configuration that belongs in the service layer, not in the BICP
protocol adapter.  These tests enforce that:

  1. The three constants are exported from db_mcp.services.vault.
  2. list_context_tree works without the caller supplying the constants.
  3. read_context_file works without the caller supplying stock_readmes.
  4. The agent class no longer carries these as class attributes.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Constants must live in vault_service
# ---------------------------------------------------------------------------


def test_vault_service_exports_folder_importance() -> None:
    """FOLDER_IMPORTANCE must be a dict exported from services.vault."""
    from db_mcp.services.vault import FOLDER_IMPORTANCE

    assert isinstance(FOLDER_IMPORTANCE, dict)
    # Core folders must be present with known importance levels
    assert FOLDER_IMPORTANCE.get("schema") == "critical"
    assert FOLDER_IMPORTANCE.get("domain") == "critical"
    assert FOLDER_IMPORTANCE.get("examples") == "recommended"


def test_vault_service_exports_expected_folders() -> None:
    """EXPECTED_FOLDERS must be a list exported from services.vault."""
    from db_mcp.services.vault import EXPECTED_FOLDERS

    assert isinstance(EXPECTED_FOLDERS, list)
    for name in ("schema", "domain", "examples", "instructions", "metrics"):
        assert name in EXPECTED_FOLDERS, f"{name!r} missing from EXPECTED_FOLDERS"


def test_vault_service_exports_stock_readmes() -> None:
    """STOCK_READMES must be a dict with at least the core folder keys."""
    from db_mcp.services.vault import STOCK_READMES

    assert isinstance(STOCK_READMES, dict)
    for name in ("schema", "domain", "examples", "instructions", "metrics", "learnings"):
        assert name in STOCK_READMES, f"{name!r} missing from STOCK_READMES"
    # Each value must be a non-empty string
    for name, content in STOCK_READMES.items():
        assert isinstance(content, str) and content.strip(), (
            f"STOCK_READMES[{name!r}] is empty"
        )


# ---------------------------------------------------------------------------
# list_context_tree must work without explicit constants
# ---------------------------------------------------------------------------


def test_list_context_tree_uses_module_defaults_when_not_supplied(tmp_path: Path) -> None:
    """list_context_tree must not require expected_folders / folder_importance /
    stock_readmes from the caller — it should fall back to module-level defaults."""
    from db_mcp.services.vault import list_context_tree

    connections_dir = tmp_path / "connections"
    connections_dir.mkdir()
    (connections_dir / "prod").mkdir()

    # Call WITHOUT the three optional constants — must not raise TypeError
    result = list_context_tree(
        connections_dir=connections_dir,
        active_connection="prod",
        is_git_enabled=lambda p: False,
    )
    assert "connections" in result
    assert any(c["name"] == "prod" for c in result["connections"])


# ---------------------------------------------------------------------------
# read_context_file must work without explicit stock_readmes
# ---------------------------------------------------------------------------


def test_read_context_file_uses_module_defaults_when_not_supplied(tmp_path: Path) -> None:
    """read_context_file must not require stock_readmes from the caller."""
    from db_mcp.services.vault import read_context_file

    conn_path = tmp_path / "prod"
    conn_path.mkdir()

    # Call WITHOUT stock_readmes — must not raise TypeError or KeyError
    result = read_context_file(
        connection_path=conn_path,
        path="schema",
    )
    # File does not exist, so the service should return the stock README content
    assert result.get("success") is True
    assert result.get("content")  # stock README for "schema" folder


# ---------------------------------------------------------------------------
# Agent class must not carry these as class attributes
# ---------------------------------------------------------------------------


def test_agent_class_has_no_folder_importance_attribute() -> None:
    """DBMCPAgent must not define _FOLDER_IMPORTANCE as a class attribute."""
    from db_mcp.bicp.agent import DBMCPAgent

    assert not hasattr(DBMCPAgent, "_FOLDER_IMPORTANCE"), (
        "DBMCPAgent._FOLDER_IMPORTANCE should be removed; "
        "it now lives in db_mcp.services.vault.FOLDER_IMPORTANCE"
    )


def test_agent_class_has_no_expected_folders_attribute() -> None:
    """DBMCPAgent must not define _EXPECTED_FOLDERS as a class attribute."""
    from db_mcp.bicp.agent import DBMCPAgent

    assert not hasattr(DBMCPAgent, "_EXPECTED_FOLDERS"), (
        "DBMCPAgent._EXPECTED_FOLDERS should be removed; "
        "it now lives in db_mcp.services.vault.EXPECTED_FOLDERS"
    )


def test_agent_class_has_no_stock_readmes_attribute() -> None:
    """DBMCPAgent must not define _STOCK_READMES as a class attribute."""
    from db_mcp.bicp.agent import DBMCPAgent

    assert not hasattr(DBMCPAgent, "_STOCK_READMES"), (
        "DBMCPAgent._STOCK_READMES should be removed; "
        "it now lives in db_mcp.services.vault.STOCK_READMES"
    )
