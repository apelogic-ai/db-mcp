"""Tests for SQL validation (EXPLAIN) and execution with file/DuckDB connectors.

TDD: these tests define the expected behavior for validate_sql and run_sql
when used with a FileConnector (DuckDB backend) instead of SQLConnector.
"""

import textwrap

import pytest

from db_mcp.connectors.file import FileConnector, FileConnectorConfig, FileSourceConfig
from db_mcp.tools.generation import _execute_query
from db_mcp.validation.explain import CostTier, explain_sql


@pytest.fixture
def csv_file(tmp_path):
    """Create a small CSV file."""
    path = tmp_path / "users.csv"
    path.write_text(
        textwrap.dedent("""\
        id,name,email,age
        1,Alice,alice@example.com,30
        2,Bob,bob@example.com,25
        3,Charlie,charlie@example.com,35
    """)
    )
    return path


@pytest.fixture
def file_connector(csv_file):
    """A FileConnector with a single CSV source."""
    config = FileConnectorConfig(sources=[FileSourceConfig(name="users", path=str(csv_file))])
    return FileConnector(config)


class TestExplainWithFileConnector:
    """explain_sql should work with FileConnector/DuckDB, not just SQLConnector."""

    def test_valid_select_returns_valid(self, file_connector, monkeypatch):
        """A valid SELECT against a file connector should return valid=True."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda **kwargs: file_connector)
        result = explain_sql("SELECT * FROM users")
        assert result.valid is True
        assert result.error is None

    def test_valid_select_returns_auto_cost_tier(self, file_connector, monkeypatch):
        """File connector queries should default to AUTO cost tier (local data)."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda **kwargs: file_connector)
        result = explain_sql("SELECT * FROM users WHERE age > 25")
        assert result.valid is True
        assert result.cost_tier == CostTier.AUTO

    def test_invalid_sql_returns_invalid(self, file_connector, monkeypatch):
        """Invalid SQL should return valid=False with an error message."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda **kwargs: file_connector)
        result = explain_sql("SELECT * FROM nonexistent_table")
        assert result.valid is False
        assert result.error is not None

    def test_syntax_error_returns_invalid(self, file_connector, monkeypatch):
        """SQL syntax errors should return valid=False."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda **kwargs: file_connector)
        result = explain_sql("SELCT * FORM users")
        assert result.valid is False
        assert result.error is not None

    def test_aggregation_query_valid(self, file_connector, monkeypatch):
        """Aggregation queries should validate successfully."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda **kwargs: file_connector)
        result = explain_sql("SELECT COUNT(*), AVG(age) FROM users")
        assert result.valid is True


class TestExecuteQueryWithFileConnector:
    """_execute_query should work with FileConnector/DuckDB, not just SQLConnector."""

    def test_select_all_returns_rows(self, file_connector, monkeypatch):
        """SELECT * should return all rows from a file connector."""
        monkeypatch.setattr(
            "db_mcp.tools.utils.resolve_connection",
            lambda connection=None, **kw: (file_connector, "test", "/test"),
        )
        result = _execute_query("SELECT * FROM users")
        assert result["rows_returned"] == 3
        assert "id" in result["columns"]
        assert "name" in result["columns"]
        assert len(result["data"]) == 3

    def test_select_with_filter(self, file_connector, monkeypatch):
        """SELECT with WHERE should filter rows."""
        monkeypatch.setattr(
            "db_mcp.tools.utils.resolve_connection",
            lambda connection=None, **kw: (file_connector, "test", "/test"),
        )
        result = _execute_query("SELECT name FROM users WHERE age > 25")
        assert result["rows_returned"] == 2
        names = [row["name"] for row in result["data"]]
        assert "Alice" in names
        assert "Charlie" in names

    def test_aggregation_query(self, file_connector, monkeypatch):
        """Aggregation queries should work with file connector."""
        monkeypatch.setattr(
            "db_mcp.tools.utils.resolve_connection",
            lambda connection=None, **kw: (file_connector, "test", "/test"),
        )
        result = _execute_query("SELECT COUNT(*) as cnt FROM users")
        assert result["rows_returned"] == 1
        assert result["data"][0]["cnt"] == 3

    def test_limit_parameter(self, file_connector, monkeypatch):
        """Limit parameter should cap the number of returned rows."""
        monkeypatch.setattr(
            "db_mcp.tools.utils.resolve_connection",
            lambda connection=None, **kw: (file_connector, "test", "/test"),
        )
        result = _execute_query("SELECT * FROM users", limit=2)
        assert result["rows_returned"] == 2

    def test_invalid_sql_raises(self, file_connector, monkeypatch):
        """Invalid SQL should raise an exception."""
        monkeypatch.setattr(
            "db_mcp.tools.utils.resolve_connection",
            lambda connection=None, **kw: (file_connector, "test", "/test"),
        )
        with pytest.raises(Exception):
            _execute_query("SELECT * FROM nonexistent_table")

    def test_returns_columns(self, file_connector, monkeypatch):
        """Result should include column names."""
        monkeypatch.setattr(
            "db_mcp.tools.utils.resolve_connection",
            lambda connection=None, **kw: (file_connector, "test", "/test"),
        )
        result = _execute_query("SELECT id, name FROM users LIMIT 1")
        assert result["columns"] == ["id", "name"]

    def test_returns_duration(self, file_connector, monkeypatch):
        """Result should include duration_ms."""
        monkeypatch.setattr(
            "db_mcp.tools.utils.resolve_connection",
            lambda connection=None, **kw: (file_connector, "test", "/test"),
        )
        result = _execute_query("SELECT * FROM users")
        assert "duration_ms" in result
        assert result["duration_ms"] >= 0
