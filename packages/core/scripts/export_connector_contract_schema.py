#!/usr/bin/env python3
"""Export versioned connector.yaml JSON schema."""

from __future__ import annotations

import json
from pathlib import Path

from db_mcp.contracts.connector_contracts import (
    CONNECTOR_CONTRACT_SCHEMA_VERSION,
    CONNECTOR_SPEC_VERSION,
    build_connector_contract_schemas,
)


def _contracts_dir(root: Path) -> Path:
    return root / "contracts" / "connector" / CONNECTOR_CONTRACT_SCHEMA_VERSION


def export_connector_contract_schema(root: Path) -> list[Path]:
    """Write versioned connector contract JSON schema files to disk."""
    target_dir = _contracts_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)

    schemas = build_connector_contract_schemas()
    written: list[Path] = []

    for name in sorted(schemas.keys()):
        schema_path = target_dir / f"{name}.schema.json"
        schema_text = json.dumps(schemas[name], indent=2, sort_keys=True) + "\n"
        schema_path.write_text(schema_text, encoding="utf-8")
        written.append(schema_path)

    manifest = {
        "schema_version": CONNECTOR_CONTRACT_SCHEMA_VERSION,
        "spec_version": CONNECTOR_SPEC_VERSION,
        "schemas": [path.name for path in written],
    }
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    written.append(manifest_path)
    return written


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    written = export_connector_contract_schema(root)
    print(f"Exported {len(written)} files:")
    for path in written:
        print(path.relative_to(root))


if __name__ == "__main__":
    main()

