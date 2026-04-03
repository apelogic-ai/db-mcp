"""Query execution and validation services."""

from datetime import datetime
from pathlib import Path
from typing import Any

from db_mcp_data.connectors import get_connector, get_connector_capabilities
from db_mcp_data.connectors.sql import SQLConnector
from db_mcp_data.execution import (
    ExecutionErrorCode,
    ExecutionRequest,
    ExecutionState,
    check_protocol_ack_gate,
    evaluate_sql_execution_policy,
)
from db_mcp_data.execution.engine import get_execution_engine
from db_mcp_data.validation.explain import (
    CostTier,
    ExplainResult,
    explain_sql,
    get_write_policy,
    should_explain_statement,
    validate_sql_permissions,
)
from sqlalchemy import text

ASYNC_ROW_THRESHOLD = 50_000


def execute_bicp_query(
    sql: str,
    *,
    connection_path: Path,
    connector: Any | None = None,
    capabilities: dict[str, Any] | None = None,
    validate_permissions: Any | None = None,
) -> tuple[list[dict[str, Any]], list[list[Any]]]:
    """Execute a BICP-approved query and return (columns, rows)."""
    if connector is None:
        connector = get_connector(connection_path=connection_path)
    if capabilities is None:
        capabilities = get_connector_capabilities(connector)
    if validate_permissions is None:
        validate_permissions = validate_sql_permissions

    is_valid, error, _, is_write = validate_permissions(sql, capabilities=capabilities)
    if not is_valid:
        raise ValueError(f"Query validation failed: {error}")

    if isinstance(connector, SQLConnector):
        engine = connector.get_engine()
        if is_write:
            with engine.begin() as conn:
                result = conn.execute(text(sql))
                if result.returns_rows:
                    column_names = list(result.keys())
                    columns = [{"name": name, "dataType": "VARCHAR"} for name in column_names]
                    rows = []
                    for i, row in enumerate(result):
                        if i >= 10000:
                            break
                        rows.append(list(row))
                else:
                    columns = []
                    rows = []
        else:
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                column_names = list(result.keys())
                columns = [{"name": name, "dataType": "VARCHAR"} for name in column_names]
                rows = []
                for i, row in enumerate(result):
                    if i >= 10000:
                        break
                    rows.append(list(row))
        return columns, rows

    result_rows = connector.execute_sql(sql)
    if result_rows:
        columns = [{"name": k, "dataType": "VARCHAR"} for k in result_rows[0].keys()]
        rows = [list(r.values()) for r in result_rows[:10000]]
    else:
        columns = []
        rows = []
    return columns, rows


def analyze_candidate_sql(
    sql: str,
    *,
    connection_path: Path,
    connector: Any | None = None,
    capabilities: dict[str, Any] | None = None,
    validate_permissions: Any | None = None,
    explain: Any | None = None,
) -> dict[str, Any]:
    """Analyze a generated SQL candidate for warnings and cost."""
    if connector is None:
        connector = get_connector(connection_path=connection_path)
    if capabilities is None:
        capabilities = get_connector_capabilities(connector)
    if validate_permissions is None:
        validate_permissions = validate_sql_permissions
    if explain is None:
        explain = explain_sql

    warnings: list[str] = []
    cost: dict[str, Any] | None = None

    is_valid, error, statement_type, is_write = validate_permissions(
        sql, capabilities=capabilities
    )
    if not is_valid:
        warnings.append(f"Validation warning: {error}")

    if not is_write and statement_type not in {"SHOW", "DESCRIBE", "DESC", "EXPLAIN"}:
        try:
            explain_result: ExplainResult = explain(sql, connection_path=connection_path)
            if explain_result.valid:
                cost = {
                    "estimated_rows": explain_result.estimated_rows,
                    "cost_units": explain_result.estimated_cost,
                }
            else:
                warnings.append(f"Cost estimation failed: {explain_result.error}")
        except Exception as exc:
            warnings.append(f"Cost estimation error: {exc}")

    return {
        "warnings": warnings,
        "cost": cost,
    }


