"""Ensure committed response JSON schema files stay in sync with models."""

from __future__ import annotations

import json
from pathlib import Path

from db_mcp_data.contracts.response_contracts import (
    RESPONSE_CONTRACT_SCHEMA_VERSION,
    build_response_contract_schemas,
)


def test_response_contract_schema_files_are_up_to_date():
    root = Path(__file__).resolve().parents[1]
    schema_dir = root / "contracts" / "response" / RESPONSE_CONTRACT_SCHEMA_VERSION
    assert schema_dir.exists(), (
        f"Schema directory missing: {schema_dir}. "
        "Run `uv run python scripts/export_response_contract_schemas.py`."
    )

    expected_schemas = build_response_contract_schemas()
    expected_files = {f"{name}.schema.json" for name in expected_schemas.keys()}

    actual_schema_files = {p.name for p in schema_dir.glob("*.schema.json")}
    assert actual_schema_files == expected_files, (
        "Schema file set mismatch. "
        "Run `uv run python scripts/export_response_contract_schemas.py`."
    )

    for name, expected in expected_schemas.items():
        path = schema_dir / f"{name}.schema.json"
        actual = json.loads(path.read_text(encoding="utf-8"))
        assert actual == expected, (
            f"Schema drift in {path}. "
            "Run `uv run python scripts/export_response_contract_schemas.py`."
        )

    manifest_path = schema_dir / "manifest.json"
    assert manifest_path.exists(), (
        f"Missing manifest file {manifest_path}. "
        "Run `uv run python scripts/export_response_contract_schemas.py`."
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest = {
        "schema_version": RESPONSE_CONTRACT_SCHEMA_VERSION,
        "schemas": sorted(expected_files),
    }
    assert manifest == expected_manifest, (
        "Manifest drift detected. "
        "Run `uv run python scripts/export_response_contract_schemas.py`."
    )
