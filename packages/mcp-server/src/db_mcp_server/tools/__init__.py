"""MCP tool wrapper modules.

Modules with real logic (call services directly):
  database   → db_mcp.services.schema
  generation → db_mcp.services.query / db_mcp_data.execution
  metrics    → db_mcp.services.metrics / db_mcp_knowledge.metrics.store
  vault      → db_mcp.services.vault

All other tool functions are imported directly from db_mcp.tools.*
in server.py (no pass-through stubs).
"""
