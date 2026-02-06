"""Tests for agent registry and configuration."""

import json
import tempfile
import tomllib
from pathlib import Path
from unittest.mock import patch

from db_mcp.agents import (
    AGENTS,
    _dict_to_toml,
    _format_toml_value,
    configure_agent_for_dbmcp,
    configure_multiple_agents,
    detect_claude_code,
    detect_claude_desktop,
    detect_codex,
    detect_installed_agents,
    get_db_mcp_binary_path,
    load_agent_config,
    remove_dbmcp_from_agent,
    save_agent_config,
)


class TestAgentDetection:
    """Test agent detection functions."""

    def test_detect_claude_desktop_by_config(self):
        """Test detecting Claude Desktop by config file."""
        with patch("db_mcp.agents.get_claude_desktop_config_path") as mock_path:
            mock_path.return_value = Path("/fake/config.json")
            with patch("pathlib.Path.exists", return_value=True):
                assert detect_claude_desktop() is True

    def test_detect_claude_desktop_by_app_macos(self):
        """Test detecting Claude Desktop by app on macOS."""
        with patch("db_mcp.agents.get_claude_desktop_config_path") as mock_path:
            mock_path.return_value = Path("/fake/config.json")
            with patch("pathlib.Path.exists", side_effect=[False, True]):
                with patch("platform.system", return_value="Darwin"):
                    assert detect_claude_desktop() is True

    def test_detect_claude_desktop_not_found(self):
        """Test when Claude Desktop is not installed."""
        with patch("db_mcp.agents.get_claude_desktop_config_path") as mock_path:
            mock_path.return_value = Path("/fake/config.json")
            with patch("pathlib.Path.exists", return_value=False):
                with patch("platform.system", return_value="Linux"):
                    assert detect_claude_desktop() is False

    def test_detect_claude_code_by_config(self):
        """Test detecting Claude Code by config file."""
        with patch("db_mcp.agents.get_claude_code_config_path") as mock_path:
            mock_path.return_value = Path("/fake/.claude.json")
            with patch("pathlib.Path.exists", return_value=True):
                assert detect_claude_code() is True

    def test_detect_claude_code_by_cli(self):
        """Test detecting Claude Code by CLI."""
        with patch("db_mcp.agents.get_claude_code_config_path") as mock_path:
            mock_path.return_value = Path("/fake/.claude.json")
            with patch("pathlib.Path.exists", return_value=False):
                with patch("shutil.which", return_value="/usr/local/bin/claude"):
                    assert detect_claude_code() is True

    def test_detect_claude_code_not_found(self):
        """Test when Claude Code is not installed."""
        with patch("db_mcp.agents.get_claude_code_config_path") as mock_path:
            mock_path.return_value = Path("/fake/.claude.json")
            with patch("pathlib.Path.exists", return_value=False):
                with patch("shutil.which", return_value=None):
                    assert detect_claude_code() is False

    def test_detect_codex_by_config(self):
        """Test detecting Codex by config directory."""
        with patch("db_mcp.agents.get_codex_config_path") as mock_path:
            config_path = Path("/fake/.codex/config.toml")
            mock_path.return_value = config_path
            with patch.object(Path, "exists") as mock_exists:
                # parent.exists() should return True
                mock_exists.return_value = True
                assert detect_codex() is True

    def test_detect_codex_by_cli(self):
        """Test detecting Codex by CLI."""
        with patch("db_mcp.agents.get_codex_config_path") as mock_path:
            config_path = Path("/fake/.codex/config.toml")
            mock_path.return_value = config_path
            with patch.object(Path, "exists", return_value=False):
                with patch("shutil.which", return_value="/usr/local/bin/codex"):
                    assert detect_codex() is True

    def test_detect_codex_not_found(self):
        """Test when Codex is not installed."""
        with patch("db_mcp.agents.get_codex_config_path") as mock_path:
            config_path = Path("/fake/.codex/config.toml")
            mock_path.return_value = config_path
            with patch.object(Path, "exists", return_value=False):
                with patch("shutil.which", return_value=None):
                    assert detect_codex() is False

    def test_detect_installed_agents(self):
        """Test detecting all installed agents."""
        # We need to patch the detect functions in the AGENTS dict
        with patch.object(AGENTS["claude-desktop"], "detect_fn", return_value=True):
            with patch.object(AGENTS["claude-code"], "detect_fn", return_value=False):
                with patch.object(AGENTS["codex"], "detect_fn", return_value=True):
                    installed = detect_installed_agents()
                    assert "claude-desktop" in installed
                    assert "claude-code" not in installed
                    assert "codex" in installed


