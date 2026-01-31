"""Tests for metrics and dimensions store (CRUD, persistence)."""

import tempfile
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def temp_provider(monkeypatch):
    """Create a temporary connection directory for metrics storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        conn_path = Path(tmpdir) / "connections" / "test-conn"
        conn_path.mkdir(parents=True)

        # Patch _get_connection_dir to use temp directory
        monkeypatch.setattr(
            "db_mcp.metrics.store._get_connection_dir",
            lambda provider_id: conn_path,
        )

        yield "test-conn", conn_path


class TestMetricsCRUD:
    """Tests for metrics catalog CRUD operations."""

    def test_load_empty_catalog(self, temp_provider):
        from db_mcp.metrics.store import load_metrics

        provider_id, _ = temp_provider
        catalog = load_metrics(provider_id)
        assert catalog.count() == 0
        assert catalog.provider_id == provider_id

    def test_add_metric(self, temp_provider):
        from db_mcp.metrics.store import add_metric, load_metrics

        provider_id, conn_path = temp_provider
        result = add_metric(
            provider_id=provider_id,
            name="dau",
            description="Daily active users",
            sql="SELECT COUNT(DISTINCT user_id) FROM sessions",
            display_name="DAU",
            tables=["sessions"],
            tags=["engagement"],
            dimensions=["carrier", "city"],
        )

        assert result["added"] is True
        assert result["metric_name"] == "dau"
        assert result["total_metrics"] == 1

        # Verify persistence
        catalog = load_metrics(provider_id)
        assert catalog.count() == 1
        metric = catalog.get_metric("dau")
        assert metric is not None
        assert metric.description == "Daily active users"
        assert metric.dimensions == ["carrier", "city"]
        assert metric.tags == ["engagement"]

    def test_add_metric_updates_existing(self, temp_provider):
        from db_mcp.metrics.store import add_metric, load_metrics

        provider_id, _ = temp_provider

        add_metric(provider_id=provider_id, name="dau", description="v1", sql="SELECT 1")
        add_metric(provider_id=provider_id, name="dau", description="v2", sql="SELECT 2")

        catalog = load_metrics(provider_id)
        assert catalog.count() == 1
        assert catalog.get_metric("dau").description == "v2"

    def test_delete_metric(self, temp_provider):
        from db_mcp.metrics.store import add_metric, delete_metric, load_metrics

        provider_id, _ = temp_provider

        add_metric(provider_id=provider_id, name="dau", description="test", sql="SELECT 1")
        result = delete_metric(provider_id, "dau")

        assert result["deleted"] is True
        assert load_metrics(provider_id).count() == 0

    def test_delete_nonexistent_metric(self, temp_provider):
        from db_mcp.metrics.store import delete_metric

        provider_id, _ = temp_provider
        result = delete_metric(provider_id, "nonexistent")
        assert result["deleted"] is False

    def test_search_metrics(self, temp_provider):
        from db_mcp.metrics.store import add_metric, search_metrics

        provider_id, _ = temp_provider

        add_metric(
            provider_id=provider_id,
            name="dau",
            description="Daily active users",
            sql="SELECT 1",
            tags=["engagement"],
        )
        add_metric(
            provider_id=provider_id,
            name="revenue",
            description="Total revenue",
            sql="SELECT 2",
            tags=["finance"],
        )

        results = search_metrics(provider_id, "active")
        assert len(results) == 1
        assert results[0].name == "dau"

        results = search_metrics(provider_id, "engagement")
        assert len(results) == 1

    def test_metric_dimensions_field_persisted(self, temp_provider):
        """Verify the dimensions field round-trips through YAML."""
        from db_mcp.metrics.store import add_metric, get_catalog_file_path

        provider_id, _ = temp_provider

        add_metric(
            provider_id=provider_id,
            name="test",
            description="test",
            sql="SELECT 1",
            dimensions=["time", "region"],
        )

        # Read raw YAML
        catalog_file = get_catalog_file_path(provider_id)
        with open(catalog_file) as f:
            data = yaml.safe_load(f)

        assert data["metrics"][0]["dimensions"] == ["time", "region"]


class TestDimensionsCRUD:
    """Tests for dimensions catalog CRUD operations."""

    def test_load_empty_dimensions(self, temp_provider):
        from db_mcp.metrics.store import load_dimensions

        provider_id, _ = temp_provider
        catalog = load_dimensions(provider_id)
        assert catalog.count() == 0
        assert catalog.provider_id == provider_id

    def test_add_dimension(self, temp_provider):
        from db_mcp.metrics.store import add_dimension, load_dimensions

        provider_id, _ = temp_provider
        result = add_dimension(
            provider_id=provider_id,
            name="carrier",
            column="cdr_agg_day.carrier",
            description="Mobile carrier",
            display_name="Carrier",
            dim_type="categorical",
            tables=["cdr_agg_day"],
            values=["tmo", "att"],
            synonyms=["network"],
        )

        assert result["added"] is True
        assert result["dimension_name"] == "carrier"
        assert result["total_dimensions"] == 1

        # Verify persistence
        catalog = load_dimensions(provider_id)
        assert catalog.count() == 1
        dim = catalog.get_dimension("carrier")
        assert dim is not None
        assert dim.description == "Mobile carrier"
        assert dim.type.value == "categorical"
        assert dim.column == "cdr_agg_day.carrier"
        assert dim.values == ["tmo", "att"]
        assert dim.synonyms == ["network"]
        assert dim.created_by == "manual"

    def test_add_dimension_updates_existing(self, temp_provider):
        from db_mcp.metrics.store import add_dimension, load_dimensions

        provider_id, _ = temp_provider

        add_dimension(
            provider_id=provider_id,
            name="carrier",
            column="old.column",
            description="v1",
        )
        add_dimension(
            provider_id=provider_id,
            name="carrier",
            column="new.column",
            description="v2",
        )

        catalog = load_dimensions(provider_id)
        assert catalog.count() == 1
        assert catalog.get_dimension("carrier").column == "new.column"

    def test_delete_dimension(self, temp_provider):
        from db_mcp.metrics.store import add_dimension, delete_dimension, load_dimensions

        provider_id, _ = temp_provider

        add_dimension(
            provider_id=provider_id,
            name="carrier",
            column="t.carrier",
        )
        result = delete_dimension(provider_id, "carrier")

        assert result["deleted"] is True
        assert load_dimensions(provider_id).count() == 0

    def test_delete_nonexistent_dimension(self, temp_provider):
        from db_mcp.metrics.store import delete_dimension

        provider_id, _ = temp_provider
        result = delete_dimension(provider_id, "nonexistent")
        assert result["deleted"] is False

    def test_search_dimensions(self, temp_provider):
        from db_mcp.metrics.store import add_dimension, search_dimensions

        provider_id, _ = temp_provider

        add_dimension(
            provider_id=provider_id,
            name="carrier",
            column="t.carrier",
            description="Mobile carrier",
            synonyms=["network"],
        )
        add_dimension(
            provider_id=provider_id,
            name="city",
            column="t.city",
            description="Geographic city",
        )

        results = search_dimensions(provider_id, "mobile")
        assert len(results) == 1
        assert results[0].name == "carrier"

        # Search by synonym
        results = search_dimensions(provider_id, "network")
        assert len(results) == 1
        assert results[0].name == "carrier"

    def test_dimension_type_persistence(self, temp_provider):
        """Verify dimension types round-trip through YAML."""
        from db_mcp.metrics.store import add_dimension, load_dimensions

        provider_id, _ = temp_provider

        for dim_type in ["temporal", "categorical", "geographic", "entity"]:
            add_dimension(
                provider_id=provider_id,
                name=f"dim_{dim_type}",
                column=f"t.{dim_type}_col",
                dim_type=dim_type,
            )

        catalog = load_dimensions(provider_id)
        assert catalog.count() == 4
        assert catalog.get_dimension("dim_temporal").type.value == "temporal"
        assert catalog.get_dimension("dim_geographic").type.value == "geographic"

    def test_invalid_dimension_type_defaults_to_categorical(self, temp_provider):
        from db_mcp.metrics.store import add_dimension, load_dimensions

        provider_id, _ = temp_provider
        add_dimension(
            provider_id=provider_id,
            name="test",
            column="t.col",
            dim_type="invalid_type",
        )

        catalog = load_dimensions(provider_id)
        assert catalog.get_dimension("test").type.value == "categorical"

    def test_dimensions_yaml_file_created(self, temp_provider):
        """Verify dimensions.yaml is created in the metrics directory."""
        from db_mcp.metrics.store import add_dimension, get_dimensions_file_path

        provider_id, _ = temp_provider
        add_dimension(
            provider_id=provider_id,
            name="carrier",
            column="t.carrier",
        )

        dim_file = get_dimensions_file_path(provider_id)
        assert dim_file.exists()

        with open(dim_file) as f:
            data = yaml.safe_load(f)

        assert data["version"] == "1.0.0"
        assert len(data["dimensions"]) == 1
        assert data["dimensions"][0]["name"] == "carrier"
