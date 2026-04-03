"""SQL generation MCP tools - get_data, run_sql, get_result.

These are the three main entry points per v2 architecture:
- get_data(intent) - Natural language -> Plan -> SQL -> Result
- run_sql(connection=..., sql=...) - Direct SQL with validation
- get_result(query_uuid, connection=...) - Fetch cached/stored query result

Uses PydanticAI with MCPSamplingModel for LLM calls through the MCP client,
and MCP Elicitation for user confirmations.

Gracefully degrades when sampling/elicitation aren't supported:
- No sampling: Returns context for client to generate SQL
- No elicitation: Auto-approves or returns confirmation_required status
"""

import asyncio
import csv
import hashlib
import io
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import (
    Any as Context,  # noqa: UP006 — Context was fastmcp.Context; moved to mcp-server in Phase 3
)

from db_mcp_data.connectors import get_connector, get_connector_capabilities
from db_mcp_data.connectors.sql import SQLConnector
from db_mcp_data.execution import (
    ExecutionErrorCode,
    ExecutionState,
    check_protocol_ack_gate,
    evaluate_sql_execution_policy,
)
from db_mcp_data.execution.engine import get_execution_engine
from db_mcp_data.execution.query_store import QueryStatus, get_query_store
from db_mcp_data.validation.explain import (
    CostTier,
    ExplainResult,
    analyze_sql_statement,
    explain_sql,
    get_write_policy,
    should_explain_statement,
    validate_read_only,
    validate_sql_permissions,
)
from db_mcp_knowledge.onboarding.schema_store import load_schema_descriptions
from db_mcp_knowledge.training.store import load_examples, load_instructions
from db_mcp_models import QueryPlan
from opentelemetry import trace
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.mcp_sampling import MCPSamplingModel
from sqlalchemy import text

import db_mcp.services.query as query_service
from db_mcp.services.context import (
    build_examples_context,
    build_rules_context,
    build_schema_context,
)
from db_mcp.tools.protocol import inject_protocol

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("db_mcp.query")

# Threshold for async execution (rows estimated to scan)
# Queries above this go async to avoid timeout
ASYNC_ROW_THRESHOLD = 50_000

# =============================================================================
# Elicitation Models
# =============================================================================


@dataclass
class PlanApproval:
    """User response for plan approval."""

    approved: bool
    notes: str = ""


@dataclass
class ExecutionConfirmation:
    """User response for query execution confirmation."""

    confirmed: bool


# =============================================================================
# PydanticAI Agents
# =============================================================================


# Agent for generating query plans
planner_agent = Agent(
    system_prompt="""You are a SQL query planner. Given a user's natural language intent
and database schema, create a structured query plan.

Your plan should identify:
1. Which tables are needed
2. How tables should be joined
3. What filters to apply
4. Any aggregations or groupings
5. Sort order and limits

Be specific about column names and table relationships.
Only use tables and columns that exist in the provided schema.
""",
    output_type=QueryPlan,
)


class SQLGenerationResult(BaseModel):
    """Result of SQL generation."""

    sql: str = Field(..., description="The generated SQL query")
    explanation: str = Field(..., description="Brief explanation of the query")


# Agent for generating SQL from a plan
sql_generator_agent = Agent(
    system_prompt="""You are a SQL generator. Given a query plan and database schema,
generate the correct SQL query.

Follow the plan exactly. Use proper SQL syntax for the specified dialect.
Include appropriate JOINs, WHERE clauses, GROUP BY, ORDER BY as specified.
Always include a LIMIT clause if not specified (default to 100).
""",
    output_type=SQLGenerationResult,
)


# =============================================================================
# Context Building
# =============================================================================


def _build_schema_context(
    provider_id: str,
    tables_hint: list[str] | None = None,
    connection_path: Path | None = None,
) -> str:
    """Backward-compatible wrapper for schema context building."""
    return build_schema_context(
        provider_id,
        tables_hint=tables_hint,
        connection_path=connection_path,
    )


def _build_examples_context(provider_id: str, limit: int = 5) -> str:
    """Backward-compatible wrapper for examples context building."""
    return build_examples_context(provider_id, limit=limit)


def _build_rules_context(provider_id: str) -> str:
    """Backward-compatible wrapper for business rules context building."""
    return build_rules_context(provider_id)


def _generate_query_uuid(sql: str) -> str:
    """Generate a deterministic UUID for a SQL query."""
    normalized = " ".join(sql.lower().split())
    hash_bytes = hashlib.sha256(normalized.encode()).digest()[:16]
    return str(uuid.UUID(bytes=hash_bytes))


def _execute_sql_on_engine(
    connector: SQLConnector,
    sql: str,
    *,
    is_write: bool,
    limit: int | None = None,
) -> tuple[list[str], list[dict[str, Any]], int | None]:
    """Execute SQL on SQLAlchemy engine with write-safe transaction handling."""
    engine = connector.get_engine()

    if is_write:
        with engine.begin() as conn:
            result = conn.execute(text(sql))
            rows_affected = result.rowcount if result.rowcount >= 0 else None
            if result.returns_rows:
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result]
            else:
                columns = []
                rows = []
        return columns, rows, rows_affected

    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = []
        for i, row in enumerate(result):
            if limit and i >= limit:
                break
            rows.append(dict(zip(columns, row)))

    return columns, rows, None


