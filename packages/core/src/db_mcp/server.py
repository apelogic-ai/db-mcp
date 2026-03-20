"""FastMCP server for db-mcp."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from pydantic_ai import Agent
from starlette.requests import Request
from starlette.responses import JSONResponse

from db_mcp.config import get_settings
from db_mcp.exec_runtime import shutdown_exec_session_manager
from db_mcp.insider import start_insider_supervisor, stop_insider_supervisor
from db_mcp.onboarding.state import get_connection_path
from db_mcp.tasks.store import get_task_store
from db_mcp.tool_catalog import build_tool_catalog, render_python_sdk, search_tool_catalog
from db_mcp.tools.api import (
    _api_describe_endpoint,
    _api_discover,
    _api_execute_sql,
    _api_mutate,
    _api_query,
)
from db_mcp.tools.code import _code
from db_mcp.tools.daemon_tasks import (
    _execute_task,
    _prepare_task,
)
from db_mcp.tools.database import (
    _describe_table,
    _detect_dialect,
    _list_catalogs,
    _list_connections,
    _list_schemas,
    _list_tables,
    _sample_table,
    _test_connection,
)
from db_mcp.tools.dialect import _get_connection_dialect, _get_dialect_rules
from db_mcp.tools.domain import (
    _domain_approve,
    _domain_generate,
    _domain_skip,
    _domain_status,
)
from db_mcp.tools.exec import _exec
from db_mcp.tools.gaps import _dismiss_knowledge_gap, _get_knowledge_gaps
from db_mcp.tools.generation import (
    _export_results,
    _get_data,
    _get_result,
    _run_sql,
    _test_elicitation,
    _test_sampling,
    _validate_sql,
)
from db_mcp.tools.metrics import (
    _metrics_add,
    _metrics_approve,
    _metrics_discover,
    _metrics_list,
    _metrics_remove,
)
from db_mcp.tools.onboarding import (
    _onboarding_add_ignore_pattern,
    _onboarding_approve,
    _onboarding_bulk_approve,
    _onboarding_discover,
    _onboarding_discover_status,
    _onboarding_import_descriptions,
    _onboarding_import_ignore_patterns,
    _onboarding_next,
    _onboarding_remove_ignore_pattern,
    _onboarding_reset,
    _onboarding_skip,
    _onboarding_start,
    _onboarding_status,
)
from db_mcp.tools.shell import (
    SHELL_DESCRIPTION_DETAILED,
    SHELL_DESCRIPTION_SHELL_MODE,
    _protocol,
    _shell,
)
from db_mcp.tools.training import (
    _import_examples,
    _import_instructions,
    _query_add_rule,
    _query_approve,
    _query_feedback,
    _query_generate,
    _query_list_examples,
    _query_list_rules,
    _query_status,
)
from db_mcp.vault import ensure_connection_structure, migrate_to_connection_structure
from db_mcp.vault.migrate import migrate_namespace


class HealthCheckFilter(logging.Filter):
    """Filter out health check requests from uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        # Filter out GET /health requests
        if "GET /health" in message:
            return False
        return True


# Apply filter to uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


def _get_auth_provider():
    """Get auth provider based on config.

    Uses DiskStore on the providers PVC for OAuth client storage, which
    persists sessions across restarts. For HA deployments with multiple
    replicas, consider using RedisStore with FernetEncryptionWrapper.
    """
    settings = get_settings()
    if settings.auth0_enabled and settings.auth0_domain:
        from fastmcp.server.auth.providers.auth0 import Auth0Provider
        from key_value.aio.stores.disk import DiskStore

        # Use connection path for OAuth session storage
        oauth_storage_path = settings.get_effective_connection_path() / ".oauth"

        provider = Auth0Provider(
            config_url=f"https://{settings.auth0_domain}/.well-known/openid-configuration",
            client_id=settings.auth0_client_id,
            client_secret=settings.auth0_client_secret,
            audience=settings.auth0_audience,
            base_url=settings.auth0_base_url,
            client_storage=DiskStore(directory=oauth_storage_path),
        )
        # Allow Claude's redirect URI for DCR compatibility
        # See: https://github.com/jlowin/fastmcp/issues/1564
        provider._allowed_client_redirect_uris = [
            "https://claude.ai/api/mcp/auth_callback",
            "http://localhost:*",
            "http://127.0.0.1:*",
        ]
        return provider
    return None


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Server lifespan for startup/shutdown tasks."""
    logger = logging.getLogger(__name__)

    # Startup: Start background task cleanup loop
    task_store = get_task_store()
    await task_store.start_cleanup_loop(interval_seconds=300)  # Every 5 minutes
    logger.info("Task store cleanup loop started")

    settings = get_settings()
    insider_supervisor = None
    if settings.tool_mode == "daemon":
        try:
            insider_supervisor = await start_insider_supervisor(
                settings.get_effective_connection_path()
            )
        except Exception as exc:
            logger.warning("Insider supervisor startup skipped: %s", exc)

    # Startup: Pull latest collab changes (session mode — pull-on-start)
    collab_user_name = None
    collab_connection_path = None
    try:
        from db_mcp.collab.manifest import get_member, load_manifest
        from db_mcp.collab.sync import collaborator_pull
        from db_mcp.traces import get_user_id_from_config

        settings = get_settings()
        connection_path = settings.get_effective_connection_path()
        manifest = load_manifest(connection_path)
        if manifest and manifest.sync.auto_sync:
            user_id = get_user_id_from_config()
            member = get_member(manifest, user_id) if user_id else None
            if member and member.role == "collaborator":
                collab_user_name = member.user_name or user_id
                collab_connection_path = connection_path
                await asyncio.to_thread(collaborator_pull, connection_path, collab_user_name)
                logger.info("Collab pull on startup for %s", member.user_name)
    except Exception as e:
        logger.debug("Collab pull on startup skipped: %s", e)

    try:
        yield
    finally:
        if insider_supervisor is not None:
            await stop_insider_supervisor()
        shutdown_exec_session_manager()
        # Shutdown: Push collab changes (session mode — push-on-stop)
        if collab_user_name and collab_connection_path:
            try:
                from db_mcp.collab.sync import collaborator_push

                result = await asyncio.to_thread(
                    collaborator_push, collab_connection_path, collab_user_name
                )
                if result.additive_merged or result.shared_state_files:
                    logger.info(
                        "Collab push on shutdown: %d additive, %d shared-state",
                        result.additive_merged,
                        len(result.shared_state_files),
                    )
            except Exception as e:
                logger.warning("Collab push on shutdown failed: %s", e)

        # Shutdown: Stop cleanup loop
        await task_store.stop_cleanup_loop()
        logger.info("Task store cleanup loop stopped")


# =============================================================================
# Server Instructions by Mode
# =============================================================================

INSTRUCTIONS_DETAILED = """
Database metadata and query intelligence server.

