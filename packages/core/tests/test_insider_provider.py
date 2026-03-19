"""Tests for insider-agent provider backends."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from db_mcp.insider.models import InsiderRunRequest, ProviderResponse
from db_mcp.insider.provider import (
    ClaudeCodeInsiderProvider,
    OpenAICompatibleInsiderProvider,
    build_provider,
)


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


def test_build_provider_supports_openai_compatible():
    provider = build_provider(
        provider="openai-compatible",
        model="gpt-4o-mini",
        api_key_env="OPENAI_KEY",
        base_url="http://localhost:11434/v1",
    )

    assert isinstance(provider, OpenAICompatibleInsiderProvider)


def test_openai_compatible_prepare_includes_model_and_base_url():
    provider = OpenAICompatibleInsiderProvider(
        model="gpt-4o-mini",
        api_key_env="OPENAI_KEY",
        base_url="http://localhost:11434/v1",
    )

    request = provider.prepare(_sample_request())

    assert request.metadata["model"] == "gpt-4o-mini"
    assert request.metadata["base_url"] == "http://localhost:11434/v1"
    assert "database knowledge curator" in request.user_prompt.lower()


def test_openai_compatible_run_uses_pydantic_ai_provider(monkeypatch):
    provider = OpenAICompatibleInsiderProvider(
        model="gpt-4o-mini",
        api_key_env="OPENAI_KEY",
        base_url="http://localhost:11434/v1",
    )
    prepared = provider.prepare(_sample_request())
    monkeypatch.setenv("OPENAI_KEY", "secret-key")
    calls: dict[str, object] = {}

    class FakeUsage:
        input_tokens = 11
        output_tokens = 7

    class FakeResult:
        output = SimpleNamespace(
            model_dump_json=lambda indent=2: json.dumps(
                {
                    "draft_domain_model_markdown": "# Draft\n",
                    "description_updates": [],
                    "example_candidates": [],
                    "findings": [],
                    "review_items": [],
                },
                indent=indent,
            ),
            model_dump=lambda mode=None: {
                "draft_domain_model_markdown": "# Draft\n",
                "description_updates": [],
                "example_candidates": [],
                "findings": [],
                "review_items": [],
            }
        )

        def usage(self):
            return FakeUsage()

    class FakeAgent:
        def __init__(self, *, model, system_prompt, output_type):
            calls["agent_model"] = model
            calls["system_prompt"] = system_prompt
            calls["output_type"] = output_type

        def run_sync(self, user_prompt):
            calls["user_prompt"] = user_prompt
            return FakeResult()

    def fake_openai_provider(*, base_url=None, api_key=None):
        calls["base_url"] = base_url
        calls["api_key"] = api_key
        return "provider"

    def fake_openai_model(model_name, *, provider):
        calls["model_name"] = model_name
        calls["provider"] = provider
        return "model"

    monkeypatch.setattr("db_mcp.insider.provider.Agent", FakeAgent)
    monkeypatch.setattr("db_mcp.insider.provider.OpenAIProvider", fake_openai_provider)
    monkeypatch.setattr("db_mcp.insider.provider.OpenAIModel", fake_openai_model)

    response = provider.run(prepared)

    assert calls["base_url"] == "http://localhost:11434/v1"
    assert calls["api_key"] == "secret-key"
    assert calls["model_name"] == "gpt-4o-mini"
    assert calls["provider"] == "provider"
    assert calls["output_type"].__name__ == "InsiderProposalBundle"
    assert "database knowledge curator" in str(calls["user_prompt"]).lower()
    assert response.input_tokens == 11
    assert response.output_tokens == 7
    assert json.loads(response.raw_text)["draft_domain_model_markdown"] == "# Draft\n"


def test_openai_compatible_run_allows_missing_key_with_base_url(monkeypatch):
    provider = OpenAICompatibleInsiderProvider(
        model="gpt-4o-mini",
        api_key_env="OPENAI_KEY",
        base_url="http://localhost:11434/v1",
    )
    prepared = provider.prepare(_sample_request())

    class FakeResult:
        output = SimpleNamespace(
            model_dump_json=lambda indent=2: json.dumps(
                {
                    "draft_domain_model_markdown": None,
                    "description_updates": [],
                    "example_candidates": [],
                    "findings": [],
                    "review_items": [],
                },
                indent=indent,
            ),
            model_dump=lambda mode=None: {
                "draft_domain_model_markdown": None,
                "description_updates": [],
                "example_candidates": [],
                "findings": [],
                "review_items": [],
            }
        )

        def usage(self):
            return SimpleNamespace(input_tokens=0, output_tokens=0)

    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.setattr(
        "db_mcp.insider.provider.OpenAIProvider",
        lambda *, base_url=None, api_key=None: "provider",
    )
    monkeypatch.setattr(
        "db_mcp.insider.provider.OpenAIModel",
        lambda model_name, *, provider: "model",
    )
    monkeypatch.setattr(
        "db_mcp.insider.provider.Agent",
        lambda **kwargs: SimpleNamespace(run_sync=lambda user_prompt: FakeResult()),
    )

    response = provider.run(prepared)

    assert response.raw_text


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
