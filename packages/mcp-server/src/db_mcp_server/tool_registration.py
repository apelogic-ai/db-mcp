"""Tool registration functions for the MCP server.

Extracted from ``_create_server()`` in ``server.py``. Each function
registers a group of tools onto a FastMCP instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_shell_tools(
    mcp: FastMCP,
    *,
    is_shell_mode: bool,
) -> None:
    """Register shell and protocol tools."""
    from db_mcp.tools.shell import (
        SHELL_DESCRIPTION_DETAILED,
        SHELL_DESCRIPTION_SHELL_MODE,
        _protocol,
        _shell,
    )

    shell_description = (
        SHELL_DESCRIPTION_SHELL_MODE if is_shell_mode else SHELL_DESCRIPTION_DETAILED
    )
    mcp.tool(name="shell", description=shell_description)(_shell)
    mcp.tool(name="protocol")(_protocol)


def register_query_tools(
    mcp: FastMCP,
    *,
    supports_sql: bool,
    supports_validate: bool,
    supports_async_jobs: bool,
) -> None:
    """Register SQL query execution tools."""
    if not supports_sql:
        return

    from db_mcp.tools.intent import _answer_intent

    from db_mcp_server.tools.generation import (
        _export_results,
        _get_result,
        _run_sql,
        _validate_sql,
    )

    mcp.tool(name="answer_intent")(_answer_intent)
    if supports_validate:
        mcp.tool(name="validate_sql")(_validate_sql)
    mcp.tool(name="run_sql")(_run_sql)
    if supports_async_jobs:
        mcp.tool(name="get_result")(_get_result)
    mcp.tool(name="export_results")(_export_results)


def register_api_tools(
    mcp: FastMCP,
    *,
    has_api: bool,
    has_api_sql: bool,
    is_full_profile: bool,
) -> None:
    """Register API connector tools."""
    if not has_api:
        return

    from db_mcp.tools.api import (
        _api_describe_endpoint,
        _api_discover,
        _api_execute_sql,
        _api_mutate,
        _api_query,
    )

    mcp.tool(name="api_query")(_api_query)
    mcp.tool(name="api_describe_endpoint")(_api_describe_endpoint)
    if has_api_sql:
        mcp.tool(name="api_execute_sql")(_api_execute_sql)
    if is_full_profile:
        mcp.tool(name="api_discover")(_api_discover)
        mcp.tool(name="api_mutate")(_api_mutate)


def register_vault_tools(mcp: FastMCP, *, is_full_profile: bool) -> None:
    """Register vault artifact tools."""
    if not is_full_profile:
        return

    from db_mcp_server.tools.vault import _save_artifact, _vault_append, _vault_write

    mcp.tool(name="save_artifact")(_save_artifact)
    mcp.tool(name="vault_write")(_vault_write)
    mcp.tool(name="vault_append")(_vault_append)


def register_database_tools(
    mcp: FastMCP,
    *,
    is_full_profile: bool,
    is_shell_mode: bool,
    has_sql: bool,
    has_api: bool,
) -> None:
    """Register database introspection and training tools."""
    if not (is_full_profile and not is_shell_mode and (has_sql or has_api)):
        return

    from db_mcp.tools.gaps import _dismiss_knowledge_gap, _get_knowledge_gaps
    from db_mcp.tools.training import (
        _query_add_rule,
        _query_approve,
        _query_feedback,
        _query_generate,
        _query_list_examples,
        _query_list_rules,
        _query_status,
    )

    from db_mcp_server.tools.database import (
        _describe_table,
        _list_catalogs,
        _list_schemas,
        _list_tables,
        _sample_table,
        _test_connection,
    )

    # Database introspection tools
    mcp.tool(name="test_connection")(_test_connection)
    mcp.tool(name="list_catalogs")(_list_catalogs)
    mcp.tool(name="list_schemas")(_list_schemas)
    mcp.tool(name="list_tables")(_list_tables)
    mcp.tool(name="describe_table")(_describe_table)
    mcp.tool(name="sample_table")(_sample_table)

    # Query training tools
    mcp.tool(name="query_status")(_query_status)
    mcp.tool(name="query_generate")(_query_generate)
    mcp.tool(name="query_approve")(_query_approve)
    mcp.tool(name="query_feedback")(_query_feedback)
    mcp.tool(name="query_add_rule")(_query_add_rule)
    mcp.tool(name="query_list_examples")(_query_list_examples)
    mcp.tool(name="query_list_rules")(_query_list_rules)

    # Knowledge gaps tools
    mcp.tool(name="get_knowledge_gaps")(_get_knowledge_gaps)
    mcp.tool(name="dismiss_knowledge_gap")(_dismiss_knowledge_gap)


def register_metrics_tools(
    mcp: FastMCP,
    *,
    is_full_profile: bool,
    is_shell_mode: bool,
    has_sql: bool,
    has_api: bool,
) -> None:
    """Register metrics and dimensions tools."""
    if not (is_full_profile and not is_shell_mode and (has_sql or has_api)):
        return

    from db_mcp_server.tools.generation import _get_data
    from db_mcp_server.tools.metrics import (
        _metrics_add,
        _metrics_approve,
        _metrics_bindings_list,
        _metrics_bindings_set,
        _metrics_bindings_validate,
        _metrics_discover,
        _metrics_list,
        _metrics_remove,
    )

    mcp.tool(name="metrics_discover")(_metrics_discover)
    mcp.tool(name="metrics_list")(_metrics_list)
    mcp.tool(name="metrics_approve")(_metrics_approve)
    mcp.tool(name="metrics_add")(_metrics_add)
    mcp.tool(name="metrics_remove")(_metrics_remove)
    mcp.tool(name="metrics_bindings_list")(_metrics_bindings_list)
    mcp.tool(name="metrics_bindings_validate")(_metrics_bindings_validate)
    mcp.tool(name="metrics_bindings_set")(_metrics_bindings_set)

    # Advanced generation tools
    mcp.tool(name="get_data")(_get_data)
