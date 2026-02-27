"""Tests for database connectivity and introspection."""

from unittest.mock import MagicMock, patch

import pytest

from db_mcp.db.connection import detect_dialect_from_url, normalize_database_url, test_connection
from db_mcp.tools.database import _detect_dialect


def test_detect_dialect_trino():
    """Test Trino dialect detection."""
    assert detect_dialect_from_url("trino://user:pass@host:8080/catalog") == "trino"


def test_detect_dialect_postgresql():
    """Test PostgreSQL dialect detection."""
    assert detect_dialect_from_url("postgresql://user:pass@host:5432/db") == "postgresql"
    assert detect_dialect_from_url("postgres://user:pass@host:5432/db") == "postgresql"
    assert detect_dialect_from_url("postgresql+psycopg2://user:pass@host/db") == "postgresql"


def test_detect_dialect_clickhouse():
    """Test ClickHouse dialect detection."""
    assert detect_dialect_from_url("clickhouse://user:pass@host:8123/db") == "clickhouse"
    assert detect_dialect_from_url("clickhouse+native://user:pass@host/db") == "clickhouse"


def test_detect_dialect_mysql():
    """Test MySQL dialect detection."""
    assert detect_dialect_from_url("mysql://user:pass@host:3306/db") == "mysql"
    assert detect_dialect_from_url("mariadb://user:pass@host:3306/db") == "mysql"


def test_detect_dialect_unknown():
    """Test unknown dialect handling."""
    assert detect_dialect_from_url("") == "unknown"
    assert detect_dialect_from_url("somedb://host/db") == "somedb"


def test_normalize_database_url():
    """Test database URL normalization."""
    # postgres -> postgresql
    assert normalize_database_url("postgres://host/db") == "postgresql://host/db"
    # postgresql stays the same
    assert normalize_database_url("postgresql://host/db") == "postgresql://host/db"
    # Other URLs unchanged
    assert normalize_database_url("trino://host/db") == "trino://host/db"
    # Empty URL
    assert normalize_database_url("") == ""


@pytest.mark.asyncio
async def test_detect_dialect_tool():
    """Test detect dialect MCP tool."""
    result = await _detect_dialect("trino://user:pass@host:8080/catalog")
    assert result["dialect"] == "trino"
    assert result["database_url_prefix"] == "trino"


def test_test_connection_forwards_connect_args_to_get_engine():
    """test_connection should pass connect_args through to get_engine."""
    mock_engine = MagicMock()
    mock_engine.url.host = "localhost"
    mock_engine.url.database = "catalog"
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (1,)
    mock_conn.execute.return_value = mock_result
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.connect.return_value.__exit__.return_value = False

    with patch("db_mcp.db.connection.get_engine", return_value=mock_engine) as mock_get_engine:
        result = test_connection(
            "trino://user@localhost:8080/catalog",
            connect_args={"http_scheme": "http"},
        )

    assert result["connected"] is True
    mock_get_engine.assert_called_once_with(
        "trino://user@localhost:8080/catalog",
        connect_args={"http_scheme": "http"},
    )


def test_get_engine_accepts_connect_args_dict():
    """get_engine should accept connect_args without hashing errors."""
    from db_mcp.db import connection

    mock_engine = MagicMock()
    with patch("db_mcp.db.connection.create_engine", return_value=mock_engine) as mock_create:
        engine = connection.get_engine("sqlite:///:memory:", connect_args={"timeout": 5})

    assert engine is mock_engine
    assert mock_create.call_args.kwargs["connect_args"] == {"timeout": 5}
