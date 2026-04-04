"""Tests for SQL statement classification and write-policy enforcement."""

from db_mcp_data.validation.explain import analyze_sql_statement, validate_sql_permissions


def test_show_create_table_is_classified_as_read():
    statement_type, is_write = analyze_sql_statement("SHOW CREATE TABLE users")
    assert statement_type == "SHOW"
    assert is_write is False


def test_show_create_table_is_allowed_in_read_only_mode():
    valid, error, statement_type, is_write = validate_sql_permissions(
        "SHOW CREATE TABLE users",
        capabilities={"allow_sql_writes": False},
    )
    assert valid is True
    assert error is None
    assert statement_type == "SHOW"
    assert is_write is False


def test_union_all_is_allowed_as_read():
    """UNION / UNION ALL / INTERSECT / EXCEPT are read-only set operations."""
    for sql in [
        "SELECT 1 UNION ALL SELECT 2",
        "SELECT 1 UNION SELECT 2",
        "SELECT 1 INTERSECT SELECT 2",
        "SELECT 1 EXCEPT SELECT 2",
    ]:
        valid, error, statement_type, is_write = validate_sql_permissions(
            sql, capabilities={"allow_sql_writes": False}
        )
        assert valid is True, f"Expected valid=True for {sql!r}, got error={error!r}"
        assert is_write is False
        assert statement_type in {"UNION", "INTERSECT", "EXCEPT"}


def test_insert_is_blocked_when_write_mode_disabled():
    valid, error, statement_type, is_write = validate_sql_permissions(
        "INSERT INTO users(id) VALUES (1)",
        capabilities={"allow_sql_writes": False},
    )
    assert valid is False
    assert "not allowed" in (error or "").lower()
    assert statement_type == "INSERT"
    assert is_write is True
