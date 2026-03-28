# Connector Plugins

`db-mcp` supports connector plugins built from:

- a declarative `connector.yaml` template
- an optional Python runtime factory for product-specific behavior

Plugins are discovered from the Python entry point group `db_mcp.connector_plugins`.

## Minimal Plugin Shape

```text
my-connector-plugin/
  pyproject.toml
  src/my_connector_plugin/
    __init__.py
    connector.yaml
    runtime.py
```

## Entry Point

```toml
[project.entry-points."db_mcp.connector_plugins"]
my_connector = "my_connector_plugin:plugin"
```

The entry point should return either:

- one `ConnectorPlugin`
- or an iterable of `ConnectorPlugin` objects

## YAML-Only Plugin

```python
from pathlib import Path

from db_mcp.connector_plugins import yaml_connector_plugin


def plugin():
    return yaml_connector_plugin(
        template_path=Path(__file__).with_name("connector.yaml"),
    )
```

## Plugin With Runtime Logic

```python
from pathlib import Path

from db_mcp.connector_plugins import ConnectorPlugin

from .runtime import build_connector


def plugin():
    return ConnectorPlugin(
        id="my_connector",
        template_path=Path(__file__).with_name("connector.yaml"),
        runtime_factory=build_connector,
    )
```

The runtime factory signature is:

```python
def build_connector(connector_data: dict, connection_path: Path, settings) -> Connector:
    ...
```

## Recommended Split

- Put static configuration in `connector.yaml`
- Put runtime discovery, routing, or SQL rewriting in `runtime.py`
- Keep runtime code small and delegate shared HTTP/auth behavior to core connector classes where possible

## Example

See [`packages/core/examples/connector_plugin_example`](/Users/lbelyaev/dev/db-mcp/packages/core/examples/connector_plugin_example).

