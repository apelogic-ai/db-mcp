"""Click command group for db-mcp.

All command logic lives in db_mcp.cli.commands.* submodules.
"""

import click

from db_mcp_cli.commands.agents_cmd import register_commands as register_agents
from db_mcp_cli.commands.api_cmd import register_commands as register_api
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

# Command sections for grouped help output
COMMAND_SECTIONS = {
    "Getting started": ["tui", "ui", "up", "init", "playground", "status", "doctor"],
    "Connections": ["list", "use", "edit", "env", "rename", "remove", "all"],
    "Query & explore": ["query", "ask", "schema", "discover", "domain"],
    "Knowledge vault": ["rules", "examples", "metrics", "gaps"],
    "Collaboration": ["collab", "sync", "pull", "git-init"],
    "Server & runtime": ["start", "serve", "runtime", "console", "traces"],
    "Advanced": ["agents", "api", "connector", "insider", "config", "migrate"],
}


class SectionedGroup(click.Group):
    """Click group that renders commands in sections."""

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        commands = {name: cmd for name, cmd in self.commands.items() if not cmd.hidden}

        shown = set()
        for section, names in COMMAND_SECTIONS.items():
            section_cmds = [(n, commands[n]) for n in names if n in commands]
            if not section_cmds:
                continue
            with formatter.section(section):
                rows = []
                for name, cmd in section_cmds:
                    help_text = cmd.get_short_help_str(limit=formatter.width - 20)
                    rows.append((name, help_text))
                    shown.add(name)
                formatter.write_dl(rows)

        # Any commands not in a section go to "Other"
        remaining = [(n, commands[n]) for n in sorted(commands) if n not in shown]
        if remaining:
            with formatter.section("Other"):
                limit = formatter.width - 20
                rows = [(n, c.get_short_help_str(limit=limit)) for n, c in remaining]
                formatter.write_dl(rows)


@click.group(cls=SectionedGroup, context_settings={"max_content_width": 120})
@click.version_option(version=_get_cli_version())
def main():
    """db-mcp — query databases, APIs, and files using natural language."""
    pass


register_core(main)
register_agents(main)
register_api(main)
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
