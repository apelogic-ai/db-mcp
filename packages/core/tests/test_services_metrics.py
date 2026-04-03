from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

CONN_PATH = Path("/tmp/connections/analytics")


@pytest.mark.asyncio
async def test_discover_metric_candidates_merges_mined_and_catalog_candidates():
    from db_mcp.services.metrics import discover_metric_candidates

    connection = "analytics"

    mined_metric = SimpleNamespace(
        metric=SimpleNamespace(name="dau", model_dump=lambda mode="json": {"name": "dau"}),
        confidence=0.93,
        source="examples",
        evidence=["example.yaml"],
    )
    mined_dimension = SimpleNamespace(
        dimension=SimpleNamespace(
            name="country",
            model_dump=lambda mode="json": {"name": "country"},
        ),
        confidence=0.88,
        source="examples",
        evidence=["example.yaml"],
        category="Geography",
    )

    catalog_metric = SimpleNamespace(name="wau", model_dump=lambda mode="json": {"name": "wau"})
    catalog_dimension = SimpleNamespace(
        name="device_type", model_dump=lambda mode="json": {"name": "device_type"}
    )

    metrics_catalog = SimpleNamespace(candidates=lambda: [catalog_metric])
    dimensions_catalog = SimpleNamespace(candidates=lambda: [catalog_dimension])

    with (
        patch(
            "db_mcp.services.metrics.mine_metrics_and_dimensions",
            return_value={
                "metric_candidates": [mined_metric],
                "dimension_candidates": [mined_dimension],
            },
        ) as mock_mine,
        patch("db_mcp.services.metrics.load_metrics", return_value=metrics_catalog),
        patch("db_mcp.services.metrics.load_dimensions", return_value=dimensions_catalog),
    ):
        result = await discover_metric_candidates(
            connection=connection,
            connection_path=CONN_PATH,
        )

    assert result == {
        "metricCandidates": [
            {
                "metric": {"name": "dau"},
                "confidence": 0.93,
                "source": "examples",
                "evidence": ["example.yaml"],
            },
            {
                "metric": {"name": "wau"},
                "confidence": 0.6,
                "source": "catalog",
                "evidence": [],
            },
        ],
        "dimensionCandidates": [
            {
                "dimension": {"name": "country"},
                "confidence": 0.88,
                "source": "examples",
                "evidence": ["example.yaml"],
                "category": "Geography",
            },
            {
                "dimension": {"name": "device_type"},
                "confidence": 0.6,
                "source": "catalog",
                "evidence": [],
                "category": "Other",
            },
        ],
    }
    mock_mine.assert_called_once_with(CONN_PATH)


def test_list_approved_metrics_returns_catalog_payload_and_counts():
    from db_mcp.services.metrics import list_approved_metrics

    connection = "analytics"

    approved_metric = SimpleNamespace(
        model_dump=lambda mode="json": {"name": "revenue", "status": "approved"}
    )
    approved_dimension = SimpleNamespace(
        model_dump=lambda mode="json": {"name": "region", "status": "approved"}
    )

    metrics_catalog = SimpleNamespace(approved=lambda: [approved_metric])
    dimensions_catalog = SimpleNamespace(approved=lambda: [approved_dimension])

    with (
        patch("db_mcp.services.metrics.load_metrics", return_value=metrics_catalog),
        patch("db_mcp.services.metrics.load_dimensions", return_value=dimensions_catalog),
    ):
        result = list_approved_metrics(connection=connection, connection_path=CONN_PATH)

    assert result == {
        "metrics": [{"name": "revenue", "status": "approved"}],
        "dimensions": [{"name": "region", "status": "approved"}],
        "metricCount": 1,
        "dimensionCount": 1,
    }


