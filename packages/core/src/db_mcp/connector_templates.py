"""Built-in connector template catalog.

Templates are stored as single YAML files under ``db_mcp/static/connector_templates`` so
community contributions can add or update one template per PR without touching Python code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from db_mcp.contracts.connector_contracts import validate_connector_contract


@dataclass(frozen=True)
class ConnectorTemplateEnvVar:
    name: str
    prompt: str
    secret: bool = True


@dataclass(frozen=True)
class ConnectorTemplate:
    id: str
    title: str
    description: str
    connector: dict[str, Any]
    env: list[ConnectorTemplateEnvVar]
    base_url_prompt: str | None = None


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "static" / "connector_templates"


def _load_template(path: Path) -> ConnectorTemplate:
    with path.open() as f:
        payload = yaml.safe_load(f) or {}

    connector = payload.get("connector") or {}
    validate_connector_contract(connector)

    env = [ConnectorTemplateEnvVar(**entry) for entry in payload.get("env", [])]

    return ConnectorTemplate(
        id=payload["id"],
        title=payload.get("title", payload["id"]),
        description=payload.get("description", ""),
        connector=connector,
        env=env,
        base_url_prompt=payload.get("base_url_prompt"),
    )


def list_connector_templates(connector_type: str | None = None) -> list[ConnectorTemplate]:
    templates = [
        _load_template(path)
        for path in sorted(_template_dir().glob("*.yaml"))
    ]
    if connector_type:
        templates = [
            template for template in templates if template.connector.get("type") == connector_type
        ]
    return templates


def get_connector_template(template_id: str) -> ConnectorTemplate | None:
    for template in list_connector_templates():
        if template.id == template_id:
            return template
    return None
