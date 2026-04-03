"""MCP presentation layer — inject_protocol and the CRITICAL_REMINDER banner.

This is the canonical location for inject_protocol.  It is an MCP-only concern:
it wraps tool responses with a structured reminder that guides the model to read
the vault protocol before writing SQL.

Rule: nothing in services/ or gateway/ may import from this module.
Entry points (tools/, bicp/) are the only permitted callers.
"""

from __future__ import annotations

import json

# Critical reminder injected into every MCP tool response
CRITICAL_REMINDER = """
## CRITICAL REMINDER

**0. FIRST: Read and follow the knowledge vault protocol:**
   shell(command='cat PROTOCOL.md')

**Database uses 3-level hierarchy: catalog.schema.table**

Before writing SQL:
1. Use list_catalogs() to see available catalogs
2. Use list_schemas(catalog='...') to see schemas
3. Use list_tables(catalog='...', schema='...') with BOTH parameters

---
"""


def inject_protocol(result: dict, session_id: str | None = None):
    """Inject the CRITICAL_REMINDER banner into an MCP tool response.

    For small results: reminder + full JSON in text content.
    For large results: reminder + summary only (full data in structuredContent).

    Args:
        result:     Tool result dict produced by a service call.
        session_id: Unused; kept for API compatibility.

    Returns:
        CallToolResult with text content and structured data, or the original
        value unchanged if it is not a dict.
    """
    if not isinstance(result, dict):
        return result

    reminder = CRITICAL_REMINDER.strip()

    data = result.get("data", [])
    is_large = isinstance(data, list) and len(data) > 20

    if is_large:
        rows = len(data)
        status = result.get("status", "unknown")
        summary = f"Status: {status}, Rows: {rows}"
        if "columns" in result:
            summary += f", Columns: {result['columns']}"
        text_output = (
            f"{reminder}\n\n--- RESULT SUMMARY ---\n{summary}\n\n"
            "(Full data in structured response)"
        )
    else:
        json_data = json.dumps(result, indent=2, default=str)
        text_output = f"{reminder}\n\n--- DATA ---\n\n{json_data}"

    # Return a rich CallToolResult when the mcp package is available (mcp-server
    # context). Fall back to a plain string so core can run without fastmcp.
    try:
        from mcp.types import CallToolResult, TextContent  # noqa: PLC0415

        return CallToolResult(
            content=[TextContent(type="text", text=text_output)],
            structuredContent=result,
            isError=False,
        )
    except ImportError:
        return text_output
