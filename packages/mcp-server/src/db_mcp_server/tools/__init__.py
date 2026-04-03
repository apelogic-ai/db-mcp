"""MCP tool wrapper modules (step 3.06).

Each module in this package is a thin MCP entry-point that:
  - Calls db_mcp.services.* (or underlying knowledge/data stores) directly
  - Applies MCP protocol formatting via db_mcp_server.protocol.inject_protocol
  - Does NOT import business logic from db_mcp.tools.*

Groups that call services.* directly (Phase 3.06 complete):
  database  → db_mcp.services.schema
  metrics   → db_mcp.metrics.store + db_mcp.services.connection
  vault     → db_mcp.services.vault

Groups that re-export from db_mcp.tools.* pending service extraction (TODO):
  api       → db_mcp.tools.api       (no services layer yet)
  code      → db_mcp.tools.code      (sandbox, no service abstraction)
  daemon    → db_mcp.tools.daemon_tasks (no services layer yet)
  exec      → db_mcp.tools.exec      (sandbox, no service abstraction)
  gaps      → db_mcp.tools.gaps      (no services layer yet)
  generation → db_mcp.tools.generation (complex, partial services coverage)
  intent    → db_mcp.tools.intent    (orchestrator, no dedicated service)
  shell     → db_mcp.tools.shell     (vault bash, no service abstraction)
  training  → db_mcp.tools.training  (no services layer yet)
  utils     → db_mcp.tools.utils     (connection helpers)
"""
