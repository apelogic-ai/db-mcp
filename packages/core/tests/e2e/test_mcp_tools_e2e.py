from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from db_mcp_server.server import create_mcp_server
from fastmcp.client import Client

from db_mcp.config import Settings, reset_settings
from db_mcp.registry import ConnectionRegistry


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
    server = create_mcp_server()

    async with Client(server) as client:
        exposed = await client.list_tools()
        exposed_names = [t.name for t in exposed]

        # Implemented tools = those registered onto the server instance.
        implemented_names = sorted((await server.get_tools()).keys())
        assert sorted(exposed_names) == implemented_names

        # Coverage harness: each exposed tool must be called exactly once.
        # If a new tool is added, this test must be updated with a new call.
        calls: dict[str, object] = {}
        connection = "playground"

        # ------------------------------------------------------------------
        # Core
        # ------------------------------------------------------------------
        calls["ping"] = await _call(client, "ping", {})
        calls["get_config"] = await _call(client, "get_config", {})
        calls["list_connections"] = await _call(client, "list_connections", {})
        calls["search_tools"] = await _call(client, "search_tools", {"query": "sql", "limit": 5})
        calls["export_tool_sdk"] = await _call(
            client,
            "export_tool_sdk",
            {"language": "python", "query": "sql", "limit": 5},
        )
        calls["protocol"] = await _call(client, "protocol", {"connection": connection})

        # insights: create a fake insight file via shell to have something to dismiss
        calls["mark_insights_processed"] = await _call(
            client, "mark_insights_processed", {"connection": connection}
        )
        calls["save_artifact"] = await _call(
            client,
            "save_artifact",
            {
                "connection": connection,
                "artifact_type": "domain_model",
                "content": "# Domain Model\n",
            },
        )
        # dismiss_insight: use deterministic non-existent id.
        # Happy path currently returns "not_found".
        calls["dismiss_insight"] = await _call(
            client, "dismiss_insight", {"insight_id": "nope", "connection": connection}
        )

        # Shell (reads/writes in connection dir)
        calls["shell"] = await _call(client, "shell", {"command": "ls", "connection": connection})

        # ------------------------------------------------------------------
        # SQL execution
        # ------------------------------------------------------------------
        calls["validate_sql"] = await _call(
            client,
            "validate_sql",
            {"sql": "SELECT COUNT(*) AS n FROM t", "connection": connection},
        )
        validate_res = calls["validate_sql"].get("structuredContent")
        assert isinstance(validate_res, dict) and validate_res.get("valid") is True
        query_id = validate_res.get("query_id")
        assert query_id, "validate_sql must return query_id"

        calls["run_sql"] = await _call(
            client, "run_sql", {"query_id": query_id, "connection": connection}
        )
        run_res = calls["run_sql"].get("structuredContent")
        assert isinstance(run_res, dict) and run_res.get("status") in {
            "success",
            "submitted",
            "complete",
        }

        calls["get_result"] = await _call(
            client, "get_result", {"query_id": query_id, "connection": connection}
        )
        calls["export_results"] = await _call(
            client,
            "export_results",
            {"sql": "SELECT COUNT(*) AS n FROM t", "format": "csv", "connection": connection},
        )

        # ------------------------------------------------------------------
        # Detailed-mode tools
        # ------------------------------------------------------------------
        calls["test_connection"] = await _call(
            client, "test_connection", {"connection": connection}
        )
        calls["list_catalogs"] = await _call(client, "list_catalogs", {"connection": connection})
        calls["list_schemas"] = await _call(
            client, "list_schemas", {"catalog": None, "connection": connection}
        )
        calls["list_tables"] = await _call(
            client, "list_tables", {"catalog": None, "schema": None, "connection": connection}
        )
        calls["describe_table"] = await _call(
            client,
            "describe_table",
            {"catalog": None, "schema": None, "table_name": "t", "connection": connection},
        )
        calls["sample_table"] = await _call(
            client,
            "sample_table",
            {
                "catalog": None,
                "schema": None,
                "table_name": "t",
                "limit": 2,
                "connection": connection,
            },
        )

        calls["query_status"] = await _call(client, "query_status", {"connection": connection})
        calls["query_generate"] = await _call(
            client,
            "query_generate",
            {"natural_language": "count rows", "connection": connection},
        )
        calls["query_feedback"] = await _call(
            client,
            "query_feedback",
            {
                "natural_language": "count rows",
                "generated_sql": "select count(*) from t",
                "feedback_type": "correction",
                "corrected_sql": "select count(*) from t",
                "connection": connection,
            },
        )
        calls["query_add_rule"] = await _call(
            client,
            "query_add_rule",
            {"rule": "Always use COUNT(*) for counts.", "connection": connection},
        )
        calls["query_list_examples"] = await _call(
            client, "query_list_examples", {"connection": connection}
        )
        calls["query_list_rules"] = await _call(
            client, "query_list_rules", {"connection": connection}
        )
        calls["query_approve"] = await _call(
            client,
            "query_approve",
            {
                "natural_language": "count rows",
                "sql": "select count(*) from t",
                "connection": connection,
            },
        )

        calls["get_knowledge_gaps"] = await _call(
            client, "get_knowledge_gaps", {"connection": connection}
        )
        calls["dismiss_knowledge_gap"] = await _call(
            client,
            "dismiss_knowledge_gap",
            {"gap_id": "nope", "reason": "n/a", "connection": connection},
        )

        calls["metrics_discover"] = await _call(
            client, "metrics_discover", {"connection": connection}
        )
        calls["metrics_list"] = await _call(client, "metrics_list", {"connection": connection})
        calls["metrics_add"] = await _call(
            client,
            "metrics_add",
            {
                "type": "metric",
                "name": "revenue",
                "description": "Test revenue metric",
                "sql": "SELECT COUNT(*) AS revenue FROM t",
                "connection": connection,
            },
        )
        calls["metrics_approve"] = await _call(
            client, "metrics_approve", {"type": "dimension", "name": "x", "connection": connection}
        )
        calls["metrics_remove"] = await _call(
            client, "metrics_remove", {"type": "dimension", "name": "x", "connection": connection}
        )
        calls["metrics_bindings_list"] = await _call(
            client, "metrics_bindings_list", {"connection": connection}
        )
        calls["metrics_bindings_validate"] = await _call(
            client,
            "metrics_bindings_validate",
            {
                "connection": connection,
                "metric_name": "revenue",
                "sql": "SELECT COUNT(*) AS revenue FROM t",
            },
        )
        calls["metrics_bindings_set"] = await _call(
            client,
            "metrics_bindings_set",
            {
                "connection": connection,
                "metric_name": "revenue",
                "sql": "SELECT COUNT(*) AS revenue FROM t",
                "tables": ["t"],
            },
        )

        calls["vault_write"] = await _call(
            client,
            "vault_write",
            {"connection": connection, "path": "domain/model.md", "content": "# Domain\n"},
        )
        calls["vault_append"] = await _call(
            client,
            "vault_append",
            {"connection": connection, "path": "learnings/patterns.md", "content": "# Patterns\n"},
        )

        calls["get_data"] = await _call(
            client, "get_data", {"intent": "show all rows from table t", "connection": connection}
        )
        calls["answer_intent"] = await _call(
            client, "answer_intent", {"intent": "show revenue", "connection": connection}
        )

        # ------------------------------------------------------------------
        # Final coverage assertion
        # ------------------------------------------------------------------
        assert sorted(calls.keys()) == sorted(exposed_names)

        # Basic invariants: each call returns a dict-like JSON object.
        for name, result in calls.items():
            assert result is not None, f"{name} returned None"
