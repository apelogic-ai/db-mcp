"""Compatibility normalization for persisted connector payloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def normalize_connector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a compatibility-normalized connector payload."""
    normalized = deepcopy(payload)
    template_id = str(normalized.get("template_id", "") or "").strip()

    if template_id == "metabase":
        return _normalize_metabase_payload(normalized)

    return normalized


def _normalize_metabase_payload(payload: dict[str, Any]) -> dict[str, Any]:
    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list):
        return payload

    normalized_endpoints: list[dict[str, Any]] = []
    for raw_endpoint in endpoints:
        if not isinstance(raw_endpoint, dict):
            continue

        endpoint = dict(raw_endpoint)
        endpoint.pop("body_template", None)
        endpoint.pop("description", None)

        query_params = endpoint.get("query_params")
        if isinstance(query_params, list):
            endpoint["query_params"] = [
                _normalize_metabase_query_param(raw_query_param)
                for raw_query_param in query_params
                if isinstance(raw_query_param, dict) and raw_query_param.get("name")
            ]

        normalized_endpoints.append(endpoint)

    payload["endpoints"] = normalized_endpoints
    return payload


def _normalize_metabase_query_param(query_param: dict[str, Any]) -> dict[str, Any]:
    normalized = {"name": str(query_param["name"])}

    query_type = str(query_param.get("type", "") or "").strip()
    if query_type:
        normalized["type"] = query_type

    return normalized
