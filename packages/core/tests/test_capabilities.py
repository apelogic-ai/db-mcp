"""Tests for capability normalization single source of truth."""

from db_mcp.capabilities import BASE_CAPABILITIES, TYPE_CAPABILITY_DEFAULTS, normalize_capabilities


def test_base_shape_contains_required_fields():
    assert set(BASE_CAPABILITIES.keys()) == {
        "supports_sql",
        "supports_validate_sql",
        "supports_async_jobs",
        "sql_mode",
    }


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
    for connector_type in ("sql", "file", "api", "metabase"):
        assert connector_type in TYPE_CAPABILITY_DEFAULTS
