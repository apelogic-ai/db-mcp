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

    @patch('db_mcp.tools.utils.resolve_connection')
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

    @patch('db_mcp.tools.utils.resolve_connection')
    def test_invalid_connection_raises_value_error(self, mock_resolve, temp_connection_dir):
        """Test that an invalid connection parameter raises ValueError."""
        # Arrange
        mock_resolve.side_effect = ValueError("Connection 'nonexistent' not found")

        # Act & Assert
        with pytest.raises(ValueError, match="Connection 'nonexistent' not found"):
            _resolve_onboarding_context(connection="nonexistent")

    @patch('db_mcp.tools.onboarding.get_settings')
    @patch('db_mcp.tools.onboarding.get_connector')
    @patch('db_mcp.onboarding.state.get_connection_path')
    def test_none_connection_uses_legacy_path(
        self,
        mock_get_connection_path,
        mock_get_connector,
        mock_get_settings,
        temp_connection_dir
    ):
        """Test that connection=None uses the legacy path."""
        # Arrange
        mock_settings = MagicMock()
        mock_settings.provider_id = "test_provider"
        mock_get_settings.return_value = mock_settings

        mock_connector = MagicMock()
        mock_get_connector.return_value = mock_connector

        mock_get_connection_path.return_value = "/path/to/connection"

        # Act
        result = _resolve_onboarding_context(connection=None)

        # Assert
        connector, provider_id, conn_path = result
        assert connector == mock_connector
        assert provider_id == "test_provider"
        assert conn_path == "/path/to/connection"

        mock_get_settings.assert_called_once()
        mock_get_connector.assert_called_once()
        mock_get_connection_path.assert_called_once()

    @patch('db_mcp.tools.onboarding.get_settings')
    @patch('db_mcp.tools.onboarding.get_connector')
    @patch('db_mcp.onboarding.state.get_connection_path')
    def test_none_connection_with_provider_id_uses_legacy_path(
        self,
        mock_get_connection_path,
        mock_get_connector,
        mock_get_settings,
        temp_connection_dir
    ):
        """Test that connection=None with explicit provider_id uses the legacy path."""
        # Arrange
        # Should not be called since provider_id is provided
        mock_get_settings.return_value = MagicMock()

        mock_connector = MagicMock()
        mock_get_connector.return_value = mock_connector

        mock_get_connection_path.return_value = "/path/to/connection"

        # Act
        result = _resolve_onboarding_context(connection=None, provider_id="explicit_provider")

        # Assert
        connector, provider_id, conn_path = result
        assert connector == mock_connector
        assert provider_id == "explicit_provider"
        assert conn_path == "/path/to/connection"

        # get_settings should not be called when provider_id is explicitly provided
        mock_get_settings.assert_not_called()
        mock_get_connector.assert_called_once()
        mock_get_connection_path.assert_called_once()

    def test_no_silent_fallback_from_resolve_connection_error(self, temp_connection_dir):
        """Test that ValueError from resolve_connection is not silently caught."""
        # This is the key test for the bug fix - ensure that when a connection
        # is explicitly provided but resolve_connection fails, we raise the error
        # instead of silently falling back to the legacy path

        with patch('db_mcp.tools.utils.resolve_connection') as mock_resolve:
            mock_resolve.side_effect = ValueError("Connection 'nova' not found")

            # This should raise ValueError, not fall back to legacy path
            with pytest.raises(ValueError, match="Connection 'nova' not found"):
                _resolve_onboarding_context(connection="nova")
