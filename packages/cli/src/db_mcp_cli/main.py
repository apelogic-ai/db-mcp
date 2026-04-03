"""Click command group for db-mcp.

All command logic lives in db_mcp.cli.commands.* submodules.
"""

import click

from db_mcp_cli.commands.agents_cmd import register_commands as register_agents
from db_mcp_cli.commands.collab import register_commands as register_collab
from db_mcp_cli.commands.connector_cmd import register_commands as register_connector
from db_mcp_cli.commands.core import register_commands as register_core
from db_mcp_cli.commands.discover_cmd import register_commands as register_discover
from db_mcp_cli.commands.domain_cmd import register_commands as register_domain
from db_mcp_cli.commands.examples_cmd import register_commands as register_examples
from db_mcp_cli.commands.gaps_cmd import register_commands as register_gaps
from db_mcp_cli.commands.git_cmds import register_commands as register_git
from db_mcp_cli.commands.insider import register_commands as register_insider
from db_mcp_cli.commands.metrics_cmd import register_commands as register_metrics
from db_mcp_cli.commands.query_cmd import register_commands as register_query
from db_mcp_cli.commands.rules_cmd import register_commands as register_rules
from db_mcp_cli.commands.runtime_cmd import register_commands as register_runtime
from db_mcp_cli.commands.schema_cmd import register_commands as register_schema
from db_mcp_cli.commands.services import register_commands as register_services
from db_mcp_cli.commands.traces import register_commands as register_traces
from db_mcp_cli.utils import _get_cli_version


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
register_insider(main)
register_runtime(main)
register_services(main)
register_connector(main)
register_metrics(main)
register_examples(main)
register_rules(main)
register_schema(main)
register_gaps(main)
register_domain(main)
register_query(main)


if __name__ == "__main__":
    main()
