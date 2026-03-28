"""Connector contract commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import yaml
from pydantic import ValidationError

from db_mcp.connector_templates import list_connector_templates
from db_mcp.contracts.connector_contracts import (
    format_validation_error,
    validate_connector_contract,
)


def _load_yaml_document(path: Path) -> dict[str, Any]:
    with path.open() as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise click.ClickException("Connector file must contain a top-level YAML mapping.")
    return data


@click.group(help="Validate and inspect connector contract files.")
def connector():
    """Connector contract tools."""


@connector.command("validate")
@click.argument("connector_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def validate(connector_file: Path):
    """Validate a connector.yaml file against the versioned contract."""
    try:
        data = _load_yaml_document(connector_file)
    except yaml.YAMLError as exc:
        raise click.ClickException(f"Failed to parse YAML: {exc}") from exc

    is_template = "connector" in data and isinstance(data["connector"], dict)
    contract_payload = data["connector"] if is_template else data

    try:
        parsed = validate_connector_contract(contract_payload)
    except ValidationError as exc:
        details = format_validation_error(exc)
        detail_lines = "\n".join(f"  - {msg}" for msg in details)
        raise click.ClickException(f"Invalid connector contract:\n{detail_lines}") from exc

    if is_template:
        template_id = data.get("id", "<unknown>")
        click.echo(f"Connector template is valid: {connector_file}")
        click.echo(f"template id: {template_id}")
    else:
        click.echo(f"Connector contract is valid: {connector_file}")
    click.echo(f"spec_version: {parsed.spec_version}")
    click.echo(f"type/profile: {parsed.type}/{parsed.effective_profile}")


@connector.command("templates")
@click.option(
    "--type",
    "connector_type",
    type=click.Choice(["all", "api", "sql", "file"]),
    default="all",
    show_default=True,
    help="Filter available templates by connector type.",
)
def templates(connector_type: str):
    """List available connector templates."""
    selected_type = None if connector_type == "all" else connector_type
    templates = list_connector_templates(selected_type)
    for template in templates:
        connector = template.connector
        click.echo(
            f"{template.id}\t{connector.get('type', '')}\t"
            f"{connector.get('profile', '')}\t{template.title}"
        )


def register_commands(main_group: click.Group) -> None:
    """Register connector subgroup with the main group."""
    main_group.add_command(connector)
