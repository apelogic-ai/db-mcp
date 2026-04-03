"""TDD tests for metric binding helpers in services.metrics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from db_mcp_models import MetricBinding, MetricDimensionBinding

from db_mcp.services.metrics import serialize_metric_binding, validate_metric_binding


class TestSerializeMetricBinding:
    """Tests for serialize_metric_binding."""

    def test_basic_binding(self) -> None:
        binding = MetricBinding(
            metric_name="dau",
            sql="COUNT(DISTINCT user_id)",
            tables=["events"],
            dimensions={},
        )
        result = serialize_metric_binding(binding)
        assert result["metric_name"] == "dau"
        assert result["sql"] == "COUNT(DISTINCT user_id)"
        assert result["tables"] == ["events"]
        assert result["dimensions"] == []

    def test_with_dimensions(self) -> None:
        binding = MetricBinding(
            metric_name="revenue",
            sql="SUM(amount)",
            tables=["orders"],
            dimensions={
                "region": MetricDimensionBinding(
                    dimension_name="region",
                    projection_sql="region",
                    filter_sql="region = ?",
                    group_by_sql="region",
                    tables=["orders"],
                ),
                "date": MetricDimensionBinding(
                    dimension_name="date",
                    projection_sql="order_date",
                    tables=["orders"],
                ),
            },
        )
        result = serialize_metric_binding(binding)
        assert len(result["dimensions"]) == 2
        # Sorted by dimension name
        assert result["dimensions"][0]["dimension_name"] == "date"
        assert result["dimensions"][1]["dimension_name"] == "region"
        assert result["dimensions"][1]["filter_sql"] == "region = ?"


class TestValidateMetricBinding:
    """Tests for validate_metric_binding."""

    def _mock_catalogs(
        self,
        *,
        metric_exists: bool = True,
        metric_dimensions: list[str] | None = None,
        dimension_names: list[str] | None = None,
    ):
        """Set up mock metric and dimension catalogs."""
        metric = None
        if metric_exists:
            metric = MagicMock()
            metric.dimensions = metric_dimensions

        metrics_catalog = MagicMock()
        metrics_catalog.get_metric.return_value = metric

        dimensions_catalog = MagicMock()

        def get_dim(name):
            if dimension_names and name in dimension_names:
                return MagicMock()
            return None

        dimensions_catalog.get_dimension.side_effect = get_dim

        return metrics_catalog, dimensions_catalog

    @patch("db_mcp.services.metrics.load_dimensions")
    @patch("db_mcp.services.metrics.load_metrics")
    def test_valid_binding(self, mock_load_metrics, mock_load_dims, tmp_path) -> None:
        mc, dc = self._mock_catalogs()
        mock_load_metrics.return_value = mc
        mock_load_dims.return_value = dc

        result = validate_metric_binding(
            provider_id="conn",
            connection_path=tmp_path,
            metric_name="dau",
            sql="COUNT(DISTINCT user_id)",
        )
        assert result["valid"] is True
        assert result["errors"] == []

    @patch("db_mcp.services.metrics.load_dimensions")
    @patch("db_mcp.services.metrics.load_metrics")
    def test_missing_metric(self, mock_load_metrics, mock_load_dims, tmp_path) -> None:
        mc, dc = self._mock_catalogs(metric_exists=False)
        mock_load_metrics.return_value = mc
        mock_load_dims.return_value = dc

        result = validate_metric_binding(
            provider_id="conn",
            connection_path=tmp_path,
            metric_name="nonexistent",
            sql="COUNT(*)",
        )
        assert result["valid"] is False
        assert any("not found" in e for e in result["errors"])

    @patch("db_mcp.services.metrics.load_dimensions")
    @patch("db_mcp.services.metrics.load_metrics")
    def test_empty_sql(self, mock_load_metrics, mock_load_dims, tmp_path) -> None:
        mc, dc = self._mock_catalogs()
        mock_load_metrics.return_value = mc
        mock_load_dims.return_value = dc

        result = validate_metric_binding(
            provider_id="conn",
            connection_path=tmp_path,
            metric_name="dau",
            sql="   ",
        )
        assert result["valid"] is False
        assert any("SQL is required" in e for e in result["errors"])

    @patch("db_mcp.services.metrics.load_dimensions")
    @patch("db_mcp.services.metrics.load_metrics")
    def test_projection_sql_required(self, mock_load_metrics, mock_load_dims, tmp_path) -> None:
        mc, dc = self._mock_catalogs(dimension_names=["region"])
        mock_load_metrics.return_value = mc
        mock_load_dims.return_value = dc

        result = validate_metric_binding(
            provider_id="conn",
            connection_path=tmp_path,
            metric_name="dau",
            sql="COUNT(*)",
            dimensions=[{"dimension_name": "region"}],
        )
        assert result["valid"] is False
        assert any("projection_sql" in e for e in result["errors"])

    @patch("db_mcp.services.metrics.load_dimensions")
    @patch("db_mcp.services.metrics.load_metrics")
    def test_table_overlap_check(self, mock_load_metrics, mock_load_dims, tmp_path) -> None:
        mc, dc = self._mock_catalogs(dimension_names=["region"])
        mock_load_metrics.return_value = mc
        mock_load_dims.return_value = dc

        result = validate_metric_binding(
            provider_id="conn",
            connection_path=tmp_path,
            metric_name="dau",
            sql="COUNT(*)",
            tables=["events"],
            dimensions=[
                {
                    "dimension_name": "region",
                    "projection_sql": "region",
                    "tables": ["users"],
                }
            ],
        )
        assert result["valid"] is False
        assert any("does not share a table" in e for e in result["errors"])

    @patch("db_mcp.services.metrics.load_dimensions")
    @patch("db_mcp.services.metrics.load_metrics")
    def test_duplicate_dimension(self, mock_load_metrics, mock_load_dims, tmp_path) -> None:
        mc, dc = self._mock_catalogs(dimension_names=["region"])
        mock_load_metrics.return_value = mc
        mock_load_dims.return_value = dc

        result = validate_metric_binding(
            provider_id="conn",
            connection_path=tmp_path,
            metric_name="dau",
            sql="COUNT(*)",
            dimensions=[
                {"dimension_name": "region", "projection_sql": "r"},
                {"dimension_name": "region", "projection_sql": "r"},
            ],
        )
        assert result["valid"] is False
        assert any("Duplicate" in e for e in result["errors"])

    @patch("db_mcp.services.metrics.load_dimensions")
    @patch("db_mcp.services.metrics.load_metrics")
    def test_missing_approved_dimensions_warning(
        self, mock_load_metrics, mock_load_dims, tmp_path
    ) -> None:
        mc, dc = self._mock_catalogs(
            metric_dimensions=["region", "date"],
            dimension_names=["region"],
        )
        mock_load_metrics.return_value = mc
        mock_load_dims.return_value = dc

        result = validate_metric_binding(
            provider_id="conn",
            connection_path=tmp_path,
            metric_name="dau",
            sql="COUNT(*)",
            dimensions=[{"dimension_name": "region", "projection_sql": "region"}],
        )
        assert result["valid"] is True
        assert any("date" in w for w in result["warnings"])
