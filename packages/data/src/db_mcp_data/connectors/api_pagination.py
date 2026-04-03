"""Pagination and response-extraction helpers for the API connector.

Extracted from ``APIConnector`` to reduce the size of ``api.py``.
Contains only stateless utility functions (no ``self``).
"""

from __future__ import annotations

from typing import Any


def get_nested_value(payload: Any, path: str) -> Any:
    """Resolve a dotted field path from a nested JSON-like payload."""
    if not path:
        return None
    value = payload
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def normalize_column_names(columns: list[Any]) -> list[str]:
    """Normalize column descriptors into a list of output field names."""
    names: list[str] = []
    for column in columns:
        if isinstance(column, dict):
            names.append(str(column.get("name") or column.get("field") or ""))
        else:
            names.append(str(column))
    return names


def rows_from_columnar_payload(
    columns: Any,
    rows_data: Any,
) -> list[dict[str, Any]]:
    """Convert column names plus row arrays into row dicts."""
    if not isinstance(columns, list) or not isinstance(rows_data, list):
        return []
    if not rows_data or not isinstance(rows_data[0], list):
        return []
    names = normalize_column_names(columns)
    return [dict(zip(names, row)) for row in rows_data]


def extract_cursor(data: list[dict], cursor_field: str) -> str | None:
    """Extract cursor value from data using a simple field path.

    Supports:
      - "data[-1].id" -> last item's "id" field
      - "id" -> last item's "id" field (shorthand)
    """
    if not data:
        return None
    item = data[-1]
    field = cursor_field
    if "." in field:
        field = field.rsplit(".", 1)[-1]
    value = item.get(field)
    return str(value) if value is not None else None


def render_template_value(value: Any, context: dict[str, Any]) -> Any:
    """Recursively render ``{{key}}`` placeholders inside a JSON-compatible value."""
    if isinstance(value, str):
        for key, replacement in context.items():
            if value == f"{{{{{key}}}}}":
                return replacement
        rendered = value
        for key, replacement in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(replacement))
        return rendered
    if isinstance(value, list):
        return [render_template_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_template_value(item, context) for key, item in value.items()}
    return value