class TestAgentConfig:
    """Test agent configuration loading/saving."""

    def test_load_agent_config_json(self):
        """Test loading JSON config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            test_config = {"mcpServers": {"test": {"command": "test"}}}

            with open(config_path, "w") as f:
                json.dump(test_config, f)

            agent = AGENTS["claude-desktop"]
            agent.config_path = config_path

            config = load_agent_config(agent)
            assert config == test_config

    def test_load_agent_config_toml(self):
        """Test loading TOML config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            test_config = {"mcp_servers": {"test": {"command": "test"}}}

            # Write TOML manually
            with open(config_path, "w") as f:
                f.write(_dict_to_toml(test_config))

            agent = AGENTS["codex"]
            agent.config_path = config_path

            config = load_agent_config(agent)
            assert config == test_config

    def test_load_agent_config_missing(self):
        """Test loading non-existent config."""
        agent = AGENTS["claude-desktop"]
        agent.config_path = Path("/nonexistent/config.json")

        config = load_agent_config(agent)
        assert config == {}

    def test_save_agent_config_json(self):
        """Test saving JSON config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            test_config = {"mcpServers": {"test": {"command": "test"}}}

            agent = AGENTS["claude-desktop"]
            agent.config_path = config_path

            save_agent_config(agent, test_config)

            with open(config_path) as f:
                saved = json.load(f)

            assert saved == test_config

    def test_save_agent_config_toml(self):
        """Test saving TOML config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            test_config = {"mcp_servers": {"test": {"command": "test"}}}

            agent = AGENTS["codex"]
            agent.config_path = config_path

            save_agent_config(agent, test_config)

            with open(config_path, "rb") as f:
                saved = tomllib.load(f)

            assert saved == test_config


class TestTomlWriter:
    """Test TOML serialization helpers."""

    def test_format_toml_value_scalars(self):
        """Test formatting scalar values."""
        assert _format_toml_value("hello") == '"hello"'
        assert _format_toml_value(42) == "42"
        assert _format_toml_value(3.14) == "3.14"
        assert _format_toml_value(True) == "true"
        assert _format_toml_value(False) == "false"
        assert _format_toml_value(["a", "b"]) == '["a", "b"]'
        assert _format_toml_value({}) is None

    def test_dict_to_toml_no_spurious_header(self):
        """Test that intermediate-only tables don't emit empty headers."""
        config = {"mcp_servers": {"db-mcp": {"command": "/bin/db-mcp", "args": ["start"]}}}
        output = _dict_to_toml(config)
        assert "[mcp_servers]" not in output
        assert "[mcp_servers.db-mcp]" in output

    def test_dict_to_toml_roundtrip_with_env(self):
        """Test that nested env maps survive a TOML round-trip."""
        config = {
            "model": "o3",
            "mcp_servers": {
                "my-server": {
                    "command": "npx",
                    "args": ["-y", "some-pkg"],
                    "env": {"API_KEY": "secret", "REGION": "us-east-1"},
                }
            },
        }
        output = _dict_to_toml(config)
        reparsed = tomllib.loads(output)
        assert reparsed == config

    def test_dict_to_toml_roundtrip_multiple_servers(self):
        """Test round-trip with multiple servers, some with env."""
        config = {
            "model": "o3",
            "approval_mode": "unless-allow-listed",
            "mcp_servers": {
                "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
                "db-mcp": {"command": "/bin/db-mcp", "args": ["start"]},
                "with-env": {
                    "command": "cmd",
                    "args": ["a"],
                    "env": {"KEY": "val"},
                },
            },
        }
        output = _dict_to_toml(config)
        reparsed = tomllib.loads(output)
        assert reparsed == config


