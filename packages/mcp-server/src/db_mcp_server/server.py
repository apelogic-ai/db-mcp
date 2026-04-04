"""FastMCP server for db-mcp."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from db_mcp.config import get_settings
from db_mcp.exec_runtime import shutdown_exec_session_manager
from db_mcp.insider import start_insider_supervisor, stop_insider_supervisor
from db_mcp_data.execution.query_store import get_query_store
from db_mcp_knowledge.vault import ensure_connection_structure, migrate_to_connection_structure
from db_mcp_knowledge.vault.migrate import migrate_namespace
from fastmcp import FastMCP
from pydantic_ai import Agent
from starlette.requests import Request
from starlette.responses import JSONResponse

from db_mcp_server.instructions import (
    INSTRUCTIONS_CODE,
    INSTRUCTIONS_DAEMON,
    INSTRUCTIONS_DETAILED,
    INSTRUCTIONS_EXEC_ONLY,
    INSTRUCTIONS_SHELL_MODE,
    _build_connection_instructions,
    _strip_validate_sql_from_instructions,
)
from db_mcp_server.tool_catalog import build_tool_catalog, render_python_sdk, search_tool_catalog
from db_mcp_server.tool_registration import (
    register_api_tools,
    register_database_tools,
    register_metrics_tools,
    register_query_tools,
    register_shell_tools,
    register_vault_tools,
)
from db_mcp_server.tools.database import _list_connections


def get_connection_path() -> Path:
    """Get active connection path from settings."""
    return get_settings().get_effective_connection_path()


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
    task_store = get_query_store()
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
        from db_mcp.traces import get_user_id_from_config
        from db_mcp_knowledge.collab.manifest import get_member, load_manifest
        from db_mcp_knowledge.collab.sync import collaborator_pull

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
                from db_mcp_knowledge.collab.sync import collaborator_push

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


def _resolve_tool_profile(settings: object, is_shell_mode: bool) -> str:
    """Resolve effective tool profile with safe fallback."""
    profile = getattr(settings, "tool_profile", "auto")
    if profile not in {"auto", "full", "query"}:
        profile = "auto"
    if profile == "auto":
        return "query" if is_shell_mode else "full"
    return profile


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server based on tool_mode setting.

    Public factory — returns a FastMCP instance with all tools registered.
    Does not call ``mcp.run()``. Use ``server.http_app()`` to get an ASGI app
    for mounting into FastAPI, or call ``server.run()`` for standalone mode.
    """
    import yaml as _yaml
    from db_mcp_data.connectors import normalize_capabilities

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
            from db_mcp_data.connectors import ConnectorConfig

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

        from db_mcp_knowledge.insights.detector import load_insights

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
        from db_mcp_knowledge.insights.detector import load_insights

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
        from db_mcp.tools.exec import _exec

        server.tool(name="exec")(_exec)
        return server
    if is_code_mode:
        from db_mcp.tools.code import _code

        server.tool(name="code")(_code)
        return server
    if is_daemon_mode:
        from db_mcp.tools.daemon_tasks import _execute_task, _prepare_task

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
        from db_mcp_knowledge.insights.detector import (
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
        from db_mcp_knowledge.insights.detector import mark_insights_processed

        connection_path = _resolve_tool_connection_path(connection)
        mark_insights_processed(connection_path)

        return {"status": "processed", "message": "Insights processing timestamp updated"}

    if is_full_profile:
        server.tool(name="mark_insights_processed")(_mark_insights_processed)

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
    # Grouped tool registrations (delegated to tool_registration module)
    # =========================================================================

    register_shell_tools(server, is_shell_mode=is_shell_mode)
    register_query_tools(
        server,
        supports_sql=supports_sql,
        supports_validate=supports_validate,
        supports_async_jobs=supports_async_jobs,
    )
    register_api_tools(
        server, has_api=has_api, has_api_sql=has_api_sql, is_full_profile=is_full_profile
    )
    register_vault_tools(server, is_full_profile=is_full_profile)
    register_database_tools(
        server,
        is_full_profile=is_full_profile,
        is_shell_mode=is_shell_mode,
        has_sql=has_sql,
        has_api=has_api,
    )
    register_metrics_tools(
        server,
        is_full_profile=is_full_profile,
        is_shell_mode=is_shell_mode,
        has_sql=has_sql,
        has_api=has_api,
    )

    return server


# Create the server instance
mcp = create_mcp_server()


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
    ensure_connection_structure(settings.get_effective_connection_path())

    # Migrate legacy provider data if present (v1 -> v2 structure)
    migrate_to_connection_structure(
        connection_path=settings.get_effective_connection_path(),
        auto_migrate=settings.auto_migrate,
        vault_path=settings.vault_path,
        providers_dir=settings.providers_dir,
        provider_id=settings.get_effective_provider_id(),
    )

    logger.info(
        f"Starting db-mcp in {settings.tool_mode} mode (connection: {settings.connection_name})"
    )

    # Always instrument tools for tracing (sends to console if running)
    try:
        from db_mcp_server.console.instrument import instrument_server

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
