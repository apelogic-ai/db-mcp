"""Tests for DataResponse and ColumnMeta gateway output types."""

import pytest
from db_mcp_models.gateway import ColumnMeta, DataResponse


class TestColumnMeta:
    def test_construction(self):
        col = ColumnMeta(name="id", type="INTEGER")
        assert col.name == "id"
        assert col.type == "INTEGER"

    def test_type_is_optional(self):
        col = ColumnMeta(name="value", type=None)
        assert col.type is None

    def test_frozen(self):
        col = ColumnMeta(name="id", type="INTEGER")
        with pytest.raises((AttributeError, TypeError)):
            col.name = "other"  # type: ignore[misc]


class TestDataResponse:
    def test_success_construction(self):
        resp = DataResponse(
            status="success",
            data=[{"id": 1}],
            columns=[ColumnMeta(name="id", type="INTEGER")],
            rows_returned=1,
        )
        assert resp.status == "success"
        assert resp.rows_returned == 1
        assert resp.error is None

    def test_error_construction(self):
        resp = DataResponse(
            status="error",
            data=[],
            columns=[],
            rows_returned=0,
            error="table not found",
        )
        assert resp.status == "error"
        assert resp.error == "table not found"

    def test_empty_data_defaults(self):
        resp = DataResponse(status="success", data=[], columns=[], rows_returned=0)
        assert resp.data == []
        assert resp.columns == []
        assert resp.error is None

    def test_frozen(self):
        resp = DataResponse(status="success", data=[], columns=[], rows_returned=0)
        with pytest.raises((AttributeError, TypeError)):
            resp.status = "error"  # type: ignore[misc]

    def test_is_success_property(self):
        ok = DataResponse(status="success", data=[], columns=[], rows_returned=0)
        err = DataResponse(status="error", data=[], columns=[], rows_returned=0, error="oops")
        assert ok.is_success is True
        assert err.is_success is False


class TestTopLevelExports:
    def test_column_meta_exported_from_db_mcp_models(self):
        from db_mcp_models import ColumnMeta as CM
        assert CM is ColumnMeta

    def test_data_response_exported_from_db_mcp_models(self):
        from db_mcp_models import DataResponse as DR
        assert DR is DataResponse
