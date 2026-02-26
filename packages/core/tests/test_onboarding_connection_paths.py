"""Tests for onboarding connection-path propagation in multi-connection mode."""

from unittest.mock import MagicMock, patch

import pytest
from db_mcp_models import OnboardingPhase

from db_mcp.onboarding.schema_store import (
    create_initial_schema,
    load_schema_descriptions,
    save_schema_descriptions,
)
from db_mcp.onboarding.state import create_initial_state
from db_mcp.tools.onboarding import _discover_tables_background, _discovery_tasks


def test_schema_store_uses_explicit_connection_path(tmp_path):
    """Schema store should load/save from the provided connection path."""
    conn_path = tmp_path / "wifimetrics-trino"
    schema = create_initial_schema(
        provider_id="wifimetrics-trino",
        dialect="trino",
        tables=[
            {
                "name": "events",
                "schema": "public",
                "catalog": "chinook",
                "full_name": "chinook.public.events",
                "columns": [{"name": "id", "type": "INTEGER"}],
            }
        ],
    )

    save_result = save_schema_descriptions(schema, connection_path=conn_path)
    assert save_result["saved"] is True
    assert "wifimetrics-trino/schema/descriptions.yaml" in save_result["file_path"]

    loaded = load_schema_descriptions("wifimetrics-trino", connection_path=conn_path)
    assert loaded is not None
    assert len(loaded.tables) == 1
    assert loaded.tables[0].full_name == "chinook.public.events"


@pytest.mark.asyncio
async def test_discover_tables_background_uses_explicit_connection_path(tmp_path):
    """Tables discovery must read/write state and schema in the selected connection path."""
    provider_id = "wifimetrics-trino"
    conn_path = tmp_path / "wifimetrics-trino"

    state = create_initial_state(provider_id)
    state.phase = OnboardingPhase.INIT
    state.dialect_detected = "trino"
    state.catalogs_discovered = []

    connector = MagicMock()
    connector.get_schemas.return_value = [None]
    connector.get_tables.return_value = [{"name": "events", "full_name": "events"}]
    connector.get_columns.return_value = []

    ignore = MagicMock()
    ignore.filter_schemas.side_effect = lambda schemas: schemas
    ignore.filter_tables.side_effect = lambda tables: tables

    discovery_id = "test-discovery"
    _discovery_tasks[discovery_id] = {"status": "running"}

    try:
        with (
            patch("db_mcp.tools.onboarding.load_state", return_value=state) as mock_load_state,
            patch("db_mcp.tools.onboarding.load_ignore_patterns", return_value=ignore),
            patch("db_mcp.tools.onboarding.get_connector", return_value=connector),
            patch(
                "db_mcp.tools.onboarding.save_schema_descriptions",
                return_value={"saved": True, "file_path": "/tmp/schema/descriptions.yaml"},
            ) as mock_save_schema,
            patch(
                "db_mcp.tools.onboarding.save_state",
                return_value={"saved": True},
            ) as mock_save_state,
        ):
            await _discover_tables_background(discovery_id, provider_id, connection_path=conn_path)

        assert mock_load_state.call_args.kwargs["connection_path"] == conn_path
        assert mock_save_schema.call_args.kwargs["connection_path"] == conn_path
        assert mock_save_state.call_args.kwargs["connection_path"] == conn_path
        assert _discovery_tasks[discovery_id]["status"] == "complete"
    finally:
        _discovery_tasks.pop(discovery_id, None)