def test_add_metric_definition_returns_success_payload():
    from db_mcp.services.metrics import add_metric_definition

    connection = "analytics"
    data = {
        "name": "revenue",
        "description": "Total revenue",
        "sql": "SELECT SUM(amount) FROM orders",
        "display_name": "Revenue",
        "tables": ["orders"],
        "parameters": [],
        "tags": ["finance"],
        "dimensions": ["region"],
        "notes": "Core KPI",
        "status": "approved",
    }

    with patch(
        "db_mcp.services.metrics.add_metric",
        return_value={"added": True, "file_path": "metrics/catalog.yaml"},
    ) as mock_add:
        result = add_metric_definition(
            connection=connection, data=data, connection_path=CONN_PATH
        )

    assert result == {
        "success": True,
        "name": "revenue",
        "type": "metric",
        "filePath": "metrics/catalog.yaml",
    }
    mock_add.assert_called_once_with(
        provider_id="analytics",
        name="revenue",
        description="Total revenue",
        sql="SELECT SUM(amount) FROM orders",
        connection_path=CONN_PATH,
        display_name="Revenue",
        tables=["orders"],
        parameters=[],
        tags=["finance"],
        dimensions=["region"],
        notes="Core KPI",
        status="approved",
    )


def test_add_dimension_definition_returns_success_payload():
    from db_mcp.services.metrics import add_dimension_definition

    connection = "analytics"
    data = {
        "name": "region",
        "column": "orders.region",
        "description": "Sales region",
        "display_name": "Region",
        "type": "categorical",
        "tables": ["orders"],
        "values": ["EMEA", "NA"],
        "synonyms": ["geo"],
        "status": "approved",
    }

    with patch(
        "db_mcp.services.metrics.add_dimension",
        return_value={"added": True, "file_path": "metrics/dimensions.yaml"},
    ) as mock_add:
        result = add_dimension_definition(
            connection=connection, data=data, connection_path=CONN_PATH
        )

    assert result == {
        "success": True,
        "name": "region",
        "type": "dimension",
        "filePath": "metrics/dimensions.yaml",
    }
    mock_add.assert_called_once_with(
        provider_id="analytics",
        name="region",
        column="orders.region",
        connection_path=CONN_PATH,
        description="Sales region",
        display_name="Region",
        dim_type="categorical",
        tables=["orders"],
        values=["EMEA", "NA"],
        synonyms=["geo"],
        status="approved",
    )


def test_update_metric_definition_replaces_existing_metric():
    from db_mcp.services.metrics import update_metric_definition

    connection = "analytics"
    original_name = "revenue"
    data = {
        "name": "gross_revenue",
        "description": "Gross revenue",
        "sql": "SELECT SUM(amount) FROM orders",
        "display_name": "Gross Revenue",
        "tables": ["orders"],
        "parameters": [],
        "tags": ["finance"],
        "dimensions": ["region"],
        "notes": "Renamed metric",
        "status": "approved",
    }

    with (
        patch("db_mcp.services.metrics.delete_metric") as mock_delete,
        patch(
            "db_mcp.services.metrics.add_metric",
            return_value={"added": True, "file_path": "metrics/catalog.yaml"},
        ) as mock_add,
    ):
        result = update_metric_definition(
            connection=connection,
            name=original_name,
            data=data,
            connection_path=CONN_PATH,
        )

    assert result == {
        "success": True,
        "name": "gross_revenue",
        "type": "metric",
    }
    mock_delete.assert_called_once_with("analytics", "revenue", connection_path=CONN_PATH)
    mock_add.assert_called_once_with(
        provider_id="analytics",
        name="gross_revenue",
        description="Gross revenue",
        sql="SELECT SUM(amount) FROM orders",
        connection_path=CONN_PATH,
        display_name="Gross Revenue",
        tables=["orders"],
        parameters=[],
        tags=["finance"],
        dimensions=["region"],
        notes="Renamed metric",
        status="approved",
    )