def _execute_query(
    sql: str,
    connection: str,
    limit: int | None = 1000,
    query_id: str | None = None,
) -> dict[str, Any]:
    """Execute a SQL query and return results.

    Uses OpenTelemetry spans for tracing.

    Args:
        sql: SQL query to execute.
        limit: Maximum rows to return.
        query_id: Optional query ID for tracing.
        connection: Connection name for multi-connection dispatch.
    """
    from db_mcp.tools.utils import require_connection, resolve_connection

    qid = query_id[:8] if query_id else "adhoc"
    sql_preview = sql[:200] + "..." if len(sql) > 200 else sql
    statement_type, is_write = analyze_sql_statement(sql)
    connection = require_connection(connection, tool_name="execute_query")

    with tracer.start_as_current_span(
        "execute_query",
        attributes={
            "query.id": qid,
            "query.limit": limit or 0,
            "sql.preview": sql_preview,
            "statement.type": statement_type,
            "statement.is_write": is_write,
        },
    ) as span:
        start_time = time.time()

        try:
            # Resolve connector
            with tracer.start_as_current_span("db_connect") as conn_span:
                connector, conn_name, conn_path = resolve_connection(connection)
                conn_span.set_attribute("db.provider", conn_name)

            # Execute query — branch on connector type
            if isinstance(connector, SQLConnector):
                with tracer.start_as_current_span("db_execute") as exec_span:
                    columns, rows, rows_affected = _execute_sql_on_engine(
                        connector, sql, is_write=is_write, limit=limit
                    )
                    exec_span.set_attribute("columns.count", len(columns))
                    exec_span.set_attribute("rows.fetched", len(rows))
                    if rows_affected is not None:
                        exec_span.set_attribute("rows.affected", rows_affected)
            else:
                # FileConnector / APIConnector: use execute_sql (DuckDB)
                rows_affected = None
                with tracer.start_as_current_span("db_execute") as exec_span:
                    all_rows = connector.execute_sql(sql)
                    if all_rows:
                        columns = list(all_rows[0].keys())
                    else:
                        columns = []
                    exec_span.set_attribute("columns.count", len(columns))

                    with tracer.start_as_current_span("fetch_rows") as fetch_span:
                        if limit and len(all_rows) > limit:
                            rows = all_rows[:limit]
                            fetch_span.set_attribute("limit_reached", True)
                        else:
                            rows = all_rows
                        fetch_span.set_attribute("rows.fetched", len(rows))

            total_duration_ms = (time.time() - start_time) * 1000
            span.set_attribute("rows.returned", len(rows))
            span.set_attribute("duration_ms", round(total_duration_ms, 2))

            logger.info(f"[WH_QUERY:{qid}] Complete: {len(rows)} rows, {total_duration_ms:.0f}ms")

            return {
                "data": rows,
                "columns": columns,
                "rows_returned": len(rows),
                "duration_ms": round(total_duration_ms, 2),
                "provider_id": conn_name,
                "statement_type": statement_type,
                "is_write": is_write,
                "rows_affected": rows_affected,
            }

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            logger.error(f"[WH_QUERY:{qid}] FAILED after {elapsed:.0f}ms: {e}")
            raise


async def _execute_query_background(
    query_id: str,
    sql: str,
    connection: str,
    execution_id: str | None = None,
) -> None:
    """Execute query in background and update query store.

    This runs in an asyncio task, allowing the MCP tool to return immediately
    while the query executes.

    Args:
        query_id: Query identifier in the store.
        sql: SQL to execute.
        connection: Connection name for multi-connection dispatch.
        execution_id: Optional execution lifecycle ID in persistent execution store.
    """
    from db_mcp.tools.utils import _resolve_connection_path

    store = get_query_store()
    execution_engine = get_execution_engine(Path(_resolve_connection_path(connection)))
    started = time.time()

    try:
        await store.update_status(query_id, QueryStatus.RUNNING)
        if execution_id:
            execution_engine.mark_running(execution_id)
        logger.info(f"Query {query_id}: Starting background execution")

        # Run the blocking query in a thread pool
        loop = asyncio.get_event_loop()
        from functools import partial

        result = await loop.run_in_executor(
            None,
            partial(
                _execute_query,
                sql,
                connection,
                limit=1000,
                query_id=query_id,
            ),
        )

        await store.update_status(
            query_id,
            QueryStatus.COMPLETE,
            result=result,
            rows_returned=result["rows_returned"],
        )
        if execution_id:
            execution_engine.mark_succeeded(
                execution_id,
                data=result.get("data", []),
                columns=result.get("columns", []),
                rows_returned=result.get("rows_returned", 0),
                rows_affected=result.get("rows_affected"),
                duration_ms=(time.time() - started) * 1000,
                metadata={
                    "provider_id": result.get("provider_id"),
                    "statement_type": result.get("statement_type"),
                    "is_write": result.get("is_write"),
                    "query_id": query_id,
                },
            )
        logger.info(f"Query {query_id}: Complete, {result['rows_returned']} rows")

    except Exception as e:
        logger.exception(f"Query {query_id}: Failed with error: {e}")
        await store.update_status(
            query_id,
            QueryStatus.ERROR,
            error=str(e),
        )
        if execution_id:
            execution_engine.mark_failed(
                execution_id,
                message=str(e),
                duration_ms=(time.time() - started) * 1000,
                metadata={"query_id": query_id},
            )


def _api_async_state(status_payload: dict[str, Any]) -> ExecutionState:
    """Map API-specific status payload to unified execution state."""
    state = str(status_payload.get("state", "")).lower()
    is_finished = bool(status_payload.get("is_execution_finished", False))

    if "cancel" in state:
        return ExecutionState.CANCELLED
    if "timeout" in state:
        return ExecutionState.TIMED_OUT
    if "failed" in state or "error" in state:
        return ExecutionState.FAILED
    if is_finished or "complete" in state or "success" in state or "finished" in state:
        return ExecutionState.SUCCEEDED
    if "submit" in state:
        return ExecutionState.SUBMITTED
    return ExecutionState.RUNNING


