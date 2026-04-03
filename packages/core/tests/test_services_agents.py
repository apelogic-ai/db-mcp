"""Tests for services/agents.py — agent config service functions.

Step 4.07: Replace agent config handlers with service calls (5 methods).
"""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# list_agents
# ---------------------------------------------------------------------------


class TestListAgents:
    def test_returns_agent_list(self):
        from db_mcp.services.agents import list_agents

        fake_agent = MagicMock()
        fake_agent.name = "Claude Desktop"
        fake_agent.config_path = MagicMock()
        fake_agent.config_path.exists.return_value = True
        fake_agent.detect_fn.return_value = True
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        fake_agents = {"claude-desktop": fake_agent}
        fake_config = {"mcpServers": {"db-mcp": {"command": "/bin/db-mcp"}}}

        with (
            patch("db_mcp.services.agents._get_agents", return_value=fake_agents),
            patch("db_mcp.services.agents._load_agent_config", return_value=fake_config),
        ):
            result = list_agents()

        assert "agents" in result
        assert len(result["agents"]) == 1
        a = result["agents"][0]
        assert a["id"] == "claude-desktop"
        assert a["name"] == "Claude Desktop"
        assert a["installed"] is True
        assert a["configExists"] is True
        assert a["dbmcpConfigured"] is True
        assert a["binaryPath"] == "/bin/db-mcp"
        assert a["configFormat"] == "json"

    def test_agent_not_installed(self):
        from db_mcp.services.agents import list_agents

        fake_agent = MagicMock()
        fake_agent.name = "Claude Desktop"
        fake_agent.config_path = MagicMock()
        fake_agent.config_path.exists.return_value = False
        fake_agent.detect_fn.return_value = False
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": fake_agent},
            ),
            patch("db_mcp.services.agents._load_agent_config", return_value={}),
        ):
            result = list_agents()

        a = result["agents"][0]
        assert a["installed"] is False
        assert a["configExists"] is False
        assert a["dbmcpConfigured"] is False
        assert a["binaryPath"] is None

    def test_agent_configured_but_no_binary(self):
        from db_mcp.services.agents import list_agents

        fake_agent = MagicMock()
        fake_agent.name = "Claude Code"
        fake_agent.config_path = MagicMock()
        fake_agent.config_path.exists.return_value = True
        fake_agent.detect_fn.return_value = True
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        fake_config = {"mcpServers": {"db-mcp": {}}}  # no "command" key

        with (
            patch("db_mcp.services.agents._get_agents", return_value={"claude-code": fake_agent}),
            patch("db_mcp.services.agents._load_agent_config", return_value=fake_config),
        ):
            result = list_agents()

        a = result["agents"][0]
        assert a["dbmcpConfigured"] is True
        assert a["binaryPath"] is None

    def test_agent_no_detect_fn(self):
        from db_mcp.services.agents import list_agents

        fake_agent = MagicMock()
        fake_agent.name = "Codex"
        fake_agent.config_path = MagicMock()
        fake_agent.config_path.exists.return_value = False
        fake_agent.detect_fn = None  # no detection function
        fake_agent.config_key = "mcp_servers"
        fake_agent.config_format = "toml"

        with (
            patch("db_mcp.services.agents._get_agents", return_value={"codex": fake_agent}),
            patch("db_mcp.services.agents._load_agent_config", return_value={}),
        ):
            result = list_agents()

        a = result["agents"][0]
        assert a["installed"] is False


# ---------------------------------------------------------------------------
# configure_agent
# ---------------------------------------------------------------------------


class TestConfigureAgent:
    def test_configure_success(self):
        from db_mcp.services.agents import configure_agent

        fake_agents = {
            "claude-desktop": MagicMock(config_path=MagicMock(__str__=lambda s: "/cfg"))
        }

        with (
            patch("db_mcp.services.agents._get_agents", return_value=fake_agents),
            patch("db_mcp.services.agents._get_binary_path", return_value="/bin/db-mcp"),
            patch("db_mcp.services.agents._configure_agent_for_dbmcp", return_value=True),
        ):
            result = configure_agent("claude-desktop")

        assert result["success"] is True

    def test_configure_failure_returns_error(self):
        from db_mcp.services.agents import configure_agent

        fake_agents = {"claude-desktop": MagicMock(config_path=MagicMock())}

        with (
            patch("db_mcp.services.agents._get_agents", return_value=fake_agents),
            patch("db_mcp.services.agents._get_binary_path", return_value="/bin/db-mcp"),
            patch("db_mcp.services.agents._configure_agent_for_dbmcp", return_value=False),
        ):
            result = configure_agent("claude-desktop")

        assert result["success"] is False
        assert result["error"] is not None

    def test_configure_unknown_agent(self):
        from db_mcp.services.agents import configure_agent

        with patch("db_mcp.services.agents._get_agents", return_value={}):
            result = configure_agent("nonexistent")

        assert result["success"] is False
        assert "unknown" in result["error"].lower()

    def test_configure_exception_becomes_error(self):
        from db_mcp.services.agents import configure_agent

        fake_agents = {"claude-desktop": MagicMock(config_path=MagicMock())}

        with (
            patch("db_mcp.services.agents._get_agents", return_value=fake_agents),
            patch("db_mcp.services.agents._get_binary_path", return_value="/bin/db-mcp"),
            patch(
                "db_mcp.services.agents._configure_agent_for_dbmcp",
                side_effect=RuntimeError("disk full"),
            ),
        ):
            result = configure_agent("claude-desktop")

        assert result["success"] is False
        assert "disk full" in result["error"]


