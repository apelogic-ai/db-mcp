"""Tests for gateway.introspect() — schema discovery via adapter routing."""

from unittest.mock import MagicMock, patch

import db_mcp_data.gateway as gateway

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sql_connector(*, catalogs=None, schemas=None, tables=None, columns=None):
    from db_mcp_data.connectors.sql import SQLConnector

    c = MagicMock(spec=SQLConnector)
    c.get_catalogs.return_value = catalogs or ["main"]
    c.get_schemas.return_value = schemas or ["public", "analytics"]
    c.get_tables.return_value = tables or [
        {"name": "orders", "schema": "public", "full_name": "public.orders"},
    ]
    c.get_columns.return_value = columns or [
        {"name": "id", "type": "INTEGER"},
        {"name": "total", "type": "NUMERIC"},
    ]
    return c


def _api_connector():
    from db_mcp_data.connectors.api import APIConnector

    c = MagicMock(spec=APIConnector)
    c.get_catalogs.return_value = [None]
    c.get_schemas.return_value = ["public"]
    c.get_tables.return_value = [{"name": "dashboards", "full_name": "dashboards"}]
    c.get_columns.return_value = [{"name": "id", "type": "INTEGER"}]
    return c


def _file_connector():
    from db_mcp_data.connectors.file import FileConnector

    c = MagicMock(spec=FileConnector)
    c.get_catalogs.return_value = [None]
    c.get_schemas.return_value = [None]
    c.get_tables.return_value = [{"name": "events", "full_name": "events"}]
    c.get_columns.return_value = [{"name": "ts", "type": "TIMESTAMP"}]
    return c


# ---------------------------------------------------------------------------
# SQL connector — all four scopes
# ---------------------------------------------------------------------------

def test_introspect_sql_catalogs(tmp_path):
    connector = _sql_connector(catalogs=["prod", "dev"])
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = gateway.introspect("prod", "catalogs", connection_path=tmp_path)
    assert result["catalogs"] == ["prod", "dev"]


def test_introspect_sql_schemas(tmp_path):
    connector = _sql_connector(schemas=["public", "analytics"])
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = gateway.introspect(
            "prod", "schemas", connection_path=tmp_path, catalog="main"
        )
    assert result["schemas"] == ["public", "analytics"]
    connector.get_schemas.assert_called_once_with(catalog="main")


def test_introspect_sql_tables(tmp_path):
    tables = [{"name": "orders", "schema": "public", "full_name": "public.orders"}]
    connector = _sql_connector(tables=tables)
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = gateway.introspect(
            "prod", "tables", connection_path=tmp_path, schema="public"
        )
    assert result["tables"] == tables
    connector.get_tables.assert_called_once_with(schema="public", catalog=None)


def test_introspect_sql_columns(tmp_path):
    cols = [{"name": "id", "type": "INTEGER"}, {"name": "total", "type": "NUMERIC"}]
    connector = _sql_connector(columns=cols)
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = gateway.introspect(
            "prod", "columns", connection_path=tmp_path,
            schema="public", table="orders"
        )
    assert result["columns"] == cols
    connector.get_columns.assert_called_once_with("orders", schema="public", catalog=None)


# ---------------------------------------------------------------------------
# API connector
# ---------------------------------------------------------------------------

def test_introspect_api_tables(tmp_path):
    connector = _api_connector()
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = gateway.introspect("metabase", "tables", connection_path=tmp_path)
    assert result["tables"] == [{"name": "dashboards", "full_name": "dashboards"}]


# ---------------------------------------------------------------------------
# File connector
# ---------------------------------------------------------------------------

def test_introspect_file_tables(tmp_path):
    connector = _file_connector()
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = gateway.introspect("local", "tables", connection_path=tmp_path)
    assert result["tables"] == [{"name": "events", "full_name": "events"}]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_introspect_invalid_scope(tmp_path):
    connector = _sql_connector()
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = gateway.introspect("prod", "indexes", connection_path=tmp_path)
    assert result["status"] == "error"
    assert "indexes" in result["error"]


def test_introspect_columns_missing_table(tmp_path):
    connector = _sql_connector()
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector):
        result = gateway.introspect("prod", "columns", connection_path=tmp_path)
    assert result["status"] == "error"
    assert "table" in result["error"].lower()


def test_introspect_unknown_connector_returns_error(tmp_path):
    with patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=object()):
        result = gateway.introspect("unknown", "tables", connection_path=tmp_path)
    assert result["status"] == "error"
    assert "No adapter found" in result["error"]
