"""Benchmark pack loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from db_mcp.benchmark.models import BenchmarkCase


def get_case_pack_path(connection_path: Path, case_pack: str = "cases.yaml") -> Path:
    """Return the benchmark case pack path for a connection."""
    return connection_path / "benchmark" / case_pack


def load_case_pack(
    connection_path: Path,
    selected_case_ids: list[str] | None = None,
    case_pack: str = "cases.yaml",
) -> list[BenchmarkCase]:
    """Load and validate benchmark cases for a connection."""
    case_pack_path = get_case_pack_path(connection_path, case_pack=case_pack)
    if not case_pack_path.exists():
        raise ValueError(f"Benchmark pack not found: {case_pack_path}")

    with open(case_pack_path) as f:
        payload = yaml.safe_load(f) or {}

    raw_cases = payload if isinstance(payload, list) else payload.get("cases", [])
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"No benchmark cases found in {case_pack_path}")

    cases = [BenchmarkCase.model_validate(item) for item in raw_cases]
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"Duplicate benchmark case id: {case.id}")
        seen.add(case.id)

    if selected_case_ids:
        selected = [case for case in cases if case.id in set(selected_case_ids)]
        missing = sorted(set(selected_case_ids) - {case.id for case in selected})
        if missing:
            raise ValueError(f"Unknown benchmark cases: {', '.join(missing)}")
        return selected

    return cases
