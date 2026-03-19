"""Tests for insider-agent provider backends."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from db_mcp.insider.models import InsiderRunRequest, ProviderResponse
from db_mcp.insider.provider import ClaudeCodeInsiderProvider, build_provider


def _sample_request() -> InsiderRunRequest:
    return InsiderRunRequest(
        connection="playground",
        connection_path="/tmp/playground",
        schema_digest="abc123",
        event_type="new_connection",
        event_payload={"source": "test"},
        context={
            "schema_yaml": "tables: []",
            "onboarding_state": {"phase": "schema"},
            "domain_model_markdown": None,
            "examples": [],
            "knowledge_gaps": [],
        },
    )


def test_build_provider_supports_claude_code():
    provider = build_provider(provider="claude-code", model="sonnet", api_key_env="IGNORED")

    assert isinstance(provider, ClaudeCodeInsiderProvider)


def test_claude_code_prepare_includes_json_schema():
    provider = ClaudeCodeInsiderProvider(model="claude-sonnet")

    request = provider.prepare(_sample_request())

    assert request.metadata["cli_binary"] == "claude"
    assert request.metadata["json_schema"]["type"] == "object"
    assert "database knowledge curator" in request.user_prompt.lower()


def test_claude_code_run_invokes_cli_with_schema(monkeypatch):
    provider = ClaudeCodeInsiderProvider(model="claude-sonnet")
    prepared = provider.prepare(_sample_request())
    calls: list[dict[str, object]] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "structured_output": {
                        "draft_domain_model_markdown": "# Draft\n",
                        "description_updates": [],
                        "example_candidates": [],
                        "findings": [],
                        "review_items": [],
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = provider.run(prepared)

    assert response.raw_text
    assert calls, "expected subprocess.run to be invoked"
    cmd = calls[0]["cmd"]
    assert "--json-schema" in cmd
    assert "--output-format" in cmd
    assert "--permission-mode" in cmd


def test_claude_code_parse_supports_structured_output_envelope():
    provider = ClaudeCodeInsiderProvider(model="claude-sonnet")
    response = ProviderResponse(
        raw_text=json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "structured_output": {
                    "draft_domain_model_markdown": "# Draft\n",
                    "description_updates": [],
                    "example_candidates": [],
                    "findings": [{"kind": "bootstrap"}],
                    "review_items": [],
                },
            }
        )
    )

    bundle = provider.parse(response)

    assert bundle.draft_domain_model_markdown == "# Draft\n"
    assert bundle.findings == [{"kind": "bootstrap"}]


def test_claude_code_run_raises_on_cli_failure(monkeypatch):
    provider = ClaudeCodeInsiderProvider(model="claude-sonnet")
    prepared = provider.prepare(_sample_request())

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="Claude Code insider run failed"):
        provider.run(prepared)
