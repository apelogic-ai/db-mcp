"""EndpointQuery params/method/max_pages must survive create() → execute() roundtrip."""

from unittest.mock import MagicMock, patch

import pytest
from db_mcp_models.gateway import DataRequest, EndpointQuery

import db_mcp_data.gateway as gateway


def _api_connector(rows=None):
    from db_mcp_data.connectors.api import APIConnector
    c = MagicMock(spec=APIConnector)
    r = rows or [{"id": 1}]
    c.query_endpoint.return_value = {"data": r, "rows_returned": len(r)}
    return c


@pytest.mark.asyncio
async def test_create_preserves_endpoint_params(tmp_path):
    """ValidatedQuery must record the full EndpointQuery, not just endpoint name."""
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(
            endpoint="dashboards",
            params={"status": "active", "limit": 10},
            method="POST",
            max_pages=3,
        ),
    )
    vq = await gateway.create(request, connection_path=tmp_path)

    assert vq.endpoint == "dashboards"
    # The full original request must be preserved on ValidatedQuery
    original_query = vq.request.query
    assert isinstance(original_query, EndpointQuery)
    assert original_query.params == {"status": "active", "limit": 10}
    assert original_query.method == "POST"
    assert original_query.max_pages == 3


@pytest.mark.asyncio
async def test_execute_reconstructs_full_endpoint_query(tmp_path):
    """execute() must call adapter with the original params/method/max_pages."""
    connector = _api_connector()
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(
            endpoint="reports",
            params={"date": "2026-01-01"},
            method="GET",
            max_pages=2,
        ),
    )
    vq = await gateway.create(request, connection_path=tmp_path)

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        await gateway.execute(vq.query_id, connection_path=tmp_path)

    # Verify query_endpoint was called with the correct params
    connector.query_endpoint.assert_called_once_with(
        "reports",
        params={"date": "2026-01-01"},
        max_pages=2,
        method_override=None,  # GET is the default, no override needed
    )


@pytest.mark.asyncio
async def test_execute_reconstructs_non_default_method(tmp_path):
    """method_override must be passed when method is not GET."""
    connector = _api_connector()
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(endpoint="submit", method="POST", params={"key": "val"}),
    )
    vq = await gateway.create(request, connection_path=tmp_path)

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        await gateway.execute(vq.query_id, connection_path=tmp_path)

    connector.query_endpoint.assert_called_once_with(
        "submit",
        params={"key": "val"},
        max_pages=1,
        method_override="POST",
    )


@pytest.mark.asyncio
async def test_run_preserves_endpoint_params_end_to_end(tmp_path):
    """gateway.run() must pass through the full EndpointQuery unchanged."""
    connector = _api_connector(rows=[{"dashboard": "revenue"}])
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(
            endpoint="dashboards",
            params={"filter": "active"},
            max_pages=5,
        ),
    )

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = await gateway.run(request, connection_path=tmp_path)

    assert result.is_success
    connector.query_endpoint.assert_called_once_with(
        "dashboards",
        params={"filter": "active"},
        max_pages=5,
        method_override=None,
    )
