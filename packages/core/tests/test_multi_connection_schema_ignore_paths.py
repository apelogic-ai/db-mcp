"""Regression tests for explicit connection path propagation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from db_mcp_models import OnboardingPhase

from db_mcp.onboarding.ignore import load_ignore_patterns, save_ignore_patterns
from db_mcp.onboarding.state import create_initial_state
from db_mcp.tools.domain import _domain_generate
from db_mcp.tools.generation import _get_data
from db_mcp.tools.onboarding import (
    _onboarding_add_ignore_pattern,
    _onboarding_discover,
    _onboarding_import_ignore_patterns,
    _onboarding_remove_ignore_pattern,
)
from db_mcp.tools.training import _query_generate


@pytest.mark.asyncio
async def test_get_data_loads_schema_from_resolved_connection_path():
    conn_path = Path("/tmp/connections/wifimetrics-trino")

    with (
        patch(
            "db_mcp.tools.utils.resolve_connection",
            return_value=(MagicMock(), "wifimetrics-trino", conn_path),
        ),
        patch(
            "db_mcp.tools.generation.load_schema_descriptions", return_value=None
        ) as mock_load_schema,
    ):
        result = await _get_data(ctx=MagicMock(), intent="test", connection="wifimetrics-trino")

    assert result["status"] == "error"
    assert mock_load_schema.call_args.kwargs["connection_path"] == conn_path


@pytest.mark.asyncio
async def test_query_generate_loads_schema_from_resolved_connection_path():
    conn_path = Path("/tmp/connections/wifimetrics-trino")

    with (
        patch(
            "db_mcp.tools.utils.resolve_connection",
            return_value=(MagicMock(), "wifimetrics-trino", conn_path),
        ),
        patch(
            "db_mcp.tools.training.load_schema_descriptions", return_value=None
        ) as mock_load_schema,
    ):
        result = await _query_generate(natural_language="test", connection="wifimetrics-trino")

    assert "error" in result
    assert mock_load_schema.call_args.kwargs["connection_path"] == conn_path


@pytest.mark.asyncio
async def test_domain_generate_loads_schema_from_resolved_connection_path():
    conn_path = Path("/tmp/connections/wifimetrics-trino")
    state = create_initial_state("wifimetrics-trino")
    state.phase = OnboardingPhase.DOMAIN

    with (
        patch(
            "db_mcp.tools.utils.resolve_connection",
            return_value=(MagicMock(), "wifimetrics-trino", conn_path),
        ),
        patch("db_mcp.tools.domain.load_state", return_value=state),
        patch(
            "db_mcp.tools.domain.load_schema_descriptions", return_value=None
        ) as mock_load_schema,
    ):
        result = await _domain_generate(connection="wifimetrics-trino")

    assert "error" in result
    assert mock_load_schema.call_args.kwargs["connection_path"] == conn_path


@pytest.mark.asyncio
async def test_onboarding_discover_loads_ignore_patterns_from_resolved_connection_path():
    conn_path = Path("/tmp/connections/wifimetrics-trino")
    connector = MagicMock()
    connector.get_catalogs.return_value = [None]
    connector.get_schemas.return_value = [None]

    state = create_initial_state("wifimetrics-trino")
    state.phase = OnboardingPhase.INIT

    ignore = MagicMock()
    ignore.patterns = []
    ignore.filter_catalogs.side_effect = lambda catalogs: catalogs
    ignore.filter_schemas.side_effect = lambda schemas: schemas

    with (
        patch(
            "db_mcp.tools.onboarding._resolve_onboarding_context",
            return_value=(connector, "wifimetrics-trino", conn_path),
        ),
        patch("db_mcp.tools.onboarding.load_state", return_value=state),
        patch(
            "db_mcp.tools.onboarding.load_ignore_patterns", return_value=ignore
        ) as mock_load_ignore,
        patch("db_mcp.tools.onboarding.save_state", return_value={"saved": True}),
    ):
        result = await _onboarding_discover(phase="structure", connection="wifimetrics-trino")

    assert result["discovered"] is True
    assert mock_load_ignore.call_args.kwargs["connection_path"] == conn_path


@pytest.mark.asyncio
async def test_onboarding_add_ignore_pattern_passes_connection_path():
    conn_path = Path("/tmp/connections/wifimetrics-trino")

    with (
        patch(
            "db_mcp.tools.onboarding._resolve_onboarding_context",
            return_value=(MagicMock(), "wifimetrics-trino", conn_path),
        ),
        patch(
            "db_mcp.tools.onboarding.add_ignore_pattern",
            return_value={"added": False, "error": "test"},
        ) as mock_add,
    ):
        await _onboarding_add_ignore_pattern("tmp_*", connection="wifimetrics-trino")

    assert mock_add.call_args.kwargs["connection_path"] == conn_path


@pytest.mark.asyncio
async def test_onboarding_remove_ignore_pattern_passes_connection_path():
    conn_path = Path("/tmp/connections/wifimetrics-trino")

    with (
        patch(
            "db_mcp.tools.onboarding._resolve_onboarding_context",
            return_value=(MagicMock(), "wifimetrics-trino", conn_path),
        ),
        patch(
            "db_mcp.tools.onboarding.remove_ignore_pattern",
            return_value={"removed": False, "error": "test"},
        ) as mock_remove,
    ):
        await _onboarding_remove_ignore_pattern("tmp_*", connection="wifimetrics-trino")

    assert mock_remove.call_args.kwargs["connection_path"] == conn_path


@pytest.mark.asyncio
async def test_onboarding_import_ignore_patterns_passes_connection_path():
    conn_path = Path("/tmp/connections/wifimetrics-trino")

    with (
        patch(
            "db_mcp.tools.onboarding._resolve_onboarding_context",
            return_value=(MagicMock(), "wifimetrics-trino", conn_path),
        ),
        patch(
            "db_mcp.tools.onboarding.import_ignore_patterns",
            return_value={"imported": False, "error": "test"},
        ) as mock_import,
    ):
        await _onboarding_import_ignore_patterns(["tmp_*"], connection="wifimetrics-trino")

    assert mock_import.call_args.kwargs["connection_path"] == conn_path


def test_ignore_store_uses_explicit_connection_path(tmp_path):
    conn_path = tmp_path / "wifimetrics-trino"

    result = save_ignore_patterns(
        "wifimetrics-trino",
        ["tmp_*", "test_*"],
        connection_path=conn_path,
    )
    assert result["saved"] is True
    assert result["file_path"].endswith(".db-mcpignore")

    ignore = load_ignore_patterns("wifimetrics-trino", connection_path=conn_path)
    assert ignore.should_ignore("tmp_table")
    assert ignore.should_ignore("test_table")
