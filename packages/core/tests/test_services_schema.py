"""Tests for schema services."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_list_catalogs_filters_none_and_reports_count(monkeypatch):
    from db_mcp_data.connectors.sql import SQLConnector

    from db_mcp.services.schema import list_catalogs

    fake_connector = MagicMock(spec=SQLConnector)
    fake_connector.get_catalogs.return_value = [None, "analytics", "warehouse"]

    monkeypatch.setattr("db_mcp_data.gateway.dispatcher.get_connector",
                        lambda *, connection_path: fake_connector)

    result = list_catalogs(connection_path=Path("/tmp/analytics"))

    assert result == {
        "success": True,
        "catalogs": ["analytics", "warehouse"],
        "count": 2,
        "has_catalogs": True,
        "error": None,
    }


def test_list_schemas_filters_none_and_preserves_catalog(monkeypatch):
    from db_mcp_data.connectors.sql import SQLConnector

    from db_mcp.services.schema import list_schemas

    fake_connector = MagicMock(spec=SQLConnector)
    fake_connector.get_schemas.return_value = [None, "public", "sales"]

    monkeypatch.setattr("db_mcp_data.gateway.dispatcher.get_connector",
                        lambda *, connection_path: fake_connector)

    result = list_schemas(connection_path=Path("/tmp/analytics"), catalog="warehouse")

    assert result == {
        "schemas": ["public", "sales"],
        "count": 2,
        "catalog": "warehouse",
        "error": None,
    }


def test_list_schemas_with_counts_adds_table_counts(monkeypatch):
    from db_mcp_data.connectors.sql import SQLConnector

    from db_mcp.services.schema import list_schemas_with_counts

    connector = MagicMock(spec=SQLConnector)
    connector.get_schemas.return_value = [None, "public", "sales"]
    connector.get_tables.side_effect = [
        [{"name": "events"}, {"name": "users"}],  # public
        [{"name": "orders"}],                       # sales
    ]

    monkeypatch.setattr("db_mcp_data.gateway.dispatcher.get_connector",
                        lambda *, connection_path: connector)

    result = list_schemas_with_counts(
        connection_path=Path("/tmp/analytics"),
        catalog="warehouse",
    )

    assert result == {
        "success": True,
        "schemas": [
            {"name": "public", "catalog": "warehouse", "tableCount": 2},
            {"name": "sales", "catalog": "warehouse", "tableCount": 1},
        ],
        "count": 2,
        "catalog": "warehouse",
        "error": None,
    }


def test_list_schemas_with_counts_lists_all_catalogs_when_catalog_not_provided(monkeypatch):
    from db_mcp_data.connectors.sql import SQLConnector

    from db_mcp.services.schema import list_schemas_with_counts

    connector = MagicMock(spec=SQLConnector)
    connector.get_catalogs.return_value = ["warehouse", "analytics"]
    connector.get_schemas.side_effect = [
        ["public", "sales"],  # warehouse
        ["events"],           # analytics
    ]
    connector.get_tables.side_effect = [
        [{"name": "a"}, {"name": "b"}],  # warehouse.public
        [{"name": "c"}],                 # warehouse.sales
        [{"name": "c"}],                 # analytics.events
    ]

    monkeypatch.setattr(
        "db_mcp_data.gateway.dispatcher.get_connector",
        lambda *, connection_path: connector,
    )

    result = list_schemas_with_counts(connection_path=Path("/tmp/analytics"))

    assert result == {
        "success": True,
        "schemas": [
            {"name": "public", "catalog": "warehouse", "tableCount": 2},
            {"name": "sales", "catalog": "warehouse", "tableCount": 1},
            {"name": "events", "catalog": "analytics", "tableCount": 1},
        ],
        "count": 3,
        "catalog": None,
        "error": None,
    }


def test_list_tables_preserves_table_payload_and_context(monkeypatch):
    from db_mcp_data.connectors.sql import SQLConnector

    from db_mcp.services.schema import list_tables

    tables = [
        {"name": "orders", "type": "table"},
        {"name": "customers", "type": "view"},
    ]
    fake_connector = MagicMock(spec=SQLConnector)
    fake_connector.get_tables.return_value = tables

    monkeypatch.setattr("db_mcp_data.gateway.dispatcher.get_connector",
                        lambda *, connection_path: fake_connector)

    result = list_tables(
        connection_path=Path("/tmp/analytics"),
        schema="public",
        catalog="warehouse",
    )

    assert result == {
        "tables": tables,
        "count": 2,
        "schema": "public",
        "catalog": "warehouse",
        "error": None,
    }


def test_describe_table_returns_columns_and_full_name(monkeypatch):
    from db_mcp_data.connectors.sql import SQLConnector

    from db_mcp.services.schema import describe_table

    columns = [
        {"name": "id", "type": "integer"},
        {"name": "total", "type": "numeric"},
    ]
    fake_connector = MagicMock(spec=SQLConnector)
    fake_connector.get_columns.return_value = columns

    monkeypatch.setattr("db_mcp_data.gateway.dispatcher.get_connector",
                        lambda *, connection_path: fake_connector)

    result = describe_table(
        table_name="orders",
        connection_path=Path("/tmp/analytics"),
        schema="public",
        catalog="warehouse",
    )

    assert result == {
        "table_name": "orders",
        "schema": "public",
        "catalog": "warehouse",
        "full_name": "warehouse.public.orders",
        "columns": columns,
        "column_count": 2,
        "error": None,
    }


def test_sample_table_clamps_limit_and_returns_rows(monkeypatch):
    from db_mcp.services.schema import sample_table

    rows = [
        {"id": 1, "total": 100},
        {"id": 2, "total": 150},
    ]
    captured = {}

    def fake_get_table_sample(table_name, schema=None, catalog=None, limit=None):
        captured["args"] = {
            "table_name": table_name,
            "schema": schema,
            "catalog": catalog,
            "limit": limit,
        }
        return rows

    fake_connector = SimpleNamespace(get_table_sample=fake_get_table_sample)

    # sample_table still uses get_connector directly (not gateway scope)
    monkeypatch.setattr("db_mcp.services.schema.get_connector",
                        lambda *, connection_path: fake_connector)

    result = sample_table(
        table_name="orders",
        connection_path=Path("/tmp/analytics"),
        schema="public",
        catalog="warehouse",
        limit=500,
    )

    assert captured["args"] == {
        "table_name": "orders",
        "schema": "public",
        "catalog": "warehouse",
        "limit": 100,
    }
    assert result == {
        "table_name": "orders",
        "schema": "public",
        "catalog": "warehouse",
        "full_name": "warehouse.public.orders",
        "rows": rows,
        "row_count": 2,
        "limit": 100,
        "error": None,
    }


def test_list_catalogs_returns_success_false_on_gateway_error(monkeypatch):
    from db_mcp_data.connectors.sql import SQLConnector

    from db_mcp.services.schema import list_catalogs

    fake_connector = MagicMock(spec=SQLConnector)
    fake_connector.get_catalogs.side_effect = RuntimeError("connection refused")

    monkeypatch.setattr("db_mcp_data.gateway.dispatcher.get_connector",
                        lambda *, connection_path: fake_connector)

    result = list_catalogs(connection_path=Path("/tmp/analytics"))

    assert result["success"] is False
    assert result["error"] is not None
    assert result["catalogs"] == []


def test_list_schemas_with_counts_returns_success_false_on_exception(monkeypatch):
    from db_mcp.services.schema import list_schemas_with_counts

    monkeypatch.setattr(
        "db_mcp.services.schema.gateway_introspect",
        lambda *a, **kw: {"status": "error", "error": "timeout"},
    )

    result = list_schemas_with_counts(connection_path=Path("/tmp/analytics"))

    assert result["success"] is False
    assert result["error"] is not None


def test_validate_link_returns_success_true_for_valid_link(monkeypatch):
    from db_mcp_data.connectors.sql import SQLConnector

    from db_mcp.services.schema import validate_link

    fake_connector = MagicMock(spec=SQLConnector)
    fake_connector.get_tables.return_value = [{"name": "orders"}]

    monkeypatch.setattr("db_mcp_data.gateway.dispatcher.get_connector",
                        lambda *, connection_path: fake_connector)

    result = validate_link("db://prod/public/orders", connection_path=Path("/tmp/myconn"))

    assert result["success"] is True
    assert result["valid"] is True
    assert result["error"] is None


def test_validate_link_returns_success_true_for_invalid_prefix():
    from db_mcp.services.schema import validate_link

    result = validate_link("http://not-db", connection_path=Path("/tmp/myconn"))

    assert result["success"] is True
    assert result["valid"] is False
    assert result["error"] is not None