def _poll_api_async_execution(
    *,
    connection: str,
    execution_id: str,
    metadata: dict[str, Any],
    started_at: datetime | None,
) -> dict[str, Any]:
    """Poll async SQL-like API execution and update unified execution store."""
    from db_mcp.tools.utils import _resolve_connection_path

    external_id = metadata.get("external_execution_id")
    if not external_id:
        return {"status": "running", "message": "Execution submitted to API."}

    connection_path = Path(_resolve_connection_path(connection))
    execution_engine = get_execution_engine(connection_path)
    connector = get_connector(connection_path=str(connection_path))

    if not hasattr(connector, "get_execution_status") or not hasattr(
        connector, "get_execution_results"
    ):
        return {
            "status": "error",
            "error_code": ExecutionErrorCode.TOOLING.value,
            "error": "Connector does not expose async SQL polling methods.",
        }

    try:
        status_payload = connector.get_execution_status(str(external_id))
    except Exception as exc:
        return {
            "status": "running",
            "message": f"Polling status failed transiently: {exc}",
        }

    state = _api_async_state(status_payload if isinstance(status_payload, dict) else {})
    status_metadata = {
        "sql_mode": metadata.get("sql_mode") or "api_async",
        "external_execution_id": str(external_id),
        "external_status": status_payload,
    }

    if state in {ExecutionState.SUBMITTED, ExecutionState.RUNNING}:
        execution_engine.update_metadata(execution_id, status_metadata, merge=True)
        return {
            "status": "running",
            "state": state.value,
            "message": "Execution is still in progress.",
        }

    if state == ExecutionState.SUCCEEDED:
        try:
            rows = connector.get_execution_results(str(external_id))
        except Exception as exc:
            return {
                "status": "running",
                "state": ExecutionState.RUNNING.value,
                "message": f"Execution finished but result fetch is retrying: {exc}",
            }

        columns = list(rows[0].keys()) if rows else []
        duration_ms = None
        if started_at is not None:
            duration_ms = (datetime.now(tz=started_at.tzinfo) - started_at).total_seconds() * 1000

        execution_engine.mark_succeeded(
            execution_id,
            data=rows,
            columns=columns,
            rows_returned=len(rows),
            rows_affected=None,
            duration_ms=duration_ms,
            metadata=status_metadata,
        )
        return {"status": "complete"}

    error_msg = "Execution failed"
    if isinstance(status_payload, dict):
        error_msg = str(status_payload.get("error") or status_payload.get("message") or error_msg)

    code = ExecutionErrorCode.ENGINE
    if state == ExecutionState.CANCELLED:
        code = ExecutionErrorCode.POLICY
    elif state == ExecutionState.TIMED_OUT:
        code = ExecutionErrorCode.TIMEOUT

    duration_ms = None
    if started_at is not None:
        duration_ms = (datetime.now(tz=started_at.tzinfo) - started_at).total_seconds() * 1000

    execution_engine.mark_failed(
        execution_id,
        message=error_msg,
        code=code,
        duration_ms=duration_ms,
        metadata=status_metadata,
    )
    return {"status": "error"}


def _check_sampling_support(ctx: Context) -> bool:
    """Check if the MCP context supports sampling."""
    try:
        return ctx.session is not None and hasattr(ctx.session, "create_message")
    except Exception:
        return False


# =============================================================================
# MCP Tools
# =============================================================================


