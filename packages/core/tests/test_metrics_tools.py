"""Tests for metrics MCP tools."""

from unittest.mock import MagicMock

import pytest
import yaml

from db_mcp.tools.metrics import (
    _metrics_add,
    _metrics_approve,
    _metrics_bindings_list,
    _metrics_bindings_set,
    _metrics_bindings_validate,
    _metrics_discover,
    _metrics_list,
    _metrics_remove,
)

CONNECTION = "test-conn"


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

    monkeypatch.setattr(
        "db_mcp_knowledge.onboarding.state.get_provider_dir", lambda provider_id: conn
    )
    # tools module now uses resolve_connection for path resolution
    monkeypatch.setattr(
        "db_mcp.tools.metrics.resolve_connection",
        lambda connection: (MagicMock(), CONNECTION, conn),
    )

    return conn


class TestMetricsList:
    @pytest.mark.asyncio
    async def test_empty_catalog(self, conn_path):
        result = await _metrics_list(connection=CONNECTION)
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
            connection=CONNECTION,
        )
        result = await _metrics_list(connection=CONNECTION)
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
            connection=CONNECTION,
        )
        result = await _metrics_list(connection=CONNECTION)
        assert len(result["dimensions"]) == 1
        assert result["dimensions"][0]["name"] == "carrier"
        assert result["dimensions"][0]["type"] == "categorical"

    @pytest.mark.asyncio
    async def test_metrics_list_surfaces_binding_coverage(self, conn_path):
        await _metrics_add(
            type="metric",
            name="dau",
            description="Daily active users",
            sql="SELECT COUNT(DISTINCT user_id) FROM sessions",
            connection=CONNECTION,
        )
        bindings_path = conn_path / "metrics" / "bindings.yaml"
        bindings_path.write_text(
            yaml.safe_dump(
                {
                    "version": "1.0.0",
                    "provider_id": CONNECTION,
                    "bindings": {
                        "dau": {
                            "sql": (
                                "SELECT COUNT(DISTINCT session_user_id) "
                                "AS dau FROM session_facts"
                            ),
                            "tables": ["session_facts"],
                        }
                    },
                },
                sort_keys=False,
            )
        )

        result = await _metrics_list(connection=CONNECTION)

        assert result["metrics"][0]["name"] == "dau"
        assert result["metrics"][0]["has_binding"] is True
        assert result["metrics"][0]["binding_dimensions"] == []


