"""MCP protocol wrapper — re-exports inject_protocol from core.

inject_protocol lives in db_mcp.tools.protocol because core tool functions
call it directly.  This module re-exports it so mcp-server callers can import
from a single db_mcp_server namespace.
"""

from db_mcp.tools.protocol import CRITICAL_REMINDER, inject_protocol

__all__ = ["CRITICAL_REMINDER", "inject_protocol"]
