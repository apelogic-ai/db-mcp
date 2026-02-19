"""Shared utilities for MCP tools."""

from pathlib import Path

from db_mcp.config import get_settings
from db_mcp.connectors import get_connector, get_connector_capabilities
from db_mcp.registry import ConnectionRegistry


def _resolve_connection_path(connection: str | None) -> str | None:
    """Resolve a connection name to its filesystem path.

    Args:
        connection: Connection name (e.g., 'prod', 'staging').
            If None, returns None (use default connection).

    Returns:
        Absolute path to the connection directory, or None.
    """
    if connection is None:
        return None
    settings = get_settings()
    base = settings.connections_dir or str(Path.home() / ".db-mcp" / "connections")
    return str(Path(base) / connection)


def resolve_connection(
    connection: str | None,
    *,
    require_type: str | None = None,
    require_capability: str | None = None,
) -> tuple:
    """Resolve a connection parameter to (connector, name, path).

    Rules:
    - connection given → look up in registry, validate type/capability
    - connection=None, no discovered connections → legacy fallback (single conn)
    - connection=None, 1 connection → use it (backward compat)
    - connection=None, multiple connections:
        - if require_type set and only one of that type → use it
        - otherwise → raise ValueError listing available connections

    Args:
        connection: Connection name, or None to use default/auto-detect.
        require_type: If set, validate the connection is this type ('sql', 'api', etc.)
        require_capability: If set, validate the connection supports this capability.

    Returns:
        Tuple of (connector_instance, connection_name, connection_path).

    Raises:
        ValueError: With a helpful message listing available connections.
    """
    registry = ConnectionRegistry.get_instance()
    connections = registry.discover()

    if connection is not None:
        # Named lookup
        if connection not in connections:
            available = list(connections.keys())
            if available:
                raise ValueError(
                    f"Connection '{connection}' not found. "
                    f"Available connections: {', '.join(available)}"
                )
            else:
                raise ValueError(
                    f"Connection '{connection}' not found. No connections are configured."
                )

        info = connections[connection]

        # Validate type if required
        if require_type is not None and info.type != require_type:
            raise ValueError(
                f"Connection '{connection}' is type '{info.type}', "
                f"but '{require_type}' is required."
            )

        connector = registry.get_connector(connection)

        # Validate capability if required
        if require_capability is not None:
            caps = get_connector_capabilities(connector)
            if not caps.get(require_capability, False):
                raise ValueError(
                    f"Connection '{connection}' does not support '{require_capability}'."
                )

        return connector, connection, info.path

    # connection=None — need to figure out which connection to use
    if not connections:
        # Legacy mode: no connections discovered in connections_dir.
        # Fall back to the single active connection from settings.
        settings = get_settings()
        connector = get_connector()
        conn_name = settings.get_effective_provider_id()
        conn_path = settings.get_effective_connection_path()

        # Still validate capability if required
        if require_capability is not None:
            caps = get_connector_capabilities(connector)
            if not caps.get(require_capability, False):
                raise ValueError(
                    f"The active connection does not support '{require_capability}'."
                )

        if require_type is not None:
            from db_mcp.connectors import (
                APIConnector,
                FileConnector,
                MetabaseConnector,
                SQLConnector,
            )
            type_map = {
                "sql": SQLConnector,
                "file": FileConnector,
                "api": APIConnector,
                "metabase": MetabaseConnector,
            }
            expected_cls = type_map.get(require_type)
            if expected_cls is not None and not isinstance(connector, expected_cls):
                raise ValueError(
                    f"The active connection is not of type '{require_type}'."
                )

        return connector, conn_name, conn_path

    # Filter candidates by type if required
    if require_type is not None:
        candidates = {
            name: info for name, info in connections.items() if info.type == require_type
        }
    else:
        candidates = dict(connections)

    if len(candidates) == 1:
        name = next(iter(candidates))
        info = candidates[name]
        connector = registry.get_connector(name)

        # Validate capability if required
        if require_capability is not None:
            caps = get_connector_capabilities(connector)
            if not caps.get(require_capability, False):
                available_names = list(connections.keys())
                raise ValueError(
                    f"Connection '{name}' does not support '{require_capability}'. "
                    f"Available connections: {', '.join(available_names)}"
                )

        return connector, name, info.path

    if len(candidates) == 0:
        available_names = list(connections.keys())
        if require_type:
            msg = f"No connections of type '{require_type}' found."
        else:
            msg = "No connections found."
        if available_names:
            msg += f" Available connections: {', '.join(available_names)}"
        raise ValueError(msg)

    # Multiple candidates — require explicit selection
    available_names = list(candidates.keys())
    if require_type:
        msg = (
            f"Multiple {require_type} connections available: {', '.join(available_names)}. "
            f"Specify connection=<name> to select one."
        )
    else:
        msg = (
            f"Multiple connections available: {', '.join(available_names)}. "
            f"Specify connection=<name> to select one."
        )
    raise ValueError(msg)


def get_resolved_provider_id(connection: str | None) -> str:
    """Resolve connection param to a provider_id string for store operations.

    This is a lighter-weight helper for tools that only need the connection
    name (not the connector object) for accessing their per-connection stores
    (training examples, metrics catalog, gaps, etc.).

    Args:
        connection: Connection name, or None to use active connection.

    Returns:
        Connection name string suitable for use as provider_id in store calls.
    """
    if connection is not None:
        return connection

    settings = get_settings()
    return settings.get_effective_provider_id()
