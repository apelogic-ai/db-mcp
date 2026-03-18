"""Shared contract helpers for the native db-mcp code runtime surface."""

from __future__ import annotations

HELPER_METHODS = [
    "read_protocol",
    "ack_protocol",
    "protocol_text",
    "connector",
    "schema_descriptions",
    "table_names",
    "describe_table",
    "find_table",
    "find_tables",
    "find_columns",
    "relevant_examples",
    "relevant_rules",
    "plan",
    "domain_model",
    "sql_rules",
    "query",
    "scalar",
    "execute",
    "finalize_answer",
]
def build_code_mode_instructions(connection: str) -> str:
    """Render native runtime instructions for an external host."""
    from db_mcp.code_runtime.interface import (
        RUNTIME_INTERFACE_NATIVE,
        build_runtime_instructions,
    )

    return build_runtime_instructions(connection, interface=RUNTIME_INTERFACE_NATIVE)


def build_code_mode_contract(
    connection: str,
    *,
    session_id: str | None = None,
) -> dict[str, object]:
    """Return the native runtime contract as structured data."""
    from db_mcp.code_runtime.interface import (
        RUNTIME_INTERFACE_NATIVE,
        build_runtime_contract,
    )

    return build_runtime_contract(
        connection,
        interface=RUNTIME_INTERFACE_NATIVE,
        session_id=session_id,
    )
