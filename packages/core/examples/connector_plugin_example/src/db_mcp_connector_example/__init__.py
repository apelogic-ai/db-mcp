from pathlib import Path

from db_mcp_data.connector_plugins import ConnectorPlugin

from .runtime import build_connector


def plugin():
    return ConnectorPlugin(
        id="example_widget",
        template_path=Path(__file__).with_name("connector.yaml"),
        runtime_factory=build_connector,
        source="community",
    )

