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

# Help layout: two top-level sections, each with subsections
HELP_SECTIONS = [
    ("General", [
        ("", [
            "tui", "up", "status", "config",
            "agents", "playground",
        ]),
    ]),
    ("Connection", [
        ("Setup & manage", [
            "init", "list", "use", "env", "edit",
            "doctor", "rename", "remove",
        ]),
        ("Query & explore", [
            "query", "ask", "schema", "discover", "domain",
        ]),
        ("Knowledge vault", [
            "rules", "examples", "metrics", "gaps",
        ]),
        ("Collaboration", [
            "collab", "sync", "pull", "git-init",
        ]),
    ]),
]

# Commands not listed above are hidden from --help
HIDDEN_COMMANDS = {
    "start", "serve", "runtime", "console", "traces",
    "all", "api", "connector", "insider", "migrate", "ui",
}


class SectionedGroup(click.Group):
    """Click group that renders commands in bold sections with subsections."""

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        commands = {
            name: cmd for name, cmd in self.commands.items() if not cmd.hidden
        }
        limit = max(formatter.width - 20, 40)

        for section_title, subsections in HELP_SECTIONS:
            formatter.write("\n")
            formatter.write(click.style(f"  {section_title}\n", bold=True))

            for sub_title, cmd_names in subsections:
                cmds = [(n, commands[n]) for n in cmd_names if n in commands]
                if not cmds:
                    continue
                if sub_title:
                    formatter.write(
                        click.style(f"    {sub_title}:\n", dim=True)
                    )
                for name, cmd in cmds:
                    help_text = cmd.get_short_help_str(limit=limit)
                    padded = name.ljust(14)
                    formatter.write(f"    {padded}{help_text}\n")


@click.group(cls=SectionedGroup, context_settings={"max_content_width": 120})
@click.version_option(version=_get_cli_version())
def main():
    """db-mcp — query databases, APIs, and files using natural language.

    \b
    Quick start:
      db-mcp playground install          Install sample Chinook SQLite database
      db-mcp tui                         Open the terminal UI
      db-mcp query run --confirmed \\
        'SELECT * FROM Artist LIMIT 5'   Run a SQL query
    """
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
