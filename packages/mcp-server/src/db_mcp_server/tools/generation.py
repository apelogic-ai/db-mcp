"""Thin MCP tool wrappers for SQL generation / query tools (step 3.06).

Calls db_mcp.services.query directly for validate_sql and run_sql.
_get_data is an MCP-specific tool (uses MCPSamplingModel and ctx.elicit)
implemented here with context building via db_mcp.services.context.
_get_result and _export_results use the execution engine and connectors directly.

No import from db_mcp.tools.generation.

Note: Do NOT add 'from __future__ import annotations' here.  FastMCP uses
pydantic to inspect function signatures at registration time.  When annotations
are stored as strings (PEP 563), pydantic cannot resolve 'Any' back to
typing.Any, which causes keyword-only parameters with Any type (e.g. ctx) to
be treated as required fields instead of optional ones.
"""

import asyncio
import csv
import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from db_mcp.services.connection import _resolve_connection_path, resolve_connection
from db_mcp.services.context import (
    build_examples_context,
    build_rules_context,
    build_schema_context,
)
from db_mcp.services.query import run_sql as svc_run_sql
from db_mcp.services.query import validate_sql as svc_validate_sql
from db_mcp_data.connectors import get_connector, get_connector_capabilities
from db_mcp_data.connectors.sql import SQLConnector
from db_mcp_data.execution import ExecutionState
from db_mcp_data.execution.engine import get_execution_engine
from db_mcp_data.execution.query_store import get_query_store
from db_mcp_data.validation.explain import (
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

from db_mcp_server.protocol import inject_protocol

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("db_mcp.query")

ASYNC_ROW_THRESHOLD = 50_000


# ---------------------------------------------------------------------------
# Elicitation models (MCP-specific, live here not in core)
# ---------------------------------------------------------------------------

@dataclass
class PlanApproval:
    approved: bool
    notes: str = ""


@dataclass
class ExecutionConfirmation:
    confirmed: bool


# ---------------------------------------------------------------------------
# PydanticAI agents (MCP Sampling — mcp-server concern)
# ---------------------------------------------------------------------------

class SQLGenerationResult(BaseModel):
    sql: str = Field(..., description="The generated SQL query")
    explanation: str = Field(..., description="Brief explanation of the query")


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

sql_generator_agent = Agent(
    system_prompt="""You are a SQL generator. Given a query plan and database schema,
generate the correct SQL query.

Follow the plan exactly. Use proper SQL syntax for the specified dialect.
Include appropriate JOINs, WHERE clauses, GROUP BY, ORDER BY as specified.
Always include a LIMIT clause if not specified (default to 100).
""",
    output_type=SQLGenerationResult,
)


# ---------------------------------------------------------------------------
# _validate_sql — thin wrapper over services.query.validate_sql
# ---------------------------------------------------------------------------

async def _validate_sql(sql: str, connection: str) -> object:
    """Validate SQL and register it for execution.

    REQUIRED before run_sql. Validates the query and returns a query_id that
    must be passed to run_sql.
    """
    connection_path = _resolve_connection_path(connection)
    result = await svc_validate_sql(
        sql=sql,
        connection=connection,
        connection_path=connection_path,
        validate_permissions=validate_sql_permissions,
        write_policy_getter=get_write_policy,
        should_explain=should_explain_statement,
        explain=explain_sql,
    )
    return inject_protocol(result)


# ---------------------------------------------------------------------------
# _run_sql — thin wrapper over services.query.run_sql
# ---------------------------------------------------------------------------

def _make_query_id(sql: str) -> str:
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, sql))


async def _execute_query_background(
    query_id: str,
    sql: str,
    *,
    connection: str,
    execution_id: str,
) -> None:
    """Background task: run SQL and update the execution store."""
    connection_path = Path(_resolve_connection_path(connection))
    execution_engine = get_execution_engine(connection_path)
    connector = get_connector(connection_path=str(connection_path))
    get_connector_capabilities(connector)  # validate connector capabilities
    try:
        if isinstance(connector, SQLConnector):
            from sqlalchemy import text as sa_text

            engine_obj = connector.get_engine()
            with engine_obj.connect() as conn:
                result = conn.execute(sa_text(sql))
                rows = [dict(r._mapping) for r in result]
                columns = list(result.keys()) if result.keys() else []
        elif hasattr(connector, "execute_sql"):
            rows = connector.execute_sql(sql)
            columns = list(rows[0].keys()) if rows else []
        else:
            rows, columns = [], []

        execution_engine.mark_succeeded(
            execution_id,
            data=rows,
            columns=columns,
            rows_returned=len(rows),
            rows_affected=None,
            duration_ms=None,
        )
    except Exception as exc:
        from db_mcp_data.execution import ExecutionErrorCode

        execution_engine.mark_failed(
            execution_id,
            message=str(exc),
            code=ExecutionErrorCode.ENGINE,
            duration_ms=None,
        )