async def _get_data(
    intent: str,
    connection: str,
    tables_hint: list[str] | None = None,
    *,
    ctx: Context = None,
) -> dict:
    """Generate and execute SQL from natural language intent.

    This is the main entry point for natural language queries.

    When MCP Sampling is supported (e.g., fm-app-v2):
    1. Generate query plan via MCP Sampling
    2. Elicit user approval for the plan
    3. Generate SQL via MCP Sampling
    4. Validate and execute

    When MCP Sampling is NOT supported (e.g., Claude Desktop):
    - Returns context for the client to generate SQL
    - Client should then call run_sql(connection=..., sql=...) with the generated SQL

    Args:
        ctx: MCP Context for sampling and elicitation
        intent: Natural language query description
        tables_hint: Optional tables to focus on
        connection: Connection name for multi-connection support.

    Returns:
        Dict with query results, or context for client-side generation
    """
    from db_mcp.tools.utils import _resolve_connection_path, resolve_connection

    # Use resolve_connection for proper validation and path resolution.
    _, provider_id, conn_path = resolve_connection(connection)

    # Check if schema is available
    schema = load_schema_descriptions(provider_id, connection_path=conn_path)
    if not schema:
        return {
            "status": "error",
            "error": "No schema descriptions found. Complete onboarding first.",
            "phase": "schema_required",
        }

    # Build context (and record knowledge-flow metrics)
    examples_store = load_examples(provider_id)
    instructions_store = load_instructions(provider_id)

    schema_context = _build_schema_context(provider_id, tables_hint, connection_path=conn_path)
    examples_context = _build_examples_context(provider_id)
    rules_context = _build_rules_context(provider_id)

    # Record knowledge-flow attributes on current span
    current_span = trace.get_current_span()
    current_span.set_attribute("knowledge.schema_tables", len(schema.tables))
    current_span.set_attribute("knowledge.examples_available", len(examples_store.examples))
    current_span.set_attribute(
        "knowledge.examples_in_context", min(len(examples_store.examples), 5)
    )
    current_span.set_attribute("knowledge.rules_available", len(instructions_store.rules))
    current_span.set_attribute("knowledge.has_schema", True)
    current_span.set_attribute("knowledge.has_domain", bool(schema_context))

    full_context = f"""
User Intent: {intent}

Database Dialect: {schema.dialect or "unknown"}

{schema_context}

{examples_context}

{rules_context}
"""

    # ==========================================================================
    # Try MCP Sampling for plan generation
    # ==========================================================================
    plan: QueryPlan | None = None

    try:
        plan_result = await planner_agent.run(
            full_context,
            model=MCPSamplingModel(session=ctx.session),
        )
        plan = plan_result.output
        plan.intent = intent
    except Exception:
        # Sampling not supported - guide the agent to explore manually
        # Use session_id for per-session protocol injection
        session_id = getattr(ctx, "session_id", None)
        return inject_protocol(
            {
                "status": "error",
                "error": "MCP Sampling not available. Use manual exploration.",
                "guidance": {
                    "summary": "This tool requires MCP Sampling (not supported here).",
                    "what_to_do": [
                        "1. Read PROTOCOL.md: shell(command='cat PROTOCOL.md')",
                        "2. Explore catalogs: list_catalogs()",
                        "3. Explore schemas: list_schemas(catalog='...')",
                        "4. List tables: list_tables(catalog='...', schema='...')",
                        "5. Describe tables: describe_table(...)",
                        "6. Search examples: shell(command='grep -ri \"keyword\" examples/')",
                        "7. Generate SQL yourself based on what you learned",
                        "8. Execute: run_sql(connection='...', sql='SELECT ...')",
                    ],
                    "important": (
                        "Do NOT skip steps. Start with list_catalogs() to understand "
                        "the database hierarchy before writing any SQL."
                    ),
                },
            },
            session_id=session_id,
        )

    # ==========================================================================
    # Try elicitation for plan approval
    # ==========================================================================
    try:
        approval_result = await ctx.elicit(
            message=f"Query Plan:\n\n{plan.summary()}\n\nApprove this plan?",
            response_type=PlanApproval,
        )

        if approval_result.action != "accept" or not approval_result.data.approved:
            return {
                "status": "cancelled",
                "message": "Plan not approved by user",
                "plan": plan.model_dump(),
            }

        if approval_result.data.notes:
            plan.approval_notes = approval_result.data.notes

        plan.approved = True

    except Exception:
        # Elicitation not supported - auto-approve
        plan.approved = True
        plan.approval_notes = "Auto-approved (elicitation not available)"

    # ==========================================================================
    # Generate SQL via MCP Sampling
    # ==========================================================================
    sql_prompt = f"""
Approved Query Plan:
{plan.summary()}

Database Dialect: {schema.dialect or "standard SQL"}

{schema_context}

Generate the SQL query that implements this plan.
"""

    try:
        sql_result = await sql_generator_agent.run(
            sql_prompt,
            model=MCPSamplingModel(session=ctx.session),
        )
        generated_sql = sql_result.output.sql
    except Exception as e:
        # This shouldn't happen if plan generation worked, but handle it
        return {
            "status": "error",
            "error": f"SQL generation failed: {e}",
            "phase": "sql_generation",
            "plan": plan.model_dump(),
        }

    # ==========================================================================
    # Validate SQL
    # ==========================================================================
    is_read_only, error = validate_read_only(generated_sql)
    if not is_read_only:
        return {
            "status": "rejected",
            "error": error,
            "sql": generated_sql,
            "plan": plan.model_dump(),
        }

    conn_path = _resolve_connection_path(connection)
    explain_result: ExplainResult = explain_sql(generated_sql, connection_path=conn_path)

    if not explain_result.valid:
        return {
            "status": "invalid",
            "error": explain_result.error,
            "sql": generated_sql,
            "plan": plan.model_dump(),
        }

    # ==========================================================================
    # Cost tier handling
    # ==========================================================================
    if explain_result.cost_tier == CostTier.REJECT:
        return {
            "status": "rejected",
            "cost_tier": "reject",
            "reason": explain_result.tier_reason,
            "estimated_rows": explain_result.estimated_rows,
            "sql": generated_sql,
            "plan": plan.model_dump(),
            "suggestion": "Narrow your query with filters or a smaller date range.",
        }

    if explain_result.cost_tier == CostTier.CONFIRM:
        # Try elicitation for execution confirmation
        try:
            confirm_result = await ctx.elicit(
                message=(
                    f"Query Execution Confirmation\n\n"
                    f"Reason: {explain_result.tier_reason}\n"
                    f"Estimated rows: {explain_result.estimated_rows:,}\n\n"
                    f"SQL:\n{generated_sql}\n\n"
                    f"Execute this query?"
                ),
                response_type=ExecutionConfirmation,
            )

            if confirm_result.action != "accept" or not confirm_result.data.confirmed:
                return {
                    "status": "cancelled",
                    "message": "Query execution not confirmed",
                    "cost_tier": "confirm",
                    "sql": generated_sql,
                    "plan": plan.model_dump(),
                }

        except Exception:
            # Elicitation not supported - return for manual confirmation
            return {
                "status": "confirm_required",
                "cost_tier": "confirm",
                "reason": explain_result.tier_reason,
                "estimated_rows": explain_result.estimated_rows,
                "sql": generated_sql,
                "plan": plan.model_dump(),
                "message": "Use run_sql(connection='...', sql=..., confirmed=true) to proceed.",
            }

    # ==========================================================================
    # Execute
    # ==========================================================================
    try:
        query_uuid = _generate_query_uuid(generated_sql)
        result = _execute_query(generated_sql, query_id=query_uuid, connection=connection)

        return {
            "status": "success",
            "query_uuid": query_uuid,
            "sql": generated_sql,
            "data": result["data"],
            "columns": result["columns"],
            "rows_returned": result["rows_returned"],
            "duration_ms": result["duration_ms"],
            "provider_id": result["provider_id"],
            "cost_tier": explain_result.cost_tier.value,
            "plan": plan.model_dump(),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": f"Execution failed: {e}",
            "sql": generated_sql,
            "plan": plan.model_dump(),
        }


