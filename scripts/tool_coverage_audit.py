#!/usr/bin/env python3
"""
Tool Coverage Audit Script for db-mcp MCP Server.

This script verifies that 100% of MCP tools implemented in the codebase
are exposed by the MCP server at runtime.

Usage:
    python scripts/tool_coverage_audit.py [--json] [--verbose]

Exit codes:
    0 - All tools are properly exposed (PASS)
    1 - Some tools are missing or extra (FAIL)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Path to the server.py file
SERVER_PY_PATH = (
    Path(__file__).parent.parent / "packages" / "core" / "src" / "db_mcp" / "server.py"
)
TOOLS_DIR = Path(__file__).parent.parent / "packages" / "core" / "src" / "db_mcp" / "tools"


def extract_tool_registrations_from_server() -> set[str]:
    """
    Extract all tool names registered via server.tool() calls in server.py.

    This parses the server.py file and finds all patterns like:
        server.tool(name="tool_name")(...)
    """
    if not SERVER_PY_PATH.exists():
        raise FileNotFoundError(f"Server file not found: {SERVER_PY_PATH}")

    content = SERVER_PY_PATH.read_text()

    # Pattern to match server.tool(name="...") or server.tool(name='...')
    pattern = r'server\.tool\(\s*name\s*=\s*["\']([^"\']+)["\']'

    matches = re.findall(pattern, content)

    return set(matches)


def extract_implemented_tools_from_codebase() -> dict[str, dict[str, Any]]:
    """
    Extract all tool implementations from the codebase.

    This looks at:
    1. All function definitions in tools/ directory that start with _
    2. The server.py file for tool registration patterns

    Returns a dict mapping tool name to info about its implementation.
    """
    tools: dict[str, dict[str, Any]] = {}

    # Parse all Python files in the tools directory
    for py_file in TOOLS_DIR.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        content = py_file.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name
                # Tool functions typically start with _
                if func_name.startswith("_") and not func_name.startswith("__"):
                    # Convert _tool_name to tool_name for comparison
                    tool_name = func_name[1:]  # Remove leading underscore

                    # Skip private helpers
                    if tool_name in (
                        "get_auth_provider",
                        "strip_validate_sql",
                        "build_connection_instructions",
                        "create_server",
                        "configure_logging",
                        "configure_observability",
                        "server_lifespan",
                    ):
                        continue

                    tools[tool_name] = {
                        "source_file": f"tools/{py_file.name}",
                        "function": func_name,
                        "line": node.lineno,
                    }

    return tools


def get_expected_tools_for_config(
    supports_sql: bool = True,
    supports_validate: bool = True,
    supports_async_jobs: bool = True,
    has_api: bool = False,
    has_api_sql: bool = False,
    is_shell_mode: bool = False,
) -> set[str]:
    """
    Calculate the expected set of tools based on configuration.

    This mirrors the logic in server.py _create_server() function.
    """
    tools: set[str] = set()

    # Core tools - always available
    tools.update(
        [
            "dismiss_insight",
            "mark_insights_processed",
            "mcp_list_improvements",
            "mcp_suggest_improvement",
            "mcp_approve_improvement",
            "ping",
            "get_config",
            "list_connections",
            "search_tools",
            "export_tool_sdk",
            "shell",
            "protocol",
        ]
    )

    # SQL execution tools
    if supports_sql:
        if supports_validate:
            tools.add("validate_sql")
        tools.add("run_sql")
        if supports_async_jobs:
            tools.add("get_result")
        tools.add("export_results")

    # API connector tools
    if has_api:
        tools.update(
            [
                "api_discover",
                "api_query",
                "api_mutate",
                "api_describe_endpoint",
            ]
        )
        if has_api_sql:
            tools.add("api_execute_sql")

    # Admin/Setup tools - always available
    tools.update(
        [
            "mcp_setup_status",
            "mcp_setup_start",
            "mcp_setup_add_ignore_pattern",
            "mcp_setup_remove_ignore_pattern",
            "mcp_setup_import_ignore_patterns",
            "mcp_setup_discover",
            "mcp_setup_discover_status",
            "mcp_setup_reset",
            "mcp_setup_next",
            "mcp_setup_approve",
            "mcp_setup_skip",
            "mcp_setup_bulk_approve",
            "mcp_setup_import_descriptions",
            "mcp_domain_status",
            "mcp_domain_generate",
            "mcp_domain_approve",
            "mcp_domain_skip",
            "import_instructions",
            "import_examples",
        ]
    )

    # Detailed mode ONLY - schema discovery and query helper tools
    if not is_shell_mode and (supports_sql or has_api):
        tools.update(
            [
                "test_connection",
                "detect_dialect",
                "list_catalogs",
                "list_schemas",
                "list_tables",
                "describe_table",
                "sample_table",
                "get_dialect_rules",
                "get_connection_dialect",
                "query_status",
                "query_generate",
                "query_approve",
                "query_feedback",
                "query_add_rule",
                "query_list_examples",
                "query_list_rules",
                "get_knowledge_gaps",
                "dismiss_knowledge_gap",
                "metrics_discover",
                "metrics_list",
                "metrics_approve",
                "metrics_add",
                "metrics_remove",
                "get_data",
                "test_elicitation",
                "test_sampling",
            ]
        )

    return tools


def _write_connector_yaml(
    connections_dir: Path,
    name: str,
    connection_type: str,
    capabilities: dict[str, Any],
) -> None:
    """Create a minimal connector.yaml for capability-based tool registration."""
    connection_path = connections_dir / name
    connection_path.mkdir(parents=True, exist_ok=True)

    lines = [f"type: {connection_type}", "capabilities:"]
    for key, value in capabilities.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = value
        lines.append(f"  {key}: {rendered}")
    (connection_path / "connector.yaml").write_text("\n".join(lines) + "\n")


@contextmanager
def _temp_server_env(config: str):
    """Set up a temporary connection config environment for server creation."""
    with tempfile.TemporaryDirectory(prefix="db-mcp-tool-audit-") as tmpdir:
        root = Path(tmpdir)
        connections_dir = root / "connections"
        connection_name = "audit"

        config_map: dict[str, tuple[str, dict[str, Any], str]] = {
            "sql": (
                "sql",
                {
                    "supports_sql": True,
                    "supports_validate_sql": True,
                    "supports_async_jobs": True,
                },
                "detailed",
            ),
            "api": (
                "api",
                {
                    "supports_sql": False,
                    "supports_validate_sql": False,
                    "supports_async_jobs": False,
                },
                "detailed",
            ),
            "metabase": (
                "metabase",
                {
                    "supports_sql": True,
                    "supports_validate_sql": False,
                    "supports_async_jobs": False,
                },
                "detailed",
            ),
            "file": (
                "file",
                {
                    "supports_sql": True,
                    "supports_validate_sql": True,
                    "supports_async_jobs": True,
                },
                "detailed",
            ),
            "shell": (
                "sql",
                {
                    "supports_sql": True,
                    "supports_validate_sql": True,
                    "supports_async_jobs": True,
                },
                "shell",
            ),
        }

        connection_type, capabilities, tool_mode = config_map[config]
        _write_connector_yaml(connections_dir, connection_name, connection_type, capabilities)

        env_overrides = {
            "CONNECTIONS_DIR": str(connections_dir),
            "CONNECTION_NAME": connection_name,
            "CONNECTION_PATH": str(connections_dir / connection_name),
            "DB_MCP_CONNECTION_PATH": str(connections_dir / connection_name),
            "DB_MCP_TOOL_MODE": tool_mode,
        }
        original = {k: os.environ.get(k) for k in env_overrides}
        os.environ.update(env_overrides)
        try:
            yield
        finally:
            for key, old_value in original.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value


def discover_runtime_tools(config: str) -> set[str]:
    """
    Discover tools exposed by a running MCP server.

    This uses the MCP protocol's tools/list method to get the actual
    tools exposed at runtime.

    For stdio transport, we would need to spawn the server and communicate
    via JSON-RPC. For simplicity, this function uses the FastMCP internals
    to get the registered tools directly.
    """
    # Import the server module and get the tool manager
    import sys

    # Add the src directory to the path
    src_path = str(Path(__file__).parent.parent / "packages" / "core" / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    try:
        with _temp_server_env(config):
            from db_mcp.config import reset_settings
            from db_mcp.registry import ConnectionRegistry
            from db_mcp.server import _create_server

            reset_settings()
            ConnectionRegistry.reset()

            server = _create_server()
            tools = server._tool_manager._tools
            return set(tools.keys())
    except Exception as e:
        print(f"Warning: Could not discover runtime tools: {e}", file=sys.stderr)
        return set()


def generate_report(
    declared_tools: set[str],
    runtime_tools: set[str],
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Generate a coverage report comparing declared vs runtime tools.
    """
    missing_tools = declared_tools - runtime_tools
    extra_tools = runtime_tools - declared_tools
    matched_tools = declared_tools & runtime_tools

    # Calculate coverage percentage safely
    coverage = round(len(matched_tools) / len(declared_tools) * 100, 2) if declared_tools else 0

    report = {
        "summary": {
            "total_declared": len(declared_tools),
            "total_runtime": len(runtime_tools),
            "matched": len(matched_tools),
            "missing": len(missing_tools),
            "extra": len(extra_tools),
            "coverage_percent": coverage,
            "status": "PASS" if not missing_tools and not extra_tools else "FAIL",
        },
        "declared_tools": sorted(declared_tools),
        "runtime_tools": sorted(runtime_tools),
        "missing_tools": sorted(missing_tools),
        "extra_tools": sorted(extra_tools),
        "matched_tools": sorted(matched_tools),
    }

    return report


