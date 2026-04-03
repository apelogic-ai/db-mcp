from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from db_mcp.services.vault import (
    create_context_file,
    save_artifact,
    vault_append,
    vault_write,
    write_context_file,
)


def test_vault_write_rejects_unregistered_path(tmp_path: Path):
    result = vault_write(
        connection_path=tmp_path,
        path="notes/todo.md",
        content="# scratch\n",
    )

    assert result["saved"] is False
    assert result["file_path"] is None
    assert "not allowed" in result["error"].lower()


def test_vault_write_rejects_invalid_schema_descriptions_yaml(tmp_path: Path):
    result = vault_write(
        connection_path=tmp_path,
        path="schema/descriptions.yaml",
        content="version: 1.0.0\ntables: []\n",
    )

    assert result["saved"] is False
    assert result["file_path"] is None
    assert "provider_id" in result["error"]
    assert not (tmp_path / "schema" / "descriptions.yaml").exists()


def test_vault_write_replaces_target_atomically(tmp_path: Path, monkeypatch):
    import db_mcp.services.vault as vault_module

    target = tmp_path / "domain" / "model.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Old Domain\n", encoding="utf-8")

    replace_calls: list[tuple[str, str]] = []

    import os

    real_replace = os.replace

    def _recording_replace(src: str, dst: str) -> None:
        replace_calls.append((src, dst))
        real_replace(src, dst)

    monkeypatch.setattr(
        vault_module,
        "os",
        type("_AtomicOS", (), {"replace": staticmethod(_recording_replace)})(),
        raising=False,
    )

    result = vault_write(
        connection_path=tmp_path,
        path="domain/model.md",
        content="# New Domain\n",
    )

    assert result["saved"] is True
    assert target.read_text(encoding="utf-8") == "# New Domain\n"
    assert replace_calls == [(str(target.with_suffix(".md.tmp")), str(target))]
    assert not target.with_suffix(".md.tmp").exists()


def test_vault_append_creates_valid_example_file(tmp_path: Path):
    content = yaml.safe_dump(
        {
            "id": "abc123",
            "natural_language": "top customers",
            "sql": "SELECT * FROM customers LIMIT 10",
            "tables_used": ["customers"],
        },
        sort_keys=False,
    )

    result = vault_append(
        connection_path=tmp_path,
        path="examples/abc123.yaml",
        content=content,
    )

    target = tmp_path / "examples" / "abc123.yaml"
    assert result["saved"] is True
    assert result["file_path"] == str(target)
    assert result["error"] is None
    assert target.exists()


def test_vault_append_rejects_existing_example_file(tmp_path: Path):
    target = tmp_path / "examples" / "abc123.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("original: true\n", encoding="utf-8")

    content = yaml.safe_dump(
        {
            "id": "abc123",
            "natural_language": "top customers",
            "sql": "SELECT * FROM customers LIMIT 10",
            "tables_used": ["customers"],
        },
        sort_keys=False,
    )

    result = vault_append(
        connection_path=tmp_path,
        path="examples/abc123.yaml",
        content=content,
    )

    assert result["saved"] is False
    assert result["file_path"] is None
    assert "already exists" in result["error"].lower()
    assert target.read_text(encoding="utf-8") == "original: true\n"


def test_vault_append_appends_to_existing_markdown_file(tmp_path: Path):
    target = tmp_path / "learnings" / "patterns.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Existing\n", encoding="utf-8")

    result = vault_append(
        connection_path=tmp_path,
        path="learnings/patterns.md",
        content="\n## New Pattern\nDetails\n",
    )

    assert result["saved"] is True
    assert result["file_path"] == str(target)
    assert result["error"] is None
    assert target.read_text(encoding="utf-8") == "# Existing\n\n## New Pattern\nDetails\n"


def test_save_artifact_writes_domain_model_to_canonical_path(tmp_path: Path):
    result = save_artifact(
        connection_path=tmp_path,
        artifact_type="domain_model",
        content="# Revenue Domain\n",
    )

    target = tmp_path / "domain" / "model.md"
    assert result["saved"] is True
    assert result["artifact_type"] == "domain_model"
    assert result["file_path"] == str(target)
    assert result["error"] is None
    assert target.read_text(encoding="utf-8") == "# Revenue Domain\n"


def test_write_context_file_rejects_non_whitelisted_path(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)

    result = write_context_file(
        connection_path=tmp_path,
        path="notes/todo.md",
        content="# scratch\n",
    )

    assert result["success"] is False
    assert "not allowed" in result["error"].lower()
    assert not (tmp_path / "notes" / "todo.md").exists()