def _gateway_runner(
    runner_sql: str,
    *,
    connector: Any | None,
    connection: str,
    connection_path: Path,
    query_id: str,
) -> dict[str, Any]:
    """Execute SQL via gateway adapter dispatch (default when no callback injected).

    When *connector* is pre-resolved (backward compat), the specific adapter is
    selected via get_adapter(connector).  When *connector* is None the gateway's
    resolve_and_dispatch() resolves the connector from connection_path internally,
    keeping all connector lifecycle management inside the gateway boundary.
    """
    from db_mcp_models.gateway import DataRequest, SQLQuery

    request = DataRequest(connection=connection, query=SQLQuery(sql=runner_sql))

    if connector is not None:
        from db_mcp_data.gateway.dispatcher import get_adapter
        try:
            adapter = get_adapter(connector)
        except ValueError as exc:
            return {
                "data": [], "columns": [], "rows_returned": 0, "rows_affected": None,
                "metadata": {"error": str(exc)},
            }
        resp = adapter.execute(connector, request, connection_path=connection_path)
    else:
        from db_mcp_data.gateway.dispatcher import resolve_and_dispatch
        resp = resolve_and_dispatch(request, connection_path=connection_path)

    if not resp.is_success:
        raise RuntimeError(resp.error or "Gateway execution failed")
    return {
        "data": resp.data,
        "columns": [c.name for c in resp.columns],
        "rows_returned": resp.rows_returned,
        "rows_affected": None,
        "metadata": {
            "provider_id": None,
            "statement_type": None,
            "is_write": False,
        },
    }


def _make_query_id(sql: str) -> str:
    """Deterministic query ID from SQL content (SHA-256 prefix)."""
    import hashlib
    import uuid

    normalized = " ".join(sql.lower().split())
    hash_bytes = hashlib.sha256(normalized.encode()).digest()[:16]
    return str(uuid.UUID(bytes=hash_bytes))


def _build_direct_sync_response(
    *,
    connection: str,
    sql: str,
    connection_path: Path,
    execution_engine: Any | None,
    execute_query: Any | None,
    generate_query_id: Any | None,
    direct_execute: Any | None,
    connector: Any | None = None,
) -> dict[str, Any]:
    if execution_engine is None:
        execution_engine = get_execution_engine(connection_path)

    # generate_query_id: use injected fn or fall back to internal implementation
    _gen_id = generate_query_id if generate_query_id is not None else _make_query_id
    direct_query_id = _gen_id(sql)

    request = ExecutionRequest(
        connection=connection,
        sql=sql,
        query_id=direct_query_id,
        idempotency_key=direct_query_id,
    )

    def _direct_runner(runner_sql: str) -> dict[str, Any]:
        # Prefer injected callbacks for backward compat; fall back to gateway.
        if direct_execute is not None:
            raw = direct_execute(runner_sql)
        elif execute_query is not None:
            raw = execute_query(
                runner_sql,
                connection=connection,
                query_id=direct_query_id,
            )
        else:
            return _gateway_runner(
                runner_sql,
                connector=connector,
                connection=connection,
                connection_path=connection_path,
                query_id=direct_query_id,
            )
        return {
            "data": raw.get("data", []),
            "columns": raw.get("columns", []),
            "rows_returned": raw.get("rows_returned", 0),
            "rows_affected": raw.get("rows_affected"),
            "metadata": {
                "provider_id": raw.get("provider_id"),
                "statement_type": raw.get("statement_type"),
                "is_write": raw.get("is_write", False),
            },
        }

    handle, exec_result = execution_engine.submit_sync(request, _direct_runner)
    if exec_result.state != ExecutionState.SUCCEEDED:
        error_message = exec_result.error.message if exec_result.error else "Execution failed"
        return {
            "status": "error",
            "execution_id": handle.execution_id,
            "state": exec_result.state.value,
            "error": error_message,
            "error_code": exec_result.error.code.value if exec_result.error else None,
            "sql": sql,
        }

    return {
        "status": "success",
        "mode": "sync",
        "execution_id": handle.execution_id,
        "state": exec_result.state.value,
        "query_id": direct_query_id,
        "sql": sql,
        "data": exec_result.data,
        "columns": exec_result.columns,
        "rows_returned": exec_result.rows_returned,
        "duration_ms": exec_result.duration_ms,
        "provider_id": exec_result.metadata.get("provider_id"),
        "cost_tier": "unknown",
        "statement_type": exec_result.metadata.get("statement_type"),
        "is_write": exec_result.metadata.get("is_write", False),
        "rows_affected": exec_result.rows_affected,
    }


