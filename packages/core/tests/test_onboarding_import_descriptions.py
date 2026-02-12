"""Tests for onboarding_import_descriptions tool."""

import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from db_mcp_models import OnboardingPhase, TableDescriptionStatus

from db_mcp.onboarding.schema_store import load_schema_descriptions
from db_mcp.onboarding.state import load_state
from db_mcp.tools.onboarding import (
    _onboarding_discover,
    _onboarding_import_descriptions,
    _onboarding_start,
)


@pytest.fixture
def temp_connection_dir(monkeypatch):
    """Create a temporary connection directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("CONNECTION_PATH", tmpdir)

        # Clear cached settings
        import db_mcp.config

        db_mcp.config._settings = None

        yield tmpdir


def _make_mock_connector():
    """Create a mock connector with standard return values."""
    mock = MagicMock()
    mock.test_connection.return_value = {
        "connected": True,
        "dialect": "postgresql",
        "url_host": "localhost",
        "url_database": "test_db",
        "error": None,
    }
    mock.get_dialect.return_value = "postgresql"
    mock.get_catalogs.return_value = [None]  # PostgreSQL doesn't use catalogs
    mock.get_schemas.return_value = ["public"]
    mock.get_tables.return_value = [
        {
            "name": "users",
            "schema": "public",
            "catalog": None,
            "type": "table",
            "full_name": "public.users",
        },
        {
            "name": "orders",
            "schema": "public",
            "catalog": None,
            "type": "table",
            "full_name": "public.orders",
        },
        {
            "name": "products",
            "schema": "public",
            "catalog": None,
            "type": "table",
            "full_name": "public.products",
        },
    ]
    mock.get_columns.side_effect = [
        # users table columns
        [
            {"name": "id", "type": "INTEGER", "nullable": False},
            {"name": "email", "type": "VARCHAR", "nullable": True},
            {"name": "created_at", "type": "TIMESTAMP", "nullable": True},
        ],
        # orders table columns
        [
            {"name": "id", "type": "INTEGER", "nullable": False},
            {"name": "user_id", "type": "INTEGER", "nullable": False},
            {"name": "total", "type": "DECIMAL", "nullable": True},
        ],
        # products table columns
        [
            {"name": "id", "type": "INTEGER", "nullable": False},
            {"name": "name", "type": "VARCHAR", "nullable": True},
            {"name": "price", "type": "DECIMAL", "nullable": True},
        ],
    ]
    return mock


@pytest.fixture
def mock_connector():
    """Mock connector for testing."""
    mock = _make_mock_connector()
    with patch("db_mcp.tools.onboarding.get_connector", return_value=mock):
        yield mock


async def _setup_schema_phase(provider_id: str, mock_connector):
    """Helper: set up schema phase with discovered tables."""
    await _onboarding_start(provider_id=provider_id)
    await _onboarding_discover(provider_id=provider_id, phase="structure")
    await _onboarding_discover(provider_id=provider_id, phase="tables")

    # Verify we're in schema phase
    state = load_state(provider_id)
    assert state is not None
    assert state.phase == OnboardingPhase.SCHEMA
    assert state.tables_total == 3

    return state


class TestImportDescriptions:
    """Tests for _onboarding_import_descriptions."""

    @pytest.mark.asyncio
    async def test_import_descriptions_success(self, temp_connection_dir, mock_connector):
        """Test successful import of table and column descriptions."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        # Define descriptions to import
        descriptions_data = {
            "public.users": {
                "description": "User account information",
                "columns": {
                    "id": "Unique user identifier",
                    "email": "User's email address",
                    "created_at": "Account creation timestamp",
                },
            },
            "public.orders": {
                "description": "Customer order records",
                "columns": {
                    "id": "Unique order identifier",
                    "user_id": "Reference to users table",
                },
            },
        }

        # Import descriptions
        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        # Verify result
        assert result["imported"] is True
        assert result["tables_updated"] == 2
        assert result["columns_updated"] == 5  # 3 columns for users + 2 for orders
        assert result["tables_not_found"] == []
        assert result["columns_not_found"] == []
        assert result["parse_warnings"] == []  # No parsing warnings for valid JSON
        assert result["phase"] == "schema"  # Should still be in schema phase (products table pending)

        # Verify schema was updated
        schema = load_schema_descriptions(provider_id)
        assert schema is not None

        users_table = next(t for t in schema.tables if t.full_name == "public.users")
        assert users_table.description == "User account information"
        assert users_table.status == TableDescriptionStatus.APPROVED

        email_col = next(c for c in users_table.columns if c.name == "email")
        assert email_col.description == "User's email address"

        orders_table = next(t for t in schema.tables if t.full_name == "public.orders")
        assert orders_table.description == "Customer order records"
        assert orders_table.status == TableDescriptionStatus.APPROVED

        # Products table should still be pending
        products_table = next(t for t in schema.tables if t.full_name == "public.products")
        assert products_table.status == TableDescriptionStatus.PENDING
        assert products_table.description is None

    @pytest.mark.asyncio
    async def test_import_descriptions_complete_all_tables(self, temp_connection_dir, mock_connector):
        """Test importing descriptions for all tables advances to domain phase."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        # Import descriptions for ALL tables
        descriptions_data = {
            "public.users": {
                "description": "User account information",
                "columns": {"id": "User ID", "email": "Email address"},
            },
            "public.orders": {
                "description": "Customer order records",
                "columns": {"id": "Order ID", "user_id": "User reference"},
            },
            "public.products": {
                "description": "Product catalog",
                "columns": {"id": "Product ID", "name": "Product name", "price": "Product price"},
            },
        }

        # Import descriptions
        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        # Verify result shows phase advancement
        assert result["imported"] is True
        assert result["tables_updated"] == 3
        assert result["columns_updated"] == 7
        assert result["parse_warnings"] == []  # No parsing warnings for valid JSON
        assert result["phase"] == "domain"  # Should advance to domain phase
        assert "All tables now complete" in result["message"]

        # Verify state advanced
        state = load_state(provider_id)
        assert state.phase == OnboardingPhase.DOMAIN

    @pytest.mark.asyncio
    async def test_import_descriptions_table_not_found(self, temp_connection_dir, mock_connector):
        """Test importing descriptions for non-existent table."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        # Include a table that doesn't exist
        descriptions_data = {
            "public.users": {
                "description": "User account information",
                "columns": {"id": "User ID"},
            },
            "public.non_existent": {
                "description": "This table doesn't exist",
                "columns": {"id": "Fake ID"},
            },
        }

        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        assert result["imported"] is True
        assert result["tables_updated"] == 1  # Only users table found
        assert result["columns_updated"] == 1
        assert result["tables_not_found"] == ["public.non_existent"]
        assert result["columns_not_found"] == []
        assert result["parse_warnings"] == []  # No parsing warnings for valid JSON

    @pytest.mark.asyncio
    async def test_import_descriptions_column_not_found(self, temp_connection_dir, mock_connector):
        """Test importing descriptions for non-existent columns."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        descriptions_data = {
            "public.users": {
                "description": "User account information",
                "columns": {
                    "id": "User ID",
                    "email": "Email address",
                    "non_existent_column": "This column doesn't exist",
                },
            },
        }

        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        assert result["imported"] is True
        assert result["tables_updated"] == 1
        assert result["columns_updated"] == 2  # Only id and email columns updated
        assert result["tables_not_found"] == []
        assert result["columns_not_found"] == ["public.users.non_existent_column"]
        assert result["parse_warnings"] == []  # No parsing warnings for valid JSON

    @pytest.mark.asyncio
    async def test_import_descriptions_partial_columns(self, temp_connection_dir, mock_connector):
        """Test importing descriptions only updates mentioned columns, not all."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        # Only provide descriptions for some columns
        descriptions_data = {
            "public.users": {
                "description": "User account information",
                "columns": {
                    "id": "User ID",
                    # email and created_at columns not mentioned - should remain None
                },
            },
        }

        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        assert result["imported"] is True
        assert result["tables_updated"] == 1
        assert result["columns_updated"] == 1  # Only id column updated
        assert result["parse_warnings"] == []  # No parsing warnings for valid JSON

        # Verify only mentioned column was updated
        schema = load_schema_descriptions(provider_id)
        users_table = next(t for t in schema.tables if t.full_name == "public.users")

        id_col = next(c for c in users_table.columns if c.name == "id")
        assert id_col.description == "User ID"

        email_col = next(c for c in users_table.columns if c.name == "email")
        assert email_col.description is None  # Should remain unchanged

        created_at_col = next(c for c in users_table.columns if c.name == "created_at")
        assert created_at_col.description is None  # Should remain unchanged

    @pytest.mark.asyncio
    async def test_import_descriptions_unparseable_text(self, temp_connection_dir, mock_connector):
        """Test importing with text that can't be parsed in any format."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        # Text that can't be parsed as any format
        result = await _onboarding_import_descriptions(
            descriptions="random text without any structure",
            provider_id=provider_id,
        )

        assert result["imported"] is False
        assert "Could not parse any table descriptions" in result["error"]
        assert "warnings" in result

    @pytest.mark.asyncio
    async def test_import_descriptions_json_array(self, temp_connection_dir, mock_connector):
        """Test importing with JSON that's an array instead of object."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        # JSON array instead of object - should generate warnings but not crash
        result = await _onboarding_import_descriptions(
            descriptions='["not", "an", "object"]',
            provider_id=provider_id,
        )

        assert result["imported"] is False
        assert "Could not parse any table descriptions" in result["error"]
        assert "warnings" in result
        assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_import_descriptions_wrong_phase(self, temp_connection_dir, mock_connector):
        """Test importing when not in schema phase."""
        provider_id = "test-provider"
        await _onboarding_start(provider_id=provider_id)  # Still in init phase

        descriptions_data = {
            "public.users": {"description": "User table"},
        }

        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        assert result["imported"] is False
        assert "Not in schema phase" in result["error"]
        assert result["phase"] == "init"

    @pytest.mark.asyncio
    async def test_import_descriptions_not_started(self, temp_connection_dir, mock_connector):
        """Test importing when onboarding not started."""
        provider_id = "test-provider"

        descriptions_data = {
            "public.users": {"description": "User table"},
        }

        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        assert result["imported"] is False
        assert "not started" in result["error"]

    @pytest.mark.asyncio
    async def test_import_descriptions_no_schema_file(self, temp_connection_dir, mock_connector):
        """Test importing when schema descriptions file doesn't exist."""
        provider_id = "test-provider"

        # Start and set phase to schema, but don't discover (no schema file created)
        await _onboarding_start(provider_id=provider_id)
        state = load_state(provider_id)
        state.phase = OnboardingPhase.SCHEMA
        from db_mcp.onboarding.state import save_state

        save_state(state)

        descriptions_data = {
            "public.users": {"description": "User table"},
        }

        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        assert result["imported"] is False
        assert "Schema descriptions not found" in result["error"]

    @pytest.mark.asyncio
    async def test_import_descriptions_empty_descriptions(self, temp_connection_dir, mock_connector):
        """Test importing with empty descriptions object."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        # Empty descriptions
        result = await _onboarding_import_descriptions(
            descriptions="{}",
            provider_id=provider_id,
        )

        assert result["imported"] is True
        assert result["tables_updated"] == 0
        assert result["columns_updated"] == 0
        assert result["tables_not_found"] == []
        assert result["columns_not_found"] == []
        assert result["parse_warnings"] == []  # No parsing warnings for empty but valid JSON

    @pytest.mark.asyncio
    async def test_import_descriptions_malformed_table_data(
        self, temp_connection_dir, mock_connector
    ):
        """Test importing with malformed table data structures."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        # Table data with mixed formats
        descriptions_data = {
            "public.users": "Simple table description",  # Simple string - now accepted
            "public.orders": {
                "description": "Order table",
                "columns": "not an object",  # Columns should be skipped with warning
            },
        }

        result = await _onboarding_import_descriptions(
            descriptions=json.dumps(descriptions_data),
            provider_id=provider_id,
        )

        assert result["imported"] is True
        assert result["tables_updated"] == 2  # Both tables processed (users as simple string, orders as object)
        assert result["columns_updated"] == 0  # No columns updated due to malformed data
        assert "parse_warnings" in result  # Should have warnings about malformed columns data

    @pytest.mark.asyncio
    async def test_import_descriptions_yaml_format(self, temp_connection_dir, mock_connector):
        """Test importing with YAML format."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        yaml_descriptions = '''public.users:
  description: User account information
  columns:
    id: Unique user identifier
    email: User's email address

public.orders:
  description: Customer order records
  columns:
    id: Unique order identifier
    user_id: Reference to users table
'''

        result = await _onboarding_import_descriptions(
            descriptions=yaml_descriptions,
            provider_id=provider_id,
        )

        assert result["imported"] is True
        assert result["tables_updated"] == 2
        assert result["columns_updated"] == 4
        assert result["parse_warnings"] == []

    @pytest.mark.asyncio
    async def test_import_descriptions_text_format(self, temp_connection_dir, mock_connector):
        """Test importing with simple text format."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        text_descriptions = '''public.users: User account information
public.orders: Customer order records
public.products: Product catalog
'''

        result = await _onboarding_import_descriptions(
            descriptions=text_descriptions,
            provider_id=provider_id,
        )

        assert result["imported"] is True
        assert result["tables_updated"] == 3
        assert result["columns_updated"] == 0  # No column descriptions in simple format
        assert result["phase"] == "domain"  # All tables described, advance to domain

    @pytest.mark.asyncio  
    async def test_import_descriptions_mixed_format_with_warnings(self, temp_connection_dir, mock_connector):
        """Test importing with messy input that generates warnings."""
        provider_id = "test-provider"
        await _setup_schema_phase(provider_id, mock_connector)

        messy_descriptions = '''public.users: User account information
  id: User ID
  email: Email address

: Empty table name should be skipped
public.orders -> Customer order records  
some garbage text without separator
'''

        result = await _onboarding_import_descriptions(
            descriptions=messy_descriptions,
            provider_id=provider_id,
        )

        assert result["imported"] is True
        assert result["tables_updated"] >= 2  # At least users and orders
        assert len(result["parse_warnings"]) > 0  # Should have warnings about empty keys and unparseable lines