"""Tests for vault_write and vault_append primitives (step 7.02)."""

from pathlib import Path

import yaml

from db_mcp.services.vault import (
    _validate_content,
    _validate_sql_fields,
    vault_append,
    vault_write,
)

# ---------------------------------------------------------------------------
# vault_write
# ---------------------------------------------------------------------------


def test_vault_write_allowed_markdown(tmp_path: Path):
    result = vault_write(tmp_path, "domain/model.md", "# Domain\n")
    assert result["saved"] is True
    assert (tmp_path / "domain" / "model.md").read_text() == "# Domain\n"


def test_vault_write_allowed_yaml(tmp_path: Path):
    content = yaml.safe_dump({
        "version": "1.0.0",
        "provider_id": "test",
        "rules": ["Always use UTC"],
    })
    result = vault_write(tmp_path, "instructions/business_rules.yaml", content)
    assert result["saved"] is True
    assert (tmp_path / "instructions" / "business_rules.yaml").exists()


def test_vault_write_rejects_unknown_path(tmp_path: Path):
    result = vault_write(tmp_path, "random/file.txt", "content")
    assert result["saved"] is False
    assert "not allowed" in result["error"].lower()


def test_vault_write_rejects_invalid_yaml(tmp_path: Path):
    result = vault_write(tmp_path, "metrics/catalog.yaml", "not: valid\n")
    assert result["saved"] is False
    assert result["error"] is not None


def test_vault_write_overwrites_existing(tmp_path: Path):
    target = tmp_path / "domain" / "model.md"
    target.parent.mkdir(parents=True)
    target.write_text("old")
    result = vault_write(tmp_path, "domain/model.md", "new")
    assert result["saved"] is True
    assert target.read_text() == "new"


# ---------------------------------------------------------------------------
# vault_append
# ---------------------------------------------------------------------------


def test_vault_append_creates_example(tmp_path: Path):
    content = yaml.safe_dump({
        "id": "ex1",
        "natural_language": "show users",
        "sql": "SELECT * FROM users",
    })
    result = vault_append(tmp_path, "examples/ex1.yaml", content)
    assert result["saved"] is True
    assert (tmp_path / "examples" / "ex1.yaml").exists()


def test_vault_append_rejects_existing_example(tmp_path: Path):
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "ex1.yaml").write_text("existing")
    content = yaml.safe_dump({
        "id": "ex1",
        "natural_language": "show users",
        "sql": "SELECT * FROM users",
    })
    result = vault_append(tmp_path, "examples/ex1.yaml", content)
    assert result["saved"] is False
    assert "already exists" in result["error"]


def test_vault_append_appends_to_markdown(tmp_path: Path):
    target = tmp_path / "learnings" / "patterns.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Patterns\n")
    result = vault_append(tmp_path, "learnings/patterns.md", "\n## New\n")
    assert result["saved"] is True
    assert target.read_text() == "# Patterns\n\n## New\n"


def test_vault_append_creates_new_markdown(tmp_path: Path):
    result = vault_append(tmp_path, "learnings/schema_gotchas.md", "# Gotchas\n")
    assert result["saved"] is True
    assert (tmp_path / "learnings" / "schema_gotchas.md").read_text() == "# Gotchas\n"


def test_vault_append_rejects_unknown_path(tmp_path: Path):
    result = vault_append(tmp_path, "random/file.txt", "content")
    assert result["saved"] is False
    assert "not allowed" in result["error"].lower()


# ---------------------------------------------------------------------------
# SQL field validation
# ---------------------------------------------------------------------------


def test_validate_sql_fields_passes_valid_sql():
    from pydantic import BaseModel, Field

    class FakeModel(BaseModel):
        sql: str = Field(json_schema_extra={"is_sql": True})

    instance = FakeModel(sql="SELECT 1")
    _validate_sql_fields(instance)  # should not raise


def test_validate_sql_fields_skips_empty():
    from pydantic import BaseModel, Field

    class FakeModel(BaseModel):
        sql: str = Field(default="", json_schema_extra={"is_sql": True})

    instance = FakeModel(sql="")
    _validate_sql_fields(instance)  # should not raise


def test_validate_content_valid_example(tmp_path: Path):
    content = yaml.safe_dump({
        "id": "ex1",
        "natural_language": "show users",
        "sql": "SELECT * FROM users",
    })
    _validate_content("examples/ex1.yaml", content)  # should not raise


def test_validate_content_invalid_model(tmp_path: Path):
    import pytest

    with pytest.raises(Exception):
        _validate_content("metrics/catalog.yaml", "not: valid\n")


# ---------------------------------------------------------------------------
# SqlExpr type
# ---------------------------------------------------------------------------


def test_sql_expr_type_importable():
    from db_mcp_models import SqlExpr

    assert SqlExpr is not None
    # It's an annotated string type
    assert hasattr(SqlExpr, "__metadata__")