async def _run_sql(
    connection: str,
    query_id: str | None = None,
    sql: str | None = None,
    confirmed: bool = False,
    ctx: Context | None = None,
) -> dict:
    """Execute a previously validated SQL query or direct SQL for SQL-like APIs.

    FOR SQL-LIKE APIs (Dune, etc.) with supports_sql=true and supports_validate_sql=false:
        Call run_sql(connection="<name>", sql="SELECT ...") directly. The SQL will be sent to
        the API's execute_sql endpoint. Depending on provider behavior, run_sql may return:
        - status='success' with rows immediately (sync response), or
        - status='submitted' with execution_id when provider runs asynchronously.
        Use get_result(query_id=<execution_id>, connection=...) to poll async submissions.

    FOR REGULAR SQL DATABASES:
        REQUIRES a query_id from validate_sql. This ensures:
        1. All queries are validated before execution
        2. User/agent has seen the query plan
        3. Query can't be modified between validation and execution

    BEFORE generating SQL:
        1. Search existing examples: shell(command='grep -ri "keyword" examples/')
        2. If found, adapt existing SQL. Don't reinvent.

    AFTER successful query:
        Save for future reuse: shell(command='cat >> examples/new.yaml << EOF...')
        See PROTOCOL.md for format.

    Args:
        connection: Connection name for multi-connection dispatch.
        query_id: Query ID from validate_sql (required for SQL engines)
        sql: Raw SQL (allowed for SQL-like APIs without validate_sql)
        confirmed: Override for high-cost queries (cost_tier='reject')
        ctx: MCP Context for progress reporting (optional)

    Returns:
        Dict with query results or error
    """

    if query_id is None and sql is None:
        return inject_protocol(
            {
                "status": "error",
                "error": "Provide query_id or sql.",
                "guidance": {
                    "next_steps": [
                        (
                            "For SQL databases: call validate_sql(sql=..., connection=...) then "
                            "run_sql(query_id=..., connection=...)"
                        ),
                        "For SQL-like APIs: call run_sql(connection=..., sql=...) directly",
                    ]
                },
            }
        )

    from db_mcp.tools.utils import _resolve_connection_path

    if query_id is None and sql is not None:
        connection_path = Path(_resolve_connection_path(connection))
        connector = get_connector(connection_path=str(connection_path))
        caps = get_connector_capabilities(connector)

        policy_error = check_protocol_ack_gate(
            connection=connection,
            connection_path=connection_path,
        )
        if policy_error is not None:
            return inject_protocol(policy_error)

        if not caps.get("supports_sql"):
            return inject_protocol(
                {
                    "status": "error",
                    "error": "Active connector does not support SQL execution.",
                }
            )

        policy_error, statement_type, is_write = evaluate_sql_execution_policy(
            sql=sql,
            capabilities=caps,
            confirmed=confirmed,
            require_validate_first=True,
        )
        if policy_error is not None:
            return inject_protocol(policy_error)

        sql_mode = caps.get("sql_mode")

        direct_execute = None
        has_execute_sql_fallback = hasattr(connector, "execute_sql")
        if sql_mode is None or sql_mode == "engine" or has_execute_sql_fallback:
            def _direct_execute(runner_sql: str) -> dict[str, Any]:
                rows_affected = None
                if isinstance(connector, SQLConnector):
                    columns, rows, rows_affected = _execute_sql_on_engine(
                        connector, runner_sql, is_write=is_write, limit=None
                    )
                else:
                    rows = connector.execute_sql(runner_sql)
                    columns = list(rows[0].keys()) if rows else []

                return {
                    "data": rows,
                    "columns": columns,
                    "rows_returned": len(rows),
                    "rows_affected": rows_affected,
                    "provider_id": None,
                    "statement_type": statement_type,
                    "is_write": is_write,
                }

            direct_execute = _direct_execute

        # Service-level direct-SQL fallback keeps explicit sql_mode diagnostics,
        # including sql_mode={sql_mode!r}, for unsupported connector paths.
        return inject_protocol(
            await query_service.run_sql(
                connection=connection,
                sql=sql,
                confirmed=confirmed,
                connection_path=connection_path,
                connector=connector,
                capabilities=caps,
                execute_query=_execute_query,
                generate_query_id=_generate_query_uuid,
                direct_execute=direct_execute,
            )
        )

    connection_path = Path(_resolve_connection_path(connection))
    connector = get_connector(connection_path=connection_path)
    capabilities = get_connector_capabilities(connector)
    return inject_protocol(
        await query_service.run_sql(
            connection=connection,
            query_id=query_id,
            confirmed=confirmed,
            connection_path=connection_path,
            connector=connector,
            capabilities=capabilities,
            spawn_background_execution=lambda **kwargs: asyncio.create_task(
                _execute_query_background(
                    kwargs["query_id"],
                    kwargs["sql"],
                    connection=kwargs["connection"],
                    execution_id=kwargs["execution_id"],
                )
            ),
            protocol_ack_checker=check_protocol_ack_gate,
            execution_policy_evaluator=evaluate_sql_execution_policy,
        )
    )