def print_report(report: dict[str, Any], verbose: bool = False, json_output: bool = False):
    """Print the coverage report in human-readable or JSON format."""

    if json_output:
        print(json.dumps(report, indent=2))
        return

    summary = report["summary"]

    print("=" * 70)
    print("MCP TOOL COVERAGE AUDIT REPORT")
    print("=" * 70)
    print()

    # Summary section
    print("SUMMARY")
    print("-" * 40)
    print(f"  Total Declared:  {summary['total_declared']}")
    print(f"  Total Runtime:   {summary['total_runtime']}")
    print(f"  Matched:         {summary['matched']}")
    print(f"  Missing:         {summary['missing']}")
    print(f"  Extra:           {summary['extra']}")
    print(f"  Coverage:        {summary['coverage_percent']}%")
    print()

    # Status
    status = summary["status"]
    status_icon = "✓" if status == "PASS" else "✗"
    print(f"STATUS: {status_icon} {status}")
    print()

    if verbose or report["missing_tools"]:
        print("MISSING TOOLS (declared but not exposed at runtime)")
        print("-" * 40)
        if report["missing_tools"]:
            for tool in report["missing_tools"]:
                print(f"  - {tool}")
        else:
            print("  (none)")
        print()

    if verbose or report["extra_tools"]:
        print("EXTRA TOOLS (exposed at runtime but not declared)")
        print("-" * 40)
        if report["extra_tools"]:
            for tool in report["extra_tools"]:
                print(f"  - {tool}")
        else:
            print("  (none)")
        print()

    if verbose:
        print("ALL DECLARED TOOLS")
        print("-" * 40)
        for tool in report["declared_tools"]:
            print(f"  - {tool}")
        print()

        print("ALL RUNTIME TOOLS")
        print("-" * 40)
        for tool in report["runtime_tools"]:
            print(f"  - {tool}")
        print()

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Audit MCP tool coverage - verify all implemented tools are exposed at runtime"
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output including all tools",
    )
    parser.add_argument(
        "--config",
        choices=["sql", "api", "metabase", "file", "shell"],
        default="sql",
        help="Configuration mode to test (default: sql)",
    )

    args = parser.parse_args()

    # Extract declared tools from server.py
    declared_tools = extract_tool_registrations_from_server()

    if args.verbose:
        print(
            f"Found {len(declared_tools)} tool registrations in server.py",
            file=sys.stderr,
        )

    # Get expected tools for the specified configuration
    config_map = {
        "sql": {
            "supports_sql": True,
            "supports_validate": True,
            "supports_async_jobs": True,
            "has_api": False,
            "has_api_sql": False,
            "is_shell_mode": False,
        },
        "api": {
            "supports_sql": False,
            "supports_validate": False,
            "supports_async_jobs": False,
            "has_api": True,
            "has_api_sql": False,
            "is_shell_mode": False,
        },
        "metabase": {
            "supports_sql": True,
            "supports_validate": False,
            "supports_async_jobs": False,
            "has_api": False,
            "has_api_sql": False,
            "is_shell_mode": False,
        },
        "file": {
            "supports_sql": True,
            "supports_validate": True,
            "supports_async_jobs": True,
            "has_api": False,
            "has_api_sql": False,
            "is_shell_mode": False,
        },
        "shell": {
            "supports_sql": True,
            "supports_validate": True,
            "supports_async_jobs": True,
            "has_api": False,
            "has_api_sql": False,
            "is_shell_mode": True,
        },
    }

    expected_tools = get_expected_tools_for_config(**config_map[args.config])

    # Discover runtime tools
    runtime_tools = discover_runtime_tools(args.config)

    if args.verbose:
        print(
            f"Discovered {len(runtime_tools)} tools at runtime",
            file=sys.stderr,
        )

    # Generate report
    report = generate_report(
        declared_tools=expected_tools,
        runtime_tools=runtime_tools,
        verbose=args.verbose,
    )

    # Add configuration info
    report["config"] = {
        "mode": args.config,
        "supports_sql": config_map[args.config]["supports_sql"],
        "supports_validate": config_map[args.config]["supports_validate"],
        "supports_async_jobs": config_map[args.config]["supports_async_jobs"],
        "has_api": config_map[args.config]["has_api"],
        "has_api_sql": config_map[args.config]["has_api_sql"],
        "is_shell_mode": config_map[args.config]["is_shell_mode"],
    }

    # Print report
    print_report(report, verbose=args.verbose, json_output=args.json)

    # Exit with appropriate code
    sys.exit(0 if report["summary"]["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
