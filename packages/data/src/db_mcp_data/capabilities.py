"""Backward-compatibility shim — canonical location is db_mcp_models.connector_capabilities."""

from db_mcp_models.connector_capabilities import (  # noqa: F401
    BASE_CAPABILITIES,
    DEFAULT_PROFILE_BY_TYPE,
    LEGACY_CAPABILITY_ALIASES,
    PROFILE_ALLOWED_TYPES,
    PROFILE_CAPABILITY_DEFAULTS,
    TYPE_CAPABILITY_DEFAULTS,
    normalize_capabilities,
    resolve_connector_profile,
)

__all__ = [
    "BASE_CAPABILITIES",
    "DEFAULT_PROFILE_BY_TYPE",
    "LEGACY_CAPABILITY_ALIASES",
    "PROFILE_ALLOWED_TYPES",
    "PROFILE_CAPABILITY_DEFAULTS",
    "TYPE_CAPABILITY_DEFAULTS",
    "normalize_capabilities",
    "resolve_connector_profile",
]
