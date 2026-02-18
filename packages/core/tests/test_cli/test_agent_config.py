"""Tests for db_mcp.cli.agent_config module.

Tests extract_database_url_from_claude_config, _configure_agents_interactive,
and _configure_claude_desktop with mocked dependencies.
"""

from unittest.mock import MagicMock, patch

import pytest

from db_mcp.cli.agent_config import (
    _configure_claude_desktop,
    _configure_agents_interactive,
    extract_database_url_from_claude_config,
)


class TestExtractDatabaseUrlFromClaudeConfig:
    def test_returns_url_when_db_mcp_entry_present(self):
        config = {
            "mcpServers": {
                "db-mcp": {
                    "command": "/usr/local/bin/db-mcp",
                    "args": ["start"],
                    "env": {
                        "DATABASE_URL": "postgresql://user:pass@localhost/mydb",
                    },
                }
            }
        }
        result = extract_database_url_from_claude_config(config)
        assert result == "postgresql://user:pass@localhost/mydb"

    def test_returns_none_when_no_mcp_servers_key(self):
        config = {}
        result = extract_database_url_from_claude_config(config)
        assert result is None

    def test_returns_none_when_mcp_servers_empty(self):
        config = {"mcpServers": {}}
        result = extract_database_url_from_claude_config(config)
        assert result is None

    def test_returns_none_when_db_mcp_entry_missing(self):
        config = {
            "mcpServers": {
                "other-server": {
                    "command": "/usr/bin/other",
                    "env": {"DATABASE_URL": "postgresql://other/db"},
                }
            }
        }
        result = extract_database_url_from_claude_config(config)
        assert result is None

    def test_returns_none_when_db_mcp_has_no_env(self):
        config = {
            "mcpServers": {
                "db-mcp": {
                    "command": "/usr/local/bin/db-mcp",
                }
            }
        }
        result = extract_database_url_from_claude_config(config)
        assert result is None

    def test_returns_none_when_env_has_no_database_url(self):
        config = {
            "mcpServers": {
                "db-mcp": {
                    "command": "/usr/local/bin/db-mcp",
                    "env": {"OTHER_VAR": "value"},
                }
            }
        }
        result = extract_database_url_from_claude_config(config)
        assert result is None

    def test_handles_malformed_config_with_non_dict_mcp_servers(self):
        # mcpServers is not a dict — .get() still works on dict, but if
        # someone passes a non-dict config it should not raise.
        config = {"mcpServers": None}
        # dict.get on None will AttributeError; but the function does
        # claude_config.get("mcpServers", {}) → {} when None is returned by
        # the outer get, so let's validate actual behaviour.
        # The function uses .get() which returns None, then checks "db-mcp" in None.
        # This raises TypeError. Confirm the function raises (documents current behaviour).
        with pytest.raises((TypeError, AttributeError)):
            extract_database_url_from_claude_config(config)

    def test_handles_extra_mcp_servers_alongside_db_mcp(self):
        config = {
            "mcpServers": {
                "some-other": {"command": "/bin/other"},
                "db-mcp": {
                    "env": {"DATABASE_URL": "sqlite:///path/to/db.sqlite"}
                },
            }
        }
        result = extract_database_url_from_claude_config(config)
        assert result == "sqlite:///path/to/db.sqlite"


class TestConfigureAgentsInteractive:
    @patch("db_mcp.cli.agent_config.detect_installed_agents", return_value=[])
    def test_returns_empty_list_when_no_agents_detected(self, mock_detect):
        result = _configure_agents_interactive()
        assert result == []
        mock_detect.assert_called_once()

    @patch("db_mcp.cli.agent_config.detect_installed_agents", return_value=["claude-desktop"])
    @patch("db_mcp.cli.agent_config.AGENTS", {
        "claude-desktop": MagicMock(name="Claude Desktop"),
    })
    @patch("rich.prompt.Prompt.ask", return_value="1")
    def test_returns_all_agents_when_choice_is_1(self, mock_ask, mock_detect):
        result = _configure_agents_interactive()
        assert result == ["claude-desktop"]

    @patch("db_mcp.cli.agent_config.detect_installed_agents", return_value=["claude-desktop"])
    @patch("db_mcp.cli.agent_config.AGENTS", {
        "claude-desktop": MagicMock(name="Claude Desktop"),
    })
    @patch("rich.prompt.Prompt.ask", return_value="3")
    def test_returns_empty_list_when_choice_is_skip(self, mock_ask, mock_detect):
        result = _configure_agents_interactive()
        assert result == []

    @patch("db_mcp.cli.agent_config.detect_installed_agents", return_value=["claude-desktop", "cursor"])
    @patch("db_mcp.cli.agent_config.AGENTS", {
        "claude-desktop": MagicMock(name="Claude Desktop"),
        "cursor": MagicMock(name="Cursor"),
    })
    @patch("rich.prompt.Confirm.ask", return_value=True)
    @patch("rich.prompt.Prompt.ask", return_value="2")
    def test_individual_selection_all_confirmed(self, mock_ask, mock_confirm, mock_detect):
        result = _configure_agents_interactive()
        assert result == ["claude-desktop", "cursor"]

    @patch("db_mcp.cli.agent_config.detect_installed_agents", return_value=["claude-desktop", "cursor"])
    @patch("db_mcp.cli.agent_config.AGENTS", {
        "claude-desktop": MagicMock(name="Claude Desktop"),
        "cursor": MagicMock(name="Cursor"),
    })
    @patch("rich.prompt.Confirm.ask", side_effect=[True, False])
    @patch("rich.prompt.Prompt.ask", return_value="2")
    def test_individual_selection_partial(self, mock_ask, mock_confirm, mock_detect):
        result = _configure_agents_interactive()
        assert result == ["claude-desktop"]

    @patch("db_mcp.cli.agent_config.detect_installed_agents", return_value=["claude-desktop"])
    @patch("db_mcp.cli.agent_config.AGENTS", {
        "claude-desktop": MagicMock(name="Claude Desktop"),
    })
    @patch("rich.prompt.Prompt.ask", return_value="1")
    def test_preselect_installed_parameter_accepted(self, mock_ask, mock_detect):
        # Verify the preselect_installed param doesn't cause errors
        result = _configure_agents_interactive(preselect_installed=False)
        assert isinstance(result, list)


class TestConfigureClaudeDesktop:
    @patch("db_mcp.cli.agent_config.get_db_mcp_binary_path", return_value="/usr/local/bin/db-mcp")
    @patch("db_mcp.agents.configure_agent_for_dbmcp")
    def test_calls_configure_agent_for_claude_desktop(self, mock_configure, mock_binary):
        _configure_claude_desktop("mydb")
        mock_configure.assert_called_once_with("claude-desktop", "/usr/local/bin/db-mcp")

    @patch("db_mcp.cli.agent_config.get_db_mcp_binary_path", return_value="/custom/path/db-mcp")
    @patch("db_mcp.agents.configure_agent_for_dbmcp")
    def test_uses_binary_path_from_helper(self, mock_configure, mock_binary):
        _configure_claude_desktop("anything")
        mock_binary.assert_called_once()
        # confirm the binary path was passed through
        call_args = mock_configure.call_args[0]
        assert "/custom/path/db-mcp" in call_args
