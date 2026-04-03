"""Tests for gateway.create() — validate and persist a DataRequest."""


import pytest
from db_mcp_models.gateway import DataRequest, EndpointQuery, SQLQuery, ValidatedQuery

import db_mcp_data.gateway as gateway

# ---------------------------------------------------------------------------
# ValidatedQuery type (models)
# ---------------------------------------------------------------------------

class TestValidatedQuery:
    def test_construction(self):
        from datetime import UTC, datetime
        vq = ValidatedQuery(
            query_id="q-abc",
            connection="prod",
            query_type="sql",
            request=DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1")),
            cost_tier="unknown",
            validated_at=datetime.now(UTC),
        )
        assert vq.query_id == "q-abc"
        assert vq.query_type == "sql"
        assert vq.sql == "SELECT 1"
        assert vq.endpoint is None

    def test_endpoint_query_type(self):
        from datetime import UTC, datetime
        vq = ValidatedQuery(
            query_id="q-ep",
            connection="metabase",
            query_type="endpoint",
            request=DataRequest(connection="metabase", query=EndpointQuery(endpoint="dashboards")),
            cost_tier="unknown",
            validated_at=datetime.now(UTC),
        )
        assert vq.query_type == "endpoint"
        assert vq.endpoint == "dashboards"
        assert vq.sql is None

    def test_frozen(self):
        from datetime import UTC, datetime
        vq = ValidatedQuery(
            query_id="q-abc",
            connection="prod",
            query_type="sql",
            request=DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1")),
            cost_tier="unknown",
            validated_at=datetime.now(UTC),
        )
        with pytest.raises((AttributeError, TypeError)):
            vq.query_id = "other"  # type: ignore[misc]

    def test_exported_from_db_mcp_models(self):
        from db_mcp_models import ValidatedQuery as VQ
        assert VQ is ValidatedQuery


# ---------------------------------------------------------------------------
# gateway.create()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_sql_query_returns_validated_query(tmp_path):
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1 AS n"))
    result = await gateway.create(request, connection_path=tmp_path)

    assert isinstance(result, ValidatedQuery)
    assert result.connection == "prod"
    assert result.query_type == "sql"
    assert result.sql == "SELECT 1 AS n"
    assert result.cost_tier == "unknown"
    assert result.query_id  # non-empty


@pytest.mark.asyncio
async def test_create_endpoint_query_returns_validated_query(tmp_path):
    request = DataRequest(
        connection="metabase",
        query=EndpointQuery(endpoint="dashboards", params={"status": "active"}),
    )
    result = await gateway.create(request, connection_path=tmp_path)

    assert isinstance(result, ValidatedQuery)
    assert result.query_type == "endpoint"
    assert result.endpoint == "dashboards"
    assert result.sql is None


@pytest.mark.asyncio
async def test_create_stores_query_in_query_store(tmp_path):
    """query_id from create() must be retrievable from QueryStore."""
    from db_mcp_data.execution.query_store import get_query_store

    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 42"))
    vq = await gateway.create(request, connection_path=tmp_path)

    store = get_query_store()
    query = await store.get(vq.query_id)
    assert query is not None
    assert query.connection == "prod"


@pytest.mark.asyncio
async def test_create_two_requests_get_distinct_query_ids(tmp_path):
    r1 = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1"))
    r2 = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 2"))
    vq1 = await gateway.create(r1, connection_path=tmp_path)
    vq2 = await gateway.create(r2, connection_path=tmp_path)
    assert vq1.query_id != vq2.query_id


@pytest.mark.asyncio
async def test_create_validated_at_is_set(tmp_path):
    from datetime import datetime
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1"))
    vq = await gateway.create(request, connection_path=tmp_path)
    assert isinstance(vq.validated_at, datetime)
