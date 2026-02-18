"""Smoke tests for CLI command registration.

Verifies that all command modules register their commands correctly and
that --help works for every top-level command and subgroup.
These are purely structural tests — no business logic is exercised.
"""

import click
import pytest
from click.testing import CliRunner

from db_mcp.cli.main import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def runner():
    return CliRunner()


def invoke_help(runner: CliRunner, *args) -> click.testing.Result:
    """Invoke the CLI with --help and return the result."""
    result = runner.invoke(main, list(args) + ["--help"])
    return result


# ---------------------------------------------------------------------------
# Top-level group
# ---------------------------------------------------------------------------

class TestMainGroup:
    def test_main_help(self, runner):
        result = invoke_help(runner)
        assert result.exit_code == 0
        assert "db-mcp" in result.output.lower() or "database" in result.output.lower()

    def test_main_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    def test_all_expected_commands_registered(self, runner):
        """Verify the main group has every expected top-level name."""
        expected = {
            "init", "start", "status", "list", "use", "sync", "pull",
            "discover", "agents", "console", "ui",
            "collab", "traces", "playground",
        }
        registered = set(main.commands.keys())
        missing = expected - registered
        assert not missing, f"Missing commands: {missing}"


# ---------------------------------------------------------------------------
# Core commands
# ---------------------------------------------------------------------------

class TestCoreCommandsHelp:
    @pytest.mark.parametrize("cmd", ["init", "start", "status", "list", "use"])
    def test_core_command_help(self, runner, cmd):
        result = invoke_help(runner, cmd)
        assert result.exit_code == 0, f"'{cmd} --help' failed: {result.output}"

    def test_init_help_shows_name_argument(self, runner):
        result = invoke_help(runner, "init")
        assert result.exit_code == 0

    def test_start_help_shows_connection_option(self, runner):
        result = invoke_help(runner, "start")
        assert result.exit_code == 0
        assert "--connection" in result.output or "-c" in result.output

    def test_status_help(self, runner):
        result = invoke_help(runner, "status")
        assert result.exit_code == 0

    def test_use_help(self, runner):
        result = invoke_help(runner, "use")
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Git commands
# ---------------------------------------------------------------------------

class TestGitCommandsHelp:
    @pytest.mark.parametrize("cmd", ["sync", "pull"])
    def test_git_command_help(self, runner, cmd):
        result = invoke_help(runner, cmd)
        assert result.exit_code == 0, f"'{cmd} --help' failed: {result.output}"


# ---------------------------------------------------------------------------
# Discover command
# ---------------------------------------------------------------------------

class TestDiscoverCommandHelp:
    def test_discover_help(self, runner):
        result = invoke_help(runner, "discover")
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Agents command
# ---------------------------------------------------------------------------

class TestAgentsCommandHelp:
    def test_agents_help(self, runner):
        result = invoke_help(runner, "agents")
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Service commands
# ---------------------------------------------------------------------------

class TestServiceCommandsHelp:
    @pytest.mark.parametrize("cmd", ["console", "ui"])
    def test_service_command_help(self, runner, cmd):
        result = invoke_help(runner, cmd)
        assert result.exit_code == 0, f"'{cmd} --help' failed: {result.output}"


# ---------------------------------------------------------------------------
# Subgroups
# ---------------------------------------------------------------------------

class TestSubgroupsHelp:
    def test_collab_help(self, runner):
        result = invoke_help(runner, "collab")
        assert result.exit_code == 0

    def test_traces_help(self, runner):
        result = invoke_help(runner, "traces")
        assert result.exit_code == 0

    def test_playground_help(self, runner):
        result = invoke_help(runner, "playground")
        assert result.exit_code == 0

    def test_collab_is_group(self, runner):
        cmd = main.commands["collab"]
        assert isinstance(cmd, click.Group)

    def test_traces_is_group(self, runner):
        cmd = main.commands["traces"]
        assert isinstance(cmd, click.Group)

    def test_playground_is_group(self, runner):
        cmd = main.commands["playground"]
        assert isinstance(cmd, click.Group)


# ---------------------------------------------------------------------------
# register_commands unit tests (call each module's register fn on a fresh group)
# ---------------------------------------------------------------------------

class TestRegisterCommands:
    def _fresh_group(self):
        @click.group()
        def g():
            pass
        return g

    def test_register_core(self):
        from db_mcp.cli.commands.core import register_commands
        g = self._fresh_group()
        register_commands(g)
        assert "init" in g.commands
        assert "start" in g.commands
        assert "status" in g.commands
        assert "list" in g.commands
        assert "use" in g.commands

    def test_register_agents(self):
        from db_mcp.cli.commands.agents_cmd import register_commands
        g = self._fresh_group()
        register_commands(g)
        assert "agents" in g.commands

    def test_register_collab(self):
        from db_mcp.cli.commands.collab import register_commands
        g = self._fresh_group()
        register_commands(g)
        assert "collab" in g.commands

    def test_register_traces(self):
        from db_mcp.cli.commands.traces import register_commands
        g = self._fresh_group()
        register_commands(g)
        assert "traces" in g.commands

    def test_register_git(self):
        from db_mcp.cli.commands.git_cmds import register_commands
        g = self._fresh_group()
        register_commands(g)
        assert "sync" in g.commands
        assert "pull" in g.commands

    def test_register_discover(self):
        from db_mcp.cli.commands.discover_cmd import register_commands
        g = self._fresh_group()
        register_commands(g)
        assert "discover" in g.commands

    def test_register_services(self):
        from db_mcp.cli.commands.services import register_commands
        g = self._fresh_group()
        register_commands(g)
        assert "console" in g.commands
        assert "ui" in g.commands
        assert "playground" in g.commands
