"""Tests for context file usage tracking functionality."""

from db_mcp.bicp.traces import extract_context_paths


def test_extract_context_paths_grep_with_path():
    """Test extracting paths from grep commands."""
    # Basic grep with quoted pattern
    command = 'grep -ri "venue" examples/'
    result = extract_context_paths(command)
    assert result == ["venue"]

    # Multiple words
    command = 'grep -rn "revenue profit" schema/ examples/'
    result = extract_context_paths(command)
    assert result == ["revenue", "profit"]

    # Single quotes
    command = "grep -i 'CUI' schema/"
    result = extract_context_paths(command)
    assert result == ["cui"]


def test_extract_context_paths_cat_with_path():
    """Test extracting paths from cat commands."""
    command = 'cat examples/revenue.yaml'
    result = extract_context_paths(command)
    assert result == []  # cat doesn't extract search terms, only grep/find

    # But if it's looking at context dirs, we want to extract the filename concepts
    command = 'cat schema/users.yaml'
    result = extract_context_paths(command)
    assert result == []  # For now, we only extract from grep/find search commands


def test_extract_context_paths_find_command():
    """Test extracting paths from find commands."""
    command = 'find examples -name "*cui*"'
    result = extract_context_paths(command)
    assert result == ["cui"]

    command = 'find schema -iname "*revenue*"'
    result = extract_context_paths(command)
    assert result == ["revenue"]

    # Multiple patterns
    command = 'find . -name "*user*" -o -name "*customer*"'
    result = extract_context_paths(command)
    assert result == ["user", "customer"]


def test_extract_context_paths_ls_command():
    """Test extracting paths from ls commands."""
    # Basic ls doesn't extract search terms
    command = 'ls examples/'
    result = extract_context_paths(command)
    assert result == []

    # ls with grep
    command = 'ls examples/ | grep revenue'
    result = extract_context_paths(command)
    assert result == ["revenue"]


def test_extract_context_paths_no_context():
    """Test commands with no context file search terms."""
    # Regular commands
    command = 'ls -la'
    result = extract_context_paths(command)
    assert result == []

    # Git commands
    command = 'git status'
    result = extract_context_paths(command)
    assert result == []

    # Grep in non-context directories
    command = 'grep -r "test" /tmp/'
    result = extract_context_paths(command)
    assert result == ["test"]  # We extract search terms regardless of directory


def test_extract_context_paths_regex_patterns():
    """Test handling of regex patterns in grep."""
    # Word boundaries
    command = r'grep -r "cui\b\|CUI\b" schema/'
    result = extract_context_paths(command)
    assert result == ["cui", "cui"]  # Both variations

    # Escape sequences
    command = r'grep -r "nas_id\|nasid" examples/'
    result = extract_context_paths(command)
    assert result == ["nas_id", "nasid"]


def test_extract_context_paths_filter_stopwords():
    """Test filtering of generic/stop words."""
    # Should filter out structural words
    command = 'grep -r "table" schema/'
    result = extract_context_paths(command)
    assert result == []  # "table" is a stop word

    # Should filter out SQL keywords
    command = 'grep -r "select" examples/'
    result = extract_context_paths(command)
    assert result == []

    # Should keep business terms
    command = 'grep -r "revenue" examples/'
    result = extract_context_paths(command)
    assert result == ["revenue"]


def test_extract_context_paths_edge_cases():
    """Test edge cases and malformed commands."""
    # Empty command
    result = extract_context_paths("")
    assert result == []

    # No quotes
    command = 'grep -r revenue examples/'
    result = extract_context_paths(command)
    assert result == []  # No quoted patterns

    # File paths in quotes (should be filtered)
    command = 'grep -r "examples/revenue.yaml" .'
    result = extract_context_paths(command)
    assert result == []  # Has "/" so filtered out

    # Very short terms
    command = 'grep -r "a" examples/'
    result = extract_context_paths(command)
    assert result == []  # Single character filtered out


def test_extract_context_paths_multiple_patterns():
    """Test commands with multiple search patterns."""
    command = 'grep -r "revenue\\|profit\\|income" examples/'
    result = extract_context_paths(command)
    expected = ["revenue", "profit", "income"]
    assert result == expected


def test_extract_context_paths_case_handling():
    """Test case normalization."""
    command = 'grep -r "Revenue\\|PROFIT\\|Income" examples/'
    result = extract_context_paths(command)
    expected = ["revenue", "profit", "income"]
    assert result == expected


if __name__ == "__main__":
    # Quick test run
    test_extract_context_paths_grep_with_path()
    test_extract_context_paths_find_command()
    test_extract_context_paths_filter_stopwords()
    print("All tests passed!")
