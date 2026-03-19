"""Review staging and application for insider-agent outputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import yaml

from db_mcp.insider.models import InsiderProposalBundle
from db_mcp.onboarding.schema_store import load_schema_descriptions


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _schema_digest_for_path(connection: Path) -> str:
    schema_path = connection / "schema" / "descriptions.yaml"
    if not schema_path.exists():
        return ""
    model = load_schema_descriptions(connection.name, connection_path=connection)
    if model is None:
        return _sha256_text(schema_path.read_text())
    payload = model.model_dump(mode="json", exclude={"generated_at"})
    return _sha256_text(json.dumps(payload, sort_keys=True))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _yaml_dump(data: Any) -> str:
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _example_candidate_path(connection: Path, slug: str) -> Path:
    return connection / "examples" / "candidates" / f"{slug}.yaml"


@dataclass(slots=True)
class ReviewArtifact:
    review_kind: str
    proposed_relative_path: Path
    proposed_content: str
    manifest: dict[str, Any]
    reasoning: dict[str, Any]


class ReviewApplier:
    """Apply low-risk outputs and stage canonical changes for review."""

    def __init__(self, connection_path: Path):
        self.connection_path = connection_path

    @property
    def insider_root(self) -> Path:
        return self.connection_path / ".insider"

    def auto_apply(self, run_id: str, bundle: InsiderProposalBundle) -> list[Path]:
        """Write agent-owned draft outputs directly."""
        written: list[Path] = []
        run_dir = self.insider_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        input_summary_path = run_dir / "output.json"
        _atomic_write(input_summary_path, json.dumps(bundle.model_dump(mode="json"), indent=2))
        written.append(input_summary_path)

        findings_path = run_dir / "findings.yaml"
        _atomic_write(findings_path, _yaml_dump({"findings": bundle.findings}))
        written.append(findings_path)

        if bundle.draft_domain_model_markdown:
            draft_path = self.connection_path / "domain" / "model.draft.md"
            _atomic_write(draft_path, bundle.draft_domain_model_markdown.rstrip() + "\n")
            written.append(draft_path)

        for candidate in bundle.example_candidates:
            candidate_path = _example_candidate_path(self.connection_path, candidate.slug)
            _atomic_write(candidate_path, _yaml_dump(candidate.model_dump(mode="json")))
            written.append(candidate_path)

        return written

    def stage_review_artifact(
        self,
        *,
        review_id: str,
        run_id: str,
        review_kind: str,
        relative_path: Path,
        proposed_content: str,
        title: str,
        schema_digest: str,
        rationale: dict[str, Any],
    ) -> tuple[Path, Path, Path]:
        """Write staged proposal files for one review item."""
        change_dir = self.insider_root / "changes" / review_id
        proposed_path = change_dir / "proposed" / relative_path
        live_path = self.connection_path / relative_path
        current_content = live_path.read_text() if live_path.exists() else ""
        diff_text = "".join(
            unified_diff(
                current_content.splitlines(keepends=True),
                proposed_content.splitlines(keepends=True),
                fromfile=str(relative_path),
                tofile=str(relative_path),
            )
        )
        _atomic_write(proposed_path, proposed_content)
        diff_path = change_dir / "diff.patch"
        _atomic_write(diff_path, diff_text)

        manifest = {
            "review_id": review_id,
            "run_id": run_id,
            "connection": self.connection_path.name,
            "schema_digest": schema_digest,
            "review_kind": review_kind,
            "title": title,
            "targets": [
                {
                    "relative_path": str(relative_path),
                    "current_sha256": _sha256_text(current_content),
                    "proposed_sha256": _sha256_text(proposed_content),
                }
            ],
            "created_at": rationale.get("created_at"),
        }
        manifest_path = change_dir / "manifest.json"
        _atomic_write(manifest_path, json.dumps(manifest, indent=2))
        reasoning_path = change_dir / "reasoning.json"
        _atomic_write(reasoning_path, json.dumps(rationale, indent=2))
        return manifest_path, diff_path, reasoning_path

    def approve(self, review: dict[str, Any]) -> str:
        """Approve and apply one staged review item."""
        manifest_path = Path(review["manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        expected_digest = manifest.get("schema_digest", "")
        current_digest = _schema_digest_for_path(self.connection_path)
        if expected_digest and current_digest and expected_digest != current_digest:
            raise ValueError("Schema digest mismatch; review item is stale")

        for target in manifest.get("targets", []):
            relative_path = Path(target["relative_path"])
            live_path = self.connection_path / relative_path
            current_content = live_path.read_text() if live_path.exists() else ""
            if _sha256_text(current_content) != target["current_sha256"]:
                raise ValueError(f"Canonical file changed since staging: {relative_path}")
            proposed_path = manifest_path.parent / "proposed" / relative_path
            proposed_content = proposed_path.read_text()
            _atomic_write(live_path, proposed_content)
        return "approved"

    def reject(self, review: dict[str, Any]) -> str:
        """Reject one staged review item without mutating canonical files."""
        return "rejected"

