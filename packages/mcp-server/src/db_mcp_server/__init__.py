"""db-mcp-server — FastMCP entry point for db-mcp.

This package contains everything that depends on FastMCP:
  server.py        — FastMCP server creation and tool registration
  instructions.py  — MCP system-prompt instruction templates
  protocol.py      — inject_protocol (MCP response wrapper)
  tool_catalog.py  — tool catalog and SDK rendering
  tools/           — thin tool wrappers (re-exported from core)
  console/         — FastMCP middleware for tracing
"""