async def _validate_sql(sql: str, connection: str) -> dict:
    """Validate SQL and register it for execution.

    REQUIRED before run_sql - validates the query and returns a query_id
    that must be passed to run_sql for execution.

    This ensures:
    1. All queries are validated before execution
    2. User/agent sees the query plan before committing
    3. Queries can't be modified between validation and execution

    Args:
        sql: SQL query to validate
        connection: Connection name for multi-connection support.

    Returns:
        Dict with validation results and query_id (if valid)
    """
    from db_mcp.tools.utils import _resolve_connection_path

    connection_path = _resolve_connection_path(connection)
    return inject_protocol(
        await query_service.validate_sql(
            sql=sql,
            connection=connection,
            connection_path=connection_path,
            validate_permissions=validate_sql_permissions,
            write_policy_getter=get_write_policy,
            should_explain=should_explain_statement,
            explain=explain_sql,
        )
    )


def _format_api_error(error: Any, default: str = "Execution failed") -> str:
    """Convert structured API error payloads into a readable string."""
    if isinstance(error, dict):
        for key in ("message", "detail", "error", "reason"):
            value = error.get(key)
            if value:
                return str(value)
        return str(error)
    if error:
        return str(error)
    return default


def _extract_api_execution_error(payload: dict[str, Any] | None) -> str | None:
    """Extract a failure message from API execution status/results payloads."""
    if not isinstance(payload, dict):
        return None

    state = str(payload.get("state") or payload.get("status") or "").lower()
    error = payload.get("error")
    is_failed_state = any(token in state for token in ("failed", "error", "cancelled"))
    if is_failed_state:
        return _format_api_error(error, f"Execution failed ({state})")
    if error and payload.get("success") is False:
        return _format_api_error(error, "API request failed")
    return None


