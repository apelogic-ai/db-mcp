"""First-class interface contracts for db-mcp code runtime surfaces."""

from __future__ import annotations

from typing import Literal

from db_mcp.code_runtime.contract import HELPER_METHODS

RUNTIME_INTERFACE_NATIVE = "native"
RUNTIME_INTERFACE_MCP = "mcp"
RUNTIME_INTERFACE_CLI = "cli"
RuntimeInterface = Literal["native", "mcp", "cli"]


def _native_instructions(connection: str) -> str:
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


def _mcp_instructions(connection: str) -> str:
    return (
        "You are using db-mcp through MCP code mode.\n\n"
        f"Connection: `{connection}`\n"
        "Boundary: MCP tool\n"
        "Tool: `code(connection=\"...\", code=\"...\", timeout_seconds=30, confirmed=False)`\n\n"
        "Start the MCP server with:\n"
        "```bash\n"
        f"db-mcp start -c {connection} --mode code\n"
        "```\n\n"
        "First step in the tool:\n"
        "```python\n"
        "print(dbmcp.read_protocol())\n"
        "```\n"
    )


def _cli_instructions(connection: str) -> str:
    return (
        "You are using db-mcp through the CLI runtime surface.\n\n"
        f"Connection: `{connection}`\n"
        "Boundary: CLI\n\n"
        "Useful commands:\n"
        "```bash\n"
        f"db-mcp runtime prompt --connection {connection}\n"
        f"db-mcp runtime run --connection {connection} --code 'print(dbmcp.read_protocol())'\n"
        "db-mcp runtime serve --host 127.0.0.1 --port 8091\n"
        "db-mcp runtime exec --server-url http://127.0.0.1:8091 --connection "
        f"{connection} --session-id demo --code 'print(dbmcp.scalar(\"SELECT 1\"))'\n"
        "```\n"
    )


def build_runtime_instructions(connection: str, *, interface: RuntimeInterface) -> str:
    """Build instructions for one explicit runtime interface."""
    if interface == RUNTIME_INTERFACE_NATIVE:
        return _native_instructions(connection)
    if interface == RUNTIME_INTERFACE_MCP:
        return _mcp_instructions(connection)
    if interface == RUNTIME_INTERFACE_CLI:
        return _cli_instructions(connection)
    raise ValueError(f"unknown runtime interface: {interface}")


def build_runtime_contract(
    connection: str,
    *,
    interface: RuntimeInterface,
    session_id: str | None = None,
) -> dict[str, object]:
    """Build a first-class runtime contract for one interface boundary."""
    base: dict[str, object] = {
        "kind": "db-mcp-code-runtime",
        "interface": interface,
        "connection": connection,
        "instructions": build_runtime_instructions(connection, interface=interface),
    }
    if session_id is not None:
        base["session_id"] = session_id

    if interface == RUNTIME_INTERFACE_NATIVE:
        base.update(
            {
                "boundary": "native_runtime_host",
                "language": "python",
                "helper_object": "dbmcp",
                "helper_methods": HELPER_METHODS,
                "protocol_required": True,
                "write_confirmation_required": True,
            }
        )
        return base

    if interface == RUNTIME_INTERFACE_MCP:
        base.update(
            {
                "boundary": "mcp_tool",
                "tool_mode": "code",
                "tool_name": "code",
                "tool_signature": {
                    "connection": "str",
                    "code": "str",
                    "timeout_seconds": "int",
                    "confirmed": "bool",
                },
                "start_command": f"db-mcp start -c {connection} --mode code",
            }
        )
        return base

    if interface == RUNTIME_INTERFACE_CLI:
        base.update(
            {
                "boundary": "cli",
                "commands": {
                    "prompt": f"db-mcp runtime prompt --connection {connection}",
                    "run": f"db-mcp runtime run --connection {connection} --code '<python>'",
                    "serve": "db-mcp runtime serve --host 127.0.0.1 --port 8091",
                    "exec": (
                        "db-mcp runtime exec --server-url http://127.0.0.1:8091 "
                        f"--connection {connection} --session-id demo --code '<python>'"
                    ),
                },
            }
        )
        return base

    raise ValueError(f"unknown runtime interface: {interface}")
