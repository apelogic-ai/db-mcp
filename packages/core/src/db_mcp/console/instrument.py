"""Instrument stub — moved to db_mcp_server.console.instrument (Phase 3).

The real FastMCP middleware implementation lives in db_mcp_server.
This stub keeps the import path alive so code that imports
`from db_mcp.console.instrument import instrument_server` continues
to work while cli/ is still in core (Phase 3.08-3.10 will clean up).
"""

from __future__ import annotations

from typing import Any


def instrument_server(mcp: Any) -> None:
    """Wire FastMCP tracing middleware.  Defers to mcp-server implementation."""
    try:
        from db_mcp_server.console.instrument import instrument_server as _real
        _real(mcp)
    except ImportError:
        pass  # db_mcp_server not installed; skip instrumentation
