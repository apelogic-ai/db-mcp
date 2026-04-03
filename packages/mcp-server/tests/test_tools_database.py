"""Tests for db_mcp_server.tools.database wrapper functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _patch_inject():
    with patch(
        "db_mcp_server.tools.database.inject_protocol", side_effect=lambda x: x
    ) as m:
        yield m


@pytest.mark.asyncio
async def test_list_connections():
    mock_registry = MagicMock()
    mock_registry.list_connections.return_value = [{"name": "test"}]

    with patch(
        "db_mcp_server.tools.database.ConnectionRegistry.get_instance",
        return_value=mock_registry,
    ):
        from db_mcp_server.tools.database import _list_connections

        result = await _list_connections()

    assert result == {"connections": [{"name": "test"}], "count": 1}
    mock_registry.list_connections.assert_called_once()


@pytest.mark.asyncio
async def test_test_connection_success():
    mock_connector = MagicMock()
    mock_connector.test_connection.return_value = {"status": "ok"}

    with (
        patch(
            "db_mcp_server.tools.database._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.database.get_connector",
            return_value=mock_connector,
        ),
    ):
        from db_mcp_server.tools.database import _test_connection

        result = await _test_connection(connection="mydb")

    assert result == {"status": "ok"}
    mock_connector.test_connection.assert_called_once()


@pytest.mark.asyncio
async def test_test_connection_error():
    with (
        patch(
            "db_mcp_server.tools.database._resolve_connection_path",
            side_effect=RuntimeError("no such connection"),
        ),
    ):
        from db_mcp_server.tools.database import _test_connection

        with pytest.raises(RuntimeError, match="no such connection"):
            await _test_connection(connection="bad")


@pytest.mark.asyncio
async def test_list_catalogs(_patch_inject):
    with (
        patch(
            "db_mcp_server.tools.database._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.database.list_catalogs",
            return_value={"catalogs": ["cat1"]},
        ) as mock_lc,
    ):
        from db_mcp_server.tools.database import _list_catalogs

        result = await _list_catalogs(connection="mydb")

    assert result == {"catalogs": ["cat1"]}
    mock_lc.assert_called_once_with(connection_path="/tmp/conn")


@pytest.mark.asyncio
async def test_sample_table(_patch_inject):
    with (
        patch(
            "db_mcp_server.tools.database._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.database.sample_table",
            return_value={"rows": []},
        ) as mock_st,
    ):
        from db_mcp_server.tools.database import _sample_table

        result = await _sample_table(
            table_name="users", connection="mydb", limit=10
        )

    assert result == {"rows": []}
    mock_st.assert_called_once_with(
        table_name="users",
        connection_path="/tmp/conn",
        schema=None,
        catalog=None,
        limit=10,
    )


@pytest.mark.asyncio
async def test_sample_table_clamps_limit(_patch_inject):
    with (
        patch(
            "db_mcp_server.tools.database._resolve_connection_path",
            return_value="/tmp/conn",
        ),
        patch(
            "db_mcp_server.tools.database.sample_table",
            return_value={"rows": []},
        ) as mock_st,
    ):
        from db_mcp_server.tools.database import _sample_table

        await _sample_table(table_name="t", connection="c", limit=999)

    mock_st.assert_called_once_with(
        table_name="t",
        connection_path="/tmp/conn",
        schema=None,
        catalog=None,
        limit=100,
    )
