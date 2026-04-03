"""REST API router for db-mcp UI (Phase 4.09).

Replaces 48 custom BICP JSON-RPC handlers with a plain REST dispatch
endpoint. Each method maps to a handler function that calls services directly.
"""

from db_mcp.api.router import router

__all__ = ["router"]
