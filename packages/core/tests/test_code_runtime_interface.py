from __future__ import annotations

from db_mcp.code_runtime.interface import (
    RUNTIME_INTERFACE_CLI,
    RUNTIME_INTERFACE_MCP,
    RUNTIME_INTERFACE_NATIVE,
    build_runtime_contract,
    build_runtime_instructions,
)


def test_native_runtime_contract_exposes_host_boundary() -> None:
    contract = build_runtime_contract(
        "playground",
        interface=RUNTIME_INTERFACE_NATIVE,
        session_id="native-session-1",
    )

    assert contract["interface"] == RUNTIME_INTERFACE_NATIVE
    assert contract["boundary"] == "native_runtime_host"
    assert contract["helper_object"] == "dbmcp"
    assert contract["session_id"] == "native-session-1"
    assert "read_protocol" in contract["helper_methods"]


def test_mcp_runtime_contract_exposes_code_tool_surface() -> None:
    contract = build_runtime_contract("playground", interface=RUNTIME_INTERFACE_MCP)

    assert contract["interface"] == RUNTIME_INTERFACE_MCP
    assert contract["boundary"] == "mcp_tool"
    assert contract["tool_name"] == "code"
    assert contract["tool_mode"] == "code"
    assert "--mode code" in str(contract["start_command"])


def test_cli_runtime_contract_exposes_cli_surface() -> None:
    contract = build_runtime_contract("playground", interface=RUNTIME_INTERFACE_CLI)

    assert contract["interface"] == RUNTIME_INTERFACE_CLI
    assert contract["boundary"] == "cli"
    commands = contract["commands"]
    assert "db-mcp runtime prompt" in str(commands["prompt"])
    assert "db-mcp runtime run" in str(commands["run"])
    assert "db-mcp runtime exec" in str(commands["exec"])


def test_runtime_instructions_change_by_interface() -> None:
    native = build_runtime_instructions("playground", interface=RUNTIME_INTERFACE_NATIVE)
    mcp = build_runtime_instructions("playground", interface=RUNTIME_INTERFACE_MCP)
    cli = build_runtime_instructions("playground", interface=RUNTIME_INTERFACE_CLI)

    assert "Helper object: `dbmcp`" in native
    assert '`code(connection="...", code="...", timeout_seconds=30, confirmed=False)`' in mcp
    assert "db-mcp runtime run --connection playground" in cli
