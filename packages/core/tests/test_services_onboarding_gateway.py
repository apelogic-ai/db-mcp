"""Tests for services/onboarding.py using gateway introspect dispatch."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from db_mcp_knowledge.onboarding.state import create_initial_state
from db_mcp_models import OnboardingPhase

# ---------------------------------------------------------------------------
# discover_structure — connector passed in, routed via adapter dispatch
# ---------------------------------------------------------------------------

def _make_sql_connector(*, catalogs=None, schemas=None):
    from db_mcp_data.connectors.sql import SQLConnector

    c = MagicMock(spec=SQLConnector)
    c.get_catalogs.return_value = catalogs if catalogs is not None else ["analytics"]
    c.get_schemas.return_value = schemas if schemas is not None else ["public"]
    return c


def test_discover_structure_via_gateway_introspect():
    """discover_structure uses gateway.introspect() for catalog/schema calls."""
    from db_mcp.services.onboarding import discover_structure

    provider_id = "prod"
    connection_path = Path("/tmp/connections/prod")

    connector = _make_sql_connector(catalogs=["analytics"], schemas=["public", "sales"])
    state = create_initial_state(provider_id)
    state.phase = OnboardingPhase.INIT
    state.dialect_detected = "postgres"

    ignore = MagicMock()
    ignore.patterns = []
    ignore.filter_catalogs.return_value = ["analytics"]
    ignore.filter_schemas.return_value = ["public", "sales"]

    with (
        patch("db_mcp.services.onboarding.load_state", return_value=state),
        patch("db_mcp.services.onboarding.load_ignore_patterns", return_value=ignore),
        patch("db_mcp.services.onboarding.save_state", return_value={"saved": True}),
        patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector),
    ):
        result = discover_structure(
            provider_id=provider_id,
            connection_path=connection_path,
        )

    assert result["discovered"] is True
    assert result["catalogs"] == ["analytics"]
    assert result["schemas_found"] == 2
    # Verify gateway reached the connector
    connector.get_catalogs.assert_called_once()
    connector.get_schemas.assert_called_once_with(catalog="analytics")


# ---------------------------------------------------------------------------
# discover_tables_background — gateway.introspect() replaces connector calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_discover_tables_background_via_gateway(tmp_path):
    """discover_tables_background uses gateway.introspect() for schema/table/column calls."""
    from db_mcp.services.onboarding import discover_tables_background

    provider_id = "prod"
    connection_path = tmp_path / "prod"
    connection_path.mkdir()

    connector = _make_sql_connector()
    connector.get_schemas.return_value = [None]
    connector.get_tables.return_value = [{"name": "orders", "full_name": "orders"}]
    connector.get_columns.return_value = [{"name": "id", "type": "INTEGER"}]

    state = create_initial_state(provider_id)
    state.phase = OnboardingPhase.INIT
    state.dialect_detected = "postgres"
    state.catalogs_discovered = []

    ignore = MagicMock()
    ignore.filter_schemas.side_effect = lambda schemas: schemas
    ignore.filter_tables.side_effect = lambda tables: tables

    task = {"status": "running"}

    with (
        patch("db_mcp.services.onboarding.load_state", return_value=state),
        patch("db_mcp.services.onboarding.load_ignore_patterns", return_value=ignore),
        patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector),
        patch(
            "db_mcp.services.onboarding.save_schema_descriptions",
            return_value={"saved": True, "file_path": str(connection_path / "schema.yaml")},
        ),
        patch("db_mcp.services.onboarding.save_state", return_value={"saved": True}),
        patch("db_mcp.services.onboarding.get_insider_supervisor", return_value=None),
    ):
        await discover_tables_background(
            discovery_id="disc-gw",
            provider_id=provider_id,
            task=task,
            connection_path=connection_path,
        )

    assert task["status"] == "complete"
    assert task["result"]["tables_found"] == 1
    # Connector methods were called (via gateway adapter dispatch)
    connector.get_schemas.assert_called()
    connector.get_tables.assert_called()
    connector.get_columns.assert_called()