## BEFORE ANY QUERY WORK

1. Read the knowledge vault protocol:
   ```
   shell(command="cat PROTOCOL.md")
   ```

2. Check SQL rules for this database:
   ```
   shell(command="cat instructions/sql_rules.md")
   ```

3. Check business metrics and dimensions:
   ```
   metrics_list()
   ```
   Use these canonical definitions when the user asks about KPIs, aggregations, or
   dimensions. Prefer metric SQL templates over generating from scratch.
   Use `metrics_discover()` to mine the vault for new candidates.

## CRITICAL: Database Hierarchy

Many databases use 3-level hierarchy: `catalog.schema.table`
- Use `list_catalogs()` FIRST if available
- Then `list_schemas(catalog="...")`
- Then `list_tables(catalog="...", schema="...")`

Do NOT skip to schema level - this causes "table not found" errors.

## After Successful Queries

Save examples and tell the user what you saved. See PROTOCOL.md for details.

## Tools Available

- Schema discovery: list_catalogs, list_schemas, list_tables, describe_table
- Query: get_data, run_sql, validate_sql, get_result, export_results
- Knowledge vault: shell (bash access to examples, learnings, instructions)
- Business rules: query_add_rule, query_list_rules
- Knowledge gaps: get_knowledge_gaps, dismiss_knowledge_gap
- Metrics: metrics_list, metrics_discover, metrics_approve, metrics_add, metrics_remove
- Training: query_approve, query_feedback, query_list_examples
- Setup: mcp_setup_*, mcp_domain_*

## Knowledge Gaps

Call `get_knowledge_gaps()` to see terms that previous sessions couldn't map to
schema columns. If you resolve any during your work, use `query_add_rule` to add
the mapping — the gap will auto-resolve.
"""

INSTRUCTIONS_DAEMON = """
Executor-like db-mcp daemon runtime.

Use this two-step workflow:

1. Call `prepare_task(question=..., connection=...)`
   This returns a lean structured context packet for the first attempt:
   - explicit disambiguation
   - decision hints (preferred tables, anti-patterns, unit/date rules, required filters)
   - relevant domain, business-rule, and SQL-rule context
   - relevant examples and rules
   - relevant tables, columns, and candidate joins

2. Write the SQL yourself and call:
   `execute_task(task_id=..., sql=..., confirmed=false)`

Use the `execution` payload returned by `execute_task(...)` directly.

If the first SQL attempt fails or uses the wrong table/filter, call
`prepare_task(question=..., connection=..., context=...)` again with refinement
context such as previous SQL, validation errors, tables to avoid, or filters
that must be applied. Refinement calls may return expanded raw context and fuller
schema detail when the backend detects ambiguity or a prior failed attempt.

Do not look for shell, exec, or code tools in this mode.
"""

INSTRUCTIONS_SHELL_MODE = """
Database query server - SHELL-FIRST MODE

## YOU HAVE ONE PRIMARY TOOL: shell

Use `shell` for ALL query preparation. It gives you access to a knowledge vault
containing everything you need: examples, schema, rules, learnings.

## IMMEDIATE FIRST STEP

```
shell(command="cat PROTOCOL.md")
```

This tells you exactly how to:
- Find existing query examples
- Understand the database schema
- Follow SQL rules for this database
- Save successful queries for reuse

## QUERY WORKFLOW

1. shell(command="cat PROTOCOL.md")           # Read the rules
2. shell(command="grep -ri 'keyword' examples/")  # Find similar queries
3. shell(command="cat schema/tables.yaml")    # Understand tables
4. Write SQL based on what you found
5. validate_sql(sql="...")                    # Validate before running
6. run_sql(query_id="...")                    # Execute
7. Save successful queries back to examples/

