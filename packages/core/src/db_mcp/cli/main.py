"""Click command group for db-mcp.

All command logic lives in db_mcp.cli.commands.* submodules.
"""

import click

from db_mcp.cli.commands.agents_cmd import register_commands as register_agents
from db_mcp.cli.commands.collab import register_commands as register_collab
from db_mcp.cli.commands.core import register_commands as register_core
from db_mcp.cli.commands.discover_cmd import register_commands as register_discover
from db_mcp.cli.commands.git_cmds import register_commands as register_git
from db_mcp.cli.commands.services import register_commands as register_services
from db_mcp.cli.commands.traces import register_commands as register_traces
from db_mcp.cli.utils import _get_cli_version


@click.group()
@click.version_option(version=_get_cli_version())
def main():
    """db-mcp - Database metadata MCP server for Claude Desktop."""
    pass


register_core(main)
register_agents(main)
register_collab(main)
register_traces(main)
register_git(main)
register_discover(main)
register_services(main)


if __name__ == "__main__":
    main()
