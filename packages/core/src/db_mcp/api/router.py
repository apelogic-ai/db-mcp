"""REST API router — replaces BICP custom handlers.

Every handler is a standalone async function that calls service functions
directly. No BICP agent dependency. Mounted at ``/api/`` on the UI server.

Handler implementations are split into domain-grouped modules under
``db_mcp.api.handlers.*``. This file keeps dispatch logic and the HANDLERS
dispatch table. Shared helpers live in ``db_mcp.api.helpers``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# Re-export helpers for backward compatibility (some callers import from router)
from db_mcp.api.helpers import (  # noqa: F401
    _config_file,
    _connections_dir,
    _is_git_enabled,
    resolve_connection_context,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def _dispatch(method: str, params: dict[str, Any]) -> Any:
    handler = HANDLERS.get(method)
    if handler is None:
        return None  # sentinel — caller returns 404
    return await handler(params)


@router.post("/{method:path}")
async def dispatch_endpoint(method: str, request: Request) -> JSONResponse:
    """Route ``POST /api/<method>`` to the matching handler function."""
    body = await request.body()
    params: dict[str, Any] = {}
    if body:
        import json as _json

        params = _json.loads(body)

    result = await _dispatch(method, params)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown method: {method}"},
        )
    return JSONResponse(content=result)


# ===================================================================
# Handler imports — domain-grouped modules
# ===================================================================

from db_mcp.api.handlers.agents import (  # noqa: E402
    handle_agents_config_snippet,
    handle_agents_config_write,
    handle_agents_configure,
    handle_agents_list,
    handle_agents_remove,
)
from db_mcp.api.handlers.connections import (  # noqa: E402
    handle_connections_complete_onboarding,
    handle_connections_create,
    handle_connections_delete,
    handle_connections_discover,
    handle_connections_get,
    handle_connections_list,
    handle_connections_render_template,
    handle_connections_save_discovery,
    handle_connections_switch,
    handle_connections_sync,
    handle_connections_templates,
    handle_connections_test,
    handle_connections_update,
)
from db_mcp.api.handlers.context import (  # noqa: E402
    handle_context_add_rule,
    handle_context_create,
    handle_context_delete,
    handle_context_read,
    handle_context_tree,
    handle_context_usage,
    handle_context_write,
)
from db_mcp.api.handlers.git import (  # noqa: E402
    handle_git_history,
    handle_git_revert,
    handle_git_show,
)
from db_mcp.api.handlers.insights import (  # noqa: E402
    handle_gaps_dismiss,
    handle_insights_analyze,
    handle_insights_save_example,
)
from db_mcp.api.handlers.metrics import (  # noqa: E402
    handle_metrics_add,
    handle_metrics_approve,
    handle_metrics_candidates,
    handle_metrics_delete,
    handle_metrics_list,
    handle_metrics_update,
)
from db_mcp.api.handlers.playground import (  # noqa: E402
    handle_playground_install,
    handle_playground_status,
)
from db_mcp.api.handlers.schema import (  # noqa: E402
    handle_sample_table,
    handle_schema_catalogs,
    handle_schema_columns,
    handle_schema_schemas,
    handle_schema_tables,
    handle_schema_validate_link,
)
from db_mcp.api.handlers.traces import (  # noqa: E402
    handle_traces_clear,
    handle_traces_dates,
    handle_traces_list,
)

# ===================================================================
# Dispatch table
# ===================================================================

HANDLERS: dict[str, Any] = {
    # Connections
    "connections/list": handle_connections_list,
    "connections/switch": handle_connections_switch,
    "connections/create": handle_connections_create,
    "connections/test": handle_connections_test,
    "connections/delete": handle_connections_delete,
    "connections/get": handle_connections_get,
    "connections/update": handle_connections_update,
    "connections/templates": handle_connections_templates,
    "connections/render-template": handle_connections_render_template,
    "connections/save-discovery": handle_connections_save_discovery,
    "connections/complete-onboarding": handle_connections_complete_onboarding,
    "connections/sync": handle_connections_sync,
    "connections/discover": handle_connections_discover,
    # Context / Vault
    "context/tree": handle_context_tree,
    "context/read": handle_context_read,
    "context/write": handle_context_write,
    "context/create": handle_context_create,
    "context/delete": handle_context_delete,
    "context/add-rule": handle_context_add_rule,
    "context/usage": handle_context_usage,
    # Git
    "context/git/history": handle_git_history,
    "context/git/show": handle_git_show,
    "context/git/revert": handle_git_revert,
    # Traces
    "traces/list": handle_traces_list,
    "traces/clear": handle_traces_clear,
    "traces/dates": handle_traces_dates,
    # Insights
    "insights/analyze": handle_insights_analyze,
    "gaps/dismiss": handle_gaps_dismiss,
    "insights/save-example": handle_insights_save_example,
    # Metrics
    "metrics/list": handle_metrics_list,
    "metrics/add": handle_metrics_add,
    "metrics/update": handle_metrics_update,
    "metrics/delete": handle_metrics_delete,
    "metrics/candidates": handle_metrics_candidates,
    "metrics/approve": handle_metrics_approve,
    # Schema
    "schema/catalogs": handle_schema_catalogs,
    "schema/schemas": handle_schema_schemas,
    "schema/tables": handle_schema_tables,
    "schema/columns": handle_schema_columns,
    "schema/validate-link": handle_schema_validate_link,
    "sample_table": handle_sample_table,
    # Agents
    "agents/list": handle_agents_list,
    "agents/configure": handle_agents_configure,
    "agents/remove": handle_agents_remove,
    "agents/config-snippet": handle_agents_config_snippet,
    "agents/config-write": handle_agents_config_write,
    # Playground
    "playground/install": handle_playground_install,
    "playground/status": handle_playground_status,
}