## OTHER TOOLS

- validate_sql / run_sql / get_result - Query execution (required for running SQL)
- export_results - Export data to CSV/JSON
- get_knowledge_gaps - View unmapped business terms from previous sessions
- dismiss_knowledge_gap - Dismiss a gap as false positive
- query_add_rule / query_list_rules - Manage business rules (synonyms, filters)
- metrics_list / metrics_discover / metrics_approve / metrics_add / metrics_remove
- query_approve / query_feedback - Save examples and feedback
- mcp_setup_* / mcp_domain_* - Admin setup (not for regular queries)

## SQL-LIKE APIs (Dune, etc.)

For API connectors with `supports_sql: true`:
- Use `api_execute_sql(sql="SELECT ...")` to run SQL queries
- Do NOT use api_query for SQL execution - that's for REST endpoints only
- The SQL is sent to the API, polled for completion, and results returned automatically

## IMPORTANT: Business Rules and Knowledge Gaps

Before generating SQL, always check business rules:
```
shell(command="cat instructions/business_rules.yaml")
```

Call `get_knowledge_gaps()` to see terms previous sessions couldn't resolve.
If you can clarify any, use `query_add_rule` to add the mapping.

DO NOT look for other schema discovery tools. Use `shell` to explore the vault.
"""

INSTRUCTIONS_EXEC_ONLY = """
Database query server - EXEC-ONLY MODE

## YOU HAVE EXACTLY ONE TOOL: exec

Use `exec(connection="...", command="...")` for all work. The command runs inside
a sandboxed container whose working directory is the selected connection vault.

## IMMEDIATE FIRST STEP

```
exec(connection="...", command="cat PROTOCOL.md")
```

The mounted workspace contains the same structure as normal db-mcp connections:
- PROTOCOL.md
- schema/
- domain/
- instructions/
- examples/
- learnings/
- metrics/
- connector.yaml

Python and SQLAlchemy are installed in the container. Use local files, Python,
and shell commands to inspect the vault and query the selected data source.
"""

INSTRUCTIONS_CODE = """
Database query server - CODE MODE

## YOU HAVE EXACTLY ONE TOOL: code

Use `code(connection="...", code="...")` for all work. The code runs as Python
inside the selected connection workspace.

## IMMEDIATE FIRST STEP

```
code(connection="...", code="print(dbmcp.read_protocol())")
```

## BUILT-IN PYTHON HELPER

Your code gets a helper object named `dbmcp`.

Use these helpers first:
- `dbmcp.read_protocol()`
- `dbmcp.connector()`
- `dbmcp.schema_descriptions()`
- `dbmcp.domain_model()`
- `dbmcp.sql_rules()`
- `dbmcp.query(sql)`
- `dbmcp.scalar(sql)`
- `dbmcp.execute(sql)`

If a statement may write, re-run the tool with `confirmed=True`.
Do not rely on shell semantics in this mode.
"""


# =============================================================================
# Server Creation
# =============================================================================


def _strip_validate_sql_from_instructions(instructions: str) -> str:
    """Remove validate_sql references for connectors that don't support it."""
    replacements = {
        (
            '5. validate_sql(sql="...")                    '
            "# Validate before running\n"
            '6. run_sql(query_id="...")                    '
            "# Execute"
        ): ('5. run_sql(sql="...")                         # Execute directly'),
        ("- validate_sql / run_sql / get_result - Query execution (required for running SQL)"): (
            "- run_sql / get_result - Query execution (run_sql accepts sql= directly)"
        ),
        "- Query: get_data, run_sql, validate_sql, get_result, export_results": (
            "- Query: get_data, run_sql, get_result, export_results"
        ),
    }
    for old, new in replacements.items():
        instructions = instructions.replace(old, new)
    return instructions


def _build_connection_instructions(all_connections: dict) -> str:
    """Build instructions section listing all available connections."""
    if not all_connections:
        return ""

    lines = ["\n## Available Connections\n"]
    for name, info in all_connections.items():
        parts = [f"- **{name}**"]
        details = []
        if info.type:
            details.append(info.type)
        if info.dialect:
            details.append(info.dialect)
        if details:
            parts.append(f"({', '.join(details)})")
        if info.is_default:
            parts.append("← default")
        if info.description:
            parts.append(f"— {info.description}")
        lines.append(" ".join(parts))

    lines.append(
        '\n**Usage:** Add `connection="name"` to any tool call to target a specific connection.'
    )
    lines.append(
        "If omitted and only one connection of the required type exists, it is used automatically."
    )
    return "\n".join(lines)


def _resolve_tool_profile(settings: object, is_shell_mode: bool) -> str:
    """Resolve effective tool profile with safe fallback."""
    profile = getattr(settings, "tool_profile", "auto")
    if profile not in {"auto", "full", "query"}:
        profile = "auto"
    if profile == "auto":
        return "query" if is_shell_mode else "full"
    return profile


