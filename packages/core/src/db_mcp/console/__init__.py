"""db-mcp.

Provides a simple web UI to view traces from the MCP server.
"""

from db_mcp.console.collector import SpanCollector
from db_mcp.console.server import start_console

__all__ = ["start_console", "SpanCollector"]
