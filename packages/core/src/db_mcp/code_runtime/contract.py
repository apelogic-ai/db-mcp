"""Shared contract helpers for db-mcp code runtime surfaces."""

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
    """Render the native runtime instructions for an external host."""
    helper_lines = "\n".join(
        [
            "- `dbmcp.read_protocol()`",
            "- `dbmcp.connector()`",
            "- `dbmcp.schema_descriptions()`",
            "- `dbmcp.table_names()`",
            "- `dbmcp.describe_table(name)`",
            "- `dbmcp.find_table(query)`",
            "- `dbmcp.find_tables(query)`",
            "- `dbmcp.find_columns(query)`",
            "- `dbmcp.relevant_examples(query)`",
            "- `dbmcp.relevant_rules(query)`",
            "- `dbmcp.plan(question)`",
            "- `dbmcp.query(sql)`",
            "- `dbmcp.scalar(sql)`",
            "- `dbmcp.execute(sql)`",
            "- `dbmcp.finalize_answer(...)`",
        ]
    )
    return (
        "You are running in the db-mcp native code runtime.\n\n"
        f"Connection: `{connection}`\n"
        "Language: Python\n"
        "Helper object: `dbmcp`\n\n"
        "First step:\n"
        "```python\n"
        "print(dbmcp.read_protocol())\n"
        "```\n\n"
        "`dbmcp.read_protocol()` returns markdown text, not a structured schema object.\n"
        "For schema discovery, prefer `dbmcp.find_table(...)`, `dbmcp.find_tables(...)`, "
        "`dbmcp.describe_table(...)`, `dbmcp.find_columns(...)`, `dbmcp.relevant_examples(...)`, "
        "and `dbmcp.plan(...)` before writing SQL.\n"
        "After querying, prefer `dbmcp.finalize_answer(...)` to construct the final answer "
        "payload consistently.\n\n"
        "Available helpers:\n"
        f"{helper_lines}\n\n"
        "Use helper-first discovery before querying. If a statement may write, rerun with "
        "confirmation."
    )


def build_code_mode_contract(
    connection: str,
    *,
    session_id: str | None = None,
) -> dict[str, object]:
    """Return the native runtime contract as structured data."""
    contract: dict[str, object] = {
        "kind": "db-mcp-code-runtime",
        "connection": connection,
        "language": "python",
        "helper_object": "dbmcp",
        "helper_methods": HELPER_METHODS,
        "protocol_required": True,
        "write_confirmation_required": True,
        "instructions": build_code_mode_instructions(connection),
    }
    if session_id is not None:
        contract["session_id"] = session_id
    return contract
