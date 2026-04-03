"""RunOptions must affect gateway.execute() behaviour, not be silently ignored."""

from unittest.mock import MagicMock, patch

import pytest
from db_mcp_models.gateway import DataRequest, RunOptions, SQLQuery

import db_mcp_data.gateway as gateway


def _sql_connector(rows=None):
    from db_mcp_data.connectors.sql import SQLConnector
    c = MagicMock(spec=SQLConnector)
    c.execute_sql.return_value = rows or [{"n": 1}]
    return c


async def _create_with_cost_tier(tmp_path, sql: str, cost_tier: str) -> str:
    """Helper: create a validated query then manually set its cost_tier in the store."""
    from db_mcp_data.execution.query_store import get_query_store

    request = DataRequest(connection="prod", query=SQLQuery(sql=sql))
    vq = await gateway.create(request, connection_path=tmp_path)

    # Override cost_tier in the store so we can test the gate
    store = get_query_store()
    async with store._lock:
        query = store._queries.get(vq.query_id)
        if query:
            query.cost_tier = cost_tier

    return vq.query_id


# ---------------------------------------------------------------------------
# cost_tier="reject" without confirmed → must be blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_blocks_reject_tier_by_default(tmp_path):
    query_id = await _create_with_cost_tier(tmp_path, "DROP TABLE x", "reject")
    connector = _sql_connector()

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = await gateway.execute(query_id, connection_path=tmp_path)

    assert result.status == "error"
    assert "reject" in result.error.lower()
    connector.execute_sql.assert_not_called()


@pytest.mark.asyncio
async def test_execute_blocks_reject_tier_with_confirmed_false(tmp_path):
    query_id = await _create_with_cost_tier(tmp_path, "DROP TABLE x", "reject")
    connector = _sql_connector()

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = await gateway.execute(
            query_id, connection_path=tmp_path, options=RunOptions(confirmed=False)
        )

    assert result.status == "error"
    connector.execute_sql.assert_not_called()


# ---------------------------------------------------------------------------
# cost_tier="reject" WITH confirmed=True → must proceed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_allows_reject_tier_when_confirmed(tmp_path):
    query_id = await _create_with_cost_tier(tmp_path, "SELECT 1", "reject")
    connector = _sql_connector(rows=[{"n": 1}])

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = await gateway.execute(
            query_id, connection_path=tmp_path, options=RunOptions(confirmed=True)
        )

    assert result.is_success
    connector.execute_sql.assert_called_once()


# ---------------------------------------------------------------------------
# Other cost tiers proceed without confirmed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", ["low", "auto", "confirm", "unknown"])
@pytest.mark.asyncio
async def test_execute_proceeds_for_non_reject_tiers(tmp_path, tier):
    query_id = await _create_with_cost_tier(tmp_path, "SELECT 1", tier)
    connector = _sql_connector(rows=[{"n": 1}])

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = await gateway.execute(query_id, connection_path=tmp_path)

    assert result.is_success


# ---------------------------------------------------------------------------
# gateway.run() passes options through to execute()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_with_confirmed_true_proceeds(tmp_path):
    """gateway.run() must thread RunOptions down to execute()."""
    connector = _sql_connector(rows=[{"n": 42}])
    request = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 42 AS n"))

    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = await gateway.run(
            request,
            connection_path=tmp_path,
            options=RunOptions(confirmed=True),
        )

    assert result.is_success
    assert result.data == [{"n": 42}]
