"""Tests for capability normalization single source of truth."""

from db_mcp.capabilities import (
    BASE_CAPABILITIES,
    DEFAULT_PROFILE_BY_TYPE,
    PROFILE_CAPABILITY_DEFAULTS,
    TYPE_CAPABILITY_DEFAULTS,
    normalize_capabilities,
    resolve_connector_profile,
)


def test_base_shape_contains_required_fields():
    assert {
        "supports_sql",
        "supports_validate_sql",
        "supports_async_jobs",
        "sql_mode",
    }.issubset(set(BASE_CAPABILITIES.keys()))


def test_base_shape_has_api_and_file_discovery_flags():
    assert {
        "supports_openapi_discovery",
        "supports_endpoint_discovery",
        "supports_sync",
        "supports_file_scan",
        "supports_dashboard_api",
    }.issubset(set(BASE_CAPABILITIES.keys()))


def test_profile_defaults_defined_for_supported_types():
    assert DEFAULT_PROFILE_BY_TYPE["sql"] == "sql_db"
    assert DEFAULT_PROFILE_BY_TYPE["file"] == "file_local"
    assert DEFAULT_PROFILE_BY_TYPE["api"] == "api_openapi"


def test_profile_capability_defaults_cover_known_profiles():
    for profile in ("sql_db", "file_local", "api_sql", "api_openapi", "api_probe", "hybrid_bi"):
        assert profile in PROFILE_CAPABILITY_DEFAULTS


def test_resolve_connector_profile_uses_type_default_when_missing():
    assert resolve_connector_profile("api", None) == "api_openapi"
    assert resolve_connector_profile("sql", "") == "sql_db"


def test_resolve_connector_profile_type_mismatch_falls_back_to_default():
    assert resolve_connector_profile("file", "api_openapi") == "file_local"


def test_resolve_connector_profile_keeps_unknown_profile_for_forward_compat():
    assert (
        resolve_connector_profile("api", "community_custom_profile")
        == "community_custom_profile"
    )


def test_api_sql_profile_enables_sql_path_by_default():
    caps = normalize_capabilities("api", profile="api_sql")
    assert caps["supports_sql"] is True
    assert caps["supports_validate_sql"] is False
    assert caps["sql_mode"] == "api_async"


def test_api_openapi_profile_enables_discovery_by_default():
    caps = normalize_capabilities("api", profile="api_openapi")
    assert caps["supports_sql"] is False
    assert caps["supports_openapi_discovery"] is True
    assert caps["supports_endpoint_discovery"] is True
    assert caps["supports_sync"] is True


def test_hybrid_bi_profile_enables_sql_and_dashboard_api():
    caps = normalize_capabilities("api", profile="hybrid_bi")
    assert caps["supports_sql"] is True
    assert caps["supports_dashboard_api"] is True


def test_overrides_still_take_precedence_over_profile_defaults():
    caps = normalize_capabilities(
        "api",
        {"supports_sql": False, "sql_mode": None, "supports_openapi_discovery": False},
        profile="api_sql",
    )
    assert caps["supports_sql"] is False
    assert caps["sql_mode"] is None
    assert caps["supports_openapi_discovery"] is False


def test_legacy_aliases_apply_after_profile_defaults():
    caps = normalize_capabilities("api", {"sql": True}, profile="api_openapi")
    assert caps["supports_sql"] is True


def test_sql_defaults():
    caps = normalize_capabilities("sql")
    assert caps["supports_sql"] is True
    assert caps["supports_validate_sql"] is True
    assert caps["supports_async_jobs"] is True
    assert caps["sql_mode"] == "engine"


def test_api_defaults():
    caps = normalize_capabilities("api")
    assert caps["supports_sql"] is False
    assert caps["supports_validate_sql"] is False
    assert caps["supports_async_jobs"] is False
    assert caps["sql_mode"] is None


def test_overrides_take_precedence():
    caps = normalize_capabilities("api", {"supports_sql": True, "sql_mode": "api_sync"})
    assert caps["supports_sql"] is True
    assert caps["sql_mode"] == "api_sync"


def test_defaults_defined_for_all_supported_types():
    for connector_type in ("sql", "file", "api"):
        assert connector_type in TYPE_CAPABILITY_DEFAULTS
