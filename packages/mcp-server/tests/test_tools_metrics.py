"""Tests for db_mcp_server.tools.metrics wrapper functions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_resolve():
    with patch(
        "db_mcp_server.tools.metrics.resolve_connection",
        return_value=("conn", "sqlite", Path("/tmp/test")),
    ) as m:
        yield m


@pytest.mark.asyncio
async def test_metrics_list(mock_resolve):
    mock_metrics_catalog = MagicMock()
    mock_metrics_catalog.metrics = []
    mock_metrics_catalog.count.return_value = 0

    mock_dims_catalog = MagicMock()
    mock_dims_catalog.dimensions = []
    mock_dims_catalog.count.return_value = 0

    mock_bindings_catalog = MagicMock()
    mock_bindings_catalog.bindings = {}

    with (
        patch(
            "db_mcp_server.tools.metrics.load_metrics",
            return_value=mock_metrics_catalog,
        ),
        patch(
            "db_mcp_server.tools.metrics.load_dimensions",
            return_value=mock_dims_catalog,
        ),
        patch(
            "db_mcp_server.tools.metrics.load_metric_bindings",
            return_value=mock_bindings_catalog,
        ),
    ):
        from db_mcp_server.tools.metrics import _metrics_list

        result = await _metrics_list(connection="mydb")

    assert "metrics" in result
    assert "dimensions" in result
    assert result["metrics"] == []
    assert result["dimensions"] == []


@pytest.mark.asyncio
async def test_metrics_approve_metric(mock_resolve):
    with patch(
        "db_mcp_server.tools.metrics.add_metric",
        return_value={"added": True},
    ) as mock_add:
        from db_mcp_server.tools.metrics import _metrics_approve

        result = await _metrics_approve(
            type="metric",
            name="dau",
            connection="mydb",
            description="daily active users",
            sql="COUNT(DISTINCT user_id)",
        )

    assert result["approved"] is True
    assert result["type"] == "metric"
    assert result["name"] == "dau"
    mock_add.assert_called_once()
    call_kwargs = mock_add.call_args.kwargs
    assert call_kwargs["name"] == "dau"
    assert call_kwargs["description"] == "daily active users"
    assert call_kwargs["sql"] == "COUNT(DISTINCT user_id)"


@pytest.mark.asyncio
async def test_metrics_approve_missing_description(mock_resolve):
    from db_mcp_server.tools.metrics import _metrics_approve

    result = await _metrics_approve(
        type="metric", name="dau", connection="mydb", description=""
    )
    assert result["approved"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_metrics_remove(mock_resolve):
    with patch(
        "db_mcp_server.tools.metrics.delete_metric",
        return_value={"deleted": True},
    ) as mock_del:
        from db_mcp_server.tools.metrics import _metrics_remove

        result = await _metrics_remove(
            type="metric", name="dau", connection="mydb"
        )

    assert result["removed"] is True
    assert result["name"] == "dau"
    mock_del.assert_called_once_with("sqlite", "dau", connection_path=Path("/tmp/test"))


@pytest.mark.asyncio
async def test_metrics_bindings_validate_success(mock_resolve):
    with patch(
        "db_mcp_server.tools.metrics._validate_metric_binding",
        return_value={"valid": True},
    ):
        from db_mcp_server.tools.metrics import _metrics_bindings_validate

        result = await _metrics_bindings_validate(
            connection="mydb",
            metric_name="dau",
            sql="COUNT(DISTINCT user_id)",
        )

    assert result["valid"] is True
    assert result["metric_name"] == "dau"


@pytest.mark.asyncio
async def test_metrics_bindings_validate_error(mock_resolve):
    with patch(
        "db_mcp_server.tools.metrics._validate_metric_binding",
        return_value={"valid": False, "error": "metric not found"},
    ):
        from db_mcp_server.tools.metrics import _metrics_bindings_validate

        result = await _metrics_bindings_validate(
            connection="mydb",
            metric_name="unknown",
            sql="SELECT 1",
        )

    assert result["valid"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_metrics_bindings_set(mock_resolve):
    with (
        patch(
            "db_mcp_server.tools.metrics._validate_metric_binding",
            return_value={"valid": True},
        ),
        patch(
            "db_mcp_server.tools.metrics.upsert_metric_binding",
            return_value={"saved": True, "file_path": "/tmp/test/metrics/bindings.yaml"},
        ) as mock_upsert,
        patch(
            "db_mcp_server.tools.metrics._serialize_metric_binding",
            return_value={"metric_name": "dau", "sql": "COUNT(...)"},
        ),
    ):
        from db_mcp_server.tools.metrics import _metrics_bindings_set

        result = await _metrics_bindings_set(
            connection="mydb",
            metric_name="dau",
            sql="COUNT(DISTINCT user_id)",
            tables=["events"],
        )

    assert result["saved"] is True
    assert result["metric_name"] == "dau"
    mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_metrics_bindings_set_validation_fails(mock_resolve):
    with patch(
        "db_mcp_server.tools.metrics._validate_metric_binding",
        return_value={"valid": False, "error": "bad sql"},
    ):
        from db_mcp_server.tools.metrics import _metrics_bindings_set

        result = await _metrics_bindings_set(
            connection="mydb",
            metric_name="dau",
            sql="BAD SQL",
        )

    assert result["saved"] is False
