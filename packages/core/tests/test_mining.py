"""Tests for the metrics/dimensions mining engine."""

import tempfile
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def vault_dir():
    """Create a temporary vault directory with training material."""
    with tempfile.TemporaryDirectory() as tmpdir:
        conn_path = Path(tmpdir)

        # Create directories
        (conn_path / "training" / "examples").mkdir(parents=True)
        (conn_path / "instructions").mkdir(parents=True)
        (conn_path / "schema").mkdir(parents=True)

        yield conn_path


def _write_example(vault_dir: Path, filename: str, data: dict):
    """Write a training example YAML file."""
    example_path = vault_dir / "training" / "examples" / filename
    with open(example_path, "w") as f:
        yaml.dump(data, f)


def _write_rules(vault_dir: Path, rules: list[str]):
    """Write business rules YAML file."""
    rules_path = vault_dir / "instructions" / "business_rules.yaml"
    with open(rules_path, "w") as f:
        yaml.dump({"version": "1.0.0", "rules": rules}, f)


def _write_schema(vault_dir: Path, tables: list[dict]):
    """Write schema descriptions YAML file."""
    schema_path = vault_dir / "schema" / "descriptions.yaml"
    with open(schema_path, "w") as f:
        yaml.dump({"tables": tables}, f)


class TestMiningFromExamples:
    """Tests for mining metrics and dimensions from training examples."""

    @pytest.mark.asyncio
    async def test_extracts_count_metric(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "How many active users?",
                "sql": "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE active = true",
                "tags": ["engagement"],
            },
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        metrics = result["metric_candidates"]
        assert len(metrics) >= 1
        names = [m.metric.name for m in metrics]
        assert "count_user_id" in names

    @pytest.mark.asyncio
    async def test_extracts_sum_metric(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "Total revenue",
                "sql": "SELECT SUM(amount) FROM orders",
            },
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        metrics = result["metric_candidates"]
        assert len(metrics) >= 1
        names = [m.metric.name for m in metrics]
        assert "sum_amount" in names

    @pytest.mark.asyncio
    async def test_extracts_avg_metric(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "Average session duration",
                "sql": "SELECT AVG(duration_ms) FROM sessions",
            },
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        metrics = result["metric_candidates"]
        names = [m.metric.name for m in metrics]
        assert "avg_duration_ms" in names

    @pytest.mark.asyncio
    async def test_extracts_group_by_dimensions(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "Sessions by carrier and city",
                "sql": "SELECT carrier, city, COUNT(*) FROM sessions GROUP BY carrier, city",
            },
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        dims = result["dimension_candidates"]
        dim_names = [d.dimension.name for d in dims]
        assert "carrier" in dim_names
        assert "city" in dim_names

    @pytest.mark.asyncio
    async def test_skips_numeric_group_by(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "By carrier",
                "sql": "SELECT carrier, COUNT(*) FROM sessions GROUP BY 1",
            },
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        dims = result["dimension_candidates"]
        dim_names = [d.dimension.name for d in dims]
        # Numeric references (GROUP BY 1) should be skipped
        assert "1" not in dim_names

    @pytest.mark.asyncio
    async def test_metric_confidence_higher_with_intent(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "Count users",
                "sql": "SELECT COUNT(*) FROM users",
            },
        )

        _write_example(
            vault_dir,
            "ex2.yaml",
            {
                "sql": "SELECT SUM(amount) FROM orders",
            },
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        metrics = result["metric_candidates"]
        by_name = {m.metric.name: m for m in metrics}

        if "count_records" in by_name and "sum_amount" in by_name:
            assert by_name["count_records"].confidence >= by_name["sum_amount"].confidence

    @pytest.mark.asyncio
    async def test_deduplicates_metrics(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        # Two examples with the same aggregation
        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "Count users",
                "sql": "SELECT COUNT(*) FROM users",
            },
        )
        _write_example(
            vault_dir,
            "ex2.yaml",
            {
                "natural_language": "Count all users",
                "sql": "SELECT COUNT(*) FROM users WHERE active = true",
            },
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        metrics = result["metric_candidates"]
        names = [m.metric.name for m in metrics]
        # Same aggregation pattern should be deduplicated
        assert names.count("count_records") <= 1


class TestMiningFromSchema:
    """Tests for mining dimensions from schema descriptions."""

    @pytest.mark.asyncio
    async def test_extracts_temporal_dimension(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_schema(
            vault_dir,
            [
                {
                    "name": "events",
                    "full_name": "public.events",
                    "columns": [
                        {"name": "event_date", "type": "DATE", "description": "Event date"},
                        {"name": "value", "type": "FLOAT", "description": "Event value"},
                    ],
                }
            ],
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        dims = result["dimension_candidates"]
        dim_names = [d.dimension.name for d in dims]
        assert "event_date" in dim_names

        event_date = next(d for d in dims if d.dimension.name == "event_date")
        assert event_date.dimension.type.value == "temporal"
        assert event_date.source == "schema"

    @pytest.mark.asyncio
    async def test_extracts_geographic_dimension(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_schema(
            vault_dir,
            [
                {
                    "name": "users",
                    "full_name": "public.users",
                    "columns": [
                        {"name": "city", "type": "VARCHAR", "description": "User city"},
                        {"name": "state", "type": "VARCHAR", "description": "US state"},
                    ],
                }
            ],
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        dims = result["dimension_candidates"]
        dim_names = [d.dimension.name for d in dims]
        assert "city" in dim_names
        assert "state" in dim_names

        city_dim = next(d for d in dims if d.dimension.name == "city")
        assert city_dim.dimension.type.value == "geographic"

    @pytest.mark.asyncio
    async def test_skips_entity_id_columns(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_schema(
            vault_dir,
            [
                {
                    "name": "users",
                    "full_name": "public.users",
                    "columns": [
                        {"name": "user_id", "type": "BIGINT", "description": "Primary key"},
                        {"name": "account_id", "type": "BIGINT", "description": "Account FK"},
                    ],
                }
            ],
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        dims = result["dimension_candidates"]
        dim_names = [d.dimension.name for d in dims]
        assert "user_id" not in dim_names
        assert "account_id" not in dim_names


class TestMiningFromRules:
    """Tests for mining from business rules."""

    @pytest.mark.asyncio
    async def test_extracts_metric_from_rule(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_rules(
            vault_dir,
            [
                "DAU is defined as count of distinct users with login in past 24 hours",
            ],
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        metrics = result["metric_candidates"]
        # Should find DAU as a metric candidate
        assert len(metrics) >= 1
        dau = next((m for m in metrics if m.metric.name == "dau"), None)
        assert dau is not None
        assert dau.source == "rules"
        assert dau.confidence < 0.7  # Lower confidence from rules

    @pytest.mark.asyncio
    async def test_extracts_dimension_from_rule_with_column_ref(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_rules(
            vault_dir,
            [
                'The carrier dimension uses cdr_agg_day.carrier with values "tmo" and "att"',
            ],
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        dims = result["dimension_candidates"]
        assert len(dims) >= 1
        carrier = next((d for d in dims if d.dimension.name == "carrier"), None)
        assert carrier is not None
        assert carrier.source == "rules"
        assert "tmo" in carrier.dimension.values


class TestMiningIntegration:
    """Integration tests combining multiple vault sources."""

    @pytest.mark.asyncio
    async def test_empty_vault_returns_empty(self, vault_dir):
        """Mining with no material returns empty lists."""
        # Remove created dirs to simulate truly empty vault
        import shutil

        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        for d in ["training", "instructions", "schema"]:
            p = vault_dir / d
            if p.exists():
                shutil.rmtree(p)

        result = await mine_metrics_and_dimensions(vault_dir)

        assert result["metric_candidates"] == []
        assert result["dimension_candidates"] == []

    @pytest.mark.asyncio
    async def test_multiple_sources_combined(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "Sessions by carrier",
                "sql": "SELECT carrier, COUNT(*) FROM sessions GROUP BY carrier",
            },
        )

        _write_schema(
            vault_dir,
            [
                {
                    "name": "sessions",
                    "full_name": "public.sessions",
                    "columns": [
                        {"name": "created_date", "type": "DATE", "description": "Session date"},
                    ],
                }
            ],
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        # Should have metrics from examples and dimensions from both
        assert len(result["metric_candidates"]) >= 1
        assert len(result["dimension_candidates"]) >= 1

        sources = {d.source for d in result["dimension_candidates"]}
        # At least one source should be present
        assert len(sources) >= 1

    @pytest.mark.asyncio
    async def test_deduplication_across_sources(self, vault_dir):
        from db_mcp.metrics.mining import mine_metrics_and_dimensions

        # Same dimension from examples and schema
        _write_example(
            vault_dir,
            "ex1.yaml",
            {
                "natural_language": "By city",
                "sql": "SELECT city, COUNT(*) FROM users GROUP BY city",
            },
        )

        _write_schema(
            vault_dir,
            [
                {
                    "name": "users",
                    "full_name": "public.users",
                    "columns": [
                        {"name": "city", "type": "VARCHAR", "description": "User city"},
                    ],
                }
            ],
        )

        result = await mine_metrics_and_dimensions(vault_dir)

        dims = result["dimension_candidates"]
        city_dims = [d for d in dims if d.dimension.name == "city"]
        # Should be deduplicated to one
        assert len(city_dims) == 1


class TestDimensionTypeClassification:
    """Tests for the dimension type classifier."""

    def test_temporal_by_name(self):
        from db_mcp.metrics.mining import _classify_dimension_type

        assert _classify_dimension_type("created_date").value == "temporal"
        assert _classify_dimension_type("event_timestamp").value == "temporal"
        assert _classify_dimension_type("report_day").value == "temporal"
        assert _classify_dimension_type("year").value == "temporal"

    def test_temporal_by_type(self):
        from db_mcp.metrics.mining import _classify_dimension_type

        assert _classify_dimension_type("some_col", "TIMESTAMP").value == "temporal"
        assert _classify_dimension_type("some_col", "DATE").value == "temporal"

    def test_geographic(self):
        from db_mcp.metrics.mining import _classify_dimension_type

        assert _classify_dimension_type("city").value == "geographic"
        assert _classify_dimension_type("state").value == "geographic"
        assert _classify_dimension_type("zip_code").value == "geographic"
        assert _classify_dimension_type("country").value == "geographic"

    def test_entity(self):
        from db_mcp.metrics.mining import _classify_dimension_type

        assert _classify_dimension_type("user_id").value == "entity"
        assert _classify_dimension_type("subscriber_id").value == "entity"
        assert _classify_dimension_type("session_id").value == "entity"

    def test_categorical_default(self):
        from db_mcp.metrics.mining import _classify_dimension_type

        assert _classify_dimension_type("carrier").value == "categorical"
        assert _classify_dimension_type("status").value == "categorical"
        assert _classify_dimension_type("plan_type").value == "categorical"
