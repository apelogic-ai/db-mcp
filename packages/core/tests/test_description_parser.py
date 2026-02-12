"""Test the universal description parser."""

import json

import pytest

from db_mcp.onboarding.description_parser import parse_descriptions


@pytest.fixture()
def known_tables():
    return {
        "dwh.public.daily_stats_cdrs": ["date", "carrier", "call_count"],
        "public.users": ["id", "username", "email"],
        "schema.orders": ["id", "amount", "status"],
        "core.customers": ["customer_id", "name", "email"],
    }


# ── Basic edge cases ──


def test_empty_input(known_tables):
    result, warnings = parse_descriptions("", known_tables)
    assert result == {}
    assert "Empty input" in warnings

    result, warnings = parse_descriptions("   \n", known_tables)
    assert result == {}
    assert warnings


def test_no_known_tables():
    result, warnings = parse_descriptions("some text", {})
    assert result == {}
    assert any("No known tables" in w for w in warnings)


def test_garbage_input_no_matches(known_tables):
    result, warnings = parse_descriptions("asdf qwer zxcv", known_tables)
    assert result == {}
    assert any("No matching tables" in w for w in warnings)


# ── Full table name matching ──


def test_full_table_name_yaml_style(known_tables):
    text = """
dwh.public.daily_stats_cdrs:
  description: Contains network statistics aggregated by date and carrier
  columns:
    date:
      description: The specific date for the statistics
    carrier:
      description: Name of the telecommunications carrier
    call_count:
      description: Number of calls processed that day
"""
    result, _ = parse_descriptions(text, known_tables)
    assert "dwh.public.daily_stats_cdrs" in result
    entry = result["dwh.public.daily_stats_cdrs"]
    assert "network statistics" in entry["description"]
    assert entry["columns"]["date"] == "The specific date for the statistics"
    assert entry["columns"]["carrier"] == "Name of the telecommunications carrier"
    assert entry["columns"]["call_count"] == "Number of calls processed that day"


def test_full_table_name_in_prose(known_tables):
    text = """
    The dwh.public.daily_stats_cdrs table contains network statistics aggregated by date.
    - date: The specific date for the statistics
    - carrier: Name of the telecommunications carrier
    """
    result, _ = parse_descriptions(text, known_tables)
    assert "dwh.public.daily_stats_cdrs" in result
    assert "network statistics" in result["dwh.public.daily_stats_cdrs"]["description"]
    assert result["dwh.public.daily_stats_cdrs"]["columns"]["date"] == "The specific date for the statistics"


# ── Short table name matching ──


def test_short_table_name_matching(known_tables):
    text = """
    users: User account information
    - username: Unique login identifier
    - email: Contact email address
    """
    result, _ = parse_descriptions(text, known_tables)
    assert "public.users" in result
    assert "User account information" in result["public.users"]["description"]
    assert result["public.users"]["columns"]["username"] == "Unique login identifier"


# ── YAML formats ──


def test_yaml_with_tables_wrapper(known_tables):
    text = """
tables:
  dwh.public.daily_stats_cdrs:
    description: Contains network statistics aggregated by date and carrier
    columns:
      date:
        description: Date
      carrier:
        description: Name of the carrier
"""
    result, _ = parse_descriptions(text, known_tables)
    assert "dwh.public.daily_stats_cdrs" in result
    assert "network statistics" in result["dwh.public.daily_stats_cdrs"]["description"]
    assert result["dwh.public.daily_stats_cdrs"]["columns"]["date"] == "Date"
    assert result["dwh.public.daily_stats_cdrs"]["columns"]["carrier"] == "Name of the carrier"


def test_yaml_block_scalar():
    """YAML block scalar (|) treated as text."""
    kt = {"dwh.public.daily_stats_cdrs": ["date", "carrier"]}
    text = """
dwh.public.daily_stats_cdrs:
  description: |
    Contains network statistics aggregated by date and carrier
  columns:
    date:
      description: Date
    carrier:
      description: Name of the carrier
"""
    result, _ = parse_descriptions(text, kt)
    assert "dwh.public.daily_stats_cdrs" in result
    assert "network statistics" in result["dwh.public.daily_stats_cdrs"]["description"]
    assert result["dwh.public.daily_stats_cdrs"]["columns"]["date"] == "Date"


# ── JSON format ──


def test_json_format(known_tables):
    """JSON treated as text — table names and descriptions are extracted."""
    text = """{
  "orders": {
    "description": "Order records from the e-commerce system",
    "columns": {
      "amount": "Order total in cents",
      "status": "Processing status"
    }
  }
}"""
    result, _ = parse_descriptions(text, known_tables)
    assert "schema.orders" in result
    assert "e-commerce system" in result["schema.orders"]["description"]
    assert result["schema.orders"]["columns"]["amount"] == "Order total in cents"
    assert result["schema.orders"]["columns"]["status"] == "Processing status"


def test_json_nested_structure(known_tables):
    payload = {
        "database_schema": {
            "orders": {
                "info": "Order records from the e-commerce system",
                "fields": {"amount": "Order total in cents", "status": "Processing status"},
            }
        }
    }
    text = json.dumps(payload)
    result, _ = parse_descriptions(text, known_tables)
    assert "schema.orders" in result
    # The "info" field is similar to "description" — parser should find it
    assert result["schema.orders"]["columns"]["amount"] == "Order total in cents"


# ── Key-value / indented formats ──


