"""Tests for insider-agent control-plane service behavior."""

from pathlib import Path

from db_mcp.insider.config import InsiderConfig
from db_mcp.insider.review import ReviewApplier
from db_mcp.insider.services import InsiderService
from db_mcp.insider.store import InsiderStore
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
                "columns": [{"name": "id", "type": "integer"}],
            }
        ],
    )
    save_schema_descriptions(schema, connection_path=connection_path)


def test_service_queue_new_connection_dedupes_by_schema_digest(tmp_path):
    connection_path = tmp_path / "playground"
    connection_path.mkdir()
    _seed_schema(connection_path)
    store = InsiderStore(tmp_path / "insider.db")
    service = InsiderService(
        store=store,
        config=InsiderConfig(enabled=True),
        connection_resolver=lambda connection: connection_path,
    )

    event_id = service.queue_new_connection(
        "playground",
        payload={"source": "manual"},
    )
    duplicate = service.queue_new_connection(
        "playground",
        payload={"source": "manual"},
    )

    assert event_id is not None
    assert duplicate is None
    events = store.list_events("playground")
    assert len(events) == 1
    assert events[0]["event_id"] == event_id


def test_service_approve_review_updates_store_and_applies_file(tmp_path):
    connection_path = tmp_path / "playground"
    connection_path.mkdir()
    _seed_schema(connection_path)
    store = InsiderStore(tmp_path / "insider.db")
    service = InsiderService(
        store=store,
        config=InsiderConfig(enabled=True),
        connection_resolver=lambda connection: connection_path,
    )
    applier = ReviewApplier(connection_path)
    manifest_path, diff_path, reasoning_path = applier.stage_review_artifact(
        review_id="rev-1",
        run_id="run-1",
        review_kind="canonical_domain_model",
        relative_path=Path("domain/model.md"),
        proposed_content="# Approved domain model\n",
        title="Apply model",
        schema_digest="",
        rationale={"created_at": "2026-01-01T00:00:00+00:00"},
    )
    store.create_review(
        review_id="rev-1",
        run_id="run-1",
        connection="playground",
        review_kind="canonical_domain_model",
        manifest_path=manifest_path,
        diff_path=diff_path,
        reasoning_path=reasoning_path,
    )

    result = service.approve_review("rev-1")

    assert result == "approved"
    assert (connection_path / "domain" / "model.md").read_text() == "# Approved domain model\n"
    review = store.get_review("rev-1")
    assert review is not None
    assert review["status"] == "approved"