def test_create_context_file_rejects_non_whitelisted_path(tmp_path: Path):
    result = create_context_file(
        connection_path=tmp_path,
        path="drafts/ideas.md",
        content="# notes\n",
    )

    assert result["success"] is False
    assert "not allowed" in result["error"].lower()
    assert not (tmp_path / "drafts" / "ideas.md").exists()


# ---------------------------------------------------------------------------
# git auto-commit integration (4.09)
# ---------------------------------------------------------------------------


# Valid minimal content for schema/descriptions.yaml (SchemaDescriptions requires provider_id)
_VALID_SCHEMA_YAML = "provider_id: test\ntables: []\n"


def test_write_context_file_returns_git_commit_false_when_no_git(tmp_path: Path):
    from db_mcp.services.vault import write_context_file

    conn_path = tmp_path / "myconn"
    conn_path.mkdir()

    result = write_context_file(conn_path, "schema/descriptions.yaml", _VALID_SCHEMA_YAML)
    assert result["success"] is True
    assert result.get("gitCommit") is False


def test_write_context_file_auto_commits_when_git_enabled(tmp_path: Path):
    from db_mcp.services.git import try_git_commit  # noqa: F401
    from db_mcp.services.vault import write_context_file

    conn_path = tmp_path / "myconn"
    conn_path.mkdir()
    (conn_path / ".git").mkdir()

    with patch("db_mcp.services.vault.try_git_commit", return_value=True) as mock_commit:
        result = write_context_file(conn_path, "schema/descriptions.yaml", _VALID_SCHEMA_YAML)

    assert result["success"] is True
    assert result["gitCommit"] is True
    mock_commit.assert_called_once()


def test_create_context_file_returns_git_commit_false_when_no_git(tmp_path: Path):
    from db_mcp.services.vault import create_context_file

    conn_path = tmp_path / "myconn"
    conn_path.mkdir()

    result = create_context_file(conn_path, "schema/descriptions.yaml", _VALID_SCHEMA_YAML)
    assert result["success"] is True
    assert result.get("gitCommit") is False


def test_create_context_file_auto_commits_when_git_enabled(tmp_path: Path):
    from db_mcp.services.vault import create_context_file

    conn_path = tmp_path / "myconn"
    conn_path.mkdir()
    (conn_path / ".git").mkdir()

    with patch("db_mcp.services.vault.try_git_commit", return_value=True) as mock_commit:
        result = create_context_file(conn_path, "schema/descriptions.yaml", _VALID_SCHEMA_YAML)

    assert result["success"] is True
    assert result["gitCommit"] is True
    mock_commit.assert_called_once()


def test_delete_context_file_uses_git_rm_when_git_enabled(tmp_path: Path):
    from db_mcp.services.vault import delete_context_file

    conn_path = tmp_path / "myconn"
    conn_path.mkdir()
    (conn_path / ".git").mkdir()
    (conn_path / "schema").mkdir()
    (conn_path / "schema" / "descriptions.yaml").write_text("tables: []\n")

    fake_git = MagicMock()
    fake_git.commit.return_value = "abc1234"

    with patch("db_mcp.services.vault._get_git_for_delete", return_value=fake_git):
        result = delete_context_file(conn_path, "schema/descriptions.yaml")

    assert result["success"] is True
    assert result["gitCommit"] is True
    fake_git.rm.assert_called_once()
    fake_git.commit.assert_called_once()


def test_delete_context_file_uses_trash_when_no_git(tmp_path: Path):
    from db_mcp.services.vault import delete_context_file

    conn_path = tmp_path / "myconn"
    conn_path.mkdir()
    (conn_path / "schema").mkdir()
    (conn_path / "schema" / "descriptions.yaml").write_text("tables: []\n")

    result = delete_context_file(conn_path, "schema/descriptions.yaml")

    assert result["success"] is True
    assert result["gitCommit"] is False
    assert result.get("trashedTo") is not None


def test_add_business_rule_auto_commits_when_git_enabled(tmp_path: Path):
    from db_mcp.services.vault import add_business_rule

    conn_path = tmp_path / "myconn"
    conn_path.mkdir()
    (conn_path / ".git").mkdir()

    with patch("db_mcp.services.vault.try_git_commit", return_value=True) as mock_commit:
        result = add_business_rule(conn_path, "myconn", "Revenue excludes refunds")

    assert result["success"] is True
    assert result.get("gitCommit") is True
    mock_commit.assert_called_once()


def test_add_business_rule_returns_git_commit_false_when_no_git(tmp_path: Path):
    from db_mcp.services.vault import add_business_rule

    conn_path = tmp_path / "myconn"
    conn_path.mkdir()

    result = add_business_rule(conn_path, "myconn", "Revenue excludes refunds")

    assert result["success"] is True
    assert result.get("gitCommit") is False
