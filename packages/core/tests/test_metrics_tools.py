"""Tests for metrics MCP tools."""

import pytest

from db_mcp.tools.metrics import (
    _metrics_add,
    _metrics_approve,
    _metrics_discover,
    _metrics_list,
    _metrics_remove,
)


@pytest.fixture
def conn_path(tmp_path, monkeypatch):
    """Set up a temporary connection directory and patch config."""
    conn = tmp_path / "test-conn"
    conn.mkdir()
    (conn / "metrics").mkdir()
    (conn / "training" / "examples").mkdir(parents=True)
    (conn / "instructions").mkdir()
    (conn / "schema").mkdir()

    monkeypatch.setenv("CONNECTION_PATH", str(conn))
    monkeypatch.setenv("CONNECTION_NAME", "test-conn")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

    # Patch get_provider_dir in the store module (it caches the import)
    monkeypatch.setattr("db_mcp.metrics.store.get_provider_dir", lambda provider_id=None: conn)
    monkeypatch.setattr("db_mcp.onboarding.state.get_provider_dir", lambda provider_id=None: conn)
    monkeypatch.setattr("db_mcp.onboarding.state.get_connection_path", lambda: conn)
    # Patch the imported reference in the tools module
    monkeypatch.setattr("db_mcp.tools.metrics.get_connection_path", lambda: conn)

    return conn


class TestMetricsList:
    @pytest.mark.asyncio
    async def test_empty_catalog(self, conn_path):
        result = await _metrics_list()
        assert result["metrics"] == []
        assert result["dimensions"] == []
        assert "0 metric(s)" in result["summary"]
        assert "guidance" in result

    @pytest.mark.asyncio
    async def test_after_adding_metric(self, conn_path):
        await _metrics_add(
            type="metric",
            name="dau",
            description="Daily active users",
            sql="SELECT COUNT(DISTINCT user_id) FROM sessions",
        )
        result = await _metrics_list()
        assert len(result["metrics"]) == 1
        assert result["metrics"][0]["name"] == "dau"
        assert "1 metric(s)" in result["summary"]

    @pytest.mark.asyncio
    async def test_after_adding_dimension(self, conn_path):
        await _metrics_add(
            type="dimension",
            name="carrier",
            column="cdr.carrier",
            description="Mobile carrier",
        )
        result = await _metrics_list()
        assert len(result["dimensions"]) == 1
        assert result["dimensions"][0]["name"] == "carrier"
        assert result["dimensions"][0]["type"] == "categorical"


class TestMetricsAdd:
    @pytest.mark.asyncio
    async def test_add_metric(self, conn_path):
        result = await _metrics_add(
            type="metric",
            name="revenue",
            description="Total revenue",
            sql="SELECT SUM(amount) FROM orders",
            tables=["orders"],
            tags=["finance"],
        )
        assert result["added"] is True

    @pytest.mark.asyncio
    async def test_add_metric_missing_sql(self, conn_path):
        result = await _metrics_add(
            type="metric",
            name="bad",
            description="",
            sql="",
        )
        assert result.get("added") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_dimension(self, conn_path):
        result = await _metrics_add(
            type="dimension",
            name="region",
            column="users.region",
            dim_type="geographic",
        )
        assert result["added"] is True

    @pytest.mark.asyncio
    async def test_add_dimension_missing_column(self, conn_path):
        result = await _metrics_add(
            type="dimension",
            name="bad",
            column="",
        )
        assert result.get("added") is False

    @pytest.mark.asyncio
    async def test_add_invalid_type(self, conn_path):
        result = await _metrics_add(type="widget", name="x")
        assert result.get("added") is False
        assert "Invalid type" in result["error"]


class TestMetricsApprove:
    @pytest.mark.asyncio
    async def test_approve_metric(self, conn_path):
        result = await _metrics_approve(
            type="metric",
            name="count_sessions",
            description="Count all sessions",
            sql="SELECT COUNT(*) FROM sessions",
        )
        assert result["approved"] is True
        assert result["type"] == "metric"
        assert result["name"] == "count_sessions"

        # Verify it shows up in the catalog
        catalog = await _metrics_list()
        assert len(catalog["metrics"]) == 1

    @pytest.mark.asyncio
    async def test_approve_dimension(self, conn_path):
        result = await _metrics_approve(
            type="dimension",
            name="city",
            column="events.city",
            dim_type="geographic",
        )
        assert result["approved"] is True
        assert result["type"] == "dimension"

        catalog = await _metrics_list()
        assert len(catalog["dimensions"]) == 1


class TestMetricsRemove:
    @pytest.mark.asyncio
    async def test_remove_metric(self, conn_path):
        await _metrics_add(
            type="metric",
            name="to_delete",
            description="temp",
            sql="SELECT 1",
        )
        result = await _metrics_remove(type="metric", name="to_delete")
        assert result["removed"] is True

        catalog = await _metrics_list()
        assert len(catalog["metrics"]) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, conn_path):
        result = await _metrics_remove(type="metric", name="nope")
        assert result["removed"] is False

    @pytest.mark.asyncio
    async def test_remove_dimension(self, conn_path):
        await _metrics_add(
            type="dimension",
            name="to_delete",
            column="t.col",
        )
        result = await _metrics_remove(type="dimension", name="to_delete")
        assert result["removed"] is True

    @pytest.mark.asyncio
    async def test_remove_invalid_type(self, conn_path):
        result = await _metrics_remove(type="widget", name="x")
        assert result["removed"] is False


class TestMetricsDiscover:
    @pytest.mark.asyncio
    async def test_discover_empty_vault(self, conn_path):
        result = await _metrics_discover()
        assert result["metric_candidates"] == []
        assert result["dimension_candidates_by_category"] == {}
        assert "0 metric" in result["summary"]
        assert "guidance" in result

    @pytest.mark.asyncio
    async def test_discover_with_examples(self, conn_path):
        import yaml

        example = {
            "natural_language": "Count users by city",
            "sql": "SELECT COUNT(*) FROM users GROUP BY city",
        }
        with open(conn_path / "training" / "examples" / "ex1.yaml", "w") as f:
            yaml.dump(example, f)

        result = await _metrics_discover()
        assert len(result["metric_candidates"]) >= 1
        assert result["metric_candidates"][0]["name"] == "count_records"

        # Dimension candidates grouped by category
        categories = result["dimension_candidates_by_category"]
        assert "Location" in categories
        assert categories["Location"][0]["name"] == "city"

    @pytest.mark.asyncio
    async def test_discover_summary(self, conn_path):
        import yaml

        example = {
            "natural_language": "Revenue by month",
            "sql": "SELECT SUM(amount) FROM orders GROUP BY month",
        }
        with open(conn_path / "training" / "examples" / "ex1.yaml", "w") as f:
            yaml.dump(example, f)

        result = await _metrics_discover()
        assert "metric candidate" in result["summary"]
        assert "dimension candidate" in result["summary"]
        assert "categor" in result["summary"]
