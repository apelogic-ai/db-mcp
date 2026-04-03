"""Capability defaults and normalization for connector types.

This module is the single source of truth for capability defaults.
Both runtime execution and server tool registration should use these helpers
to avoid drift.
"""

from __future__ import annotations

from typing import Any

# Baseline shape every capability map should expose.
BASE_CAPABILITIES: dict[str, Any] = {
    "supports_sql": False,
    "supports_validate_sql": False,
    "supports_async_jobs": False,
    "sql_mode": None,
    "supports_openapi_discovery": False,
    "supports_endpoint_discovery": False,
    "supports_sync": False,
    "supports_file_scan": False,
    "supports_dashboard_api": False,
}

# Type-specific defaults (overlaid on top of BASE_CAPABILITIES).
TYPE_CAPABILITY_DEFAULTS: dict[str, dict[str, Any]] = {
    "sql": {
        "supports_sql": True,
        "supports_validate_sql": True,
        "supports_async_jobs": True,
        "sql_mode": "engine",
        "supports_sync": False,
    },
    "file": {
        "supports_sql": True,
        "supports_validate_sql": True,
        "supports_async_jobs": True,
        "sql_mode": "engine",
        "supports_file_scan": True,
        "supports_sync": False,
    },
    "api": {
        "supports_sql": False,
        "supports_validate_sql": False,
        "supports_async_jobs": False,
        "sql_mode": None,
        "supports_endpoint_discovery": True,
        "supports_sync": True,
    },
}

DEFAULT_PROFILE_BY_TYPE: dict[str, str] = {
    "sql": "sql_db",
    "file": "file_local",
    "api": "api_openapi",
}

PROFILE_ALLOWED_TYPES: dict[str, set[str]] = {
    "sql_db": {"sql"},
    "file_local": {"file"},
    "api_sql": {"api"},
    "api_openapi": {"api"},
    "api_probe": {"api"},
    "hybrid_bi": {"api"},
}

PROFILE_CAPABILITY_DEFAULTS: dict[str, dict[str, Any]] = {
    "sql_db": {
        "supports_sql": True,
        "supports_validate_sql": True,
        "supports_async_jobs": True,
        "sql_mode": "engine",
    },
    "file_local": {
        "supports_sql": True,
        "supports_validate_sql": True,
        "supports_async_jobs": True,
        "sql_mode": "engine",
        "supports_file_scan": True,
    },
    "api_sql": {
        "supports_sql": True,
        "supports_validate_sql": False,
        "supports_async_jobs": True,
        "sql_mode": "api_async",
        "supports_endpoint_discovery": True,
        "supports_sync": False,
    },
    "api_openapi": {
        "supports_sql": False,
        "supports_validate_sql": False,
        "supports_async_jobs": False,
        "sql_mode": None,
        "supports_openapi_discovery": True,
        "supports_endpoint_discovery": True,
        "supports_sync": True,
    },
    "api_probe": {
        "supports_sql": False,
        "supports_validate_sql": False,
        "supports_async_jobs": False,
        "sql_mode": None,
        "supports_openapi_discovery": False,
        "supports_endpoint_discovery": True,
        "supports_sync": True,
    },
    "hybrid_bi": {
        "supports_sql": True,
        "supports_validate_sql": False,
        "supports_async_jobs": False,
        "sql_mode": "api_sync",
        "supports_openapi_discovery": False,
        "supports_endpoint_discovery": True,
        "supports_sync": True,
        "supports_dashboard_api": True,
    },
}

LEGACY_CAPABILITY_ALIASES: dict[str, str] = {
    "sql": "supports_sql",
    "validate_sql": "supports_validate_sql",
    "async_jobs": "supports_async_jobs",
}


def resolve_connector_profile(connector_type: str, profile: str | None) -> str:
    """Return effective connector profile with type-safe fallback."""
    candidate = (profile or "").strip()
    if not candidate:
        return DEFAULT_PROFILE_BY_TYPE.get(connector_type, "")

    allowed = PROFILE_ALLOWED_TYPES.get(candidate)
    if not allowed:
        # Unknown profile: keep user-provided value for forward compatibility.
        return candidate

    if connector_type in allowed:
        return candidate

    return DEFAULT_PROFILE_BY_TYPE.get(connector_type, "")


def normalize_capabilities(
    connector_type: str,
    overrides: dict[str, Any] | None = None,
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    """Return normalized capability flags for a connector type.

    Args:
        connector_type: Connector type string (sql, file, api).
        overrides: Optional capability map from connector.yaml.
    """
    caps: dict[str, Any] = dict(BASE_CAPABILITIES)
    caps.update(TYPE_CAPABILITY_DEFAULTS.get(connector_type, {}))

    effective_profile = resolve_connector_profile(connector_type, profile)
    caps.update(PROFILE_CAPABILITY_DEFAULTS.get(effective_profile, {}))

    if isinstance(overrides, dict):
        merged_overrides = dict(overrides)
        for legacy_key, canonical_key in LEGACY_CAPABILITY_ALIASES.items():
            if canonical_key not in merged_overrides and legacy_key in merged_overrides:
                merged_overrides[canonical_key] = merged_overrides[legacy_key]
        caps.update(merged_overrides)

    return caps
