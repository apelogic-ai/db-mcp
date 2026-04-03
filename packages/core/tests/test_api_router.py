"""Tests for the REST API router (Phase 4.09).

These tests verify that the REST dispatch endpoint correctly routes
method calls to service functions, replacing the BICP custom handlers.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """Create a test FastAPI app with the API router mounted."""
    from db_mcp.api.router import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


def _post(client, method: str, params: dict | None = None):
    """Helper to POST to the dispatch endpoint."""
    return client.post(
        f"/api/{method}",
        content=json.dumps(params) if params else b"",
        headers={"Content-Type": "application/json"} if params else {},
    )


# ── Dispatch tests ──────────────────────────────────────────────────


class TestDispatch:
    def test_unknown_method_returns_404(self, client):
        resp = _post(client, "unknown/method")
        assert resp.status_code == 404

    def test_empty_body_passes_empty_dict(self, client):
        with patch(
            "db_mcp.api.handlers.traces.traces_service.clear_traces",
            return_value={"success": True},
        ):
            resp = _post(client, "traces/clear")
            assert resp.status_code == 200
            assert resp.json()["success"] is True


# ── Connection handler tests ────────────────────────────────────────


class TestConnectionHandlers:
    def test_connections_list(self, client):
        expected = {"connections": [{"name": "prod", "isActive": True}]}
        with patch(
            "db_mcp.api.handlers.connections.connection_service.list_connections_summary",
            return_value=expected,
        ):
            resp = _post(client, "connections/list")
            assert resp.status_code == 200
            assert resp.json()["connections"][0]["name"] == "prod"

    def test_connections_switch(self, client):
        with patch(
            "db_mcp.api.handlers.connections.switch_active_connection",
            return_value={"success": True},
        ):
            resp = _post(client, "connections/switch", {"name": "prod"})
            assert resp.json()["success"] is True

    def test_connections_create_sql(self, client):
        with patch(
            "db_mcp.api.handlers.connections.create_sql_connection",
            return_value={"success": True, "dialect": "postgresql"},
        ):
            resp = _post(
                client,
                "connections/create",
                {"name": "mydb", "connectorType": "sql", "databaseUrl": "postgresql://..."},
            )
            assert resp.json()["success"] is True

    def test_connections_create_missing_name(self, client):
        resp = _post(client, "connections/create", {"name": ""})
        assert resp.json()["success"] is False
        assert "required" in resp.json()["error"].lower()

    def test_connections_create_invalid_name(self, client):
        resp = _post(client, "connections/create", {"name": "bad name!"})
        assert resp.json()["success"] is False
        assert "invalid" in resp.json()["error"].lower()

    def test_connections_test_named(self, client):
        with patch(
            "db_mcp.api.handlers.connections.connection_service.test_named_connection",
            return_value={"success": True, "dialect": "postgresql"},
        ):
            resp = _post(client, "connections/test", {"name": "prod"})
            assert resp.json()["success"] is True

    def test_connections_test_database_url(self, client):
        with patch(
            "db_mcp.api.handlers.connections.test_database_url",
            return_value={"success": True, "dialect": "postgresql"},
        ):
            resp = _post(
                client, "connections/test", {"databaseUrl": "postgresql://..."}
            )
            assert resp.json()["success"] is True

    def test_connections_test_api(self, client):
        with patch(
            "db_mcp.api.handlers.connections.test_api_connection",
            return_value={"success": True},
        ):
            resp = _post(
                client,
                "connections/test",
                {"connectorType": "api", "baseUrl": "https://api.example.com"},
            )
            assert resp.json()["success"] is True

    def test_connections_test_file(self, client):
        with patch(
            "db_mcp.api.handlers.connections.test_file_directory",
            return_value={"success": True},
        ):
            resp = _post(
                client,
                "connections/test",
                {"connectorType": "file", "directory": "/tmp/data"},
            )
            assert resp.json()["success"] is True

    def test_connections_delete(self, client):
        with patch(
            "db_mcp.api.handlers.connections.delete_connection",
            return_value={"success": True},
        ):
            resp = _post(client, "connections/delete", {"name": "old"})
            assert resp.json()["success"] is True

    def test_connections_get(self, client):
        with patch(
            "db_mcp.api.handlers.connections.connection_service.get_named_connection_details",
            return_value={"success": True, "name": "prod", "connectorType": "sql"},
        ):
            resp = _post(client, "connections/get", {"name": "prod"})
            assert resp.json()["name"] == "prod"

    def test_connections_templates(self, client):
        with patch(
            "db_mcp.api.handlers.connections.list_connector_templates",
            return_value=[MagicMock(id="dune")],
        ):
            with patch(
                "db_mcp.api.handlers.connections.build_api_template_descriptor",
                return_value={"id": "dune", "connectorType": "api"},
            ):
                resp = _post(client, "connections/templates", {})
                assert resp.json()["success"] is True


# ── Context handler tests ───────────────────────────────────────────


class TestContextHandlers:
    def test_context_tree(self, client):
        expected = {"connections": []}
        with patch(
            "db_mcp.api.handlers.context.vault_service.list_context_tree",
            return_value=expected,
        ):
            resp = _post(client, "context/tree")
            assert resp.status_code == 200
            assert "connections" in resp.json()

    def test_context_read(self, client):
        with patch(
            "db_mcp.api.handlers.context.vault_service.read_context_file",
            return_value={"success": True, "content": "hello"},
        ):
            resp = _post(
                client, "context/read", {"connection": "prod", "path": "README.md"}
            )
            assert resp.json()["content"] == "hello"

    def test_context_read_missing_params(self, client):
        resp = _post(client, "context/read", {"connection": ""})
        assert resp.json()["success"] is False

    def test_context_write(self, client):
        with patch(
            "db_mcp.api.handlers.context.vault_service.write_context_file",
            return_value={"success": True},
        ):
            with patch(
                "db_mcp.api.handlers.context.vault_service.try_git_commit",
                return_value=False,
            ):
                resp = _post(
                    client,
                    "context/write",
                    {"connection": "prod", "path": "README.md", "content": "hello"},
                )
                assert resp.json()["success"] is True

    def test_context_create(self, client):
        with patch(
            "db_mcp.api.handlers.context.vault_service.create_context_file",
            return_value={"success": True},
        ):
            with patch(
                "db_mcp.api.handlers.context.vault_service.try_git_commit",
                return_value=False,
            ):
                resp = _post(
                    client,
                    "context/create",
                    {"connection": "prod", "path": "notes.md", "content": ""},
                )
                assert resp.json()["success"] is True

    def test_context_delete(self, client):
        with patch(
            "db_mcp.api.handlers.context.vault_service.delete_context_file",
            return_value={"success": True, "trashedTo": ".trash/README.md"},
        ):
            with patch(
                "db_mcp.api.handlers.context._is_git_enabled", return_value=False
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    resp = _post(
                        client,
                        "context/delete",
                        {"connection": "prod", "path": "notes.md"},
                    )
                    assert resp.json()["success"] is True

    def test_context_delete_invalid_path(self, client):
        resp = _post(
            client, "context/delete", {"connection": "prod", "path": "../etc/passwd"}
        )
        assert resp.json()["success"] is False

    def test_context_add_rule(self, client):
        with patch(
            "db_mcp.api.handlers.context.vault_service.add_business_rule",
            return_value={"success": True},
        ):
            with patch(
                "db_mcp.api.handlers.context.vault_service.try_git_commit",
                return_value=False,
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    resp = _post(
                        client,
                        "context/add-rule",
                        {"connection": "prod", "rule": "1 GB = 1073741824 bytes"},
                    )
                    assert resp.json()["success"] is True

    def test_context_usage(self, client):
        with patch(
            "db_mcp.api.handlers.context.vault_service.get_context_usage",
            return_value={"files": {}, "folders": {}},
        ):
            with patch("pathlib.Path.exists", return_value=True):
                resp = _post(client, "context/usage", {"connection": "prod"})
                assert "files" in resp.json()


# ── Git handler tests ───────────────────────────────────────────────


class TestGitHandlers:
    def test_git_history(self, client):
        with patch(
            "db_mcp.api.handlers.git.git_service.get_git_history",
            return_value={"success": True, "commits": []},
        ):
            resp = _post(
                client,
                "context/git/history",
                {"connection": "prod", "path": "schema/descriptions.yaml"},
            )
            assert resp.json()["success"] is True

    def test_git_show(self, client):
        with patch(
            "db_mcp.api.handlers.git.git_service.get_git_content",
            return_value={"success": True, "content": "old content"},
        ):
            resp = _post(
                client,
                "context/git/show",
                {"connection": "prod", "path": "file.yaml", "commit": "abc123"},
            )
            assert resp.json()["content"] == "old content"

    def test_git_revert(self, client):
        with patch(
            "db_mcp.api.handlers.git.git_service.revert_git_file",
            return_value={"success": True},
        ):
            resp = _post(
                client,
                "context/git/revert",
                {"connection": "prod", "path": "file.yaml", "commit": "abc123"},
            )
            assert resp.json()["success"] is True


# ── Trace handler tests ─────────────────────────────────────────────


class TestTraceHandlers:
    def test_traces_list(self, client):
        with patch(
            "db_mcp.api.handlers.traces.traces_service.list_traces",
            return_value={"success": True, "traces": [], "source": "live"},
        ):
            resp = _post(client, "traces/list", {"source": "live"})
            assert resp.json()["success"] is True

    def test_traces_clear(self, client):
        with patch(
            "db_mcp.api.handlers.traces.traces_service.clear_traces",
            return_value={"success": True},
        ):
            resp = _post(client, "traces/clear")
            assert resp.json()["success"] is True

    def test_traces_dates(self, client):
        with patch(
            "db_mcp.api.handlers.traces.traces_service.get_trace_dates",
            return_value={"success": True, "enabled": True, "dates": ["2026-04-01"]},
        ):
            resp = _post(client, "traces/dates")
            assert resp.json()["dates"] == ["2026-04-01"]


# ── Insights handler tests ──────────────────────────────────────────


class TestInsightsHandlers:
    def test_insights_analyze(self, client):
        with patch(
            "db_mcp.api.handlers.insights.insights_service.analyze_insights",
            return_value={"traceCount": 10},
        ):
            resp = _post(client, "insights/analyze", {"days": 7})
            assert resp.json()["success"] is True
            assert resp.json()["analysis"]["traceCount"] == 10

    def test_gaps_dismiss(self, client):
        with patch(
            "db_mcp.api.handlers.insights.insights_service.dismiss_gap",
            return_value={"success": True, "count": 5},
        ):
            resp = _post(
                client,
                "gaps/dismiss",
                {"connection": "prod", "gapId": "gap-1", "reason": "not relevant"},
            )
            assert resp.json()["success"] is True

    def test_insights_save_example(self, client):
        with patch(
            "db_mcp.api.handlers.insights.insights_service.save_example",
            return_value={"success": True, "example_id": "ex-1", "total_examples": 5},
        ):
            with patch(
                "db_mcp.api.handlers.insights.vault_service.try_git_commit",
                return_value=False,
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    resp = _post(
                        client,
                        "insights/save-example",
                        {"connection": "prod", "sql": "SELECT 1", "intent": "test"},
                    )
                    assert resp.json()["success"] is True
                    assert resp.json()["example_id"] == "ex-1"


# ── Metrics handler tests ───────────────────────────────────────────


class TestMetricsHandlers:
    def test_metrics_list(self, client):
        with patch(
            "db_mcp.api.handlers.metrics.metrics_service.list_approved_metrics",
            return_value={"metrics": [], "dimensions": [], "metricCount": 0, "dimensionCount": 0},
        ):
            with patch("pathlib.Path.exists", return_value=True):
                resp = _post(client, "metrics/list", {"connection": "prod"})
                assert resp.json()["success"] is True

    def test_metrics_add(self, client):
        with patch(
            "db_mcp.api.handlers.metrics.metrics_service.add_metric_definition",
            return_value={"success": True, "name": "revenue"},
        ):
            with patch(
                "db_mcp.api.handlers.metrics.vault_service.try_git_commit",
                return_value=False,
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    resp = _post(
                        client,
                        "metrics/add",
                        {
                            "connection": "prod",
                            "type": "metric",
                            "data": {"name": "revenue", "sql": "SELECT SUM(amount) FROM orders"},
                        },
                    )
                    assert resp.json()["success"] is True

    def test_metrics_delete(self, client):
        with patch(
            "db_mcp.api.handlers.metrics.metrics_service.delete_metric_definition",
            return_value={"success": True},
        ):
            with patch(
                "db_mcp.api.handlers.metrics.vault_service.try_git_commit",
                return_value=False,
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    resp = _post(
                        client,
                        "metrics/delete",
                        {"connection": "prod", "type": "metric", "name": "revenue"},
                    )
                    assert resp.json()["success"] is True

    def test_metrics_candidates(self, client):
        with patch(
            "db_mcp.api.handlers.metrics.metrics_service.discover_metric_candidates",
            new_callable=AsyncMock,
            return_value={"metricCandidates": [], "dimensionCandidates": []},
        ):
            with patch("pathlib.Path.exists", return_value=True):
                resp = _post(client, "metrics/candidates", {"connection": "prod"})
                assert resp.json()["success"] is True


# ── Schema handler tests ────────────────────────────────────────────


class TestSchemaHandlers:
    def test_schema_catalogs(self, client):
        with patch(
            "db_mcp.api.handlers.schema.resolve_connection_context",
            return_value=("prod", Path("/tmp/prod")),
        ):
            with patch(
                "db_mcp.api.handlers.schema.schema_service.list_catalogs",
                return_value={"success": True, "catalogs": ["default"]},
            ):
                resp = _post(client, "schema/catalogs")
                assert resp.json()["catalogs"] == ["default"]

    def test_schema_tables(self, client):
        with patch(
            "db_mcp.api.handlers.schema.resolve_connection_context",
            return_value=("prod", Path("/tmp/prod")),
        ):
            with patch(
                "db_mcp.api.handlers.schema.schema_service.list_tables_with_descriptions",
                return_value={"success": True, "tables": [{"name": "orders"}]},
            ):
                resp = _post(client, "schema/tables", {"schema": "public"})
                assert resp.json()["tables"][0]["name"] == "orders"

    def test_sample_table(self, client):
        with patch(
            "db_mcp.api.handlers.schema.schema_service.sample_table",
            return_value={"rows": [{"id": 1}], "row_count": 1, "limit": 5},
        ):
            resp = _post(
                client,
                "sample_table",
                {"connection": "prod", "table_name": "orders"},
            )
            assert resp.json()["row_count"] == 1


# ── Agent handler tests ─────────────────────────────────────────────


class TestAgentHandlers:
    def test_agents_list(self, client):
        with patch(
            "db_mcp.api.handlers.agents.agents_service.list_agents",
            return_value={"agents": []},
        ):
            resp = _post(client, "agents/list")
            assert "agents" in resp.json()

    def test_agents_configure(self, client):
        with patch(
            "db_mcp.api.handlers.agents.agents_service.configure_agent",
            return_value={"success": True},
        ):
            resp = _post(client, "agents/configure", {"agentId": "claude-desktop"})
            assert resp.json()["success"] is True

    def test_agents_remove(self, client):
        with patch(
            "db_mcp.api.handlers.agents.agents_service.remove_agent",
            return_value={"success": True},
        ):
            resp = _post(client, "agents/remove", {"agentId": "claude-desktop"})
            assert resp.json()["success"] is True


# ── Playground handler tests ────────────────────────────────────────


class TestPlaygroundHandlers:
    def test_playground_install(self, client):
        with patch(
            "db_mcp.playground.install_playground",
            return_value={"success": True},
        ):
            resp = _post(client, "playground/install")
            assert resp.json()["success"] is True

    def test_playground_status(self, client):
        with patch(
            "db_mcp.playground.is_playground_installed",
            return_value=True,
        ):
            resp = _post(client, "playground/status")
            assert resp.json()["installed"] is True