def _create_server() -> FastMCP:
    """Create and configure the MCP server based on tool_mode setting."""
    import yaml as _yaml

    from db_mcp.connectors import normalize_capabilities

    settings = get_settings()
    is_shell_mode = settings.tool_mode == "shell"
    is_exec_mode = settings.tool_mode == "exec-only"
    is_code_mode = settings.tool_mode == "code"
    is_daemon_mode = settings.tool_mode == "daemon"
    tool_profile = _resolve_tool_profile(settings, is_shell_mode)
    is_full_profile = tool_profile == "full"

    # =========================================================================
    # Registry-based aggregate capability detection
    # =========================================================================
    from db_mcp.registry import ConnectionRegistry

    registry = ConnectionRegistry.get_instance()
    all_connections = registry.discover()

    if all_connections:
        # Scan all connections for aggregate capabilities
        has_sql = False
        has_api = False
        has_validate = False
        has_async_jobs = False
        has_api_sql = False  # API connectors that support SQL (for api_execute_sql)

        for name, info in all_connections.items():
            yaml_path = info.path / "connector.yaml"
            try:
                with open(yaml_path) as _f:
                    _yaml_data = _yaml.safe_load(_f) or {}
            except Exception:
                _yaml_data = {}

            conn_type = _yaml_data.get("type", "sql")
            profile = _yaml_data.get("profile")
            raw_caps = dict(_yaml_data.get("capabilities", {}) or {})
            merged = normalize_capabilities(conn_type, raw_caps, profile=profile)

            if conn_type == "api":
                has_api = True
                if merged.get("supports_sql"):
                    has_api_sql = True
            if merged.get("supports_sql"):
                if conn_type != "api":
                    has_sql = True
            if merged.get("supports_validate_sql"):
                has_validate = True
            if merged.get("supports_async_jobs"):
                has_async_jobs = True

        # Legacy variables for compat
        is_api = has_api and not has_sql  # pure API mode (no SQL connections)
        supports_sql = has_sql
        supports_validate = has_validate
        supports_async_jobs = has_async_jobs
    else:
        # Legacy single-connection mode: read directly from connector.yaml
        try:
            from db_mcp.connectors import ConnectorConfig

            conn_path = Path(settings.get_effective_connection_path())
            yaml_path = conn_path / "connector.yaml"
            _connector_config = ConnectorConfig.from_yaml(yaml_path)
            connector_type = getattr(_connector_config, "type", "sql")
            profile = getattr(_connector_config, "profile", "")
            raw_caps = getattr(_connector_config, "capabilities", {}) or {}
        except Exception:
            connector_type = "sql"
            profile = ""
            raw_caps = {}

        connector_caps = normalize_capabilities(connector_type, raw_caps, profile=profile)

        is_api = connector_type == "api"
        has_api = is_api
        has_sql = connector_caps.get("supports_sql", False)
        has_validate = connector_caps.get("supports_validate_sql", False)
        has_async_jobs = connector_caps.get("supports_async_jobs", False)
        has_api_sql = is_api and has_sql
        supports_sql = has_sql
        supports_validate = has_validate
        supports_async_jobs = has_async_jobs

    if is_exec_mode:
        instructions = INSTRUCTIONS_EXEC_ONLY
    elif is_code_mode:
        instructions = INSTRUCTIONS_CODE
    elif is_daemon_mode:
        instructions = INSTRUCTIONS_DAEMON
    else:
        instructions = INSTRUCTIONS_SHELL_MODE if is_shell_mode else INSTRUCTIONS_DETAILED

    # Adapt instructions when validate_sql is not supported
    if not is_exec_mode and not is_code_mode and not supports_validate:
        instructions = _strip_validate_sql_from_instructions(instructions)

    # Append multi-connection section when multiple connections are configured
    if len(all_connections) > 1:
        instructions = instructions + _build_connection_instructions(all_connections)

    server = FastMCP(
        name="db-mcp",
        auth=_get_auth_provider(),
        lifespan=server_lifespan,
        instructions=instructions,
    )

    # =========================================================================
    # MCP Resources - always exposed
    # =========================================================================

    @server.resource("db-mcp://ground-rules")
    def get_ground_rules() -> str:
        """Ground rules for working with this database - READ FIRST.

        Contains critical instructions for:
        - Database hierarchy (catalog.schema.table)
        - How to search and save query examples
        - User transparency requirements
        - SQL generation workflow
        """
        connection_path = get_connection_path()
        protocol_path = connection_path / "PROTOCOL.md"
        if protocol_path.exists():
            return protocol_path.read_text()
        return "PROTOCOL.md not found. Run connection initialization."

    @server.resource("db-mcp://sql-rules")
    def get_sql_rules() -> str:
        """SQL generation rules specific to this database.

        Contains:
        - Database hierarchy rules (2-level vs 3-level)
        - Dialect-specific syntax guidance
        - Common mistakes to avoid
        - Query patterns and examples
        """
        connection_path = get_connection_path()
        rules_path = connection_path / "instructions" / "sql_rules.md"
        if rules_path.exists():
            return rules_path.read_text()
        return "sql_rules.md not found."

    # NOTE: Schema and domain model are NOT exposed as resources because:
    # 1. They can be large and change during onboarding
    # 2. MCP has no content-change notification (only list-change)
    # 3. Client caching could serve stale data
    # Use shell tool instead: cat schema/descriptions.yaml, cat domain/model.md

    @server.resource("db-mcp://insights/pending")
    def get_pending_insights() -> str:
        """Pending insights from trace analysis.

        Contains actionable observations about query patterns,
        errors, knowledge gaps, and learning opportunities.
        Check this resource periodically to stay proactive.

        Returns empty when nothing needs attention.

        Also includes timing information to help with conversational suggestions.
        """
        import time

        from db_mcp.insights.detector import load_insights

        connection_path = get_connection_path()
        store = load_insights(connection_path)
        pending = store.pending()

        # Calculate timing information for conversational suggestions
        current_time = time.time()
        if store.last_processed_at > 0:
            hours_since = (current_time - store.last_processed_at) / 3600
        else:
            hours_since = float("inf")

        # Determine if conversational suggestion is warranted
        should_suggest = len(pending) > 0 and hours_since >= 24.0

        if not pending:
            if store.last_processed_at > 0:
                note = f" Last processed {hours_since:.1f}h ago."
            else:
                note = " Never processed."
            return f"No pending insights. Everything looks good.{note}"

        if store.last_processed_at > 0:
            processed_line = f"**Last processed:** {hours_since:.1f} hours ago\n"
        else:
            processed_line = "**Last processed:** Never\n"
        suggest_str = "YES" if should_suggest else "NO"

        lines = [
            f"# Pending Insights ({len(pending)})\n",
            processed_line,
            f"**Conversational suggestion warranted:** {suggest_str}\n\n",
        ]
        for i, insight in enumerate(pending, 1):
            icon = {
                "action": "!",
                "warning": "!",
                "info": "i",
            }.get(insight.severity, "-")
            lines.append(
                f"## [{icon}] {insight.title}\n"
                f"**Category:** {insight.category} | "
                f"**Severity:** {insight.severity}\n\n"
                f"{insight.summary}\n"
            )
            if insight.details:
                for k, v in insight.details.items():
                    if isinstance(v, list) and v:
                        lines.append(f"- **{k}:** {v}")
                    elif v is not None:
                        lines.append(f"- **{k}:** {v}")
            lines.append(f"\n*Dismiss: `dismiss_insight('{insight.id}')`*\n")

        return "\n".join(lines)

    @server.resource("db-mcp://connections")
    def get_connections() -> str:
        """List all available database connections.

        Returns connection names, types, dialects, and descriptions.
        Use this to discover which connections are available for
        multi-connection queries.
        """
        import json

        from db_mcp.registry import ConnectionRegistry

        registry = ConnectionRegistry.get_instance()
        connections = registry.list_connections()
        return json.dumps(connections, indent=2)

    @server.resource("db-mcp://schema/{connection}")
    def get_connection_schema(connection: str) -> str:
        """Get the cached schema for a specific connection.

        Returns the schema.md content for the named connection.
        Use this to understand table structures before writing
        cross-connection queries.
        """
        from db_mcp.registry import ConnectionRegistry

        registry = ConnectionRegistry.get_instance()
        conn_path = registry.get_connection_path(connection)
        schema_path = conn_path / "schema.md"
        if schema_path.exists():
            return schema_path.read_text()
        # Fall back to descriptions.yaml
        desc_path = conn_path / "schema" / "descriptions.yaml"
        if desc_path.exists():
            return desc_path.read_text()
        return f"No schema found for connection '{connection}'."

    # Health check endpoint for k8s probes
    @server.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        """Health check endpoint for load balancers and k8s probes."""
        return JSONResponse(
            {
                "status": "healthy",
                "service": "db-mcp",
                "connection": settings.connection_name,
                "tool_mode": settings.tool_mode,
                "tool_profile": tool_profile,
            }
        )

    # =========================================================================
    # MCP Prompts - suggested actions for the agent
    # =========================================================================

    @server.prompt("review-insights")
    def review_insights_prompt() -> str:
        """Review pending insights and take action.

        Checks for new trace insights (query patterns, errors,
        knowledge gaps) and guides you through resolving them.
        """
        from db_mcp.insights.detector import load_insights

        connection_path = get_connection_path()
        store = load_insights(connection_path)
        pending = store.pending()

        if not pending:
            return (
                "Check the db-mcp://insights/pending resource. "
                "If there are no pending insights, let the user know "
                "everything looks good."
            )

        return (
            "Read the db-mcp://insights/pending resource. "
            f"There are {len(pending)} pending insight(s). "
            "For each insight:\n"
            "1. Explain what was detected and why it matters\n"
            "2. Suggest a specific action (save example, add rule, "
            "investigate error)\n"
            "3. If the user agrees, execute the action using "
            "the appropriate MCP tool\n"
            "4. Dismiss the insight when resolved"
        )

    if is_exec_mode:
        server.tool(name="exec")(_exec)
        return server
    if is_code_mode:
        server.tool(name="code")(_code)
        return server
    if is_daemon_mode:
        server.tool(name="prepare_task")(_prepare_task)
        server.tool(name="execute_task")(_execute_task)
        return server

    # =========================================================================
    # Core tools - always available
    # =========================================================================

    def _resolve_tool_connection_path(connection: str) -> Path:
        """Resolve connection arg to a concrete connection path."""
        from db_mcp.tools.utils import require_connection, resolve_connection

        connection = require_connection(connection, tool_name="insights")
        _, _, conn_path = resolve_connection(connection)
        return conn_path

    async def _dismiss_insight(insight_id: str, connection: str) -> dict:
        """Dismiss a pending insight after reviewing or resolving it.

        Args:
            insight_id: The ID of the insight to dismiss
                (shown in insights/pending resource).
            connection: Connection name for multi-connection support.
        """
        from db_mcp.insights.detector import (
            load_insights,
            save_insights,
        )

        connection_path = _resolve_tool_connection_path(connection)
        store = load_insights(connection_path)
        if store.dismiss(insight_id):
            save_insights(connection_path, store)
            remaining = len(store.pending())
            return {
                "status": "dismissed",
                "insight_id": insight_id,
                "remaining": remaining,
            }
        return {
            "status": "not_found",
            "insight_id": insight_id,
        }

    if is_full_profile:
        server.tool(name="dismiss_insight")(_dismiss_insight)

    async def _mark_insights_processed(connection: str) -> dict:
        """Mark insights as processed to update the timestamp.

        Call this when you've reviewed insights with the user, either through
        the review-insights prompt or after a conversational suggestion.
        This updates the last processed timestamp to prevent repeated suggestions.
        """
        from db_mcp.insights.detector import mark_insights_processed

        connection_path = _resolve_tool_connection_path(connection)
        mark_insights_processed(connection_path)

        return {"status": "processed", "message": "Insights processing timestamp updated"}

    if is_full_profile:
        server.tool(name="mark_insights_processed")(_mark_insights_processed)

    async def _mcp_list_improvements(connection: str) -> dict:
        """List pending improvements (backward-compatible alias for insights)."""
        from db_mcp.insights.detector import load_insights

        store = load_insights(_resolve_tool_connection_path(connection))
        improvements = [
            {
                "id": insight.id,
                "category": insight.category,
                "severity": insight.severity,
                "title": insight.title,
                "summary": insight.summary,
                "details": insight.details,
                "detected_at": insight.detected_at,
            }
            for insight in store.pending()
        ]
        return {
            "improvements": improvements,
            "count": len(improvements),
        }

    if is_full_profile:
        server.tool(name="mcp_list_improvements")(_mcp_list_improvements)

    async def _mcp_suggest_improvement(connection: str) -> dict:
        """Suggest the highest-priority pending improvement.

        This tool is a compatibility alias over the insights subsystem.
        """
        from db_mcp.insights.detector import load_insights

        severity_rank = {"action": 3, "warning": 2, "info": 1}
        pending = load_insights(_resolve_tool_connection_path(connection)).pending()
        if not pending:
            return {"status": "none", "improvement": None}

        best = sorted(
            pending,
            key=lambda i: (severity_rank.get(i.severity, 0), i.detected_at),
            reverse=True,
        )[0]
        return {
            "status": "ok",
            "improvement": {
                "id": best.id,
                "category": best.category,
                "severity": best.severity,
                "title": best.title,
                "summary": best.summary,
                "details": best.details,
                "detected_at": best.detected_at,
            },
        }

    if is_full_profile:
        server.tool(name="mcp_suggest_improvement")(_mcp_suggest_improvement)

    async def _mcp_approve_improvement(improvement_id: str, connection: str) -> dict:
        """Approve (resolve) an improvement by ID.

        For compatibility this maps to dismissing a pending insight.
        """
        from db_mcp.insights.detector import load_insights, save_insights

        connection_path = _resolve_tool_connection_path(connection)
        store = load_insights(connection_path)
        if not store.dismiss(improvement_id):
            return {"status": "not_found", "improvement_id": improvement_id}

        save_insights(connection_path, store)
        return {
            "status": "approved",
            "improvement_id": improvement_id,
            "remaining": len(store.pending()),
        }

    if is_full_profile:
        server.tool(name="mcp_approve_improvement")(_mcp_approve_improvement)

    def _connection_is_configured(connection: str | None = None) -> bool:
        """Check whether the selected connection has required source config."""
        try:
            connector = registry.get_connector(connection)
        except Exception:
            return False

        # SQL connector path
        config = getattr(connector, "config", None)
        database_url = getattr(config, "database_url", None)
        if isinstance(database_url, str):
            return bool(database_url.strip())

        # Metabase/file connector path
        base_url = getattr(config, "base_url", None)
        if isinstance(base_url, str):
            return bool(base_url.strip())
        directory = getattr(config, "directory", None)
        if isinstance(directory, str) and directory.strip():
            return True
        sources = getattr(config, "sources", None)
        if isinstance(sources, list):
            return len(sources) > 0

        # API connector path
        api_config = getattr(connector, "api_config", None)
        api_base_url = getattr(api_config, "base_url", None)
        if isinstance(api_base_url, str):
            return bool(api_base_url.strip())

        # If the connector resolves and we can't infer fields, treat as configured.
        return True

    async def _ping() -> dict:
        """Health check - verify server is running."""
        resolved_connection = settings.connection_name or registry.get_default_name()
        return {
            "status": "ok",
            "connection": resolved_connection,
            "tool_mode": settings.tool_mode,
            "tool_profile": tool_profile,
            "database_configured": _connection_is_configured(resolved_connection),
        }

    async def _get_config(connection: str | None = None) -> dict:
        """Get current server configuration (non-sensitive)."""
        resolved_connection = connection or settings.connection_name or registry.get_default_name()
        connection_path = registry.get_connection_path(resolved_connection)
        return {
            "connection": resolved_connection,
            "connection_path": str(connection_path),
            "tool_mode": settings.tool_mode,
            "tool_profile": tool_profile,
            "database_configured": _connection_is_configured(resolved_connection),
        }

    server.tool(name="ping")(_ping)
    server.tool(name="get_config")(_get_config)
    server.tool(name="list_connections")(_list_connections)

    async def _search_tools(
        query: str = "",
        limit: int = 12,
        category: str | None = None,
        include_parameters: bool = False,
    ) -> dict:
        """Search active MCP tools and return the best matches.

        Useful for code-execution workflows where the agent should discover a
        narrow tool set first, then generate wrapper code only for matching tools.
        """
        catalog = build_tool_catalog(server)
        matches = search_tool_catalog(catalog=catalog, query=query, limit=limit, category=category)
        result_tools: list[dict] = []
        for item in matches:
            tool_entry = {
                "name": item["name"],
                "category": item["category"],
                "description": item["description"],
                "required": item["required"],
            }
            if include_parameters:
                tool_entry["properties"] = item["properties"]
            result_tools.append(tool_entry)

        return {
            "query": query,
            "category": category,
            "count": len(result_tools),
            "tools": result_tools,
        }

    async def _export_tool_sdk(
        language: str = "python",
        query: str = "",
        limit: int = 40,
        category: str | None = None,
    ) -> dict:
        """Export a small SDK wrapper for active tools (Python MVP).

        Use `query` and/or `category` to generate wrappers for a focused subset.
        """
        normalized = language.strip().lower()
        if normalized != "python":
            return {
                "status": "error",
                "error": "Unsupported language. Currently supported: python",
            }

        catalog = build_tool_catalog(server)
        selected = search_tool_catalog(
            catalog=catalog,
            query=query,
            limit=limit,
            category=category,
        )
        code = render_python_sdk(selected)
        return {
            "status": "ok",
            "language": "python",
            "query": query,
            "category": category,
            "tool_count": len(selected),
            "tool_names": [item["name"] for item in selected],
            "code": code,
        }

    server.tool(name="search_tools")(_search_tools)
    server.tool(name="export_tool_sdk")(_export_tool_sdk)

    # =========================================================================
    # Shell tool - with mode-specific description
    # =========================================================================

    shell_description = (
        SHELL_DESCRIPTION_SHELL_MODE if is_shell_mode else SHELL_DESCRIPTION_DETAILED
    )
    server.tool(name="shell", description=shell_description)(_shell)
    server.tool(name="protocol")(_protocol)

    # =========================================================================
    # SQL execution tools - SQL, File, and SQL-like API connectors
    # =========================================================================

    if supports_sql:
        if supports_validate:
            server.tool(name="validate_sql")(_validate_sql)
        server.tool(name="run_sql")(_run_sql)
        if supports_async_jobs:
            server.tool(name="get_result")(_get_result)
        server.tool(name="export_results")(_export_results)

    # =========================================================================
    # API connector tools - registered when ANY connection is API type
    # =========================================================================

    if has_api:
        server.tool(name="api_query")(_api_query)
        server.tool(name="api_describe_endpoint")(_api_describe_endpoint)
        if has_api_sql:
            server.tool(name="api_execute_sql")(_api_execute_sql)
        if is_full_profile:
            server.tool(name="api_discover")(_api_discover)
            server.tool(name="api_mutate")(_api_mutate)

    # =========================================================================
    # Admin/Setup tools - always available (not for casual query use)
    # =========================================================================

    if is_full_profile:
        # MCP setup tools (schema discovery wizard)
        server.tool(name="mcp_setup_status")(_onboarding_status)
        server.tool(name="mcp_setup_start")(_onboarding_start)
        server.tool(name="mcp_setup_add_ignore_pattern")(_onboarding_add_ignore_pattern)
        server.tool(name="mcp_setup_remove_ignore_pattern")(_onboarding_remove_ignore_pattern)
        server.tool(name="mcp_setup_import_ignore_patterns")(_onboarding_import_ignore_patterns)
        server.tool(name="mcp_setup_discover")(_onboarding_discover)
        server.tool(name="mcp_setup_discover_status")(_onboarding_discover_status)
        server.tool(name="mcp_setup_reset")(_onboarding_reset)
        server.tool(name="mcp_setup_next")(_onboarding_next)
        server.tool(name="mcp_setup_approve")(_onboarding_approve)
        server.tool(name="mcp_setup_skip")(_onboarding_skip)
        server.tool(name="mcp_setup_bulk_approve")(_onboarding_bulk_approve)
        server.tool(name="mcp_setup_import_descriptions")(_onboarding_import_descriptions)

        # MCP domain tools (domain model generation)
        server.tool(name="mcp_domain_status")(_domain_status)
        server.tool(name="mcp_domain_generate")(_domain_generate)
        server.tool(name="mcp_domain_approve")(_domain_approve)
        server.tool(name="mcp_domain_skip")(_domain_skip)

        # Import tools (bulk import from legacy format)
        server.tool(name="import_instructions")(_import_instructions)
        server.tool(name="import_examples")(_import_examples)

    # =========================================================================
    # Detailed mode ONLY - schema discovery and query helper tools
    # =========================================================================

    if is_full_profile and not is_shell_mode and (has_sql or has_api):
        # Database introspection tools
        server.tool(name="test_connection")(_test_connection)
        server.tool(name="detect_dialect")(_detect_dialect)
        server.tool(name="list_catalogs")(_list_catalogs)
        server.tool(name="list_schemas")(_list_schemas)
        server.tool(name="list_tables")(_list_tables)
        server.tool(name="describe_table")(_describe_table)
        server.tool(name="sample_table")(_sample_table)

        # Dialect tools
        server.tool(name="get_dialect_rules")(_get_dialect_rules)
        server.tool(name="get_connection_dialect")(_get_connection_dialect)

        # Query training tools
        server.tool(name="query_status")(_query_status)
        server.tool(name="query_generate")(_query_generate)
        server.tool(name="query_approve")(_query_approve)
        server.tool(name="query_feedback")(_query_feedback)
        server.tool(name="query_add_rule")(_query_add_rule)
        server.tool(name="query_list_examples")(_query_list_examples)
        server.tool(name="query_list_rules")(_query_list_rules)

        # Knowledge gaps tools
        server.tool(name="get_knowledge_gaps")(_get_knowledge_gaps)
        server.tool(name="dismiss_knowledge_gap")(_dismiss_knowledge_gap)

        # Metrics & dimensions tools
        server.tool(name="metrics_discover")(_metrics_discover)
        server.tool(name="metrics_list")(_metrics_list)
        server.tool(name="metrics_approve")(_metrics_approve)
        server.tool(name="metrics_add")(_metrics_add)
        server.tool(name="metrics_remove")(_metrics_remove)

        # Advanced generation tools
        server.tool(name="get_data")(_get_data)
        server.tool(name="test_elicitation")(_test_elicitation)
        server.tool(name="test_sampling")(_test_sampling)

    return server


