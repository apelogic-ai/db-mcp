"""Connector plugin registry.

Provides a small plugin surface for shipping connector templates and optional
runtime factories via Python entry points.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

ENTRY_POINT_GROUP = "db_mcp.connector_plugins"

ConnectorRuntimeFactory = Callable[[dict[str, Any], Path, Any], Any]


@dataclass(frozen=True)
class ConnectorPlugin:
    """A connector plugin backed by a declarative template and optional runtime."""

    id: str
    template_path: Path
    runtime_factory: ConnectorRuntimeFactory | None = None
    source: str = "builtin"
    package_name: str | None = None


def yaml_connector_plugin(
    *,
    template_path: str | Path,
    runtime_factory: ConnectorRuntimeFactory | None = None,
    source: str = "community",
    package_name: str | None = None,
) -> ConnectorPlugin:
    """Create a connector plugin from a template YAML file."""
    path = Path(template_path).resolve()
    with path.open() as f:
        payload = yaml.safe_load(f) or {}

    plugin_id = str(payload.get("id", "") or "").strip()
    if not plugin_id:
        raise ValueError(f"Connector template is missing id: {path}")

    return ConnectorPlugin(
        id=plugin_id,
        template_path=path,
        runtime_factory=runtime_factory,
        source=source,
        package_name=package_name,
    )


def _builtin_template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / "connectors"


def _builtin_runtime_factory(plugin_id: str) -> ConnectorRuntimeFactory | None:
    if plugin_id == "metabase":
        from db_mcp.connector_plugins.builtin.metabase import build_metabase_connector

        return build_metabase_connector
    if plugin_id == "superset":
        from db_mcp.connector_plugins.builtin.superset import build_superset_connector

        return build_superset_connector
    return None


def _builtin_connector_plugins() -> list[ConnectorPlugin]:
    plugins: list[ConnectorPlugin] = []
    for path in sorted(_builtin_template_dir().glob("*.yaml")):
        plugin = yaml_connector_plugin(
            template_path=path,
            source="builtin",
            package_name="db-mcp",
        )
        runtime_factory = _builtin_runtime_factory(plugin.id)
        if runtime_factory is not None:
            plugin = replace(plugin, runtime_factory=runtime_factory)
        plugins.append(plugin)
    return plugins


def _iter_plugin_entry_points() -> list[Any]:
    discovered = entry_points()
    if hasattr(discovered, "select"):
        return list(discovered.select(group=ENTRY_POINT_GROUP))
    return list(discovered.get(ENTRY_POINT_GROUP, []))


def _normalize_plugin_exports(exported: Any, *, package_name: str | None) -> list[ConnectorPlugin]:
    if callable(exported) and not isinstance(exported, ConnectorPlugin):
        exported = exported()

    if isinstance(exported, ConnectorPlugin):
        return [
            replace(
                exported,
                package_name=exported.package_name or package_name,
            )
        ]

    if isinstance(exported, Iterable) and not isinstance(exported, (str, bytes, dict)):
        plugins: list[ConnectorPlugin] = []
        for item in exported:
            if not isinstance(item, ConnectorPlugin):
                raise TypeError(
                    "Connector plugin entry points must return ConnectorPlugin objects"
                )
            plugins.append(replace(item, package_name=item.package_name or package_name))
        return plugins

    raise TypeError("Connector plugin entry points must return a ConnectorPlugin or iterable")


@lru_cache(maxsize=1)
def list_connector_plugins() -> list[ConnectorPlugin]:
    """List built-in and installed connector plugins."""
    plugins = list(_builtin_connector_plugins())
    seen_ids = {plugin.id for plugin in plugins}

    for entry_point in _iter_plugin_entry_points():
        exported = entry_point.load()
        loaded_plugins = _normalize_plugin_exports(
            exported,
            package_name=getattr(entry_point, "module", None),
        )
        for plugin in loaded_plugins:
            if plugin.id in seen_ids:
                continue
            plugins.append(plugin)
            seen_ids.add(plugin.id)

    return plugins


def get_connector_plugin(plugin_id: str) -> ConnectorPlugin | None:
    """Resolve a connector plugin by id."""
    for plugin in list_connector_plugins():
        if plugin.id == plugin_id:
            return plugin
    return None


def clear_connector_plugin_cache() -> None:
    """Clear plugin registry cache for tests and reloads."""
    list_connector_plugins.cache_clear()
