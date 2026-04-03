"""discover_structure must call gateway.introspect(), not adapter directly."""

from unittest.mock import MagicMock, patch

from db_mcp_knowledge.onboarding.state import create_initial_state
from db_mcp_models import OnboardingPhase


def _sql_connector(catalogs=None, schemas=None):
    from db_mcp_data.connectors.sql import SQLConnector
    c = MagicMock(spec=SQLConnector)
    c.get_catalogs.return_value = catalogs or ["prod"]
    c.get_schemas.return_value = schemas or ["public"]
    return c


def _make_state(provider_id, phase=OnboardingPhase.INIT):
    state = create_initial_state(provider_id)
    state.phase = phase
    state.dialect_detected = "postgres"
    return state


def _make_ignore(catalogs=None, schemas=None):
    ignore = MagicMock()
    ignore.patterns = []
    ignore.filter_catalogs.side_effect = lambda c: catalogs if catalogs is not None else c
    ignore.filter_schemas.side_effect = lambda s: schemas if schemas is not None else s
    return ignore


# ---------------------------------------------------------------------------
# discover_structure signature no longer accepts connector
# ---------------------------------------------------------------------------

def test_discover_structure_does_not_accept_connector_param():
    """discover_structure must not have a connector parameter."""
    import inspect

    from db_mcp.services.onboarding import discover_structure
    sig = inspect.signature(discover_structure)
    assert "connector" not in sig.parameters, (
        "discover_structure still has a 'connector' parameter — "
        "it should route through gateway.introspect() using connection_path"
    )


def test_discover_structure_requires_connection_path():
    """connection_path must be a required (non-optional) parameter."""
    import inspect

    from db_mcp.services.onboarding import discover_structure
    sig = inspect.signature(discover_structure)
    assert "connection_path" in sig.parameters
    param = sig.parameters["connection_path"]
    assert param.default is inspect.Parameter.empty, (
        "connection_path should be required, not optional"
    )


# ---------------------------------------------------------------------------
# gateway.introspect() is called, not adapter directly
# ---------------------------------------------------------------------------

def test_discover_structure_routes_through_gateway_introspect(tmp_path):
    """discover_structure must call gateway.introspect, not get_adapter."""
    from db_mcp.services.onboarding import discover_structure

    provider_id = "prod"
    connection_path = tmp_path / provider_id
    connection_path.mkdir()

    connector = _sql_connector(catalogs=["analytics"], schemas=["public"])
    state = _make_state(provider_id)
    ignore = _make_ignore()

    introspect_calls = []

    def _fake_introspect(connection, scope, *, connection_path=None, catalog=None, **kw):
        introspect_calls.append(scope)
        if scope == "catalogs":
            return {"catalogs": ["analytics"]}
        if scope == "schemas":
            return {"schemas": ["public"]}
        return {}

    with (
        patch("db_mcp.services.onboarding.load_state", return_value=state),
        patch("db_mcp.services.onboarding.load_ignore_patterns", return_value=ignore),
        patch("db_mcp.services.onboarding.save_state", return_value={"saved": True}),
        patch("db_mcp.services.onboarding.gateway_introspect", side_effect=_fake_introspect),
    ):
        result = discover_structure(
            provider_id=provider_id,
            connection_path=connection_path,
        )

    assert result["discovered"] is True
    assert "catalogs" in introspect_calls
    assert "schemas" in introspect_calls
    # Adapter must not be touched directly
    connector.get_catalogs.assert_not_called()
    connector.get_schemas.assert_not_called()


def test_discover_structure_passes_connection_path_to_gateway(tmp_path):
    """gateway.introspect() must receive the connection_path."""
    from db_mcp.services.onboarding import discover_structure

    provider_id = "prod"
    connection_path = tmp_path / provider_id
    connection_path.mkdir()

    state = _make_state(provider_id)
    ignore = _make_ignore(catalogs=["analytics"], schemas=["public"])

    received_paths = []

    def _fake_introspect(connection, scope, *, connection_path=None, catalog=None, **kw):
        received_paths.append(connection_path)
        if scope == "catalogs":
            return {"catalogs": ["analytics"]}
        return {"schemas": ["public"]}

    with (
        patch("db_mcp.services.onboarding.load_state", return_value=state),
        patch("db_mcp.services.onboarding.load_ignore_patterns", return_value=ignore),
        patch("db_mcp.services.onboarding.save_state", return_value={"saved": True}),
        patch("db_mcp.services.onboarding.gateway_introspect", side_effect=_fake_introspect),
    ):
        discover_structure(provider_id=provider_id, connection_path=connection_path)

    assert all(p == connection_path for p in received_paths)
