"""Local OTel console for dbmeta.

Provides a simple web UI to view traces from the MCP server.
"""

from dbmcp.console.collector import SpanCollector
from dbmcp.console.server import start_console

__all__ = ["start_console", "SpanCollector"]
