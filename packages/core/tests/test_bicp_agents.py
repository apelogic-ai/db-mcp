"""Tests for agents/* BICP handlers."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from db_mcp.agents import AGENTS, _dict_to_toml


def _make_json_config(tmpdir, agent_id, servers=None):
    """Create a JSON agent config file and point the AGENTS dict at it."""
    config_path = Path(tmpdir) / f"{agent_id}.json"
    config = {}
    if servers is not None:
        config[AGENTS[agent_id].config_key] = servers
    with open(config_path, "w") as f:
        json.dump(config, f)
    AGENTS[agent_id].config_path = config_path
    return config_path


def _make_toml_config(tmpdir, servers=None):
    """Create a TOML agent config for codex."""
    config_path = Path(tmpdir) / "config.toml"
    config = {}
    if servers is not None:
        config["mcp_servers"] = servers
    config_path.write_text(_dict_to_toml(config))
    AGENTS["codex"].config_path = config_path
    return config_path


@pytest.fixture
def _patch_agents():
    """Patch agent detection to control installed/not-installed state."""
    original_paths = {aid: a.config_path for aid, a in AGENTS.items()}
    yield
    for aid, path in original_paths.items():
        AGENTS[aid].config_path = path


class TestHandleAgentsList:
    @pytest.mark.asyncio
    async def test_lists_all_agents(self, _patch_agents):
        from db_mcp.bicp.agent import DBMCPAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_json_config(
                tmpdir,
                "claude-desktop",
                {"db-mcp": {"command": "/bin/db-mcp", "args": ["start"]}},
            )
            _make_json_config(tmpdir, "claude-code", {})
            AGENTS["codex"].config_path = Path(tmpdir) / "nonexistent.toml"

            with (
                patch.object(AGENTS["claude-desktop"], "detect_fn", return_value=True),
                patch.object(AGENTS["claude-code"], "detect_fn", return_value=True),
                patch.object(AGENTS["codex"], "detect_fn", return_value=False),
            ):
                agent = DBMCPAgent.__new__(DBMCPAgent)
                agent._method_handlers = {}
                agent._settings = None
                agent._dialect = "postgresql"

                # Register only agents handlers
                agent._method_handlers["agents/list"] = agent._handle_agents_list

                result = await agent._handle_agents_list({})

            assert "agents" in result
            agents = {a["id"]: a for a in result["agents"]}

            # claude-desktop: installed, configured
            assert agents["claude-desktop"]["installed"] is True
            assert agents["claude-desktop"]["dbmcpConfigured"] is True
            assert agents["claude-desktop"]["configExists"] is True

            # claude-code: installed, not configured
            assert agents["claude-code"]["installed"] is True
            assert agents["claude-code"]["dbmcpConfigured"] is False

            # codex: not installed
            assert agents["codex"]["installed"] is False
            assert agents["codex"]["configExists"] is False


class TestHandleAgentsConfigure:
    @pytest.mark.asyncio
    async def test_configure_success(self, _patch_agents):
        from db_mcp.bicp.agent import DBMCPAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_json_config(tmpdir, "claude-desktop", {})

            with patch(
                "db_mcp.agents.get_db_mcp_binary_path",
                return_value="/bin/db-mcp",
            ):
                agent = DBMCPAgent.__new__(DBMCPAgent)
                agent._method_handlers = {}
                agent._settings = None
                agent._dialect = "postgresql"

                result = await agent._handle_agents_configure({"agentId": "claude-desktop"})

            assert result["success"] is True

            # Verify config was written
            with open(AGENTS["claude-desktop"].config_path) as f:
                config = json.load(f)
            assert "db-mcp" in config["mcpServers"]

    @pytest.mark.asyncio
    async def test_configure_invalid_agent(self):
        from db_mcp.bicp.agent import DBMCPAgent

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "postgresql"

        result = await agent._handle_agents_configure({"agentId": "nonexistent"})
        assert result["success"] is False
        assert "error" in result


class TestHandleAgentsRemove:
    @pytest.mark.asyncio
    async def test_remove_success(self, _patch_agents):
        from db_mcp.bicp.agent import DBMCPAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            _make_json_config(
                tmpdir,
                "claude-desktop",
                {"db-mcp": {"command": "/bin/db-mcp", "args": ["start"]}},
            )

            agent = DBMCPAgent.__new__(DBMCPAgent)
            agent._method_handlers = {}
            agent._settings = None
            agent._dialect = "postgresql"

            result = await agent._handle_agents_remove({"agentId": "claude-desktop"})

            assert result["success"] is True

            with open(AGENTS["claude-desktop"].config_path) as f:
                config = json.load(f)
            assert "db-mcp" not in config["mcpServers"]

    @pytest.mark.asyncio
    async def test_remove_invalid_agent(self):
        from db_mcp.bicp.agent import DBMCPAgent

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "postgresql"

        result = await agent._handle_agents_remove({"agentId": "bad"})
        assert result["success"] is False


class TestHandleAgentsConfigSnippet:
    @pytest.mark.asyncio
    async def test_snippet_json(self, _patch_agents):
        from db_mcp.bicp.agent import DBMCPAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            servers = {"db-mcp": {"command": "/bin/db-mcp", "args": ["start"]}}
            _make_json_config(tmpdir, "claude-desktop", servers)

            agent = DBMCPAgent.__new__(DBMCPAgent)
            agent._method_handlers = {}
            agent._settings = None
            agent._dialect = "postgresql"

            result = await agent._handle_agents_config_snippet({"agentId": "claude-desktop"})

            assert result["success"] is True
            assert result["format"] == "json"
            assert result["configKey"] == "mcpServers"
            # Snippet should be valid JSON
            parsed = json.loads(result["snippet"])
            assert "db-mcp" in parsed

    @pytest.mark.asyncio
    async def test_snippet_toml(self, _patch_agents):
        from db_mcp.bicp.agent import DBMCPAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            servers = {"db-mcp": {"command": "/bin/db-mcp", "args": ["start"]}}
            _make_toml_config(tmpdir, servers)

            agent = DBMCPAgent.__new__(DBMCPAgent)
            agent._method_handlers = {}
            agent._settings = None
            agent._dialect = "postgresql"

            result = await agent._handle_agents_config_snippet({"agentId": "codex"})

            assert result["success"] is True
            assert result["format"] == "toml"
            assert result["configKey"] == "mcp_servers"
            assert "db-mcp" in result["snippet"]

    @pytest.mark.asyncio
    async def test_snippet_no_config(self, _patch_agents):
        from db_mcp.bicp.agent import DBMCPAgent

        AGENTS["claude-desktop"].config_path = Path("/nonexistent/config.json")

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "postgresql"

        result = await agent._handle_agents_config_snippet({"agentId": "claude-desktop"})

        assert result["success"] is True
        assert result["snippet"] == ""

    @pytest.mark.asyncio
    async def test_snippet_invalid_agent(self):
        from db_mcp.bicp.agent import DBMCPAgent

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "postgresql"

        result = await agent._handle_agents_config_snippet({"agentId": "bad"})
        assert result["success"] is False


class TestHandleAgentsConfigWrite:
    """Tests for agents/config-write — editable config snippet saving."""

    def _make_agent(self):
        from db_mcp.bicp.agent import DBMCPAgent

        agent = DBMCPAgent.__new__(DBMCPAgent)
        agent._method_handlers = {}
        agent._settings = None
        agent._dialect = "postgresql"
        return agent

    @pytest.mark.asyncio
    async def test_write_json_success(self, _patch_agents):
        """Valid JSON snippet updates the MCP servers section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            servers = {"db-mcp": {"command": "/old/path", "args": ["start"]}}
            _make_json_config(tmpdir, "claude-desktop", servers)

            new_snippet = json.dumps(
                {"db-mcp": {"command": "/new/path", "args": ["start"]}},
                indent=2,
            )
            agent = self._make_agent()
            result = await agent._handle_agents_config_write(
                {"agentId": "claude-desktop", "snippet": new_snippet}
            )

            assert result["success"] is True

            # Verify config was updated
            with open(AGENTS["claude-desktop"].config_path) as f:
                config = json.load(f)
            assert config["mcpServers"]["db-mcp"]["command"] == "/new/path"

    @pytest.mark.asyncio
    async def test_write_toml_success(self, _patch_agents):
        """Valid TOML snippet updates the MCP servers section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            servers = {"db-mcp": {"command": "/old/path", "args": ["start"]}}
            _make_toml_config(tmpdir, servers)

            new_snippet = '[db-mcp]\ncommand = "/new/toml/path"\nargs = ["start"]'
            agent = self._make_agent()
            result = await agent._handle_agents_config_write(
                {"agentId": "codex", "snippet": new_snippet}
            )

            assert result["success"] is True

            # Verify config was updated
            import tomllib

            with open(AGENTS["codex"].config_path, "rb") as f:
                config = tomllib.load(f)
            assert config["mcp_servers"]["db-mcp"]["command"] == "/new/toml/path"

    @pytest.mark.asyncio
    async def test_write_invalid_json(self, _patch_agents):
        """Invalid JSON snippet is rejected with a parse error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_json_config(
                tmpdir,
                "claude-desktop",
                {"db-mcp": {"command": "/old", "args": ["start"]}},
            )

            agent = self._make_agent()
            result = await agent._handle_agents_config_write(
                {"agentId": "claude-desktop", "snippet": "{invalid json!!!"}
            )

            assert result["success"] is False
            assert "error" in result

            # Original config should be untouched
            with open(AGENTS["claude-desktop"].config_path) as f:
                config = json.load(f)
            assert config["mcpServers"]["db-mcp"]["command"] == "/old"

    @pytest.mark.asyncio
    async def test_write_invalid_toml(self, _patch_agents):
        """Invalid TOML snippet is rejected with a parse error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_toml_config(
                tmpdir,
                {"db-mcp": {"command": "/old", "args": ["start"]}},
            )

            agent = self._make_agent()
            result = await agent._handle_agents_config_write(
                {"agentId": "codex", "snippet": "[invalid\ntoml = !!!"}
            )

            assert result["success"] is False
            assert "error" in result

            # Original config should be untouched
            import tomllib

            with open(AGENTS["codex"].config_path, "rb") as f:
                config = tomllib.load(f)
            assert config["mcp_servers"]["db-mcp"]["command"] == "/old"

    @pytest.mark.asyncio
    async def test_write_json_not_object(self, _patch_agents):
        """JSON snippet that is not an object is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_json_config(tmpdir, "claude-desktop", {})

            agent = self._make_agent()
            result = await agent._handle_agents_config_write(
                {"agentId": "claude-desktop", "snippet": '"just a string"'}
            )

            assert result["success"] is False
            assert "object" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_write_preserves_other_keys(self, _patch_agents):
        """Writing snippet preserves non-MCP keys in the config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "claude-desktop.json"
            config = {
                "theme": "dark",
                "mcpServers": {
                    "db-mcp": {"command": "/old", "args": ["start"]},
                    "other-mcp": {"command": "/other", "args": []},
                },
            }
            with open(config_path, "w") as f:
                json.dump(config, f)
            AGENTS["claude-desktop"].config_path = config_path

            new_snippet = json.dumps(
                {"db-mcp": {"command": "/new", "args": ["start"]}},
                indent=2,
            )
            agent = self._make_agent()
            result = await agent._handle_agents_config_write(
                {"agentId": "claude-desktop", "snippet": new_snippet}
            )

            assert result["success"] is True

            with open(config_path) as f:
                saved = json.load(f)
            # Theme preserved
            assert saved["theme"] == "dark"
            # MCP section replaced entirely
            assert saved["mcpServers"]["db-mcp"]["command"] == "/new"
            # Other MCP servers NOT preserved — snippet replaces the whole section
            assert "other-mcp" not in saved["mcpServers"]

    @pytest.mark.asyncio
    async def test_write_invalid_agent(self):
        """Unknown agent ID is rejected."""
        agent = self._make_agent()
        result = await agent._handle_agents_config_write(
            {"agentId": "nonexistent", "snippet": "{}"}
        )
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_write_empty_snippet(self, _patch_agents):
        """Empty snippet is rejected."""
        agent = self._make_agent()
        result = await agent._handle_agents_config_write(
            {"agentId": "claude-desktop", "snippet": ""}
        )
        assert result["success"] is False
