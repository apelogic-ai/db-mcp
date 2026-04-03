import inspect
from unittest.mock import patch

from db_mcp_data.connector_plugins import (
    ConnectorPlugin,
    clear_connector_plugin_cache,
    list_connector_plugins,
    yaml_connector_plugin,
)
from db_mcp_data.connector_templates import get_connector_template
from db_mcp_data.connectors import get_connector
from db_mcp_data.connectors.api import APIConnector


class _StubConnector:
    def test_connection(self):
        return {"connected": True}

    def get_dialect(self):
        return "stub"

    def get_catalogs(self):
        return [None]

    def get_schemas(self, catalog=None):
        return [None]

    def get_tables(self, schema=None, catalog=None):
        return []

    def get_columns(self, table_name, schema=None, catalog=None):
        return []

    def get_table_sample(self, table_name, schema=None, catalog=None, limit=5):
        return []

    def execute_sql(self, sql, params=None):
        return []


class _FakeEntryPoint:
    def __init__(self, value, module="db_mcp_connector_example"):
        self._value = value
        self.module = module

    def load(self):
        return self._value


def test_builtin_connector_plugins_cover_shipped_templates():
    clear_connector_plugin_cache()

    plugins = list_connector_plugins()
    ids = {plugin.id for plugin in plugins}
    plugin_by_id = {plugin.id: plugin for plugin in plugins}

    assert {"jira", "dune", "metabase", "superset"}.issubset(ids)
    assert all(plugin.template_path.name.endswith(".yaml") for plugin in plugins)
    assert plugin_by_id["metabase"].runtime_factory is not None
    assert plugin_by_id["superset"].runtime_factory is not None


def test_generic_api_connector_source_is_vendor_neutral():
    source = inspect.getsource(APIConnector).lower()

    assert "metabase" not in source
    assert "superset" not in source


def test_entry_point_connector_plugin_is_loaded(tmp_path):
    template_path = tmp_path / "widget.yaml"
    template_path.write_text(
        "id: widget\n"
        "title: Widget API\n"
        "connector:\n"
        "  spec_version: 1.0.0\n"
        "  type: api\n"
        "  profile: api_openapi\n"
        "  base_url: https://widget.example.com\n"
    )

    plugin = yaml_connector_plugin(template_path=template_path)

    clear_connector_plugin_cache()
    with patch(
        "db_mcp_data.connector_plugins.registry._iter_plugin_entry_points",
        return_value=[_FakeEntryPoint(lambda: plugin)],
    ):
        plugins = list_connector_plugins()

    assert any(item.id == "widget" for item in plugins)
    template = get_connector_template("widget")
    assert template is not None
    assert template.title == "Widget API"


def test_get_connector_uses_plugin_runtime_factory(tmp_path):
    (tmp_path / "connector.yaml").write_text(
        "spec_version: 1.0.0\n"
        "type: api\n"
        "template_id: widget_runtime\n"
        "base_url: https://widget.example.com\n"
    )

    stub = _StubConnector()

    def _factory(connector_data, conn_path):
        assert connector_data["template_id"] == "widget_runtime"
        assert conn_path == tmp_path
        return stub

    plugin = ConnectorPlugin(
        id="widget_runtime",
        template_path=tmp_path / "widget_runtime.yaml",
        runtime_factory=_factory,
        source="test",
    )

    clear_connector_plugin_cache()
    with patch("db_mcp_data.connectors.get_connector_plugin", return_value=plugin):
        connector = get_connector(connection_path=tmp_path)

    assert connector is stub
