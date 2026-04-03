"""Connector plugin SDK.

Community packages can register entry points in the ``db_mcp.connector_plugins``
group and return one or more ``ConnectorPlugin`` objects backed by YAML
templates plus optional runtime factories.
"""

from db_mcp_data.connector_plugins.registry import (
    ConnectorPlugin,
    clear_connector_plugin_cache,
    get_connector_plugin,
    list_connector_plugins,
    yaml_connector_plugin,
)

__all__ = [
    "ConnectorPlugin",
    "clear_connector_plugin_cache",
    "get_connector_plugin",
    "list_connector_plugins",
    "yaml_connector_plugin",
]

