"""Tests for operator-journey BICP endpoints.

Covers:
- wizard/state/get
- wizard/state/save
- dashboard/summary
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from db_mcp.bicp.agent import DBMCPAgent


def _make_agent() -> DBMCPAgent:
    agent = DBMCPAgent.__new__(DBMCPAgent)
    agent._method_handlers = {}
    agent._settings = None
    agent._dialect = "postgresql"
    return agent


@pytest.mark.asyncio
async def test_wizard_state_round_trip_per_connection(monkeypatch, tmp_path):
    """Saved wizard state can be loaded back for the same connection."""
    monkeypatch.setenv("HOME", str(tmp_path))

    conn = tmp_path / ".db-mcp" / "connections" / "playground"
    conn.mkdir(parents=True, exist_ok=True)

    agent = _make_agent()

    state = {
        "wizardId": "triage",
        "step": "capture-patterns",
        "completedSteps": ["review-queue", "resolve-vocab"],
        "skippedSteps": [],
        "connection": "playground",
        "updatedAt": "2026-03-04T10:00:00Z",
    }

    save_result = await agent._handle_wizard_state_save(state)
    assert save_result["success"] is True

    loaded = await agent._handle_wizard_state_get(
        {"wizardId": "triage", "connection": "playground"}
    )
    assert loaded is not None
    assert loaded["wizardId"] == "triage"
    assert loaded["step"] == "capture-patterns"
    assert loaded["connection"] == "playground"


@pytest.mark.asyncio
async def test_wizard_state_save_rejects_invalid_wizard_id():
    agent = _make_agent()

    result = await agent._handle_wizard_state_save(
        {
            "wizardId": "unknown",
            "step": "x",
            "completedSteps": [],
            "skippedSteps": [],
            "connection": None,
            "updatedAt": "2026-03-04T10:00:00Z",
        }
    )

    assert result["success"] is False
    assert "wizardId" in result["error"]


@pytest.mark.asyncio
async def test_dashboard_summary_returns_stable_shape(monkeypatch):
    agent = _make_agent()

    async def fake_connections_list(_params):
        return {
            "connections": [
                {
                    "name": "playground",
                    "isActive": True,
                    "hasSchema": True,
                    "hasDomain": True,
                    "hasCredentials": True,
                }
            ],
            "activeConnection": "playground",
        }

    async def fake_insights(_params):
        return {
            "success": True,
            "analysis": {
                "traceCount": 12,
                "errorCount": 2,
                "validationFailureCount": 1,
                "knowledgeCaptureCount": 3,
                "knowledgeStatus": {
                    "hasSchema": True,
                    "hasDomain": True,
                    "exampleCount": 5,
                    "ruleCount": 2,
                    "metricCount": 1,
                },
                "vocabularyGaps": [{"status": "open"}],
                "repeatedQueries": [{"is_example": False}],
                "errors": [{"error_type": "soft", "sql": "SELECT 1", "is_saved": False}],
            },
        }

    with (
        patch.object(agent, "_handle_connections_list", side_effect=fake_connections_list),
        patch.object(agent, "_handle_insights_analyze", side_effect=fake_insights),
    ):
        result = await agent._handle_dashboard_summary({"connection": "playground"})

    assert "setup" in result
    assert "semantic" in result
    assert "queue" in result
    assert "recent" in result

    assert result["setup"]["activeConnection"] == "playground"
    assert "items" in result["queue"]
    assert isinstance(result["queue"]["items"], list)
    assert "openItems" in result["queue"]
