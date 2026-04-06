"""Core command wiring: registers init, server, and connection management commands."""

import click

from db_mcp_cli.commands.connection_cmd import (
    all,
    doctor,
    edit,
    env_cmd,
    list_cmd,
    remove,
    rename,
    status,
    use,
)
from db_mcp_cli.commands.init_cmd import init
from db_mcp_cli.commands.server_cmd import config, start


def register_commands(main_group: click.Group) -> None:
    """Register all core commands with the main group."""
    main_group.add_command(init)
    main_group.add_command(start)
    main_group.add_command(config)
    main_group.add_command(status)
    main_group.add_command(list_cmd)
    main_group.add_command(use)
    main_group.add_command(edit)
    main_group.add_command(rename)
    main_group.add_command(remove)
    main_group.add_command(all)
    main_group.add_command(doctor)
    main_group.add_command(env_cmd)