# Create the server instance
mcp = _create_server()


def _configure_logging():
    """Configure logging before anything else."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _configure_observability():
    """Configure observability (Logfire, local console, and/or JSONL traces)."""
    settings = get_settings()
    logger = logging.getLogger(__name__)

    # Always try to set up HTTP tracing to console (silent if console not running)
    try:
        from db_mcp.console.http_exporter import setup_http_tracing

        console_port = int(os.environ.get("DB_MCP_CONSOLE_PORT", "8080"))
        setup_http_tracing(console_port=console_port)
        logger.debug(f"HTTP tracing configured (port {console_port})")
    except Exception as e:
        logger.debug(f"HTTP tracing not available: {e}")

    # Set up JSONL trace exporter if enabled
    try:
        from db_mcp.traces import setup_trace_exporter

        connection_path = get_connection_path()
        exporter = setup_trace_exporter(connection_path)
        if exporter:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor

            # Get or create tracer provider
            provider = trace.get_tracer_provider()
            if not isinstance(provider, TracerProvider):
                provider = TracerProvider()
                trace.set_tracer_provider(provider)

            # Add JSONL exporter
            provider.add_span_processor(SimpleSpanProcessor(exporter))
            logger.info(f"JSONL trace exporter enabled: {exporter.traces_dir}")
    except Exception as e:
        logger.debug(f"JSONL trace exporter not available: {e}")

    # Also configure Logfire if token is set
    if settings.logfire_token:
        import logfire

        logfire.configure(
            token=settings.logfire_token,
            service_name="db-mcp",
            environment=os.environ.get("ENVIRONMENT", "development"),
            # Disable scrubbing to preserve SQL queries and user input in logs
            # Default patterns would scrub 'password', 'secret', 'auth', 'session', etc.
            scrubbing=False,
        )
        # Instrument MCP server (all tool calls)
        logfire.instrument_mcp()
        # Instrument all PydanticAI agents automatically
        Agent.instrument_all()
        logger.info("Logfire observability enabled (scrubbing disabled)")


def main():
    """Run the MCP server."""
    _configure_logging()
    _configure_observability()

    settings = get_settings()
    logger = logging.getLogger(__name__)

    # Migrate from legacy ~/.dbmeta namespace if present
    migrate_namespace()

    # Ensure connection directory structure exists
    ensure_connection_structure()

    # Migrate legacy provider data if present (v1 -> v2 structure)
    migrate_to_connection_structure()

    logger.info(
        f"Starting db-mcp in {settings.tool_mode} mode (connection: {settings.connection_name})"
    )

    # Always instrument tools for tracing (sends to console if running)
    try:
        from db_mcp.console.instrument import instrument_server

        instrument_server(mcp)
        logger.debug("Tool instrumentation enabled")
    except Exception as e:
        logger.debug(f"Tool instrumentation not available: {e}")

    if settings.mcp_transport == "http":
        mcp.run(
            transport="http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            path=settings.mcp_path,
        )
    else:
        # Default: stdio for local/Claude Desktop
        mcp.run()


if __name__ == "__main__":
    main()
