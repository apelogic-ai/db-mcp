"""list_schemas_with_counts and validate_link must route through gateway.introspect()."""

from unittest.mock import MagicMock, patch


def _sql_connector(catalogs=None, schemas=None, tables=None, columns=None):
    from db_mcp_data.connectors.sql import SQLConnector
    c = MagicMock(spec=SQLConnector)
    c.get_catalogs.return_value = catalogs or ["main"]
    c.get_schemas.return_value = schemas or ["public"]
    c.get_tables.return_value = tables or [{"name": "orders", "full_name": "public.orders"}]
    c.get_columns.return_value = columns or [{"name": "id"}, {"name": "total"}]
    return c


def _patch(connector):
    return patch("db_mcp_data.gateway.dispatcher.get_connector", return_value=connector)


# ---------------------------------------------------------------------------
# list_schemas_with_counts
# ---------------------------------------------------------------------------

def test_list_schemas_with_counts_does_not_call_get_connector_directly(tmp_path):
    """list_schemas_with_counts must not call services/schema.py's get_connector."""
    from db_mcp.services.schema import list_schemas_with_counts

    connector = _sql_connector(
        catalogs=["warehouse"],
        schemas=["public", "analytics"],
        tables=[{"name": "orders"}, {"name": "users"}],
    )

    with _patch(connector):
        result = list_schemas_with_counts(connection_path=tmp_path)

    # Must reach the connector through the gateway
    connector.get_catalogs.assert_called()
    assert result["count"] == 2
    assert result["error"] is None


def test_list_schemas_with_counts_routes_through_gateway(tmp_path):
    """gateway dispatcher must be the resolver, not services.schema.get_connector."""
    from db_mcp.services.schema import list_schemas_with_counts

    connector = _sql_connector(
        catalogs=["prod"],
        schemas=["public"],
        tables=[{"name": "t1"}, {"name": "t2"}, {"name": "t3"}],
    )

    called_direct = []

    def _direct_get_connector(*a, **kw):
        called_direct.append(True)
        return connector

    with (
        _patch(connector),
        patch("db_mcp.services.schema.get_connector", side_effect=_direct_get_connector),
    ):
        result = list_schemas_with_counts(connection_path=tmp_path, catalog="prod")

    assert not called_direct, "services/schema.get_connector was called directly — not via gateway"
    assert result["schemas"][0]["tableCount"] == 3


def test_list_schemas_with_counts_table_count_per_schema(tmp_path):
    from db_mcp.services.schema import list_schemas_with_counts
    connector = _sql_connector(catalogs=[None], schemas=["public", "staging"])
    connector.get_tables.side_effect = [
        [{"name": "a"}, {"name": "b"}],   # public → 2 tables
        [{"name": "c"}],                   # staging → 1 table
    ]

    with _patch(connector):
        result = list_schemas_with_counts(connection_path=tmp_path)

    schemas = result["schemas"]
    assert len(schemas) == 2
    counts = {s["name"]: s["tableCount"] for s in schemas}
    assert counts["public"] == 2
    assert counts["staging"] == 1


# ---------------------------------------------------------------------------
# validate_link
# ---------------------------------------------------------------------------

def test_validate_link_does_not_call_get_connector_directly(tmp_path):
    """validate_link must not call services/schema.py's get_connector."""
    from db_mcp.services.schema import validate_link

    connector = _sql_connector(
        tables=[{"name": "orders", "full_name": "public.orders"}],
        columns=[{"name": "id"}, {"name": "total"}],
    )

    called_direct = []

    def _direct_get_connector(*a, **kw):
        called_direct.append(True)
        return connector

    with (
        _patch(connector),
        patch("db_mcp.services.schema.get_connector", side_effect=_direct_get_connector),
    ):
        result = validate_link("db://main/public/orders", connection_path=tmp_path)

    assert not called_direct, "services/schema.get_connector was called directly — not via gateway"
    assert result["valid"] is True


def test_validate_link_valid_table(tmp_path):
    connector = _sql_connector(
        tables=[{"name": "orders", "full_name": "public.orders"}],
    )
    with _patch(connector):
        from db_mcp.services.schema import validate_link
        result = validate_link("db://main/public/orders", connection_path=tmp_path)
    assert result["valid"] is True
    assert result["parsed"]["table"] == "orders"


def test_validate_link_unknown_table_returns_invalid(tmp_path):
    connector = _sql_connector(tables=[{"name": "orders"}])
    with _patch(connector):
        from db_mcp.services.schema import validate_link
        result = validate_link("db://main/public/missing_table", connection_path=tmp_path)
    assert result["valid"] is False
    assert "missing_table" in result["error"]


def test_validate_link_valid_column(tmp_path):
    connector = _sql_connector(
        tables=[{"name": "orders"}],
        columns=[{"name": "id"}, {"name": "total"}],
    )
    with _patch(connector):
        from db_mcp.services.schema import validate_link
        result = validate_link("db://main/public/orders/total", connection_path=tmp_path)
    assert result["valid"] is True


def test_validate_link_unknown_column_returns_invalid(tmp_path):
    connector = _sql_connector(
        tables=[{"name": "orders"}],
        columns=[{"name": "id"}],
    )
    with _patch(connector):
        from db_mcp.services.schema import validate_link
        result = validate_link("db://main/public/orders/ghost_col", connection_path=tmp_path)
    assert result["valid"] is False
    assert "ghost_col" in result["error"]