def test_key_value_with_indented_columns():
    kt = {
        "public.users": ["id", "email", "name"],
        "public.orders": ["id", "user_id", "total"],
    }
    text = """
users: This is the user accounts table
  id: Primary key for users
  email: User's email address
  name: Full name of the user

orders: Customer order records
  total: Order total in cents
"""
    result, _ = parse_descriptions(text, kt)
    assert "public.users" in result
    assert "public.orders" in result
    assert "user accounts" in result["public.users"]["description"]
    assert result["public.users"]["columns"]["email"] == "User's email address"
    assert result["public.orders"]["columns"]["total"] == "Order total in cents"


# ── Markdown format ──


def test_markdown_bullet_list():
    kt = {
        "public.users": ["id", "username", "email"],
        "public.posts": ["id", "title", "content"],
    }
    text = """
## users
User account information

- username: Unique login identifier
- email: Contact email address

## posts
Blog post data

- title: Post headline
- content: Full post body text
"""
    result, _ = parse_descriptions(text, kt)
    assert "public.users" in result
    assert "public.posts" in result
    assert result["public.users"]["columns"]["username"] == "Unique login identifier"
    assert result["public.posts"]["columns"]["title"] == "Post headline"


# ── Fuzzy matching ──


def test_fuzzy_matching_underscores_vs_spaces_and_case():
    kt = {"data.user_profiles": ["user_id", "first_name"]}
    text = """
USER PROFILES: Stores detailed user profile information
  user id: Primary key
  first name: Given name
"""
    result, _ = parse_descriptions(text, kt)
    assert "data.user_profiles" in result
    assert "Stores detailed" in result["data.user_profiles"]["description"]
    assert result["data.user_profiles"]["columns"]["user_id"] == "Primary key"
    assert result["data.user_profiles"]["columns"]["first_name"] == "Given name"


# ── Column scoping ──


def test_column_scoping_to_table_context():
    kt = {
        "public.users": ["id", "name", "email"],
        "public.orders": ["id", "name", "amount"],
    }
    text = """
users: User accounts table
  id: User primary key
  name: User full name
  email: User email address

orders: Purchase records table
  id: Order identifier
  name: Order display name
  amount: Total cost
"""
    result, _ = parse_descriptions(text, kt)
    assert result["public.users"]["columns"]["id"] == "User primary key"
    assert result["public.users"]["columns"]["name"] == "User full name"
    assert result["public.orders"]["columns"]["id"] == "Order identifier"
    assert result["public.orders"]["columns"]["name"] == "Order display name"


# ── Wiki/data dictionary formats ──


def test_wiki_page_format():
    kt = {
        "reporting.daily_metrics": ["metric_date", "metric_name", "metric_value"],
        "reporting.user_stats": ["user_id", "login_count", "last_seen"],
    }
    text = """
=== daily_metrics ===
Daily aggregated metrics for business intelligence.

* metric_date - The date for which metrics were calculated
* metric_name - Name of the specific metric being tracked
* metric_value - Numerical value of the metric

=== user_stats ===
User activity statistics for the platform

* login_count - Number of times user has logged in
* last_seen - Timestamp of most recent activity
"""
    result, _ = parse_descriptions(text, kt)
    assert "reporting.daily_metrics" in result
    assert "reporting.user_stats" in result
    assert result["reporting.daily_metrics"]["columns"]["metric_date"] == "The date for which metrics were calculated"
    assert result["reporting.user_stats"]["columns"]["login_count"] == "Number of times user has logged in"


def test_data_dictionary_format():
    kt = {
        "prod.customers": ["customer_id", "company_name", "industry"],
        "prod.contracts": ["contract_id", "start_date", "end_date"],
    }
    text = """
customers: Master customer information
  customer_id: Primary key, auto-generated
  company_name: Legal company name
  industry: Industry classification code

contracts: Customer contract records
  start_date: Contract effective date
  end_date: Contract expiration date
"""
    result, _ = parse_descriptions(text, kt)
    assert "prod.customers" in result
    assert "prod.contracts" in result
    assert "Master customer" in result["prod.customers"]["description"]
    assert result["prod.customers"]["columns"]["customer_id"] == "Primary key, auto-generated"
    assert result["prod.contracts"]["columns"]["start_date"] == "Contract effective date"


# ── Multiple schemas with same table name ──


def test_multiple_schemas_same_table_name():
    kt = {
        "public.users": ["id", "email"],
        "admin.users": ["id", "role"],
        "archive.users": ["id", "deleted_at"],
    }
    text = """
public.users: Main user accounts
  email: Primary email address

admin.users: Administrative user accounts
  role: User's administrative role

archive.users: Deleted user records
  deleted_at: When the user was archived
"""
    result, _ = parse_descriptions(text, kt)
    assert "public.users" in result
    assert "admin.users" in result
    assert "archive.users" in result
    assert result["public.users"]["columns"]["email"] == "Primary email address"
    assert result["admin.users"]["columns"]["role"] == "User's administrative role"
    assert result["archive.users"]["columns"]["deleted_at"] == "When the user was archived"


# ── Partial matches ──


def test_partial_table_matches():
    kt = {
        "dwh.users": ["id", "email"],
        "dwh.orders": ["id", "total"],
        "dwh.products": ["id", "name"],
    }
    text = """
users: User account records
  email: User's email address

orders: Customer purchase data
"""
    result, _ = parse_descriptions(text, kt)
    assert "dwh.users" in result
    assert "dwh.orders" in result
    assert "dwh.products" not in result