async def _run_sql(
    connection: str,
    query_id: str | None = None,
    sql: str | None = None,
    confirmed: bool = False,
    ctx: object = None,
) -> object:
    """Execute a previously validated SQL query or direct SQL for SQL-like APIs.

    For SQL databases: pass query_id from validate_sql.
    For SQL-like APIs (supports_sql=true, supports_validate_sql=false): pass sql directly.
    """
    connection_path = Path(_resolve_connection_path(connection))
    connector = get_connector(connection_path=str(connection_path))
    capabilities = get_connector_capabilities(connector)

    result = await svc_run_sql(
        connection=connection,
        query_id=query_id,
        sql=sql,
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
    )
    return inject_protocol(result)


# ---------------------------------------------------------------------------
# _get_data — MCP Sampling-based natural language query tool
# ---------------------------------------------------------------------------

def _check_sampling_support(ctx: Any) -> bool:
    return ctx is not None and ctx.session is not None and hasattr(
        ctx.session, "create_message"
    )


async def _get_data(
    intent: str,
    connection: str,
    tables_hint: list[str] | None = None,
    *,
    ctx: Any = None,
) -> dict:
    """Generate and execute SQL from natural language intent.

    When MCP Sampling is supported: generate plan → approve → generate SQL → validate → execute.
    When not supported: return context for client-side generation.
    """

    _, provider_id, conn_path = resolve_connection(connection)

    schema = load_schema_descriptions(provider_id, connection_path=conn_path)
    if not schema:
        return {
            "status": "error",
            "error": "No schema descriptions found. Complete onboarding first.",
            "phase": "schema_required",
        }

    examples_store = load_examples(provider_id)
    instructions_store = load_instructions(provider_id)

    schema_context = build_schema_context(
        provider_id, tables_hint=tables_hint, connection_path=conn_path
    )
    examples_context = build_examples_context(provider_id)
    rules_context = build_rules_context(provider_id)

    current_span = trace.get_current_span()
    current_span.set_attribute("knowledge.schema_tables", len(schema.tables))
    current_span.set_attribute("knowledge.examples_available", len(examples_store.examples))
    current_span.set_attribute("knowledge.rules_available", len(instructions_store.rules))

    full_context = (
        f"User Intent: {intent}\n\n"
        f"Database Dialect: {schema.dialect or 'unknown'}\n\n"
        f"{schema_context}\n\n{examples_context}\n\n{rules_context}"
    )

    # ---- MCP Sampling path ------------------------------------------------
    if _check_sampling_support(ctx):
        try:
            from pydantic_ai.models.mcp_sampling import MCPSamplingModel

            plan_result = await planner_agent.run(
                full_context, model=MCPSamplingModel(session=ctx.session)
            )
            plan = plan_result.output

            approval_result = await ctx.elicit(
                message=f"Query plan: {plan.model_dump_json(indent=2)}\n\nApprove?",
                schema=PlanApproval,
            )
            if not approval_result.data.approved:
                return {"status": "cancelled", "reason": "User did not approve query plan."}

            sql_result = await sql_generator_agent.run(
                f"Plan: {plan.model_dump_json()}\n\nSchema: {schema_context}",
                model=MCPSamplingModel(session=ctx.session),
            )
            generated_sql = sql_result.output.sql

            validation = await svc_validate_sql(
                sql=generated_sql,
                connection=connection,
                connection_path=conn_path,
                validate_permissions=validate_sql_permissions,
                write_policy_getter=get_write_policy,
                should_explain=should_explain_statement,
                explain=explain_sql,
            )
            if not validation.get("valid"):
                return inject_protocol(validation)

            query_id = validation.get("query_id")
            conn_obj = get_connector(connection_path=str(conn_path))
            caps = get_connector_capabilities(conn_obj)
            exec_result = await svc_run_sql(
                connection=connection,
                query_id=query_id,
                connection_path=conn_path,
                connector=conn_obj,
                capabilities=caps,
            )
            return inject_protocol(exec_result)

        except Exception as exc:
            logger.warning("MCP Sampling path failed; falling back to context return: %s", exc)

    # ---- Context return (no MCP Sampling) ---------------------------------
    return {
        "status": "context_ready",
        "intent": intent,
        "connection": connection,
        "schema_context": schema_context,
        "examples_context": examples_context,
        "rules_context": rules_context,
        "dialect": schema.dialect or "unknown",
        "guidance": {
            "next_steps": [
                "Use the provided context to generate SQL, then call validate_sql.",
                "After validation, call run_sql with the returned query_id.",
            ]
        },
    }


