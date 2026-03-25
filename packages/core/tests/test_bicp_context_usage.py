"""Tests for BICP context usage aggregation."""

import json
from pathlib import Path
from types import MethodType
from unittest.mock import MagicMock

import pytest

from db_mcp.bicp.agent import DBMCPAgent


def _make_agent(connections_dir: Path) -> DBMCPAgent:
    agent = DBMCPAgent.__new__(DBMCPAgent)
    agent._settings = MagicMock()
    agent._get_connections_dir = MethodType(lambda self: connections_dir, agent)
    return agent


def _write_trace_file(trace_file: Path, spans: list[dict]) -> None:
    trace_file.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for idx, attrs in enumerate(spans, start=1):
        lines.append(
            json.dumps(
                {
                    "ts": 1_741_000_000_000_000_000 + idx,
                    "trace_id": f"trace-{idx}",
                    "span_id": f"span-{idx}",
                    "name": attrs.pop("name", "tools/call"),
                    "duration_ms": 5.0,
                    "status": "OK",
                    "attrs": attrs,
                }
            )
        )
    trace_file.write_text("\n".join(lines) + "\n")


@pytest.mark.asyncio
async def test_context_usage_tracks_root_and_relative_vault_files(tmp_path: Path) -> None:
    connections_dir = tmp_path / "connections"
    conn_path = connections_dir / "demo"
    trace_file = conn_path / "traces" / "default" / "2026-03-11.jsonl"

    _write_trace_file(
        trace_file,
        [
            {"tool.name": "shell", "command": "cat PROTOCOL.md && cat connector.yaml"},
            {"tool.name": "protocol_tool"},
            {"tool.name": "import_instructions", "path": "metrics/catalog.yaml"},
            {
                "name": "resources/read",
                "resource.uri": f"file://{conn_path / 'knowledge_gaps.yaml'}",
            },
            {"knowledge.files_used": ["domain/model.md", "examples/example-1.yaml"]},
        ],
    )

    agent = _make_agent(connections_dir)

    result = await agent._handle_context_usage({"connection": "demo", "days": 30})

    assert result["files"]["PROTOCOL.md"]["count"] == 2
    assert result["files"]["connector.yaml"]["count"] == 1
    assert result["files"]["knowledge_gaps.yaml"]["count"] == 1
    assert result["files"]["metrics/catalog.yaml"]["count"] == 1
    assert result["files"]["domain/model.md"]["count"] == 1
    assert result["files"]["examples/example-1.yaml"]["count"] == 1
    assert result["folders"]["metrics"]["count"] == 1
    assert result["folders"]["domain"]["count"] == 1
    assert result["folders"]["examples"]["count"] == 1


@pytest.mark.asyncio
async def test_context_usage_reads_beyond_latest_fifty_traces(tmp_path: Path) -> None:
    connections_dir = tmp_path / "connections"
    conn_path = connections_dir / "demo"
    trace_file = conn_path / "traces" / "default" / "2026-03-11.jsonl"

    spans = [{"name": "initialize"} for _ in range(60)]
    spans[0] = {
        "tool.name": "shell",
        "command": "cat instructions/business_rules.yaml",
    }
    _write_trace_file(trace_file, spans)

    agent = _make_agent(connections_dir)

    result = await agent._handle_context_usage({"connection": "demo", "days": 30})

    assert result["files"]["instructions/business_rules.yaml"]["count"] == 1
    assert result["folders"]["instructions"]["count"] == 1


@pytest.mark.asyncio
async def test_context_tree_marks_nested_trace_directories_as_non_empty(tmp_path: Path) -> None:
    connections_dir = tmp_path / "connections"
    conn_path = connections_dir / "demo"
    (conn_path / "traces" / "user-1").mkdir(parents=True)
    (conn_path / "traces" / "user-1" / "2026-03-11.jsonl").write_text("{}\n")

    agent = _make_agent(connections_dir)

    result = await agent._handle_context_tree({})
    folder = next(
        folder
        for folder in result["connections"][0]["folders"]
        if folder["name"] == "traces"
    )

    assert folder["isEmpty"] is False
