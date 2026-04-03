"""Re-export shim — canonical location is db_mcp_data.connectors.templates."""

from db_mcp_data.connectors.templates import (  # noqa: F401
    ConnectorTemplate,
    ConnectorTemplateEnvVar,
    get_connector_template,
    list_connector_templates,
    match_connector_template,
    materialize_connector_template,
)
