from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastmcp.client import Client

from db_mcp.config import Settings, reset_settings
from db_mcp.registry import ConnectionRegistry
from db_mcp.server import _create_server


def _init_sqlite(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t(v) VALUES ('a'), ('b')")
        conn.commit()
    finally:
        conn.close()


def _write_connection(connections_dir: Path, name: str, db_path: Path) -> None:
    (connections_dir / name).mkdir(parents=True)
    (connections_dir / name / "connector.yaml").write_text(
        "\n".join(
            [
                "type: sql",
                f"database_url: sqlite:///{db_path}",
                "capabilities:",
                "  supports_validate_sql: true",
                "  supports_async_jobs: true",
            ]
        )
        + "\n"
    )


@pytest.fixture
def mcp_env(tmp_path, monkeypatch):
    # Build a realistic on-disk connection directory like production.
    connections_dir = tmp_path / "connections"
    db_path = tmp_path / "playground.sqlite"
    _init_sqlite(db_path)
    _write_connection(connections_dir, "playground", db_path)

    # Force settings to use our temp connections.
    monkeypatch.setenv("CONNECTIONS_DIR", str(connections_dir))
    monkeypatch.setenv("CONNECTION_PATH", str(connections_dir / "playground"))
    monkeypatch.setenv("DB_MCP_CONNECTION_PATH", str(connections_dir / "playground"))
    monkeypatch.setenv("CONNECTION_NAME", "playground")
    monkeypatch.setenv("DB_MCP_TOOL_MODE", "detailed")

    # Ensure singletons do not leak between tests.
    ConnectionRegistry.reset()
    reset_settings()

    # Validate registry wiring via Settings explicitly.
    settings = Settings(connections_dir=str(connections_dir), connection_name="playground")
    ConnectionRegistry.get_instance(settings)

    return {
        "tmp_path": tmp_path,
        "connections_dir": connections_dir,
        "db_path": db_path,
    }


async def _call(client: Client, name: str, args: dict) -> object:
    # FastMCP client returns CallToolResult-like wrappers; we only need to assert
    # it doesn't raise and yields a JSON-serializable structure.
    return (await client.call_tool(name, args)).data


@pytest.mark.asyncio
async def test_all_tools_exposed_and_happy_path_invoked(mcp_env):
    server = _create_server()

    async with Client(server) as client:
        exposed = await client.list_tools()
        exposed_names = [t.name for t in exposed]

        # Implemented tools = those registered onto the server instance.
        implemented_names = sorted((await server.get_tools()).keys())
        assert sorted(exposed_names) == implemented_names

        # Coverage harness: each exposed tool must be called exactly once.
        # If a new tool is added, this test must be updated with a new call.
        calls: dict[str, object] = {}

        # ------------------------------------------------------------------
        # Core
        # ------------------------------------------------------------------
        calls["ping"] = await _call(client, "ping", {})
        calls["get_config"] = await _call(client, "get_config", {})
        calls["list_connections"] = await _call(client, "list_connections", {})
        calls["protocol"] = await _call(client, "protocol", {})

        # insights: create a fake insight file via shell to have something to dismiss
        calls["mark_insights_processed"] = await _call(client, "mark_insights_processed", {})
        # dismiss_insight: use deterministic non-existent id.
        # Happy path currently returns "not_found".
        calls["dismiss_insight"] = await _call(client, "dismiss_insight", {"insight_id": "nope"})

        # Shell (reads/writes in connection dir)
        calls["shell"] = await _call(client, "shell", {"command": "ls"})

        # ------------------------------------------------------------------
        # SQL execution
        # ------------------------------------------------------------------
        calls["validate_sql"] = await _call(
            client, "validate_sql", {"sql": "SELECT COUNT(*) AS n FROM t"}
        )
        validate_res = calls["validate_sql"].get("structuredContent")
        assert isinstance(validate_res, dict) and validate_res.get("valid") is True
        query_id = validate_res.get("query_id")
        assert query_id, "validate_sql must return query_id"

        calls["run_sql"] = await _call(client, "run_sql", {"query_id": query_id})
        run_res = calls["run_sql"].get("structuredContent")
        assert isinstance(run_res, dict) and run_res.get("status") in {
            "success",
            "submitted",
            "complete",
        }

        calls["get_result"] = await _call(client, "get_result", {"query_id": query_id})
        calls["export_results"] = await _call(
            client,
            "export_results",
            {"sql": "SELECT COUNT(*) AS n FROM t", "format": "csv"},
        )

        # ------------------------------------------------------------------
        # Setup / onboarding
        # ------------------------------------------------------------------
        calls["mcp_setup_status"] = await _call(client, "mcp_setup_status", {})
        calls["mcp_setup_start"] = await _call(client, "mcp_setup_start", {})
        calls["mcp_setup_add_ignore_pattern"] = await _call(
            client, "mcp_setup_add_ignore_pattern", {"pattern": "tmp_*"}
        )
        calls["mcp_setup_remove_ignore_pattern"] = await _call(
            client, "mcp_setup_remove_ignore_pattern", {"pattern": "tmp_*"}
        )
        calls["mcp_setup_import_ignore_patterns"] = await _call(
            client,
            "mcp_setup_import_ignore_patterns",
            {"patterns": ["foo*", "bar*"]},
        )
        calls["mcp_setup_discover"] = await _call(client, "mcp_setup_discover", {})
        # mcp_setup_discover_status requires discovery_id; use a fake one to test the tool
        calls["mcp_setup_discover_status"] = await _call(
            client,
            "mcp_setup_discover_status",
            {"discovery_id": "fake-id"},
        )
        calls["mcp_setup_next"] = await _call(client, "mcp_setup_next", {})
        calls["mcp_setup_skip"] = await _call(client, "mcp_setup_skip", {})
        calls["mcp_setup_bulk_approve"] = await _call(client, "mcp_setup_bulk_approve", {})
        calls["mcp_setup_import_descriptions"] = await _call(
            client,
            "mcp_setup_import_descriptions",
            {"descriptions": "tables: {}\n"},
        )
        calls["mcp_setup_approve"] = await _call(
            client, "mcp_setup_approve", {"description": "Test description"}
        )
        calls["mcp_setup_reset"] = await _call(client, "mcp_setup_reset", {})

        # ------------------------------------------------------------------
        # Domain
        # ------------------------------------------------------------------
        calls["mcp_domain_status"] = await _call(client, "mcp_domain_status", {})
        calls["mcp_domain_generate"] = await _call(client, "mcp_domain_generate", {})
        calls["mcp_domain_skip"] = await _call(client, "mcp_domain_skip", {})
        calls["mcp_domain_approve"] = await _call(client, "mcp_domain_approve", {})

        # ------------------------------------------------------------------
        # Import
        # ------------------------------------------------------------------
        calls["import_instructions"] = await _call(
            client, "import_instructions", {"rules": ["Be nice", "Be accurate"]}
        )
        calls["import_examples"] = await _call(
            client,
            "import_examples",
            {
                "examples": [{"natural_language": "count rows", "sql": "select count(*) from t"}],
            },
        )

        # ------------------------------------------------------------------
        # Detailed-mode tools
        # ------------------------------------------------------------------
        calls["test_connection"] = await _call(client, "test_connection", {})
        db_path = mcp_env["db_path"]
        calls["detect_dialect"] = await _call(
            client, "detect_dialect", {"database_url": f"sqlite:///{db_path}"}
        )
        calls["list_catalogs"] = await _call(client, "list_catalogs", {})
        calls["list_schemas"] = await _call(client, "list_schemas", {"catalog": None})
        calls["list_tables"] = await _call(
            client, "list_tables", {"catalog": None, "schema": None}
        )
        calls["describe_table"] = await _call(
            client,
            "describe_table",
            {"catalog": None, "schema": None, "table_name": "t"},
        )
        calls["sample_table"] = await _call(
            client,
            "sample_table",
            {"catalog": None, "schema": None, "table_name": "t", "limit": 2},
        )
        calls["get_dialect_rules"] = await _call(
            client, "get_dialect_rules", {"dialect": "postgresql"}
        )
        calls["get_connection_dialect"] = await _call(client, "get_connection_dialect", {})

        calls["query_status"] = await _call(client, "query_status", {})
        calls["query_generate"] = await _call(
            client,
            "query_generate",
            {"natural_language": "count rows"},
        )
        calls["query_feedback"] = await _call(
            client,
            "query_feedback",
            {
                "natural_language": "count rows",
                "generated_sql": "select count(*) from t",
                "feedback_type": "correction",
                "corrected_sql": "select count(*) from t",
            },
        )
        calls["query_add_rule"] = await _call(
            client,
            "query_add_rule",
            {"rule": "Always use COUNT(*) for counts."},
        )
        calls["query_list_examples"] = await _call(client, "query_list_examples", {})
        calls["query_list_rules"] = await _call(client, "query_list_rules", {})
        calls["query_approve"] = await _call(
            client,
            "query_approve",
            {"natural_language": "count rows", "sql": "select count(*) from t"},
        )

        calls["get_knowledge_gaps"] = await _call(client, "get_knowledge_gaps", {})
        calls["dismiss_knowledge_gap"] = await _call(
            client, "dismiss_knowledge_gap", {"gap_id": "nope", "reason": "n/a"}
        )

        calls["metrics_discover"] = await _call(client, "metrics_discover", {})
        calls["metrics_list"] = await _call(client, "metrics_list", {})
        calls["metrics_add"] = await _call(
            client,
            "metrics_add",
            {"type": "dimension", "name": "x", "description": "Test dimension"},
        )
        calls["metrics_approve"] = await _call(
            client, "metrics_approve", {"type": "dimension", "name": "x"}
        )
        calls["metrics_remove"] = await _call(
            client, "metrics_remove", {"type": "dimension", "name": "x"}
        )

        calls["get_data"] = await _call(
            client, "get_data", {"intent": "show all rows from table t"}
        )
        calls["test_elicitation"] = await _call(client, "test_elicitation", {})
        calls["test_sampling"] = await _call(client, "test_sampling", {})

        # ------------------------------------------------------------------
        # Final coverage assertion
        # ------------------------------------------------------------------
        assert sorted(calls.keys()) == sorted(exposed_names)

        # Basic invariants: each call returns a dict-like JSON object.
        for name, result in calls.items():
            assert result is not None, f"{name} returned None"
