"""Tests for insider-agent review staging and approval."""

import json
from pathlib import Path

import pytest
from db_mcp_knowledge.onboarding.schema_store import (
    create_initial_schema,
    save_schema_descriptions,
)

from db_mcp.insider.review import ReviewApplier


def _seed_schema(connection_path: Path) -> None:
    schema = create_initial_schema(
        provider_id=connection_path.name,
        dialect="sqlite",
        tables=[
            {
                "name": "users",
                "schema": "main",
                "catalog": None,
                "full_name": "main.users",
                "columns": [{"name": "id", "type": "integer"}, {"name": "email", "type": "text"}],
            }
        ],
    )
    save_schema_descriptions(schema, connection_path=connection_path)


def test_review_approve_applies_staged_file(tmp_path):
    connection_path = tmp_path / "playground"
    connection_path.mkdir()
    _seed_schema(connection_path)
    applier = ReviewApplier(connection_path)

    manifest_path, diff_path, reasoning_path = applier.stage_review_artifact(
        review_id="rev-1",
        run_id="run-1",
        review_kind="canonical_domain_model",
        relative_path=Path("domain/model.md"),
        proposed_content="# Domain model\n",
        title="Apply domain model",
        schema_digest="",
        rationale={"created_at": "2026-01-01T00:00:00+00:00"},
    )
    row = {
        "manifest_path": str(manifest_path),
        "diff_path": str(diff_path),
        "reasoning_path": str(reasoning_path),
    }

    result = applier.approve(row)

    assert result == "approved"
    assert (connection_path / "domain" / "model.md").read_text() == "# Domain model\n"


def test_review_approve_rejects_stale_schema_digest(tmp_path):
    connection_path = tmp_path / "playground"
    connection_path.mkdir()
    _seed_schema(connection_path)
    applier = ReviewApplier(connection_path)

    manifest_path, _, reasoning_path = applier.stage_review_artifact(
        review_id="rev-2",
        run_id="run-2",
        review_kind="canonical_domain_model",
        relative_path=Path("domain/model.md"),
        proposed_content="# Domain model\n",
        title="Apply domain model",
        schema_digest="digest-one",
        rationale={"created_at": "2026-01-01T00:00:00+00:00"},
    )

    manifest = json.loads(manifest_path.read_text())
    manifest["schema_digest"] = "mismatch"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="Schema digest mismatch"):
        applier.approve(
            {
                "manifest_path": str(manifest_path),
                "reasoning_path": str(reasoning_path),
            }
        )
