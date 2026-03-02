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
}

# Type-specific defaults (overlaid on top of BASE_CAPABILITIES).
TYPE_CAPABILITY_DEFAULTS: dict[str, dict[str, Any]] = {
    "sql": {
        "supports_sql": True,
        "supports_validate_sql": True,
        "supports_async_jobs": True,
        "sql_mode": "engine",
    },
    "file": {
        "supports_sql": True,
        "supports_validate_sql": True,
        "supports_async_jobs": True,
        "sql_mode": "engine",
    },
    "metabase": {
        "supports_sql": True,
        "supports_validate_sql": False,
        "supports_async_jobs": False,
        "sql_mode": "api_sync",
    },
    "api": {
        "supports_sql": False,
        "supports_validate_sql": False,
        "supports_async_jobs": False,
        "sql_mode": None,
    },
}


def normalize_capabilities(
    connector_type: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return normalized capability flags for a connector type.

    Args:
        connector_type: Connector type string (sql, file, api, metabase).
        overrides: Optional capability map from connector.yaml.
    """
    caps: dict[str, Any] = dict(BASE_CAPABILITIES)
    caps.update(TYPE_CAPABILITY_DEFAULTS.get(connector_type, {}))

    if isinstance(overrides, dict):
        caps.update(overrides)

    return caps