def _api_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize API query tool payloads into row dictionaries."""
    data = response.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _find_endpoint_name(connector: Any, candidates: tuple[str, ...]) -> str | None:
    endpoints = getattr(connector.api_config, "endpoints", [])
    endpoint_names = {getattr(ep, "name", "") for ep in endpoints}
    for candidate in candidates:
        if candidate in endpoint_names:
            return candidate
    return None


def _resolve_api_execution(query_id: str, connection: str) -> dict[str, Any] | None:
    """Resolve API execution IDs that are not tracked in the internal query store."""
    from db_mcp.tools.utils import resolve_connection

    try:
        connector, _, _ = resolve_connection(connection, require_type="api")
    except Exception:
        return None

    if not hasattr(connector, "query_endpoint") or not hasattr(connector, "api_config"):
        return None

    status_endpoint = _find_endpoint_name(
        connector,
        ("get_execution_status", "execution_status"),
    )
    results_endpoint = _find_endpoint_name(
        connector,
        ("get_execution_results", "execution_results"),
    )
    if status_endpoint is None and results_endpoint is None:
        return None

    state = ""
    is_finished = False
    if status_endpoint is not None:
        status_response = connector.query_endpoint(
            status_endpoint,
            params={"execution_id": query_id},
        )
        if status_response.get("error"):
            return {
                "status": "error",
                "query_id": query_id,
                "error": status_response["error"],
            }

        status_rows = _api_rows(status_response)
        status_payload = status_rows[0] if status_rows else {}
        status_error = _extract_api_execution_error(status_payload)
        if status_error:
            return {
                "status": "error",
                "query_id": query_id,
                "error": status_error,
                "message": f"Query failed: {status_error}",
            }

        state = str(status_payload.get("state") or status_payload.get("status") or "").lower()
        is_finished = bool(status_payload.get("is_execution_finished"))
        is_complete = is_finished or any(
            token in state for token in ("complete", "success", "finished")
        )
        if not is_complete:
            is_running = any(token in state for token in ("running", "executing"))
            if is_running:
                return {
                    "status": "running",
                    "query_id": query_id,
                    "message": "Query is still executing on the API provider.",
                    "guidance": {
                        "next_steps": [
                            (
                                "Poll again in 10-30 seconds: "
                                f"get_result('{query_id}', connection='{connection}')"
                            )
                        ]
                    },
                }
            return {
                "status": "pending",
                "query_id": query_id,
                "message": "Query is queued on the API provider.",
                "guidance": {
                    "next_steps": [
                        (
                            "Poll again in 5-10 seconds: "
                            f"get_result('{query_id}', connection='{connection}')"
                        )
                    ]
                },
            }

    if results_endpoint is None:
        return {
            "status": "complete",
            "query_id": query_id,
            "data": [],
            "columns": [],
            "rows_returned": 0,
        }

    results_response = connector.query_endpoint(
        results_endpoint,
        params={"execution_id": query_id},
    )
    if results_response.get("error"):
        return {
            "status": "error",
            "query_id": query_id,
            "error": results_response["error"],
            "message": f"Query failed: {results_response['error']}",
        }

    rows = _api_rows(results_response)
    if len(rows) == 1 and any(
        key in rows[0] for key in ("execution_id", "state", "error", "is_execution_finished")
    ):
        # Some APIs return a status envelope instead of row data.
        api_error = _extract_api_execution_error(rows[0])
        if api_error:
            return {
                "status": "error",
                "query_id": query_id,
                "error": api_error,
                "message": f"Query failed: {api_error}",
            }

    columns = list(rows[0].keys()) if rows else []
    return {
        "status": "complete",
        "query_id": query_id,
        "data": rows,
        "columns": columns,
        "rows_returned": len(rows),
        "provider_id": connection,
        "message": (
            f"Query completed successfully. {len(rows)} rows returned."
            if rows
            else f"Query completed successfully with no rows (state={state or 'complete'})."
        ),
    }


async def _get_result(query_id: str, connection: str) -> dict:
    """Get status and results for a query.

    Use this to poll for results after run_sql returns status='submitted'.
    Call repeatedly until status is 'complete' or 'error'.

    Args:
        query_id: Query ID from validate_sql or run_sql
        connection: Connection name for multi-connection dispatch.

    Returns:
        Dict with query status and results (when complete)
    """
    from db_mcp.tools.utils import _resolve_connection_path

    store = get_query_store()
    query = await store.get(query_id)

    if query is None:
        # Fallback to unified execution store for direct SQL execution IDs.
        connection_path = Path(_resolve_connection_path(connection))
        execution_engine = get_execution_engine(connection_path)
        execution_result = execution_engine.get_result(query_id)
        if execution_result is not None:
            metadata = execution_result.metadata or {}
            should_poll_api_sql = bool(metadata.get("external_execution_id")) or (
                metadata.get("sql_mode") == "api_async"
            )
            if (
                execution_result.state in {ExecutionState.SUBMITTED, ExecutionState.RUNNING}
                and should_poll_api_sql
            ):
                poll_outcome = _poll_api_async_execution(
                    connection=connection,
                    execution_id=query_id,
                    metadata=metadata,
                    started_at=execution_result.started_at,
                )
                if poll_outcome.get("status") == "error":
                    return inject_protocol(
                        {
                            "status": "error",
                            "query_id": query_id,
                            "execution_id": query_id,
                            "state": execution_result.state.value,
                            "error": poll_outcome.get("error", "Execution failed"),
                            "error_code": poll_outcome.get("error_code"),
                        }
                    )

                # Reload after polling attempt because state may have transitioned.
                execution_result = execution_engine.get_result(query_id) or execution_result
                metadata = execution_result.metadata or metadata

            if execution_result.state == ExecutionState.SUCCEEDED:
                rows_returned = execution_result.rows_returned
                return inject_protocol(
                    {
                        "status": "complete",
                        "query_id": query_id,
                        "execution_id": query_id,
                        "state": execution_result.state.value,
                        "sql": None,
                        "data": execution_result.data,
                        "columns": execution_result.columns,
                        "rows_returned": rows_returned,
                        "duration_ms": execution_result.duration_ms,
                    }
                )

            if execution_result.state == ExecutionState.FAILED:
                return inject_protocol(
                    {
                        "status": "error",
                        "query_id": query_id,
                        "execution_id": query_id,
                        "state": execution_result.state.value,
                        "error": (
                            execution_result.error.message
                            if execution_result.error
                            else "Execution failed"
                        ),
                        "error_code": (
                            execution_result.error.code.value if execution_result.error else None
                        ),
                    }
                )

            if execution_result.state in {
                ExecutionState.SUBMITTED,
                ExecutionState.RUNNING,
                ExecutionState.PRECHECK,
            }:
                return inject_protocol(
                    {
                        "status": "running",
                        "query_id": query_id,
                        "execution_id": query_id,
                        "state": execution_result.state.value,
                        "external_execution_id": metadata.get("external_execution_id"),
                        "message": "Execution is in progress.",
                    }
                )
        api_payload = _resolve_api_execution(query_id=query_id, connection=connection)
        if api_payload is not None:
            return inject_protocol(api_payload)
        return inject_protocol(
            {
                "status": "not_found",
                "query_id": query_id,
                "message": "Query not found. It may have expired or the ID is invalid.",
            }
        )

    if query.connection is not None and query.connection != connection:
        return inject_protocol(
            {
                "status": "error",
                "query_id": query_id,
                "error": (
                    f"Query belongs to connection '{query.connection}', "
                    f"but get_result was called with connection '{connection}'."
                ),
            }
        )

    if query.status == QueryStatus.READY:
        return inject_protocol(
            {
                "status": "validated",
                "query_id": query_id,
                "sql": query.sql,
                "estimated_rows": query.estimated_rows,
                "cost_tier": query.cost_tier,
                "message": "Query is validated but not yet executed.",
                "guidance": {
                    "next_steps": [
                        f"Execute with: run_sql(query_id='{query_id}', connection='{connection}')"
                    ]
                },
            }
        )

    if query.status == QueryStatus.DISPATCHED:
        return inject_protocol(
            {
                "status": "pending",
                "query_id": query_id,
                "elapsed_seconds": round(query.elapsed_seconds, 1),
                "message": "Query is queued and will start shortly.",
                "guidance": {
                    "next_steps": [
                        (
                            f"Poll again in 5 seconds: get_result('{query_id}', "
                            f"connection='{connection}')"
                        )
                    ]
                },
            }
        )

    if query.status == QueryStatus.RUNNING:
        return inject_protocol(
            {
                "status": "running",
                "query_id": query_id,
                "elapsed_seconds": round(query.elapsed_seconds, 1),
                "running_seconds": round(query.running_seconds, 1)
                if query.running_seconds
                else None,
                "message": f"Query is executing ({query.elapsed_seconds:.0f}s elapsed).",
                "guidance": {
                    "next_steps": [
                        (
                            f"Poll again in 10-30 seconds: get_result('{query_id}', "
                            f"connection='{connection}')"
                        ),
                        "Tell the user the query is still running",
                    ]
                },
            }
        )

    if query.status == QueryStatus.ERROR:
        return inject_protocol(
            {
                "status": "error",
                "query_id": query_id,
                "elapsed_seconds": round(query.elapsed_seconds, 1),
                "error": query.error,
                "sql": query.sql,
                "message": f"Query failed: {query.error}",
            }
        )

    if query.status == QueryStatus.EXPIRED:
        return inject_protocol(
            {
                "status": "expired",
                "query_id": query_id,
                "message": "Query has expired. Please re-validate with validate_sql.",
            }
        )

    if query.status == QueryStatus.COMPLETE:
        result = query.result or {}
        rows_returned = result.get("rows_returned", 0)
        is_large = rows_returned > 100

        return inject_protocol(
            {
                "status": "complete",
                "query_id": query_id,
                "elapsed_seconds": round(query.elapsed_seconds, 1),
                "sql": query.sql,
                "data": result.get("data", []),
                "columns": result.get("columns", []),
                "rows_returned": rows_returned,
                "duration_ms": result.get("duration_ms"),
                "provider_id": result.get("provider_id"),
                "presentation_hints": {
                    "downloadable": True,
                    "large_result": is_large,
                    "display_recommendation": "export" if is_large else "table",
                },
                "guidance": {
                    "summary": f"Query completed successfully. {rows_returned} rows returned.",
                    "next_steps": (
                        ["Export results to CSV for the user", "Offer to refine the query"]
                        if is_large
                        else ["Present data in a table", "Summarize key insights"]
                    ),
                },
            }
        )

    # Fallback for unknown status
    return inject_protocol(
        {
            "status": query.status,
            "query_id": query_id,
            "message": f"Query in unexpected state: {query.status}",
        }
    )


async def _export_results(
    sql: str,
    connection: str,
    format: str = "csv",
    filename: str | None = None,
    *,
    ctx: Context = None,
) -> dict:
    """Export query results as CSV or other formats.

    Executes the query and returns the results formatted for export.
    The agent can use this to create downloadable files.

    Args:
        ctx: MCP Context
        sql: SQL query to execute and export
        format: Export format - 'csv' (default), 'json', or 'markdown'
        filename: Optional filename (without extension)
        connection: Connection name for multi-connection support.

    Returns:
        Dict with formatted content and file metadata
    """
    # Validate read-only
    is_read_only, error = validate_read_only(sql)
    if not is_read_only:
        return {
            "status": "rejected",
            "error": error,
        }

    # Execute query (pass connection for multi-connection dispatch)
    try:
        result = _execute_query(sql, limit=10000, connection=connection)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Query execution failed: {e}",
        }

    data = result["data"]
    columns = result["columns"]
    rows_returned = result["rows_returned"]

    # Generate filename if not provided
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not filename:
        query_hash = hashlib.sha256(sql.encode()).hexdigest()[:8]
        filename = f"export_{query_hash}_{timestamp}"

    # Format the content based on requested format
    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data)
        content = output.getvalue()
        mime_type = "text/csv"
        extension = "csv"

    elif format == "json":
        import json

        content = json.dumps(data, indent=2, default=str)
        mime_type = "application/json"
        extension = "json"

    elif format == "markdown":
        # Create markdown table
        lines = []
        # Header
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
        # Rows
        for row in data:
            values = [str(row.get(col, "")) for col in columns]
            lines.append("| " + " | ".join(values) + " |")
        content = "\n".join(lines)
        mime_type = "text/markdown"
        extension = "md"

    else:
        return {
            "status": "error",
            "error": f"Unsupported format: {format}. Use 'csv', 'json', or 'markdown'.",
        }

    full_filename = f"{filename}.{extension}"

    return {
        "status": "success",
        "format": format,
        "filename": full_filename,
        "mime_type": mime_type,
        "content": content,
        "rows_exported": rows_returned,
        "columns": columns,
        "file_size_bytes": len(content.encode("utf-8")),
        "instructions": {
            "hint": (
                f"Export ready: {full_filename} ({rows_returned} rows). "
                "Save this content as a file and present to user for download."
            ),
            "for_chatgpt": (
                "Use create_file tool to write content to /mnt/user-data/outputs/, "
                "then use present_files to create download link."
            ),
            "for_claude": ("Create a downloadable artifact with this content."),
        },
    }


# =============================================================================
# Test Tools (can be removed in production)
# =============================================================================


@dataclass
class TestConfirmation:
    """Simple yes/no confirmation for testing."""

    confirmed: bool


async def _test_elicitation(message: str = "Test message", *, ctx: Context = None) -> dict:
    """Test if MCP elicitation is supported by the client.

    Args:
        ctx: MCP Context
        message: Message to show in elicitation prompt

    Returns:
        Dict with elicitation test result
    """
    try:
        result = await ctx.elicit(
            message=f"{message}\n\nDo you confirm?",
            response_type=TestConfirmation,
        )

        return {
            "status": "elicitation_supported",
            "action": result.action,
            "confirmed": result.data.confirmed if result.data else None,
            "message": "Elicitation works!",
        }

    except Exception as e:
        return {
            "status": "elicitation_not_supported",
            "error": str(e),
            "message": "Client does not support MCP elicitation.",
        }


async def _test_sampling(prompt: str = "Say hello", *, ctx: Context = None) -> dict:
    """Test if MCP sampling is supported by the client.

    Args:
        ctx: MCP Context
        prompt: Test prompt for the LLM

    Returns:
        Dict with sampling test result
    """
    try:
        # Simple agent just to test sampling works
        test_agent = Agent(
            system_prompt="You are a helpful assistant. Keep responses brief.",
        )

        result = await test_agent.run(
            prompt,
            model=MCPSamplingModel(session=ctx.session),
        )

        return {
            "status": "sampling_supported",
            "response": str(result.output),
            "message": "MCP Sampling works!",
        }

    except Exception as e:
        return {
            "status": "sampling_not_supported",
            "error": str(e),
            "message": "Client does not support MCP sampling.",
        }
