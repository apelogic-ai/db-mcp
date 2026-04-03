"""Tests for gateway dispatcher — routes DataRequest to the correct adapter."""

from unittest.mock import MagicMock, patch

import pytest
from db_mcp_models.gateway import DataRequest, EndpointQuery, SQLQuery

import db_mcp_data.gateway as gateway
from db_mcp_data.gateway.dispatcher import _ADAPTERS, get_adapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sql_connector():
    from db_mcp_data.connectors.sql import SQLConnector
    return MagicMock(spec=SQLConnector)


def _api_connector():
    from db_mcp_data.connectors.api import APIConnector
    return MagicMock(spec=APIConnector)


def _file_connector():
    from db_mcp_data.connectors.file import FileConnector
    return MagicMock(spec=FileConnector)


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

def test_adapters_registry_is_non_empty():
    assert len(_ADAPTERS) >= 3


def test_registry_contains_all_three_adapter_types():
    from db_mcp_data.gateway.api_adapter import APIAdapter
    from db_mcp_data.gateway.file_adapter import FileAdapter
    from db_mcp_data.gateway.sql_adapter import SQLAdapter

    types = {type(a) for a in _ADAPTERS}
    assert SQLAdapter in types
    assert APIAdapter in types
    assert FileAdapter in types


# ---------------------------------------------------------------------------
# get_adapter routing
# ---------------------------------------------------------------------------

def test_get_adapter_routes_sql_connector():
    from db_mcp_data.gateway.sql_adapter import SQLAdapter
    adapter = get_adapter(_sql_connector())
    assert isinstance(adapter, SQLAdapter)


def test_get_adapter_routes_api_connector():
    from db_mcp_data.gateway.api_adapter import APIAdapter
    adapter = get_adapter(_api_connector())
    assert isinstance(adapter, APIAdapter)


def test_get_adapter_routes_file_connector():
    from db_mcp_data.gateway.file_adapter import FileAdapter
    adapter = get_adapter(_file_connector())
    assert isinstance(adapter, FileAdapter)


def test_get_adapter_raises_for_unknown_connector():
    with pytest.raises(ValueError, match="No adapter found"):
        get_adapter(object())


def test_api_adapter_wins_over_file_for_api_connector():
    """APIConnector extends FileConnector — APIAdapter must be checked first."""
    from db_mcp_data.gateway.api_adapter import APIAdapter
    adapter = get_adapter(_api_connector())
    assert isinstance(adapter, APIAdapter)


# ---------------------------------------------------------------------------
# gateway.run() — end-to-end dispatch (connector mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_routes_to_sql_adapter(tmp_path):
    connector = _sql_connector()
    connector.execute_sql.return_value = [{"n": 1}]

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1 AS n"))
        result = await gateway.run(request, connection_path=tmp_path)

    assert result.is_success
    assert result.data == [{"n": 1}]


@pytest.mark.asyncio
async def test_run_routes_to_api_adapter_endpoint(tmp_path):
    connector = _api_connector()
    connector.query_endpoint.return_value = {"data": [{"id": 1}], "rows_returned": 1}

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        request = DataRequest(
            connection="metabase",
            query=EndpointQuery(endpoint="dashboards"),
        )
        result = await gateway.run(request, connection_path=tmp_path)

    assert result.is_success
    assert result.data == [{"id": 1}]


@pytest.mark.asyncio
async def test_run_routes_to_file_adapter(tmp_path):
    connector = _file_connector()
    connector.execute_sql.return_value = [{"val": 42}]

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        request = DataRequest(connection="local", query=SQLQuery(sql="SELECT 42 AS val"))
        result = await gateway.run(request, connection_path=tmp_path)

    assert result.is_success
    assert result.data == [{"val": 42}]


@pytest.mark.asyncio
async def test_run_returns_error_for_unknown_connector(tmp_path):
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=object()):
        request = DataRequest(connection="unknown", query=SQLQuery(sql="SELECT 1"))
        result = await gateway.run(request, connection_path=tmp_path)

    assert result.status == "error"
    assert "No adapter found" in result.error
