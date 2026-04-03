"""Shared control-plane services for insider-agent operations."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

import yaml
from db_mcp_knowledge.onboarding.schema_store import load_schema_descriptions
from db_mcp_knowledge.onboarding.state import load_state

from db_mcp.insider.config import InsiderConfig, get_insider_db_path, load_insider_config
from db_mcp.insider.logging import log_event
from db_mcp.insider.models import (
    AgentEvent,
    InsiderProposalBundle,
    InsiderRunRequest,
    ReviewItemProposal,
    utc_now,
)
from db_mcp.insider.review import ReviewApplier, _schema_digest_for_path
from db_mcp.insider.store import InsiderStore


def _default_connection_resolver(connection: str) -> Path:
    return Path.home() / ".db-mcp" / "connections" / connection


class InsiderService:
    """Shared insider control-plane service used by runtime and operator surfaces."""

    def __init__(
        self,
        *,
        store: InsiderStore | None = None,
        config: InsiderConfig | None = None,
        connection_resolver: Callable[[str], Path] | None = None,
        config_loader: Callable[[Path | None], InsiderConfig] = load_insider_config,
    ):
        self.store = store or InsiderStore()
        self._config = config
        self._connection_resolver = connection_resolver or _default_connection_resolver
        self._config_loader = config_loader

    def resolve_connection_path(self, connection: str) -> Path:
        """Resolve one connection name to its vault path."""
        return self._connection_resolver(connection)

    def get_config(self, connection_path: Path | None = None) -> InsiderConfig:
        """Return effective insider config for one connection."""
        if self._config is not None:
            return self._config
        return self._config_loader(connection_path)

    def get_status(self, connection: str) -> dict[str, Any]:
        """Return operator-facing status summary for one connection."""
        conn_path = self.resolve_connection_path(connection)
        config = self.get_config(conn_path)
        pending_events = self.store.pending_events(connection)
        pending_reviews = self.list_reviews(connection, status="pending")
        return {
            "connection": connection,
            "connection_path": str(conn_path),
            "enabled": config.enabled,
            "provider": config.provider,
            "model": config.model,
            "base_url": config.base_url,
            "db_path": str(get_insider_db_path()),
            "pending_events": len(pending_events),
            "pending_reviews": len(pending_reviews),
        }

    def queue_new_connection(
        self,
        connection: str,
        *,
        payload: dict[str, Any] | None = None,
        force: bool = False,
    ) -> str | None:
        """Persist one new-connection observation if enabled and not duplicated."""
        conn_path = self.resolve_connection_path(connection)
        config = self.get_config(conn_path)
        if not config.enabled or not config.triggers.new_connection:
            return None
        event = AgentEvent(
            event_id=uuid.uuid4().hex,
            connection=connection,
            event_type="new_connection",
            schema_digest=_schema_digest_for_path(conn_path),
            payload=payload or {},
        )
        created = self.store.create_event(event, force=force)
        if not created:
            return None
        log_event(
            "insider_event_emitted",
            connection=connection,
            event_type=event.event_type,
            event_id=event.event_id,
            status="pending",
        )
        return event.event_id

    def pending_events(self, connection: str | None = None) -> list[dict[str, Any]]:
        """List pending observation rows."""
        return self.store.pending_events(connection)

    def pending_connections(self) -> list[str]:
        """Return distinct connections with pending insider work."""
        return sorted({row["connection"] for row in self.store.pending_events()})

    def list_events(
        self,
        connection: str | None = None,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List recent insider events."""
        return self.store.list_events(connection, limit=limit)

    def create_batch(self, connection: str, event_ids: list[str]) -> str:
        """Persist one batch for the provided event ids."""
        return self.store.create_batch(connection, event_ids)

    def list_runs(self, connection: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        """List recent insider runs."""
        return self.store.list_runs(connection, limit=limit)

    def list_reviews(
        self,
        connection: str | None = None,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List staged insider reviews."""
        rows = self.store.list_reviews(connection, limit=limit)
        if status is None:
            return rows
        return [row for row in rows if row["status"] == status]

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        """Return one staged review row."""
        return self.store.get_review(review_id)

    def approve_review(self, review_id: str) -> str:
        """Approve and apply one staged review item."""
        review = self.store.get_review(review_id)
        if review is None:
            raise ValueError(f"Review item {review_id!r} was not found.")
        applier = ReviewApplier(self.resolve_connection_path(review["connection"]))
        try:
            result = applier.approve(review)
        except Exception as exc:
            self.store.set_review_status(review_id, "stale", str(exc))
            raise
        self.store.set_review_status(review_id, "approved")
        log_event(
            "insider_review_applied",
            connection=review["connection"],
            review_id=review_id,
            status="approved",
            review_kind=review["review_kind"],
        )
        return result

    def reject_review(self, review_id: str, reason: str | None = None) -> str:
        """Reject one staged review item."""
        review = self.store.get_review(review_id)
        if review is None:
            raise ValueError(f"Review item {review_id!r} was not found.")
        self.store.set_review_status(review_id, "rejected", reason)
        log_event(
            "insider_review_rejected",
            connection=review["connection"],
            review_id=review_id,
            status="rejected",
            review_kind=review["review_kind"],
            reason=reason,
        )
        return "rejected"

    def get_budget_summary(self, connection: str | None = None) -> dict[str, Any]:
        """Return aggregated usage summary."""
        return self.store.get_budget_summary(connection)

    def build_run_request(self, connection: str, connection_path: Path) -> InsiderRunRequest:
        """Build deterministic insider model input from vault artifacts."""
        schema = load_schema_descriptions(connection, connection_path=connection_path)
        onboarding_state = load_state(connection, connection_path=connection_path)
        examples_dir = connection_path / "examples"
        example_files = (
            sorted(path for path in examples_dir.glob("*.yaml") if path.is_file())[:5]
            if examples_dir.exists()
            else []
        )
        examples = []
        for path in example_files:
            with open(path) as f:
                examples.append(yaml.safe_load(f) or {})
        gaps_path = connection_path / "knowledge_gaps.yaml"
        knowledge_gaps = yaml.safe_load(gaps_path.read_text()) if gaps_path.exists() else []
        domain_model_path = connection_path / "domain" / "model.md"
        schema_path = connection_path / "schema" / "descriptions.yaml"
        return InsiderRunRequest(
            connection=connection,
            connection_path=str(connection_path),
            schema_digest=_schema_digest_for_path(connection_path),
            event_type="new_connection",
            event_payload={"connection": connection},
            context={
                "schema_yaml": schema_path.read_text() if schema_path.exists() else "",
                "onboarding_state": onboarding_state.model_dump(mode="json")
                if onboarding_state
                else {},
                "domain_model_markdown": domain_model_path.read_text()
                if domain_model_path.exists()
                else None,
                "examples": examples,
                "knowledge_gaps": knowledge_gaps,
                "schema_model": schema.model_dump(mode="json") if schema else {},
            },
        )

    def apply_bundle(
        self,
        *,
        run_id: str,
        connection: str,
        connection_path: Path,
        schema_digest: str,
        bundle: InsiderProposalBundle,
    ) -> tuple[list[Path], int]:
        """Auto-apply drafts and stage canonical proposals for review."""
        applier = ReviewApplier(connection_path)
        applied_paths = applier.auto_apply(run_id, bundle)
        review_count = 0

        review_items = list(bundle.review_items)
        if bundle.description_updates and not any(
            item.kind == "schema_descriptions" for item in review_items
        ):
            review_items.append(
                ReviewItemProposal(
                    kind="schema_descriptions",
                    title="Apply generated schema descriptions",
                    payload={},
                )
            )

        for review_item in review_items:
            review_id = uuid.uuid4().hex
            relative_path: Path
            proposed_content: str
            if review_item.kind == "schema_descriptions":
                schema = load_schema_descriptions(connection, connection_path=connection_path)
                if schema is None:
                    raise ValueError("Cannot stage schema descriptions without an existing schema")
                for update in bundle.description_updates:
                    table = schema.get_table(update.table_full_name)
                    if table is None:
                        raise ValueError(
                            "Unknown table in description update: "
                            f"{update.table_full_name}"
                        )
                    table.description = update.description
                    known_columns = {column.name: column for column in table.columns}
                    for column_update in update.columns:
                        column = known_columns.get(column_update.name)
                        if column is None:
                            raise ValueError(
                                "Unknown column in description update: "
                                f"{update.table_full_name}.{column_update.name}"
                            )
                        column.description = column_update.description
                relative_path = Path("schema/descriptions.yaml")
                proposed_content = yaml.dump(
                    schema.model_dump(mode="json", by_alias=True),
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
            elif review_item.kind == "canonical_domain_model":
                relative_path = Path("domain/model.md")
                proposed_content = str(review_item.payload.get("markdown", "")).rstrip() + "\n"
            elif review_item.kind == "canonical_examples":
                example_payload = review_item.payload.get("example", {})
                tables = example_payload.get("tables", [])
                schema = load_schema_descriptions(connection, connection_path=connection_path)
                known_tables = {table.full_name for table in schema.tables} if schema else set()
                unknown = [table for table in tables if table not in known_tables]
                if unknown:
                    raise ValueError(f"Unknown tables in canonical example proposal: {unknown}")
                slug = str(example_payload.get("slug") or uuid.uuid4().hex[:8])
                relative_path = Path("examples") / f"{slug}.yaml"
                proposed_content = yaml.dump(
                    example_payload,
                    default_flow_style=False,
                    sort_keys=False,
                )
            else:
                raise ValueError(f"Unsupported review kind: {review_item.kind}")

            manifest_path, diff_path, reasoning_path = applier.stage_review_artifact(
                review_id=review_id,
                run_id=run_id,
                review_kind=review_item.kind,
                relative_path=relative_path,
                proposed_content=proposed_content,
                title=review_item.title,
                schema_digest=schema_digest,
                rationale={
                    "created_at": utc_now(),
                    "title": review_item.title,
                    "kind": review_item.kind,
                    "payload_preview": review_item.payload,
                },
            )
            self.store.create_review(
                review_id=review_id,
                run_id=run_id,
                connection=connection,
                review_kind=review_item.kind,
                manifest_path=manifest_path,
                diff_path=diff_path,
                reasoning_path=reasoning_path,
            )
            review_count += 1
            log_event(
                "insider_review_staged",
                connection=connection,
                run_id=run_id,
                review_id=review_id,
                status="pending",
                review_kind=review_item.kind,
            )

        return applied_paths, review_count