async def run_sql(
    connection: str,
    query_id: str | None = None,
    sql: str | None = None,
    confirmed: bool = False,
    connection_path: Path | None = None,
    *,
    connector: Any | None = None,
    capabilities: dict | None = None,
    execution_engine: Any | None = None,
    execute_query: Any | None = None,
    spawn_background_execution: Any | None = None,
    generate_query_id: Any | None = None,
    direct_execute: Any | None = None,
    protocol_ack_checker: Any | None = None,
    execution_policy_evaluator: Any | None = None,
) -> dict:
    """Execute SQL or a previously validated query."""
    if protocol_ack_checker is None:
        protocol_ack_checker = check_protocol_ack_gate
    if execution_policy_evaluator is None:
        execution_policy_evaluator = evaluate_sql_execution_policy

    if query_id is None and sql is None:
        return {
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

    if query_id is None and sql is not None:
        if connection_path is None:
            raise ValueError("connection_path is required for direct SQL execution")

        # Resolve capabilities via gateway when no overrides are injected.
        # connector is resolved lazily below only for the SQL-API execution path.
        if capabilities is not None:
            caps = capabilities
        elif connector is not None:
            caps = get_connector_capabilities(connector)
        else:
            from db_mcp_data import gateway as _gateway_module
            caps = _gateway_module.capabilities(connection_path=connection_path)

        policy_error = protocol_ack_checker(
            connection=connection,
            connection_path=connection_path,
        )
        if policy_error is not None:
            return policy_error

        if not caps.get("supports_sql"):
            return {
                "status": "error",
                "error": "Active connector does not support SQL execution.",
            }

        policy_error, _, _ = execution_policy_evaluator(
            sql=sql,
            capabilities=caps,
            confirmed=confirmed,
            require_validate_first=True,
        )
        if policy_error is not None:
            return policy_error

        sql_mode = caps.get("sql_mode")
        if sql_mode in {None, "engine"}:
            # connector may be None here; _gateway_runner uses resolve_and_dispatch.
            return _build_direct_sync_response(
                connection=connection,
                sql=sql,
                connection_path=connection_path,
                execution_engine=execution_engine,
                execute_query=execute_query,
                generate_query_id=generate_query_id,
                direct_execute=direct_execute,
                connector=connector,
            )

        # SQL-API execution path: need the actual connector for submit_sql().
        if connector is None:
            connector = get_connector(connection_path=connection_path)
        if hasattr(connector, "submit_sql"):
            if execution_engine is None:
                execution_engine = get_execution_engine(connection_path)
            _gen_id = generate_query_id if generate_query_id is not None else _make_query_id
            direct_query_id = _gen_id(sql)
            request = ExecutionRequest(
                connection=connection,
                sql=sql,
                query_id=direct_query_id,
                idempotency_key=direct_query_id,
                metadata={"sql_mode": sql_mode or "api_sync"},
            )
            handle = execution_engine.submit_async(request)
            try:
                submission = connector.submit_sql(sql)
            except Exception as exc:
                execution_engine.mark_failed(
                    handle.execution_id,
                    message=str(exc),
                    code=ExecutionErrorCode.ENGINE,
                    metadata={"sql_mode": sql_mode or "api_sync"},
                )
                return {
                    "status": "error",
                    "query_id": handle.execution_id,
                    "execution_id": handle.execution_id,
                    "state": ExecutionState.FAILED.value,
                    "sql": sql,
                    "error": str(exc),
                    "error_code": ExecutionErrorCode.ENGINE.value,
                }

            if submission.get("mode") == "sync":
                rows = submission.get("rows", [])
                if not isinstance(rows, list):
                    rows = []
                columns = list(rows[0].keys()) if rows else []
                execution_engine.mark_succeeded(
                    handle.execution_id,
                    data=rows,
                    columns=columns,
                    rows_returned=len(rows),
                    rows_affected=None,
                    duration_ms=None,
                    metadata={
                        "sql_mode": sql_mode or "api_sync",
                        "submission_mode": "sync",
                    },
                )
                return {
                    "status": "success",
                    "mode": "sync",
                    "query_id": direct_query_id,
                    "execution_id": handle.execution_id,
                    "state": ExecutionState.SUCCEEDED.value,
                    "sql": sql,
                    "data": rows,
                    "columns": columns,
                    "rows_returned": len(rows),
                    "duration_ms": None,
                    "provider_id": None,
                    "cost_tier": "unknown",
                    "statement_type": None,
                    "is_write": False,
                    "rows_affected": None,
                }

            external_id = submission.get("execution_id")
            if external_id:
                execution_engine.update_metadata(
                    handle.execution_id,
                    {
                        "sql_mode": sql_mode or "api_sync",
                        "external_execution_id": str(external_id),
                        "submission_mode": "async",
                    },
                    merge=True,
                )
                execution_engine.mark_running(handle.execution_id)
                return {
                    "status": "submitted",
                    "mode": "async",
                    "query_id": handle.execution_id,
                    "execution_id": handle.execution_id,
                    "state": ExecutionState.RUNNING.value,
                    "sql": sql,
                    "external_execution_id": str(external_id),
                    "message": (
                        "Query submitted to SQL API. "
                        f"Use get_result('{handle.execution_id}', connection='{connection}') "
                        "to poll status."
                    ),
                    "poll_interval_seconds": 5,
                }

        if direct_execute is not None:
            return _build_direct_sync_response(
                connection=connection,
                sql=sql,
                connection_path=connection_path,
                execution_engine=execution_engine,
                execute_query=execute_query,
                generate_query_id=generate_query_id,
                direct_execute=direct_execute,
                connector=connector,
            )

        return {
            "status": "error",
            "error": (
                "Unsupported direct SQL execution path. "
                f"Connector must implement submit_sql() or execute_sql(); sql_mode={sql_mode!r}."
            ),
            "sql": sql,
        }

    if query_id is not None:
        from db_mcp_data import gateway as _gateway_module
        query = await _gateway_module.get_query(query_id)
        if query is None:
            return {
                "status": "error",
                "error": "Query not found. Use validate_sql first to get a query_id.",
                "query_id": query_id,
                "guidance": {
                    "next_steps": [
                        "1. Call validate_sql(sql='YOUR SQL HERE')",
                        (
                            "2. Use the returned query_id with "
                            "run_sql(query_id='...', connection='...')"
                        ),
                    ],
                },
            }
        if query.status == "expired":
            return {
                "status": "error",
                "error": "Query validation has expired. Please re-validate.",
                "query_id": query_id,
                "guidance": {
                    "next_steps": [
                        "Call validate_sql again with your SQL",
                        "Query IDs expire after 30 minutes",
                    ],
                },
            }
        if query.connection is not None and query.connection != connection:
            return {
                "status": "error",
                "error": (
                    f"Query was validated for connection '{query.connection}', "
                    f"but run_sql was called with connection '{connection}'."
                ),
                "query_id": query_id,
            }
        if not query.can_execute:
            return {
                "status": "error",
                "error": f"Query cannot be executed. Status: {query.status}",
                "query_id": query_id,
            }

        execution_connection = query.connection if query.connection is not None else connection
        if connection_path is None:
            raise ValueError("connection_path is required for validated query execution")

        # Resolve capabilities via gateway when no overrides are injected.
        # connector stays None; _gateway_runner uses resolve_and_dispatch for execution.
        if capabilities is not None:
            caps = capabilities
        elif connector is not None:
            caps = get_connector_capabilities(connector)
        else:
            from db_mcp_data import gateway as _gateway_module
            caps = _gateway_module.capabilities(connection_path=connection_path)

        policy_error = protocol_ack_checker(
            connection=execution_connection,
            connection_path=connection_path,
        )
        if policy_error is not None:
            return policy_error

        policy_error, _, _ = execution_policy_evaluator(
            sql=query.sql,
            capabilities=caps,
            confirmed=confirmed,
            require_validate_first=False,
            query_id=query_id,
        )
        if policy_error is not None:
            return policy_error

        if query.estimated_rows and query.estimated_rows > ASYNC_ROW_THRESHOLD:
            started = await _gateway_module.start_query_execution(query_id)
            if not started:
                return {
                    "status": "error",
                    "error": "Failed to start query execution",
                    "query_id": query_id,
                }

            if execution_engine is None:
                execution_engine = get_execution_engine(connection_path)
            if spawn_background_execution is None:
                raise NotImplementedError("async background execution is not wired yet")

            request = ExecutionRequest(
                connection=execution_connection,
                sql=query.sql,
                query_id=query_id,
                idempotency_key=query_id,
            )
            handle = execution_engine.submit_async(request)
            spawn_background_execution(
                query_id=query_id,
                sql=query.sql,
                connection=execution_connection,
                execution_id=handle.execution_id,
            )
            return {
                "status": "submitted",
                "mode": "async",
                "query_id": query_id,
                "execution_id": handle.execution_id,
                "state": handle.state.value,
                "sql": query.sql,
                "estimated_rows": query.estimated_rows,
                "message": (
                    f"Query submitted for background execution. "
                    f"Estimated ~{query.estimated_rows:,} rows to scan. "
                    f"Use get_result('{query_id}', connection='{connection}') to check status."
                ),
                "poll_interval_seconds": 10,
                "guidance": {
                    "next_steps": [
                        f"Poll status with: get_result('{query_id}', connection='{connection}')",
                        "Check every 10-30 seconds until status is 'complete'",
                    ],
                },
            }

        await _gateway_module.mark_running(query_id)

        if execute_query is not None:
            # Backward-compat path: caller injected an execute_query callback.
            # Route through ExecutionEngine so execution_id / duration_ms / metadata
            # are preserved from the callback's response dict.
            if execution_engine is None:
                execution_engine = get_execution_engine(connection_path)

            request = ExecutionRequest(
                connection=execution_connection,
                sql=query.sql,
                query_id=query_id,
                idempotency_key=query_id,
            )

            def _validated_runner(runner_sql: str) -> dict[str, Any]:
                raw = execute_query(runner_sql, connection=execution_connection, query_id=query_id)
                return {
                    "data": raw.get("data", []),
                    "columns": raw.get("columns", []),
                    "rows_returned": raw.get("rows_returned", 0),
                    "rows_affected": raw.get("rows_affected"),
                    "metadata": {
                        "provider_id": raw.get("provider_id"),
                        "statement_type": raw.get("statement_type"),
                        "is_write": raw.get("is_write", False),
                    },
                }

            handle, exec_result = execution_engine.submit_sync(request, _validated_runner)
            if exec_result.state != ExecutionState.SUCCEEDED:
                err = exec_result.error.message if exec_result.error else "Execution failed"
                await _gateway_module.mark_error(query_id, error=err)
                return {
                    "status": "error",
                    "error": f"Execution failed: {err}",
                    "query_id": query_id,
                    "execution_id": handle.execution_id,
                    "state": exec_result.state.value,
                    "sql": query.sql,
                }

            result = {
                "data": exec_result.data,
                "columns": exec_result.columns,
                "rows_returned": exec_result.rows_returned,
                "duration_ms": exec_result.duration_ms,
                "provider_id": exec_result.metadata.get("provider_id"),
                "statement_type": exec_result.metadata.get("statement_type"),
                "is_write": exec_result.metadata.get("is_write", False),
                "rows_affected": exec_result.rows_affected,
            }
            await _gateway_module.mark_complete(
                query_id,
                result=result,
                rows_returned=result["rows_returned"],
            )
            _execution_id = handle.execution_id
            _state = exec_result.state.value

        else:
            # Primary path: dispatch through gateway.execute().
            # The gateway resolves the connector internally; run_sql owns only
            # the policy checks and lifecycle state transitions around it.
            from db_mcp_models.gateway import RunOptions
            _options = RunOptions(confirmed=confirmed) if confirmed else None
            response = await _gateway_module.execute(
                query_id,
                connection_path=connection_path,
                options=_options,
            )
            if not response.is_success:
                err = response.error or "Execution failed"
                await _gateway_module.mark_error(query_id, error=err)
                return {
                    "status": "error",
                    "error": f"Execution failed: {err}",
                    "query_id": query_id,
                    "execution_id": query_id,
                    "state": "failed",
                    "sql": query.sql,
                }

            result = {
                "data": response.data,
                "columns": [c.name for c in response.columns],
                "rows_returned": response.rows_returned,
                "duration_ms": None,
                "provider_id": None,
                "statement_type": None,
                "is_write": False,
                "rows_affected": None,
            }
            await _gateway_module.mark_complete(
                query_id,
                result=result,
                rows_returned=result["rows_returned"],
            )
            _execution_id = query_id
            _state = ExecutionState.SUCCEEDED.value

        rows_returned = result["rows_returned"]
        is_large = rows_returned > 100
        return {
            "status": "success",
            "query_id": query_id,
            "execution_id": _execution_id,
            "state": _state,
            "sql": query.sql,
            "data": result["data"],
            "columns": result["columns"],
            "rows_returned": rows_returned,
            "duration_ms": result["duration_ms"],
            "provider_id": result["provider_id"],
            "cost_tier": query.cost_tier,
            "statement_type": result.get("statement_type"),
            "is_write": result.get("is_write", False),
            "rows_affected": result.get("rows_affected"),
            "presentation_hints": {
                "downloadable": True,
                "suggested_filename": f"query_{query_id[:8]}_{datetime.now():%Y%m%d_%H%M%S}",
                "suggested_formats": ["csv", "xlsx"],
                "large_result": is_large,
                "display_recommendation": "export" if is_large else "table",
            },
            "guidance": {
                "summary": f"Query returned {rows_returned} rows.",
                "next_steps": (
                    ["Export results to CSV for the user"]
                    if is_large
                    else ["Present data in a table", "Summarize key insights"]
                ),
            },
        }

    raise NotImplementedError("run_sql service extraction is not complete yet")


async def validate_sql(
    sql: str,
    connection: str,
    connection_path: Path,
    *,
    connector: Any | None = None,
    capabilities: dict | None = None,
    validate_permissions: Any | None = None,
    write_policy_getter: Any | None = None,
    should_explain: Any | None = None,
    explain: Any | None = None,
) -> dict:
    """Validate SQL for a resolved connection path."""
    # Resolve capabilities via gateway when no overrides are injected.
    if capabilities is not None:
        caps = capabilities
    elif connector is not None:
        caps = get_connector_capabilities(connector)
    else:
        from db_mcp_data import gateway as _gateway_module
        caps = _gateway_module.capabilities(connection_path=connection_path)
    if validate_permissions is None:
        validate_permissions = validate_sql_permissions
    if write_policy_getter is None:
        write_policy_getter = get_write_policy
    if should_explain is None:
        should_explain = should_explain_statement
    if explain is None:
        explain = explain_sql
    if not caps.get("supports_validate_sql", True):
        return {
            "valid": False,
            "error": "Validation is not supported for this connector.",
            "sql": sql,
            "query_id": None,
            "guidance": {
                "next_steps": [
                    "Call run_sql(connection=..., sql=...) directly",
                    "Or use api_query for connector-specific endpoints",
                ]
            },
        }

    is_allowed, error, statement_type, is_write = validate_permissions(sql, capabilities=caps)
    if not is_allowed:
        return {
            "valid": False,
            "error": error,
            "sql": sql,
            "query_id": None,
            "statement_type": statement_type,
            "is_write": is_write,
        }

    _, _, require_write_confirmation = write_policy_getter(caps)
    write_confirmation_required = is_write and require_write_confirmation

    if is_write:
        _write_cost_tier = "confirm" if require_write_confirmation else "auto"
        from db_mcp_data import gateway as _gateway_module
        from db_mcp_models.gateway import DataRequest as _DR
        from db_mcp_models.gateway import SQLQuery as _SQ
        _vq = await _gateway_module.create(
            _DR(connection=connection, query=_SQ(sql=sql)),
            connection_path=connection_path,
            cost_tier=_write_cost_tier,
            explanation=[],
        )
        _qid = _vq.query_id
        return {
            "valid": True,
            "query_id": _qid,
            "sql": sql,
            "cost_tier": _write_cost_tier,
            "tier_reason": (
                "Write statement requires explicit execution confirmation."
                if require_write_confirmation
                else "Statement validated."
            ),
            "estimated_rows": None,
            "estimated_cost": None,
            "estimated_size_gb": None,
            "explanation": [],
            "statement_type": statement_type,
            "is_write": is_write,
            "write_confirmation_required": write_confirmation_required,
            "message": (
                f"Query validated successfully. "
                f"Use run_sql(query_id='{_qid}', connection='{connection}') to execute. "
                f"Query ID expires in 30 minutes."
            ),
            "guidance": {
                "next_steps": [
                    (
                        f"Execute with: run_sql(query_id='{_qid}', "
                        f"connection='{connection}', confirmed=true)"
                    )
                    if is_write and require_write_confirmation
                    else (
                        f"Execute with: run_sql(query_id='{_qid}', "
                        f"connection='{connection}')"
                    ),
                    (
                        "Write statements require explicit confirmation on this connection."
                        if is_write and require_write_confirmation
                        else "Review the cost_tier and estimated_rows before executing"
                    ),
                    "Double-check affected tables/filters before execution."
                    if is_write
                    else "If cost_tier is 'confirm' or 'reject', consider adding filters",
                ],
            },
        }

    if should_explain(statement_type, is_write=is_write):
        explain_result = explain(sql, connection_path=connection_path)
        if not explain_result.valid:
            return {
                "valid": False,
                "error": explain_result.error,
                "sql": sql,
                "query_id": None,
                "statement_type": statement_type,
                "is_write": is_write,
            }
    else:
        explain_result = ExplainResult(
            valid=True,
            explanation=[],
            estimated_rows=None,
            estimated_cost=None,
            estimated_size_gb=None,
            cost_tier=CostTier.CONFIRM
            if is_write and require_write_confirmation
            else CostTier.AUTO,
            tier_reason=(
                "Write statement requires explicit execution confirmation."
                if is_write and require_write_confirmation
                else (
                    f"{statement_type} statements are validated without EXPLAIN."
                    if statement_type in {"SHOW", "DESCRIBE", "DESC", "EXPLAIN"}
                    else "Statement validated."
                )
            ),
        )

    _expl = explain_result.explanation[:5] if explain_result.explanation else []
    _read_cost_tier = explain_result.cost_tier.value
    from db_mcp_data import gateway as _gateway_module
    from db_mcp_models.gateway import DataRequest as _DR
    from db_mcp_models.gateway import SQLQuery as _SQ
    _vq = await _gateway_module.create(
        _DR(connection=connection, query=_SQ(sql=sql)),
        connection_path=connection_path,
        cost_tier=_read_cost_tier,
        estimated_rows=explain_result.estimated_rows,
        estimated_cost=explain_result.estimated_cost,
        explanation=_expl,
    )
    _qid = _vq.query_id
    return {
        "valid": True,
        "query_id": _qid,
        "sql": sql,
        "cost_tier": _read_cost_tier,
        "tier_reason": explain_result.tier_reason,
        "estimated_rows": explain_result.estimated_rows,
        "estimated_cost": explain_result.estimated_cost,
        "estimated_size_gb": explain_result.estimated_size_gb,
        "explanation": _expl,
        "statement_type": statement_type,
        "is_write": is_write,
        "write_confirmation_required": write_confirmation_required,
        "message": (
            f"Query validated successfully. "
            f"Use run_sql(query_id='{_qid}', connection='{connection}') to execute. "
            f"Query ID expires in 30 minutes."
        ),
        "guidance": {
            "next_steps": [
                (
                    f"Execute with: run_sql(query_id='{_qid}', "
                    f"connection='{connection}', confirmed=true)"
                )
                if is_write and require_write_confirmation
                else (
                    f"Execute with: run_sql(query_id='{_qid}', "
                    f"connection='{connection}')"
                ),
                (
                    "Write statements require explicit confirmation on this connection."
                    if is_write and require_write_confirmation
                    else "Review the cost_tier and estimated_rows before executing"
                ),
                "Double-check affected tables/filters before execution."
                if is_write
                else "If cost_tier is 'confirm' or 'reject', consider adding filters",
            ],
        },
    }