class TestAgentConfiguration:
    """Test agent configuration for db-mcp."""

    def test_configure_claude_desktop(self):
        """Test configuring Claude Desktop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            agent = AGENTS["claude-desktop"]
            agent.config_path = config_path

            result = configure_agent_for_dbmcp("claude-desktop", "/usr/local/bin/db-mcp")

            assert result is True
            assert config_path.exists()

            with open(config_path) as f:
                config = json.load(f)

            assert "mcpServers" in config
            assert "db-mcp" in config["mcpServers"]
            assert config["mcpServers"]["db-mcp"]["command"] == "/usr/local/bin/db-mcp"
            assert config["mcpServers"]["db-mcp"]["args"] == ["start"]

    def test_configure_codex(self):
        """Test configuring Codex."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"

            agent = AGENTS["codex"]
            agent.config_path = config_path

            result = configure_agent_for_dbmcp("codex", "/usr/local/bin/db-mcp")

            assert result is True
            assert config_path.exists()

            with open(config_path, "rb") as f:
                config = tomllib.load(f)

            assert "mcp_servers" in config
            assert "db-mcp" in config["mcp_servers"]
            assert config["mcp_servers"]["db-mcp"]["command"] == "/usr/local/bin/db-mcp"
            assert config["mcp_servers"]["db-mcp"]["args"] == ["start"]

    def test_configure_preserves_existing_servers(self):
        """Test that configuring db-mcp preserves other MCP servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Create existing config with another server
            existing_config = {
                "mcpServers": {"github": {"command": "npx", "args": ["@github/mcp"]}}
            }

            with open(config_path, "w") as f:
                json.dump(existing_config, f)

            agent = AGENTS["claude-desktop"]
            agent.config_path = config_path

            configure_agent_for_dbmcp("claude-desktop", "/usr/local/bin/db-mcp")

            with open(config_path) as f:
                config = json.load(f)

            assert "github" in config["mcpServers"]
            assert "db-mcp" in config["mcpServers"]

    def test_configure_removes_legacy_dbmeta(self):
        """Test that configuring db-mcp removes legacy dbmeta entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Create config with legacy dbmeta
            existing_config = {
                "mcpServers": {"dbmeta": {"command": "old-dbmeta", "args": ["start"]}}
            }

            with open(config_path, "w") as f:
                json.dump(existing_config, f)

            agent = AGENTS["claude-desktop"]
            agent.config_path = config_path

            configure_agent_for_dbmcp("claude-desktop", "/usr/local/bin/db-mcp")

            with open(config_path) as f:
                config = json.load(f)

            assert "dbmeta" not in config["mcpServers"]
            assert "db-mcp" in config["mcpServers"]

    def test_configure_codex_preserves_env_maps(self):
        """Test that configuring Codex preserves existing env maps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"

            # Pre-existing Codex config with env map on another server
            existing_toml = (
                'model = "o3"\n\n'
                "[mcp_servers.other]\n"
                'command = "npx"\n'
                'args = ["-y", "other-pkg"]\n\n'
                "[mcp_servers.other.env]\n"
                'API_KEY = "secret"\n'
            )
            config_path.write_text(existing_toml)

            agent = AGENTS["codex"]
            agent.config_path = config_path

            result = configure_agent_for_dbmcp("codex", "/usr/local/bin/db-mcp")

            assert result is True

            with open(config_path, "rb") as f:
                config = tomllib.load(f)

            # db-mcp was added
            assert "db-mcp" in config["mcp_servers"]
            assert config["mcp_servers"]["db-mcp"]["command"] == "/usr/local/bin/db-mcp"
            # other server's env map survived
            assert config["mcp_servers"]["other"]["env"]["API_KEY"] == "secret"

    def test_configure_invalid_agent(self):
        """Test configuring invalid agent ID."""
        result = configure_agent_for_dbmcp("invalid-agent", "/usr/local/bin/db-mcp")
        assert result is False

    def test_configure_multiple_agents(self):
        """Test configuring multiple agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up paths for both agents
            claude_path = Path(tmpdir) / "claude.json"
            codex_path = Path(tmpdir) / "codex.toml"

            AGENTS["claude-desktop"].config_path = claude_path
            AGENTS["codex"].config_path = codex_path

            results = configure_multiple_agents(
                ["claude-desktop", "codex"], "/usr/local/bin/db-mcp"
            )

            assert results["claude-desktop"] is True
            assert results["codex"] is True
            assert claude_path.exists()
            assert codex_path.exists()