class TestMetricBindings:
    @pytest.mark.asyncio
    async def test_bindings_list_empty(self, conn_path):
        result = await _metrics_bindings_list(connection=CONNECTION)
        assert result["bindings"] == []
        assert "0 binding(s)" in result["summary"]

    @pytest.mark.asyncio
    async def test_bindings_set_and_list(self, conn_path):
        await _metrics_add(
            type="metric",
            name="revenue",
            description="Total revenue",
            sql="",
            dimensions=["region"],
            connection=CONNECTION,
        )
        await _metrics_add(
            type="dimension",
            name="region",
            column="orders.region",
            connection=CONNECTION,
        )

        result = await _metrics_bindings_set(
            connection=CONNECTION,
            metric_name="revenue",
            sql="SELECT SUM(amount) AS revenue FROM orders",
            tables=["orders"],
            dimensions=[
                {
                    "dimension_name": "region",
                    "projection_sql": "orders.region",
                    "group_by_sql": "orders.region",
                    "tables": ["orders"],
                }
            ],
        )

        assert result["saved"] is True
        assert result["binding"]["metric_name"] == "revenue"
        assert result["validation"]["valid"] is True

        listed = await _metrics_bindings_list(connection=CONNECTION)
        assert listed["bindings"][0]["metric_name"] == "revenue"
        assert listed["bindings"][0]["dimensions"][0]["dimension_name"] == "region"

    @pytest.mark.asyncio
    async def test_bindings_validate_reports_unknown_metric(self, conn_path):
        result = await _metrics_bindings_validate(
            connection=CONNECTION,
            metric_name="missing_metric",
            sql="SELECT 1",
        )

        assert result["valid"] is False
        assert "not found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_bindings_set_rejects_unknown_dimension(self, conn_path):
        await _metrics_add(
            type="metric",
            name="revenue",
            description="Total revenue",
            sql="",
            dimensions=["region"],
            connection=CONNECTION,
        )

        result = await _metrics_bindings_set(
            connection=CONNECTION,
            metric_name="revenue",
            sql="SELECT SUM(amount) AS revenue FROM orders",
            tables=["orders"],
            dimensions=[
                {
                    "dimension_name": "missing_dimension",
                    "projection_sql": "orders.region",
                }
            ],
        )

        assert result["saved"] is False
        assert result["validation"]["valid"] is False


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
            connection=CONNECTION,
        )
        assert result["added"] is True

    @pytest.mark.asyncio
    async def test_add_metric_missing_sql(self, conn_path):
        result = await _metrics_add(
            type="metric",
            name="bad",
            description="",
            sql="",
            connection=CONNECTION,
        )
        assert result.get("added") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_metric_allows_logical_definition_without_sql(self, conn_path):
        result = await _metrics_add(
            type="metric",
            name="logical_revenue",
            description="Total revenue",
            sql="",
            connection=CONNECTION,
        )
        assert result["added"] is True

    @pytest.mark.asyncio
    async def test_add_dimension(self, conn_path):
        result = await _metrics_add(
            type="dimension",
            name="region",
            column="users.region",
            dim_type="geographic",
            connection=CONNECTION,
        )
        assert result["added"] is True

    @pytest.mark.asyncio
    async def test_add_dimension_missing_column(self, conn_path):
        result = await _metrics_add(
            type="dimension",
            name="bad",
            column="",
            connection=CONNECTION,
        )
        assert result.get("added") is False

    @pytest.mark.asyncio
    async def test_add_invalid_type(self, conn_path):
        result = await _metrics_add(type="widget", name="x", connection=CONNECTION)
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
            connection=CONNECTION,
        )
        assert result["approved"] is True
        assert result["type"] == "metric"
        assert result["name"] == "count_sessions"

        # Verify it shows up in the catalog
        catalog = await _metrics_list(connection=CONNECTION)
        assert len(catalog["metrics"]) == 1

    @pytest.mark.asyncio
    async def test_approve_dimension(self, conn_path):
        result = await _metrics_approve(
            type="dimension",
            name="city",
            column="events.city",
            dim_type="geographic",
            connection=CONNECTION,
        )
        assert result["approved"] is True
        assert result["type"] == "dimension"

        catalog = await _metrics_list(connection=CONNECTION)
        assert len(catalog["dimensions"]) == 1


class TestMetricsRemove:
    @pytest.mark.asyncio
    async def test_remove_metric(self, conn_path):
        await _metrics_add(
            type="metric",
            name="to_delete",
            description="temp",
            sql="SELECT 1",
            connection=CONNECTION,
        )
        result = await _metrics_remove(type="metric", name="to_delete", connection=CONNECTION)
        assert result["removed"] is True

        catalog = await _metrics_list(connection=CONNECTION)
        assert len(catalog["metrics"]) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, conn_path):
        result = await _metrics_remove(type="metric", name="nope", connection=CONNECTION)
        assert result["removed"] is False

    @pytest.mark.asyncio
    async def test_remove_dimension(self, conn_path):
        await _metrics_add(
            type="dimension",
            name="to_delete",
            column="t.col",
            connection=CONNECTION,
        )
        result = await _metrics_remove(type="dimension", name="to_delete", connection=CONNECTION)
        assert result["removed"] is True

    @pytest.mark.asyncio
    async def test_remove_invalid_type(self, conn_path):
        result = await _metrics_remove(type="widget", name="x", connection=CONNECTION)
        assert result["removed"] is False


class TestMetricsDiscover:
    @pytest.mark.asyncio
    async def test_discover_empty_vault(self, conn_path):
        result = await _metrics_discover(connection=CONNECTION)
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

        result = await _metrics_discover(connection=CONNECTION)
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

        result = await _metrics_discover(connection=CONNECTION)
        assert "metric candidate" in result["summary"]
        assert "dimension candidate" in result["summary"]
        assert "categor" in result["summary"]
