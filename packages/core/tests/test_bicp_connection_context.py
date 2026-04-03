"""Regression tests for BICP active-connection routing."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from bicp_agent import (
    ColumnInfo,
    QueryCost,
    SchemaDescribeParams,
    SchemaInfo,
    SchemaListParams,
    SemanticObjectType,
    TableInfo,
)

from db_mcp.bicp.agent import DBMCPAgent

# Patch target for the module-level get_active_connection_path imported by agent.py
_ACTIVE_PATH_PATCH = "db_mcp.bicp.agent.get_active_connection_path"


def _make_agent() -> DBMCPAgent:
    agent = DBMCPAgent.__new__(DBMCPAgent)
    agent._settings = MagicMock()
    agent._settings.provider_id = "default"
    agent._settings.get_effective_provider_id.return_value = "default"
    agent._settings.get_effective_connection_path.return_value = Path("/tmp/connections/default")
    return agent


def test_detect_dialect_delegates_to_connection_service():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.connection_service.get_connection_dialect",
            return_value="trino",
        ) as mock_get_connection_dialect,
    ):
        assert agent._detect_dialect() == "trino"

    mock_get_connection_dialect.assert_called_once_with(connection_path=active_path)


@pytest.mark.asyncio
async def test_generate_candidates_delegates_semantic_context_load_to_service():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    schema = MagicMock()
    schema.tables = []
    examples = SimpleNamespace(examples=[])

    query = SimpleNamespace(natural_language="show me events")

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.context_service.load_semantic_context",
            return_value=(schema, examples),
        ) as mock_load_context,
    ):
        await agent.generate_candidates(MagicMock(), query)

    mock_load_context.assert_called_once_with("wifimetrics-trino", connection_path=active_path)


@pytest.mark.asyncio
async def test_semantic_search_delegates_semantic_context_load_to_service():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    schema = MagicMock()
    schema.tables = []
    examples = SimpleNamespace(examples=[])

    params = SimpleNamespace(
        query="events",
        object_types={SemanticObjectType.TABLE, SemanticObjectType.METRIC},
        limit=5,
    )

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.context_service.load_semantic_context",
            return_value=(schema, examples),
        ) as mock_load_context,
    ):
        await agent.semantic_search(params)

    mock_load_context.assert_called_once_with("wifimetrics-trino", connection_path=active_path)


@pytest.mark.asyncio
async def test_execute_query_uses_active_connection_for_query_service():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    query = SimpleNamespace(final_sql="SELECT 1")

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.query_service.execute_bicp_query",
            return_value=([{"name": "x", "dataType": "VARCHAR"}], [[1]]),
        ) as mock_execute_bicp_query,
    ):
        await agent.execute_query(MagicMock(), query)

    mock_execute_bicp_query.assert_called_once_with("SELECT 1", connection_path=active_path)


@pytest.mark.asyncio
async def test_execute_query_allows_write_when_connection_policy_enables_it():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    query = SimpleNamespace(final_sql="INSERT INTO events(id) VALUES (1)")

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.query_service.execute_bicp_query",
            return_value=([], []),
        ) as mock_execute_bicp_query,
    ):
        columns, rows = await agent.execute_query(MagicMock(), query)

    assert columns == []
    assert rows == []
    mock_execute_bicp_query.assert_called_once_with(
        "INSERT INTO events(id) VALUES (1)",
        connection_path=active_path,
    )


@pytest.mark.asyncio
async def test_list_schemas_delegates_to_schema_service():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.schema_service.list_schemas_with_counts",
            return_value={
                "schemas": [
                    {"name": "public", "catalog": "chinook", "tableCount": 2},
                    {"name": "sales", "catalog": "chinook", "tableCount": 1},
                ],
                "count": 2,
                "catalog": "chinook",
                "error": None,
            },
        ) as mock_list_schemas,
    ):
        result = await agent.list_schemas(SchemaListParams(catalog="chinook"))

    assert result.schemas == [
        SchemaInfo(catalog="chinook", schema_="public", table_count=2),
        SchemaInfo(catalog="chinook", schema_="sales", table_count=1),
    ]
    mock_list_schemas.assert_called_once_with(active_path, catalog="chinook")


@pytest.mark.asyncio
async def test_describe_schema_delegates_to_schema_service():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")
    schema = SimpleNamespace(
        tables=[
            SimpleNamespace(
                name="events",
                full_name="chinook.public.events",
                description="Event stream",
                columns=[SimpleNamespace(name="event_id", description="Event identifier")],
            )
        ]
    )

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.schema_service.list_tables",
            return_value={
                "tables": [{"name": "events", "full_name": "chinook.public.events"}],
                "count": 1,
                "schema": "public",
                "catalog": "chinook",
                "error": None,
            },
        ) as mock_list_tables,
        patch(
            "db_mcp.bicp.agent.schema_service.describe_table",
            return_value={
                "table_name": "events",
                "schema": "public",
                "catalog": "chinook",
                "full_name": "chinook.public.events",
                "columns": [
                    {
                        "name": "event_id",
                        "type": "INTEGER",
                        "nullable": False,
                        "primary_key": True,
                    }
                ],
                "column_count": 1,
                "error": None,
            },
        ) as mock_describe_table,
        patch(
            "db_mcp.bicp.agent.context_service.load_schema_knowledge", return_value=schema
        ) as mock_load_schema,
    ):
        result = await agent.describe_schema(
            SchemaDescribeParams(schema_="public", catalog="chinook", include_columns=True)
        )

    assert result.tables == [
        TableInfo(
            name="events",
            description="Event stream",
            columns=[
                ColumnInfo(
                    name="event_id",
                    data_type="INTEGER",
                    nullable=False,
                    description="Event identifier",
                    is_primary_key=True,
                )
            ],
        )
    ]
    mock_list_tables.assert_called_once_with(active_path, schema="public", catalog="chinook")
    mock_describe_table.assert_called_once_with(
        table_name="events",
        connection_path=active_path,
        schema="public",
        catalog="chinook",
    )
    mock_load_schema.assert_called_once_with("wifimetrics-trino", connection_path=active_path)


@pytest.mark.asyncio
async def test_generate_candidates_delegates_sql_analysis_to_query_service():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")

    schema = SimpleNamespace(
        tables=[
            SimpleNamespace(
                name="events",
                full_name="chinook.public.events",
                description="Event stream",
                columns=[SimpleNamespace(name="event_id"), SimpleNamespace(name="event_name")],
            )
        ]
    )
    examples = SimpleNamespace(examples=[])
    query = SimpleNamespace(natural_language="show me events")

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.context_service.load_semantic_context",
            return_value=(schema, examples),
        ),
        patch(
            "db_mcp.bicp.agent.query_service.analyze_candidate_sql",
            return_value={
                "warnings": ["Validation warning: uses fallback"],
                "cost": QueryCost(estimated_rows=10, cost_units=5.0),
            },
        ) as mock_analyze_sql,
    ):
        result = await agent.generate_candidates(MagicMock(), query)

    assert result[0].warnings == ["Validation warning: uses fallback"]
    assert result[0].estimated_cost == QueryCost(estimated_rows=10, cost_units=5.0)
    mock_analyze_sql.assert_called_once_with(
        "SELECT event_id, event_name FROM chinook.public.events LIMIT 100",
        connection_path=active_path,
    )


@pytest.mark.asyncio
async def test_execute_query_delegates_to_query_service():
    agent = _make_agent()
    active_path = Path("/tmp/connections/wifimetrics-trino")
    query = SimpleNamespace(final_sql="SELECT 1")

    with (
        patch(_ACTIVE_PATH_PATCH, return_value=active_path),
        patch(
            "db_mcp.bicp.agent.query_service.execute_bicp_query",
            return_value=(
                [{"name": "x", "dataType": "VARCHAR"}],
                [[1]],
            ),
        ) as mock_execute_bicp_query,
    ):
        columns, rows = await agent.execute_query(MagicMock(), query)

    assert columns == [{"name": "x", "dataType": "VARCHAR"}]
    assert rows == [[1]]
    mock_execute_bicp_query.assert_called_once_with(
        "SELECT 1",
        connection_path=active_path,
    )
