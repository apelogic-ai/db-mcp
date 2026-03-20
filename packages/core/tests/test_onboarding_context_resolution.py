"""Tests for _resolve_onboarding_context function."""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from db_mcp.tools.onboarding import _resolve_onboarding_context


@pytest.fixture
def temp_connection_dir(monkeypatch):
    """Create a temporary connection directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("CONNECTION_PATH", tmpdir)

        # Clear cached settings
        import db_mcp.config

        db_mcp.config._cached_settings = None

        yield tmpdir


class TestResolveOnboardingContext:
    """Test _resolve_onboarding_context behavior."""

    @patch("db_mcp.tools.utils.resolve_connection")
    def test_valid_connection_resolves_correctly(self, mock_resolve, temp_connection_dir):
        """Test that a valid connection parameter resolves correctly."""
        # Arrange
        mock_connector = MagicMock()
        mock_resolve.return_value = (mock_connector, "playground", "/path/to/playground")

        # Act
        result = _resolve_onboarding_context(connection="playground")

        # Assert
        mock_resolve.assert_called_once_with("playground")
        connector, conn_name, conn_path = result
        assert connector == mock_connector
        assert conn_name == "playground"
        assert conn_path == "/path/to/playground"

    @patch("db_mcp.tools.utils.resolve_connection")
    def test_invalid_connection_raises_value_error(self, mock_resolve, temp_connection_dir):
        """Test that an invalid connection parameter raises ValueError."""
        # Arrange
        mock_resolve.side_effect = ValueError("Connection 'nonexistent' not found")

        # Act & Assert
        with pytest.raises(ValueError, match="Connection 'nonexistent' not found"):
            _resolve_onboarding_context(connection="nonexistent")

    def test_none_connection_uses_legacy_path(self, temp_connection_dir):
        """Test that connection=None now raises ValueError."""
        with pytest.raises(ValueError, match="requires connection"):
            _resolve_onboarding_context(connection=None)

    def test_none_connection_with_provider_id_uses_legacy_path(self, temp_connection_dir):
        """Test that connection=None with explicit provider_id now raises ValueError."""
        with pytest.raises(ValueError, match="requires connection"):
            _resolve_onboarding_context(connection=None, provider_id="explicit_provider")

    def test_no_silent_fallback_from_resolve_connection_error(self, temp_connection_dir):
        """Test that ValueError from resolve_connection is not silently caught."""
        # This is the key test for the bug fix - ensure that when a connection
        # is explicitly provided but resolve_connection fails, we raise the error
        # instead of silently falling back to the legacy path

        with patch("db_mcp.tools.utils.resolve_connection") as mock_resolve:
            mock_resolve.side_effect = ValueError("Connection 'missing_connection' not found")

            # This should raise ValueError, not fall back to legacy path
            with pytest.raises(
                ValueError, match="Connection 'missing_connection' not found"
            ):
                _resolve_onboarding_context(connection="missing_connection")
