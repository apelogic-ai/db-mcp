"""Tests for insider-agent supervisor behavior."""

from pathlib import Path

from db_mcp.insider.config import InsiderConfig
from db_mcp.insider.models import (
    ColumnDescriptionUpdate,
    ExampleCandidate,
    InsiderProposalBundle,
    ReviewItemProposal,
    TableDescriptionUpdate,
)
from db_mcp.insider.store import InsiderStore
from db_mcp.insider.supervisor import InsiderSupervisor
from db_mcp.onboarding.schema_store import create_initial_schema, save_schema_descriptions


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


def test_supervisor_apply_bundle_writes_drafts_and_stages_review(tmp_path):
    connection_path = tmp_path / "playground"
    connection_path.mkdir()
    _seed_schema(connection_path)
    store = InsiderStore(tmp_path / "insider.db")
    supervisor = InsiderSupervisor(config=InsiderConfig(enabled=True), store=store)

    bundle = InsiderProposalBundle(
        draft_domain_model_markdown="# Draft model\n",
        description_updates=[
            TableDescriptionUpdate(
                table_full_name="main.users",
                description="Primary user table",
                columns=[ColumnDescriptionUpdate(name="email", description="User email address")],
            )
        ],
        example_candidates=[
            ExampleCandidate(
                slug="users-by-email",
                natural_language="Show users by email",
                sql="SELECT email FROM main.users",
                tables=["main.users"],
            )
        ],
        findings=[{"kind": "bootstrap", "summary": "Seeded vault"}],
        review_items=[
            ReviewItemProposal(
                kind="canonical_domain_model",
                title="Promote generated domain model",
                payload={"markdown": "# Canonical domain model\n"},
            )
        ],
    )

    applied_paths, review_count = supervisor._apply_bundle(
        run_id="run-123",
        connection="playground",
        conn_path=connection_path,
        schema_digest="schema-1",
        bundle=bundle,
    )

    assert (connection_path / "domain" / "model.draft.md").exists()
    assert (connection_path / "examples" / "candidates" / "users-by-email.yaml").exists()
    assert (connection_path / ".insider" / "runs" / "run-123" / "output.json").exists()
    assert review_count == 2
    assert any(path.name == "output.json" for path in applied_paths)
    reviews = store.list_reviews("playground")
    assert len(reviews) == 2
