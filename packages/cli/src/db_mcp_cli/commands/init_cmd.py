"""Init command: interactive setup wizard for greenfield/brownfield connections."""

import click
from db_mcp.agents import AGENTS, detect_installed_agents
from rich.panel import Panel

from db_mcp_cli.git_ops import is_git_url
from db_mcp_cli.init_flow import _init_brownfield, _init_greenfield
from db_mcp_cli.utils import console


@click.command()
@click.argument("name", default="default", required=False)
@click.argument("source", default=None, required=False)
@click.option(
    "--template",
    "template_name",
    default=None,
    help="Built-in connector template id for greenfield API connections (for example: jira).",
)
def init(name: str, source: str | None, template_name: str | None):
    """Configure a new database connection.

    NAME is the connection name (default: "default").

    SOURCE is an optional git URL to clone an existing connection config.
    This enables "brownfield" setup where you join an existing team's
    semantic layer instead of starting from scratch.

    Examples:
        db-mcp init                           # New connection "default"
        db-mcp init mydb                      # New connection "mydb"
        db-mcp init mydb git@github.com:org/db-mcp-mydb.git  # Clone from git
    """
    # MCP client setup is optional for initialization; warn but continue.
    if not detect_installed_agents():
        supported_clients = ", ".join(agent.name for agent in AGENTS.values())
        console.print(
            Panel.fit(
                "[bold yellow]No MCP Clients Auto-Detected[/bold yellow]\n\n"
                f"db-mcp supports: {supported_clients}.\n"
                "Setup will continue now.\n"
                "You can choose one or several clients during agent setup,\n"
                "or select 'Configure later' and run [cyan]db-mcp agents[/cyan]\n"
                "or [cyan]db-mcp ui[/cyan] afterward.",
                border_style="yellow",
            )
        )

    # Determine if this is brownfield (git clone) or greenfield (new setup)
    is_brownfield = source and is_git_url(source)

    if is_brownfield:
        _init_brownfield(name, source)
    else:
        _init_greenfield(name, template_name=template_name)
