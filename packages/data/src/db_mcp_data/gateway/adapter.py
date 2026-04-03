"""ConnectorAdapter protocol and registry.

An adapter is a stateless bridge between the gateway and a physical connector.
The gateway resolves the connector instance (via get_connector) and passes it
to the appropriate adapter. Adapters normalise connector-specific return shapes
into consistent dicts.

Adapter contract
────────────────
  can_handle(connector)               → bool
      Return True if this adapter knows how to drive the given connector.
      Used by the gateway dispatcher (2.07) to route DataRequests.

  execute(connector, request, *, connection_path)  → dict
      Run the request against the connector. Returns a normalised result dict
      compatible with the existing ExecutionResult shape.

  introspect(connector, scope, *, catalog, schema, table) → dict
      Return schema objects for the requested scope:
        "catalogs"  → list of catalog names
        "schemas"   → list of schema names (optionally scoped to a catalog)
        "tables"    → list of table dicts (optionally scoped to catalog/schema)
        "columns"   → list of column dicts for a specific table
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from db_mcp_models.gateway import DataRequest

VALID_SCOPES: frozenset[str] = frozenset({"catalogs", "schemas", "tables", "columns"})


@runtime_checkable
class ConnectorAdapter(Protocol):
    """Protocol every adapter must satisfy."""

    def can_handle(self, connector: Any) -> bool:
        """Return True if this adapter can drive the given connector instance."""
        ...

    def execute(
        self,
        connector: Any,
        request: DataRequest,
        *,
        connection_path: Path,
    ) -> dict[str, Any]:
        """Execute a DataRequest and return a normalised result dict."""
        ...

    def introspect(
        self,
        connector: Any,
        scope: str,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        table: str | None = None,
    ) -> dict[str, Any]:
        """Return schema objects for *scope* from the connector.

        scope must be one of VALID_SCOPES.
        """
        ...
