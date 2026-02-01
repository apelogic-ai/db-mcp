"""Tests for SQL validation (EXPLAIN) with file/DuckDB connectors.

TDD: these tests define the expected behavior for validate_sql
when used with a FileConnector (DuckDB backend) instead of SQLConnector.
"""

import textwrap

import pytest

from db_mcp.connectors.file import FileConnector, FileConnectorConfig, FileSourceConfig
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
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda: file_connector)
        result = explain_sql("SELECT * FROM users")
        assert result.valid is True
        assert result.error is None

    def test_valid_select_returns_auto_cost_tier(self, file_connector, monkeypatch):
        """File connector queries should default to AUTO cost tier (local data)."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda: file_connector)
        result = explain_sql("SELECT * FROM users WHERE age > 25")
        assert result.valid is True
        assert result.cost_tier == CostTier.AUTO

    def test_invalid_sql_returns_invalid(self, file_connector, monkeypatch):
        """Invalid SQL should return valid=False with an error message."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda: file_connector)
        result = explain_sql("SELECT * FROM nonexistent_table")
        assert result.valid is False
        assert result.error is not None

    def test_syntax_error_returns_invalid(self, file_connector, monkeypatch):
        """SQL syntax errors should return valid=False."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda: file_connector)
        result = explain_sql("SELCT * FORM users")
        assert result.valid is False
        assert result.error is not None

    def test_aggregation_query_valid(self, file_connector, monkeypatch):
        """Aggregation queries should validate successfully."""
        monkeypatch.setattr("db_mcp.validation.explain.get_connector", lambda: file_connector)
        result = explain_sql("SELECT COUNT(*), AVG(age) FROM users")
        assert result.valid is True
