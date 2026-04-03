"""Tests for SQL dialect loading."""

import tempfile
from pathlib import Path

import pytest
import yaml
from db_mcp_data.dialect import get_dialect_file_path, load_dialect_rules


@pytest.fixture
def temp_resources_dir(monkeypatch):
    """Create a temporary resources directory with dialect files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sql-dialects directory with test files
        dialects_dir = Path(tmpdir) / "sql-dialects"
        dialects_dir.mkdir(parents=True)

        # Create trino dialect file
        trino_data = {
            "version": "1.0",
            "description": "Trino SQL dialect rules",
            "rules": [
                "Use DOUBLE instead of FLOAT",
                "Use VARCHAR instead of TEXT",
            ],
        }
        with open(dialects_dir / "trino.yaml", "w") as f:
            yaml.dump(trino_data, f)

        # Create postgresql dialect file
        pg_data = {
            "version": "1.0",
            "description": "PostgreSQL SQL dialect rules",
            "rules": [
                "Use TEXT for variable-length strings",
                "Use SERIAL for auto-increment",
            ],
        }
        with open(dialects_dir / "postgresql.yaml", "w") as f:
            yaml.dump(pg_data, f)

        yield Path(tmpdir)


def test_get_dialect_file_path_trino(temp_resources_dir):
    """Test finding Trino dialect file."""
    path = get_dialect_file_path("trino", resources_dir=temp_resources_dir)
    assert path is not None
    assert path.exists()
    assert "trino.yaml" in str(path)


def test_load_dialect_rules_trino(temp_resources_dir):
    """Test loading Trino dialect rules."""
    result = load_dialect_rules("trino", resources_dir=temp_resources_dir)
    assert result["found"] is True
    assert result["dialect"] == "trino"
    assert len(result["rules"]) > 0
    assert result["error"] is None


def test_load_dialect_rules_postgresql(temp_resources_dir):
    """Test loading PostgreSQL dialect rules."""
    result = load_dialect_rules("postgresql", resources_dir=temp_resources_dir)
    assert result["found"] is True
    assert result["dialect"] == "postgresql"
    assert len(result["rules"]) > 0


def test_load_dialect_rules_unknown(temp_resources_dir):
    """Test loading unknown dialect."""
    result = load_dialect_rules("unknowndb", resources_dir=temp_resources_dir)
    assert result["found"] is False
    assert result["dialect"] == "unknowndb"
    assert "No dialect file found" in result["error"]


