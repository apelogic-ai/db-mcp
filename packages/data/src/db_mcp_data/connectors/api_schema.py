"""Schema introspection helpers for the API connector.

Extracted from ``APIConnector`` to reduce the size of ``api.py``.
Contains stateless utility functions for schema type mapping.
"""

from __future__ import annotations


def map_schema_type(base_type: str | None) -> str:
    """Best-effort type mapping for API schema metadata."""
    if not base_type:
        return "VARCHAR"
    lowered = base_type.lower()
    if "integer" in lowered:
        return "INTEGER"
    if "decimal" in lowered:
        return "DECIMAL"
    if "float" in lowered or "number" in lowered:
        return "DOUBLE"
    if "boolean" in lowered:
        return "BOOLEAN"
    if "datetime" in lowered or "date" in lowered:
        return "TIMESTAMP"
    return "VARCHAR"
