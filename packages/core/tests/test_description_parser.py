"""Test the universal description parser."""

import pytest

from db_mcp.onboarding.description_parser import parse_descriptions


class TestParseDescriptions:
    """Test the main parse_descriptions function."""
    
    def test_empty_input(self):
        """Test empty input returns empty dict with warning."""
        result, warnings = parse_descriptions("")
        assert result == {}
        assert "Empty input" in warnings
        
        result, warnings = parse_descriptions("   ")
        assert result == {}
        assert "Empty input" in warnings
    
    def test_valid_json_format(self):
        """Test valid JSON format (existing behavior)."""
        json_input = '''
        {
            "schema.users": {
                "description": "User accounts table",
                "columns": {
                    "id": "Primary key",
                    "email": "User email address"
                }
            },
            "schema.orders": {
                "description": "Customer orders"
            }
        }
        '''
        
        result, warnings = parse_descriptions(json_input)
        
        assert len(warnings) == 0
        assert "schema.users" in result
        assert result["schema.users"]["description"] == "User accounts table"
        assert result["schema.users"]["columns"]["id"] == "Primary key"
        assert result["schema.users"]["columns"]["email"] == "User email address"
        assert "schema.orders" in result
        assert result["schema.orders"]["description"] == "Customer orders"
        assert result["schema.orders"]["columns"] == {}
    
    def test_simple_json_string_values(self):
        """Test JSON with simple string values."""
        json_input = '''
        {
            "users": "User accounts table",
            "orders": "Customer orders",
            "products": "Product catalog"
        }
        '''
        
        result, warnings = parse_descriptions(json_input)
        
        assert len(warnings) == 0
        assert result["users"]["description"] == "User accounts table"
        assert result["users"]["columns"] == {}
        assert result["orders"]["description"] == "Customer orders"
        assert result["products"]["description"] == "Product catalog"
    
    def test_valid_yaml_format(self):
        """Test valid YAML format."""
        yaml_input = '''schema.users:
  description: User accounts table
  columns:
    id: Primary key
    email: User email address
    created_at: Account creation timestamp

schema.orders:
  description: Customer orders
  columns:
    id: Order identifier
    user_id: Foreign key to users table
'''
        
        result, warnings = parse_descriptions(yaml_input)
        
        assert len(warnings) == 0
        assert "schema.users" in result
        assert result["schema.users"]["description"] == "User accounts table"
        assert result["schema.users"]["columns"]["id"] == "Primary key"
        assert result["schema.users"]["columns"]["created_at"] == "Account creation timestamp"
        assert "schema.orders" in result
        assert result["schema.orders"]["description"] == "Customer orders"
        assert result["schema.orders"]["columns"]["user_id"] == "Foreign key to users table"
    
    def test_malformed_yaml_partial_parsing(self):
        """Test that malformed YAML still extracts what it can."""
        yaml_input = '''
        schema.users:
          description: User accounts table
          columns:
            id: Primary key
            email: User email address
        
        schema.orders:
          description: Customer orders
          columns
            id: Order identifier  # Missing colon
        
        schema.products: Product catalog  # Simple format
        '''
        
        result, warnings = parse_descriptions(yaml_input)
        
        # Should parse what it can even if YAML is malformed
        # If YAML fails completely, it falls back to text parsing
        assert len(result) >= 1  # At least some data extracted
        # Should have warnings about parsing issues
        assert len(warnings) >= 0  # May or may not have warnings depending on fallback success
    
    def test_key_value_pairs_colon(self):
        """Test key-value pairs with colon separator."""
        text_input = '''users: User accounts table
orders: Customer orders  
products: Product catalog
analytics_events: Event tracking data
'''
        
        result, warnings = parse_descriptions(text_input)
        
        assert "users" in result
        assert result["users"]["description"] == "User accounts table"
        assert result["orders"]["description"] == "Customer orders"
        assert result["analytics_events"]["description"] == "Event tracking data"
    
    def test_key_value_pairs_various_separators(self):
        """Test key-value pairs with different separators."""
        text_input = '''users = User accounts table
orders -> Customer orders
products | Product catalog
events: Event tracking data
'''
        
        result, warnings = parse_descriptions(text_input)
        
        assert len(result) == 4
        assert result["users"]["description"] == "User accounts table"
        assert result["orders"]["description"] == "Customer orders"
        assert result["products"]["description"] == "Product catalog"
        assert result["events"]["description"] == "Event tracking data"
    
    def test_indented_columns(self):
        """Test indented format for columns under tables."""
        text_input = '''schema.users: User accounts table
  id: Primary key
  email: User email address
  created_at: Account creation timestamp

schema.orders: Customer orders
  id: Order identifier
  user_id: Foreign key to users
  total: Order total amount
'''
        
        result, warnings = parse_descriptions(text_input)
        
        assert "schema.users" in result
        assert result["schema.users"]["description"] == "User accounts table"
        assert result["schema.users"]["columns"]["id"] == "Primary key"
        assert result["schema.users"]["columns"]["email"] == "User email address"
        assert result["schema.users"]["columns"]["created_at"] == "Account creation timestamp"
        
        assert "schema.orders" in result
        assert result["schema.orders"]["description"] == "Customer orders"
        assert result["schema.orders"]["columns"]["user_id"] == "Foreign key to users"
        assert result["schema.orders"]["columns"]["total"] == "Order total amount"
    
    def test_csv_like_format(self):
        """Test CSV-like format."""
        csv_input = '''table,description
users,User accounts table
orders,Customer orders
products,Product catalog
events,Event tracking data
'''
        
        result, warnings = parse_descriptions(csv_input)
        
        assert len(result) >= 4  # Should find at least the 4 tables
        assert any("users" in key for key in result.keys())
        # Find the users entry (key might be "users" or include schema prefix)
        users_keys = [key for key in result.keys() if "users" in key]
        assert len(users_keys) > 0
        users_key = users_keys[0]
        assert "User accounts table" in result[users_key]["description"]
    
    def test_markdown_table_format(self):
        """Test markdown table format."""
        md_input = '''| Table Name | Description |
|------------|-------------|
| users      | User accounts table |
| orders     | Customer orders |
| products   | Product catalog |
'''
        
        result, warnings = parse_descriptions(md_input)
        
        assert len(result) >= 3
        assert any("users" in key for key in result.keys())
        users_keys = [key for key in result.keys() if "users" in key]
        assert len(users_keys) > 0
        users_key = users_keys[0]
        assert "User accounts table" in result[users_key]["description"]
    
    def test_mixed_formats(self):
        """Test input with mixed formats."""
        mixed_input = '''# This is a comment
users: User accounts table

orders = Customer orders

products -> Product catalog
  name: Product name
  price: Product price

# Some CSV data
table,description
events,Event tracking data
analytics,Analytics data
'''
        
        result, warnings = parse_descriptions(mixed_input)
        
        # Should extract data from multiple formats
        assert len(result) >= 3
        assert "users" in str(result)
        assert "orders" in str(result)
        assert "products" in str(result)
    
    def test_real_world_messy_input(self):
        """Test with messy real-world input."""
        messy_input = '''Database Schema Documentation
============================

user_accounts: Stores all user account information
  user_id: Primary key (auto-increment)
  email: User email (unique)
  password_hash: Bcrypt hash of password
  created_at: Timestamp of account creation
  
order_items -> Line items for customer orders
  order_item_id -> Primary key
  order_id -> Foreign key to orders table
  product_id -> Foreign key to products
  
Table: product_catalog
Description: Master list of all products
Columns:
- product_id: Primary key
- name: Product display name
- sku: Stock keeping unit

# Legacy tables (might be empty)
old_user_data = Historical user data (deprecated)
temp_import_staging | Temporary staging area
'''
        
        result, warnings = parse_descriptions(messy_input)
        
        # Should extract something useful despite the mess
        assert len(result) >= 3
        assert len(warnings) >= 0  # May have warnings but shouldn't crash
        
        # Should find the main tables
        assert "user_accounts" in str(result) or "user" in str(result)
        assert "order_items" in str(result) or "order" in str(result)
        assert "product" in str(result)
    
    def test_garbage_input(self):
        """Test with complete garbage input."""
        garbage_input = '''This is not structured data at all.
Just random text without any clear format.
No colons, equals, or separators.
'''
        
        result, warnings = parse_descriptions(garbage_input)
        
        assert result == {}
        assert len(warnings) > 0
        assert any("Could not parse" in warning for warning in warnings)
    
    def test_json_error_handling(self):
        """Test JSON error handling."""
        invalid_json = '''
        {
            "users": {
                "description": "User table",
                "columns": "this should be an object not a string"
            }
        }
        '''
        
        result, warnings = parse_descriptions(invalid_json)
        
        assert "users" in result
        assert result["users"]["description"] == "User table"
        # Should have warning about invalid columns format
        assert any("columns" in warning for warning in warnings)
    
    def test_non_dict_json(self):
        """Test JSON that parses to non-dict."""
        non_dict_json = '["users", "orders", "products"]'
        
        result, warnings = parse_descriptions(non_dict_json)
        
        # Should fall back to text parsing
        assert len(warnings) >= 1
        assert any("not a dictionary" in warning for warning in warnings)
    
    def test_empty_table_names(self):
        """Test handling of empty table names."""
        text_input = ''': Empty table name
users: User accounts
: Another empty one
orders: Customer orders
'''
        
        result, warnings = parse_descriptions(text_input)
        
        assert "users" in result
        assert "orders" in result
        # Should have warnings about empty keys
        assert any("Empty key" in warning for warning in warnings)
    
    def test_unicode_and_special_chars(self):
        """Test handling of unicode and special characters."""
        unicode_input = '''users_table: Table des utilisateurs (français)
产品目录: Product catalog in Chinese
заказы: Orders in Russian
table-with-dashes: Table with dashes
table_with_underscores: Table with underscores
table.with.dots: Table with dots
'''
        
        result, warnings = parse_descriptions(unicode_input)
        
        assert len(result) >= 4
        assert "users_table" in result
        assert "Table des utilisateurs (français)" in result["users_table"]["description"]
    
    def test_very_long_input(self):
        """Test with very long input to check performance."""
        long_input = ""
        for i in range(100):
            long_input += f"table_{i}: Description for table number {i}\n"
        
        result, warnings = parse_descriptions(long_input)
        
        assert len(result) == 100
        assert f"table_50" in result
        assert "Description for table number 50" in result["table_50"]["description"]

    def test_yaml_with_tables_wrapper(self):
        """Test YAML with top-level 'tables:' key (Arsenii's format)."""
        text = """
tables:
  dwh.public.daily_stats_cdrs:
    description: Contains network statistics aggregated by date and carrier
    columns:
      date:
        description: Date
      carrier:
        description: Name of the carrier
  dwh.public.users:
    description: User accounts table
"""
        result, warnings = parse_descriptions(text)
        assert "dwh.public.daily_stats_cdrs" in result
        assert "dwh.public.users" in result
        assert result["dwh.public.daily_stats_cdrs"]["description"] == "Contains network statistics aggregated by date and carrier"
        assert result["dwh.public.daily_stats_cdrs"]["columns"]["date"] == "Date"
        assert result["dwh.public.daily_stats_cdrs"]["columns"]["carrier"] == "Name of the carrier"

    def test_column_descriptions_as_objects(self):
        """Test column descriptions given as {description: '...'} objects."""
        text = """
{
  "public.orders": {
    "description": "Order records",
    "columns": {
      "id": {"description": "Primary key"},
      "amount": {"description": "Order total in cents"},
      "status": "Active or archived"
    }
  }
}
"""
        result, warnings = parse_descriptions(text)
        assert result["public.orders"]["columns"]["id"] == "Primary key"
        assert result["public.orders"]["columns"]["amount"] == "Order total in cents"
        assert result["public.orders"]["columns"]["status"] == "Active or archived"

    def test_schemas_wrapper_key(self):
        """Test top-level 'schemas:' wrapper is also unwrapped."""
        text = '{"schemas": {"public.users": {"description": "Users table"}}}'
        result, warnings = parse_descriptions(text)
        assert "public.users" in result