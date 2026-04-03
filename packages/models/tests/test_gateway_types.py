"""Tests for gateway DataRequest / RunOptions types."""

import pytest
from db_mcp_models.gateway import DataRequest, EndpointQuery, RunOptions, SQLQuery


class TestSQLQuery:
    def test_construction(self):
        q = SQLQuery(sql="SELECT 1")
        assert q.sql == "SELECT 1"
        assert q.params == {}

    def test_construction_with_params(self):
        q = SQLQuery(sql="SELECT * FROM t WHERE id = :id", params={"id": 42})
        assert q.params == {"id": 42}

    def test_frozen(self):
        q = SQLQuery(sql="SELECT 1")
        with pytest.raises((AttributeError, TypeError)):
            q.sql = "SELECT 2"  # type: ignore[misc]


class TestEndpointQuery:
    def test_construction(self):
        q = EndpointQuery(endpoint="dashboards")
        assert q.endpoint == "dashboards"
        assert q.params == {}
        assert q.method == "GET"
        assert q.max_pages == 1

    def test_construction_with_overrides(self):
        q = EndpointQuery(
            endpoint="reports", method="POST",
            params={"status": "active"}, max_pages=3,
        )
        assert q.method == "POST"
        assert q.max_pages == 3

    def test_frozen(self):
        q = EndpointQuery(endpoint="dashboards")
        with pytest.raises((AttributeError, TypeError)):
            q.endpoint = "other"  # type: ignore[misc]


class TestDataRequest:
    def test_with_sql_query(self):
        r = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1"))
        assert r.connection == "prod"
        assert isinstance(r.query, SQLQuery)

    def test_with_endpoint_query(self):
        r = DataRequest(connection="metabase", query=EndpointQuery(endpoint="dashboards"))
        assert isinstance(r.query, EndpointQuery)

    def test_frozen(self):
        r = DataRequest(connection="prod", query=SQLQuery(sql="SELECT 1"))
        with pytest.raises((AttributeError, TypeError)):
            r.connection = "staging"  # type: ignore[misc]


class TestRunOptions:
    def test_defaults(self):
        opts = RunOptions()
        assert opts.confirmed is False
        assert opts.timeout_seconds is None

    def test_confirmed_override(self):
        opts = RunOptions(confirmed=True)
        assert opts.confirmed is True

    def test_frozen(self):
        opts = RunOptions()
        with pytest.raises((AttributeError, TypeError)):
            opts.confirmed = True  # type: ignore[misc]