# ---------------------------------------------------------------------------
# remove_agent
# ---------------------------------------------------------------------------


class TestRemoveAgent:
    def test_remove_success(self):
        from db_mcp.services.agents import remove_agent

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": MagicMock()},
            ),
            patch("db_mcp.services.agents._remove_dbmcp_from_agent", return_value=True),
        ):
            result = remove_agent("claude-desktop")

        assert result["success"] is True

    def test_remove_unknown_agent(self):
        from db_mcp.services.agents import remove_agent

        with patch("db_mcp.services.agents._get_agents", return_value={}):
            result = remove_agent("nonexistent")

        assert result["success"] is False
        assert "unknown" in result["error"].lower()

    def test_remove_failure_returns_error(self):
        from db_mcp.services.agents import remove_agent

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": MagicMock()},
            ),
            patch("db_mcp.services.agents._remove_dbmcp_from_agent", return_value=False),
        ):
            result = remove_agent("claude-desktop")

        assert result["success"] is False

    def test_remove_exception_becomes_error(self):
        from db_mcp.services.agents import remove_agent

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": MagicMock()},
            ),
            patch(
                "db_mcp.services.agents._remove_dbmcp_from_agent",
                side_effect=RuntimeError("permission denied"),
            ),
        ):
            result = remove_agent("claude-desktop")

        assert result["success"] is False
        assert "permission denied" in result["error"]


# ---------------------------------------------------------------------------
# get_agent_config_snippet
# ---------------------------------------------------------------------------


class TestGetAgentConfigSnippet:
    def test_json_snippet(self):
        from db_mcp.services.agents import get_agent_config_snippet

        fake_agent = MagicMock()
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        fake_config = {"mcpServers": {"db-mcp": {"command": "/bin/db-mcp"}}}

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": fake_agent},
            ),
            patch("db_mcp.services.agents._load_agent_config", return_value=fake_config),
        ):
            result = get_agent_config_snippet("claude-desktop")

        import json

        assert result["success"] is True
        assert result["format"] == "json"
        assert result["configKey"] == "mcpServers"
        parsed = json.loads(result["snippet"])
        assert "db-mcp" in parsed

    def test_toml_snippet(self):
        from db_mcp.services.agents import get_agent_config_snippet

        fake_agent = MagicMock()
        fake_agent.config_key = "mcp_servers"
        fake_agent.config_format = "toml"

        fake_config = {"mcp_servers": {"db-mcp": {"command": "/bin/db-mcp"}}}

        with (
            patch("db_mcp.services.agents._get_agents", return_value={"codex": fake_agent}),
            patch("db_mcp.services.agents._load_agent_config", return_value=fake_config),
            patch(
                "db_mcp.services.agents._dict_to_toml",
                return_value="[db-mcp]\ncommand = ...\n",
            ),
        ):
            result = get_agent_config_snippet("codex")

        assert result["success"] is True
        assert result["format"] == "toml"
        assert "[db-mcp]" in result["snippet"]

    def test_empty_snippet_when_no_config(self):
        from db_mcp.services.agents import get_agent_config_snippet

        fake_agent = MagicMock()
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": fake_agent},
            ),
            patch("db_mcp.services.agents._load_agent_config", return_value={}),
        ):
            result = get_agent_config_snippet("claude-desktop")

        assert result["success"] is True
        assert result["snippet"] == ""

    def test_unknown_agent(self):
        from db_mcp.services.agents import get_agent_config_snippet

        with patch("db_mcp.services.agents._get_agents", return_value={}):
            result = get_agent_config_snippet("nonexistent")

        assert result["success"] is False
        assert "unknown" in result["error"].lower()


