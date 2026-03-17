"""Tool catalog, discovery, and SDK rendering helpers."""

from __future__ import annotations

import keyword
import re
from typing import Any

_NAME_RE = re.compile(r"[^0-9a-zA-Z_]+")


def _safe_identifier(value: str) -> str:
    ident = _NAME_RE.sub("_", value).strip("_")
    if not ident:
        ident = "tool"
    if ident[0].isdigit():
        ident = f"tool_{ident}"
    if keyword.iskeyword(ident):
        ident = f"{ident}_"
    return ident


def _infer_category(name: str) -> str:
    if name in {"ping", "get_config", "list_connections", "search_tools", "export_tool_sdk"}:
        return "system"
    if name.startswith("api_"):
        return "api"
    if (
        name.startswith("mcp_setup_")
        or name.startswith("mcp_domain_")
        or name.startswith("import_")
    ):
        return "onboarding"
    if name.startswith("query_"):
        return "training"
    if name.startswith("metrics_"):
        return "metrics"
    if name in {"shell", "protocol", "exec"}:
        return "shell"
    if name == "code":
        return "code"
    if name in {"dismiss_insight", "mark_insights_processed"} or name.startswith("mcp_"):
        return "insights"
    if name in {"run_sql", "validate_sql", "get_result", "get_data", "export_results"}:
        return "query"
    if name.startswith("list_") or name in {
        "describe_table",
        "sample_table",
        "test_connection",
        "detect_dialect",
        "get_dialect_rules",
        "get_connection_dialect",
    }:
        return "schema"
    return "other"


def build_tool_catalog(server: Any) -> list[dict[str, Any]]:
    """Build tool metadata from the active FastMCP tool manager."""
    manager = getattr(server, "_tool_manager", None)
    tools = getattr(manager, "_tools", {}) if manager is not None else {}
    if not isinstance(tools, dict):
        return []

    entries: list[dict[str, Any]] = []
    for name, tool in sorted(tools.items()):
        description = (getattr(tool, "description", "") or "").strip()
        parameters = getattr(tool, "parameters", {}) or {}
        if not isinstance(parameters, dict):
            parameters = {}
        required = parameters.get("required", [])
        if not isinstance(required, list):
            required = []
        properties = parameters.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        entries.append(
            {
                "name": name,
                "description": description,
                "category": _infer_category(name),
                "required": [item for item in required if isinstance(item, str)],
                "properties": properties,
            }
        )
    return entries


def _score_tool(entry: dict[str, Any], tokens: list[str], phrase: str) -> int:
    hay_name = entry["name"].lower()
    hay_desc = entry["description"].lower()
    score = 0
    if phrase:
        if phrase in hay_name:
            score += 10
        if phrase in hay_desc:
            score += 4
    for token in tokens:
        if token in hay_name:
            score += 3
        if token in hay_desc:
            score += 1
    if hay_name.startswith(phrase):
        score += 2
    return score


def search_tool_catalog(
    catalog: list[dict[str, Any]],
    query: str = "",
    limit: int = 12,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Search tool metadata with a simple lexical scorer."""
    phrase = query.strip().lower()
    tokens = [tok for tok in re.split(r"\s+", phrase) if tok]
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in catalog:
        if category and entry["category"] != category:
            continue
        score = _score_tool(entry, tokens, phrase) if phrase else 1
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [entry for _, entry in scored[:limit]]


def _schema_type(schema: dict[str, Any]) -> tuple[str, bool]:
    if not isinstance(schema, dict):
        return "Any", False

    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        types = []
        has_null = False
        for variant in any_of:
            if not isinstance(variant, dict):
                continue
            type_value = variant.get("type")
            if type_value == "null":
                has_null = True
            elif isinstance(type_value, str):
                types.append(type_value)
        base = types[0] if types else "any"
        py_type, _ = _schema_type({"type": base})
        return py_type, has_null

    type_value = schema.get("type")
    if type_value == "string":
        return "str", False
    if type_value == "integer":
        return "int", False
    if type_value == "number":
        return "float", False
    if type_value == "boolean":
        return "bool", False
    if type_value == "array":
        return "list[Any]", False
    if type_value == "object":
        return "dict[str, Any]", False
    return "Any", False


def render_python_sdk(
    catalog: list[dict[str, Any]],
    class_name: str = "DbMcpTools",
) -> str:
    """Render a small async Python SDK from tool metadata."""
    lines = [
        '"""Generated db-mcp tool client wrappers."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "from collections.abc import Awaitable, Callable",
        "",
        "",
        f"class {class_name}:",
        "    def __init__(",
        "        self,",
        "        call_tool: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],",
        "    ) -> None:",
        "        self._call_tool = call_tool",
        "",
    ]

    for entry in catalog:
        name = entry["name"]
        method_name = _safe_identifier(name)
        if entry["description"]:
            description = entry["description"].splitlines()[0]
        else:
            description = "No description."

        properties = entry.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        required = set(entry.get("required", []))

        required_items: list[tuple[str, dict[str, Any]]] = []
        optional_items: list[tuple[str, dict[str, Any]]] = []
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                prop_schema = {}
            if prop_name in required:
                required_items.append((prop_name, prop_schema))
            else:
                optional_items.append((prop_name, prop_schema))

        signature = ["self"]
        payload_lines = ["        payload: dict[str, Any] = {}"]

        for prop_name, prop_schema in required_items:
            ident = _safe_identifier(prop_name)
            py_type, nullable = _schema_type(prop_schema)
            annotation = f"{py_type} | None" if nullable else py_type
            signature.append(f"{ident}: {annotation}")
            payload_lines.append(f'        payload["{prop_name}"] = {ident}')

        for prop_name, prop_schema in optional_items:
            ident = _safe_identifier(prop_name)
            py_type, nullable = _schema_type(prop_schema)
            has_default = "default" in prop_schema
            if has_default:
                default_value = repr(prop_schema["default"])
                annotation = f"{py_type} | None" if nullable else py_type
                signature.append(f"{ident}: {annotation} = {default_value}")
                payload_lines.append(f'        payload["{prop_name}"] = {ident}')
            else:
                signature.append(f"{ident}: {py_type} | None = None")
                payload_lines.append(f"        if {ident} is not None:")
                payload_lines.append(f'            payload["{prop_name}"] = {ident}')

        lines.append(f"    async def {method_name}({', '.join(signature)}) -> dict[str, Any]:")
        lines.append(f'        """{description}"""')
        lines.extend(payload_lines)
        lines.append(f'        return await self._call_tool("{name}", payload)')
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
