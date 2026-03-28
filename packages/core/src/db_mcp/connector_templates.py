"""Connector template catalog backed by built-in and installed plugins."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from db_mcp.connector_plugins import get_connector_plugin, list_connector_plugins
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
    source: str = "builtin"
    package_name: str | None = None


def _load_template(
    path: Path,
    *,
    source: str = "builtin",
    package_name: str | None = None,
) -> ConnectorTemplate:
    with Path(path).open() as f:
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
        source=source,
        package_name=package_name,
    )


def list_connector_templates(connector_type: str | None = None) -> list[ConnectorTemplate]:
    templates = [
        _load_template(
            plugin.template_path,
            source=plugin.source,
            package_name=plugin.package_name,
        )
        for plugin in list_connector_plugins()
    ]
    if connector_type:
        templates = [
            template for template in templates if template.connector.get("type") == connector_type
        ]
    return templates


def get_connector_template(template_id: str) -> ConnectorTemplate | None:
    plugin = get_connector_plugin(template_id)
    if plugin is None:
        return None
    return _load_template(
        plugin.template_path,
        source=plugin.source,
        package_name=plugin.package_name,
    )


def materialize_connector_template(
    template_id: str,
    *,
    base_url: str | None = None,
    env_name_overrides: dict[str, str] | None = None,
    auth_overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    template = get_connector_template(template_id)
    if template is None:
        return None

    connector = deepcopy(template.connector)
    connector["template_id"] = template.id
    if base_url:
        connector["base_url"] = base_url

    auth = connector.get("auth")
    if isinstance(auth, dict):
        if env_name_overrides:
            for env_key in ("token_env", "username_env", "password_env"):
                current_name = auth.get(env_key)
                if isinstance(current_name, str) and current_name in env_name_overrides:
                    auth[env_key] = env_name_overrides[current_name]

        if auth_overrides:
            for key, value in auth_overrides.items():
                if value not in (None, ""):
                    auth[key] = value

    return connector


def match_connector_template(connector: dict[str, Any]) -> str | None:
    explicit_template_id = str(connector.get("template_id", "") or "").strip()
    if explicit_template_id:
        if get_connector_template(explicit_template_id) is not None:
            return explicit_template_id
        return None

    connector_type = connector.get("type")
    profile = connector.get("profile")
    auth = connector.get("auth", {}) or {}
    auth_type = auth.get("type")
    connector_endpoint_names = {
        endpoint.get("name", "")
        for endpoint in connector.get("endpoints", []) or []
        if isinstance(endpoint, dict)
    }
    connector_endpoint_signatures = {
        (
            str(endpoint.get("path", "") or "").strip(),
            str(endpoint.get("method", "GET") or "GET").strip().upper(),
        )
        for endpoint in connector.get("endpoints", []) or []
        if isinstance(endpoint, dict)
    }

    for template in list_connector_templates(connector_type):
        template_auth = template.connector.get("auth", {}) or {}
        template_endpoint_names = {
            endpoint.get("name", "")
            for endpoint in template.connector.get("endpoints", []) or []
            if isinstance(endpoint, dict)
        }
        template_endpoint_signatures = {
            (
                str(endpoint.get("path", "") or "").strip(),
                str(endpoint.get("method", "GET") or "GET").strip().upper(),
            )
            for endpoint in template.connector.get("endpoints", []) or []
            if isinstance(endpoint, dict)
        }
        if (
            template.connector.get("profile") == profile
            and template_auth.get("type") == auth_type
            and (
                template_endpoint_names.issubset(connector_endpoint_names)
                or template_endpoint_signatures.issubset(connector_endpoint_signatures)
            )
        ):
            return template.id

    return None