class TestRemoveAgent:
    """Test removing db-mcp from agent configs."""

    def test_remove_from_json_agent(self):
        """Test removing db-mcp from a JSON agent config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            existing = {
                "mcpServers": {
                    "db-mcp": {"command": "/bin/db-mcp", "args": ["start"]},
                    "github": {"command": "npx", "args": ["@github/mcp"]},
                }
            }
            with open(config_path, "w") as f:
                json.dump(existing, f)

            AGENTS["claude-desktop"].config_path = config_path
            result = remove_dbmcp_from_agent("claude-desktop")

            assert result is True
            with open(config_path) as f:
                config = json.load(f)
            assert "db-mcp" not in config["mcpServers"]
            assert "github" in config["mcpServers"]

    def test_remove_from_toml_agent(self):
        """Test removing db-mcp from a TOML agent config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            existing = {
                "model": "o3",
                "mcp_servers": {
                    "db-mcp": {"command": "/bin/db-mcp", "args": ["start"]},
                    "other": {"command": "npx", "args": ["-y", "other"]},
                },
            }
            config_path.write_text(_dict_to_toml(existing))

            AGENTS["codex"].config_path = config_path
            result = remove_dbmcp_from_agent("codex")

            assert result is True
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            assert "db-mcp" not in config["mcp_servers"]
            assert "other" in config["mcp_servers"]

    def test_remove_not_configured_is_noop(self):
        """Test removing when db-mcp is not configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            existing = {"mcpServers": {"github": {"command": "npx"}}}
            with open(config_path, "w") as f:
                json.dump(existing, f)

            AGENTS["claude-desktop"].config_path = config_path
            result = remove_dbmcp_from_agent("claude-desktop")

            assert result is True
            with open(config_path) as f:
                config = json.load(f)
            assert "github" in config["mcpServers"]

    def test_remove_no_config_section_is_noop(self):
        """Test removing when config has no MCP servers section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            with open(config_path, "w") as f:
                json.dump({}, f)

            AGENTS["claude-desktop"].config_path = config_path
            result = remove_dbmcp_from_agent("claude-desktop")
            assert result is True

    def test_remove_invalid_agent(self):
        """Test removing from an invalid agent ID."""
        result = remove_dbmcp_from_agent("nonexistent-agent")
        assert result is False


class TestGetBinaryPath:
    """Test get_db_mcp_binary_path."""

    def test_returns_string(self):
        """Test that it returns a string path."""
        path = get_db_mcp_binary_path()
        assert isinstance(path, str)
        assert len(path) > 0

    def test_dev_mode_returns_db_mcp(self):
        """In dev mode (not frozen), returns 'db-mcp'."""
        with patch("db_mcp.agents.getattr", return_value=False):
            # Not frozen — should return "db-mcp"
            path = get_db_mcp_binary_path()
            assert path == "db-mcp"