def test_update_dimension_definition_replaces_existing_dimension():
    from db_mcp.services.metrics import update_dimension_definition

    connection = "analytics"
    original_name = "region"
    data = {
        "name": "sales_region",
        "column": "orders.sales_region",
        "description": "Sales region",
        "display_name": "Sales Region",
        "type": "categorical",
        "tables": ["orders"],
        "values": ["EMEA", "NA"],
        "synonyms": ["geo"],
    }

    with (
        patch("db_mcp.services.metrics.delete_dimension") as mock_delete,
        patch(
            "db_mcp.services.metrics.add_dimension",
            return_value={"added": True, "file_path": "metrics/dimensions.yaml"},
        ) as mock_add,
    ):
        result = update_dimension_definition(
            connection=connection,
            name=original_name,
            data=data,
            connection_path=CONN_PATH,
        )

    assert result == {
        "success": True,
        "name": "sales_region",
        "type": "dimension",
    }
    mock_delete.assert_called_once_with("analytics", "region", connection_path=CONN_PATH)
    mock_add.assert_called_once_with(
        provider_id="analytics",
        name="sales_region",
        column="orders.sales_region",
        connection_path=CONN_PATH,
        description="Sales region",
        display_name="Sales Region",
        dim_type="categorical",
        tables=["orders"],
        values=["EMEA", "NA"],
        synonyms=["geo"],
    )


def test_delete_metric_definition_returns_success_payload():
    from db_mcp.services.metrics import delete_metric_definition

    with patch(
        "db_mcp.services.metrics.delete_metric",
        return_value={"deleted": True},
    ) as mock_delete:
        result = delete_metric_definition(
            connection="analytics", name="revenue", connection_path=CONN_PATH
        )

    assert result == {
        "success": True,
        "name": "revenue",
        "type": "metric",
    }
    mock_delete.assert_called_once_with("analytics", "revenue", connection_path=CONN_PATH)


def test_delete_dimension_definition_returns_success_payload():
    from db_mcp.services.metrics import delete_dimension_definition

    with patch(
        "db_mcp.services.metrics.delete_dimension",
        return_value={"deleted": True},
    ) as mock_delete:
        result = delete_dimension_definition(
            connection="analytics", name="region", connection_path=CONN_PATH
        )

    assert result == {
        "success": True,
        "name": "region",
        "type": "dimension",
    }
    mock_delete.assert_called_once_with("analytics", "region", connection_path=CONN_PATH)


def test_approve_metric_candidate_marks_payload_and_delegates_to_add_metric():
    from db_mcp.services.metrics import approve_metric_candidate

    connection = "analytics"
    data = {
        "name": "revenue",
        "description": "Total revenue",
        "sql": "SELECT SUM(amount) FROM orders",
    }

    with patch(
        "db_mcp.services.metrics.add_metric_definition",
        return_value={"success": True, "name": "revenue", "type": "metric"},
    ) as mock_add:
        result = approve_metric_candidate(
            connection=connection, data=data, connection_path=CONN_PATH
        )

    assert result == {"success": True, "name": "revenue", "type": "metric"}
    mock_add.assert_called_once_with(
        "analytics",
        {
            "name": "revenue",
            "description": "Total revenue",
            "sql": "SELECT SUM(amount) FROM orders",
            "created_by": "approved",
            "status": "approved",
        },
        connection_path=CONN_PATH,
    )


def test_approve_dimension_candidate_marks_payload_and_delegates_to_add_dimension():
    from db_mcp.services.metrics import approve_dimension_candidate

    connection = "analytics"
    data = {
        "name": "region",
        "column": "orders.region",
        "description": "Sales region",
    }

    with patch(
        "db_mcp.services.metrics.add_dimension_definition",
        return_value={"success": True, "name": "region", "type": "dimension"},
    ) as mock_add:
        result = approve_dimension_candidate(
            connection=connection, data=data, connection_path=CONN_PATH
        )

    assert result == {"success": True, "name": "region", "type": "dimension"}
    mock_add.assert_called_once_with(
        "analytics",
        {
            "name": "region",
            "column": "orders.region",
            "description": "Sales region",
            "created_by": "approved",
            "status": "approved",
        },
        connection_path=CONN_PATH,
    )
