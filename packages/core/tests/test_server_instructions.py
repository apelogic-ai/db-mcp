"""Tests that server instructions adapt based on connector capabilities."""

from db_mcp.server import (
    INSTRUCTIONS_SHELL_MODE,
    _strip_validate_sql_from_instructions,
)


def test_instructions_omit_validate_when_unsupported():
    """When supports_validate_sql=false, instructions drop validate_sql."""
    result = _strip_validate_sql_from_instructions(INSTRUCTIONS_SHELL_MODE)

    assert "validate_sql" not in result
    assert 'run_sql(sql="...")' in result


def test_instructions_keep_validate_when_supported():
    """Default instructions include validate_sql workflow."""
    assert "validate_sql" in INSTRUCTIONS_SHELL_MODE
    assert 'run_sql(query_id="...")' in INSTRUCTIONS_SHELL_MODE