# ---------------------------------------------------------------------------
# write_agent_config
# ---------------------------------------------------------------------------


class TestWriteAgentConfig:
    def test_write_json_success(self):
        import json

        from db_mcp.services.agents import write_agent_config

        fake_agent = MagicMock()
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        snippet = json.dumps({"db-mcp": {"command": "/new/path"}})

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": fake_agent},
            ),
            patch("db_mcp.services.agents._load_agent_config", return_value={}),
            patch("db_mcp.services.agents._save_agent_config") as mock_save,
        ):
            result = write_agent_config("claude-desktop", snippet)

        assert result["success"] is True
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][1]
        assert saved_config["mcpServers"]["db-mcp"]["command"] == "/new/path"

    def test_write_toml_success(self):
        from db_mcp.services.agents import write_agent_config

        fake_agent = MagicMock()
        fake_agent.config_key = "mcp_servers"
        fake_agent.config_format = "toml"

        snippet = '[db-mcp]\ncommand = "/new/path"\n'

        with (
            patch("db_mcp.services.agents._get_agents", return_value={"codex": fake_agent}),
            patch("db_mcp.services.agents._load_agent_config", return_value={}),
            patch("db_mcp.services.agents._save_agent_config") as mock_save,
        ):
            result = write_agent_config("codex", snippet)

        assert result["success"] is True
        saved_config = mock_save.call_args[0][1]
        assert saved_config["mcp_servers"]["db-mcp"]["command"] == "/new/path"

    def test_write_invalid_json_rejected(self):
        from db_mcp.services.agents import write_agent_config

        fake_agent = MagicMock()
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": fake_agent},
            ),
            patch("db_mcp.services.agents._save_agent_config") as mock_save,
        ):
            result = write_agent_config("claude-desktop", "{not valid json!!!")

        assert result["success"] is False
        assert "json" in result["error"].lower()
        mock_save.assert_not_called()

    def test_write_invalid_toml_rejected(self):
        from db_mcp.services.agents import write_agent_config

        fake_agent = MagicMock()
        fake_agent.config_key = "mcp_servers"
        fake_agent.config_format = "toml"

        with (
            patch("db_mcp.services.agents._get_agents", return_value={"codex": fake_agent}),
            patch("db_mcp.services.agents._save_agent_config") as mock_save,
        ):
            result = write_agent_config("codex", "[invalid\ntoml = !!!")

        assert result["success"] is False
        assert "toml" in result["error"].lower()
        mock_save.assert_not_called()

    def test_write_json_not_object_rejected(self):
        from db_mcp.services.agents import write_agent_config

        fake_agent = MagicMock()
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": fake_agent},
            ),
            patch("db_mcp.services.agents._save_agent_config") as mock_save,
        ):
            result = write_agent_config("claude-desktop", '"just a string"')

        assert result["success"] is False
        assert "object" in result["error"].lower()
        mock_save.assert_not_called()

    def test_write_empty_snippet_rejected(self):
        from db_mcp.services.agents import write_agent_config

        fake_agent = MagicMock()
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        with patch(
            "db_mcp.services.agents._get_agents",
            return_value={"claude-desktop": fake_agent},
        ):
            result = write_agent_config("claude-desktop", "")

        assert result["success"] is False
        assert result["error"] is not None

    def test_write_unknown_agent(self):
        from db_mcp.services.agents import write_agent_config

        with patch("db_mcp.services.agents._get_agents", return_value={}):
            result = write_agent_config("nonexistent", "{}")

        assert result["success"] is False
        assert "unknown" in result["error"].lower()

    def test_write_preserves_other_keys(self):
        import json

        from db_mcp.services.agents import write_agent_config

        fake_agent = MagicMock()
        fake_agent.config_key = "mcpServers"
        fake_agent.config_format = "json"

        existing_config = {"theme": "dark", "mcpServers": {"old-mcp": {}}}
        snippet = json.dumps({"db-mcp": {"command": "/new"}})

        with (
            patch(
                "db_mcp.services.agents._get_agents",
                return_value={"claude-desktop": fake_agent},
            ),
            patch("db_mcp.services.agents._load_agent_config", return_value=existing_config),
            patch("db_mcp.services.agents._save_agent_config") as mock_save,
        ):
            result = write_agent_config("claude-desktop", snippet)

        assert result["success"] is True
        saved = mock_save.call_args[0][1]
        assert saved["theme"] == "dark"
        assert "db-mcp" in saved["mcpServers"]