# ---------------------------------------------------------------------------
# _get_result — poll async query results from the execution engine
# ---------------------------------------------------------------------------

async def _get_result(query_id: str, connection: str) -> object:
    """Get status and results for a query. Poll until status is 'complete' or 'error'."""
    store = get_query_store()
    query = await store.get(query_id)

    if query is not None:
        from db_mcp_data.execution.query_store import QueryStatus  # local import

        if query.status == QueryStatus.COMPLETE:
            return inject_protocol({
                "status": "complete",
                "query_id": query_id,
                "data": query.result or [],
                "rows_returned": len(query.result or []),
            })
        if query.status == QueryStatus.ERROR:
            return inject_protocol({
                "status": "error",
                "query_id": query_id,
                "error": query.error or "Query failed",
            })
        return inject_protocol({
            "status": "running",
            "query_id": query_id,
            "message": "Query is still running. Poll again shortly.",
        })

    # Fall back to unified execution store
    connection_path = Path(_resolve_connection_path(connection))
    execution_engine = get_execution_engine(connection_path)
    execution_result = execution_engine.get_result(query_id)

    if execution_result is None:
        return inject_protocol({
            "status": "error",
            "query_id": query_id,
            "error": f"Query '{query_id}' not found. It may have expired.",
        })

    if execution_result.state == ExecutionState.SUCCEEDED:
        return inject_protocol({
            "status": "complete",
            "query_id": query_id,
            "data": execution_result.data or [],
            "columns": execution_result.columns or [],
            "rows_returned": execution_result.rows_returned or 0,
            "duration_ms": execution_result.duration_ms,
        })

    if execution_result.state == ExecutionState.FAILED:
        return inject_protocol({
            "status": "error",
            "query_id": query_id,
            "error": execution_result.error or "Execution failed",
        })

    return inject_protocol({
        "status": "running",
        "query_id": query_id,
        "state": execution_result.state.value,
        "message": "Query is still running. Poll again shortly.",
    })


# ---------------------------------------------------------------------------
# _export_results — execute SQL and return formatted output
# ---------------------------------------------------------------------------

async def _export_results(
    sql: str,
    connection: str,
    format: str = "csv",
    filename: str | None = None,
    *,
    ctx: Any = None,
) -> dict:
    """Export query results as CSV, JSON, or Markdown."""
    is_read_only, error = validate_read_only(sql)
    if not is_read_only:
        return {"status": "rejected", "error": error}

    connection_path = Path(_resolve_connection_path(connection))
    connector = get_connector(connection_path=str(connection_path))

    try:
        if isinstance(connector, SQLConnector):
            from sqlalchemy import text as sa_text

            engine_obj = connector.get_engine()
            with engine_obj.connect() as conn:
                result = conn.execute(sa_text(sql))
                columns = list(result.keys())
                data = [dict(r._mapping) for r in result]
        elif hasattr(connector, "execute_sql"):
            data = connector.execute_sql(sql)
            columns = list(data[0].keys()) if data else []
        else:
            return {"status": "error", "error": "Connector does not support SQL execution."}
    except Exception as exc:
        return {"status": "error", "error": f"Query execution failed: {exc}"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not filename:
        query_hash = hashlib.sha256(sql.encode()).hexdigest()[:8]
        filename = f"export_{query_hash}_{timestamp}"

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data)
        content = output.getvalue()
        ext = "csv"
        mime = "text/csv"
    elif format == "json":
        import json
        content = json.dumps(data, indent=2, default=str)
        ext = "json"
        mime = "application/json"
    elif format == "markdown":
        if not data:
            content = "No data returned."
        else:
            header = "| " + " | ".join(columns) + " |"
            separator = "| " + " | ".join(["---"] * len(columns)) + " |"
            rows_md = [
                "| " + " | ".join(str(row.get(c, "")) for c in columns) + " |"
                for row in data
            ]
            content = "\n".join([header, separator] + rows_md)
        ext = "md"
        mime = "text/markdown"
    else:
        return {"status": "error", "error": f"Unsupported format: '{format}'."}

    return {
        "status": "complete",
        "format": format,
        "filename": f"{filename}.{ext}",
        "mime_type": mime,
        "rows_exported": len(data),
        "content": content,
    }
