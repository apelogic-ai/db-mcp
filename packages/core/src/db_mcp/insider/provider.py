"""Provider interface and first concrete provider for the insider agent."""

from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from db_mcp.insider.models import (
    InsiderProposalBundle,
    InsiderRunRequest,
    ProviderRequest,
    ProviderResponse,
)


class InsiderProvider(ABC):
    """Abstract provider interface."""

    @abstractmethod
    def prepare(self, request: InsiderRunRequest) -> ProviderRequest:
        raise NotImplementedError

    @abstractmethod
    def run(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError

    @abstractmethod
    def parse(self, response: ProviderResponse) -> InsiderProposalBundle:
        raise NotImplementedError


def _build_user_prompt(request: InsiderRunRequest) -> str:
    schema_yaml = request.context.get("schema_yaml", "")
    onboarding_state = request.context.get("onboarding_state", {})
    domain_model = request.context.get("domain_model_markdown")
    existing_examples = request.context.get("examples", [])
    findings_context = request.context.get("knowledge_gaps", [])
    return (
        "You are an internal database knowledge curator.\n"
        "Return only valid JSON matching the required shape.\n\n"
        f"Connection: {request.connection}\n"
        f"Schema digest: {request.schema_digest}\n"
        f"Event type: {request.event_type}\n"
        f"Event payload:\n{json.dumps(request.event_payload, indent=2)}\n\n"
        f"Onboarding state:\n{json.dumps(onboarding_state, indent=2)}\n\n"
        f"Existing domain model:\n{domain_model or ''}\n\n"
        f"Existing examples:\n{json.dumps(existing_examples, indent=2)}\n\n"
        f"Knowledge gaps:\n{json.dumps(findings_context, indent=2)}\n\n"
        f"Schema descriptions:\n{schema_yaml}\n\n"
        "Produce a JSON object with keys:\n"
        "- draft_domain_model_markdown: string|null\n"
        "- description_updates: array of "
        "{table_full_name, description, columns:[{name,description}]}\n"
        "- example_candidates: array of {slug, natural_language, sql, tables, notes, tags}\n"
        "- findings: array of objects\n"
        "- review_items: array of {kind, title, payload}\n"
        "Use review_items kinds only from: schema_descriptions, "
        "canonical_examples, canonical_domain_model."
    )


def _parse_bundle_text(raw_text: str) -> InsiderProposalBundle:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    data = json.loads(text or "{}")
    if (
        isinstance(data, dict)
        and data.get("type") == "result"
        and isinstance(data.get("structured_output"), dict)
    ):
        data = data["structured_output"]
    return InsiderProposalBundle.model_validate(data)


class OpenAICompatibleInsiderProvider(InsiderProvider):
    """Direct LLM backend using pydantic-ai over an OpenAI-compatible chat API."""

    def __init__(self, *, model: str, api_key_env: str, base_url: str | None = None):
        self.model = model
        self.api_key_env = api_key_env
        self.base_url = base_url

    def prepare(self, request: InsiderRunRequest) -> ProviderRequest:
        return ProviderRequest(
            system_prompt="You produce structured bootstrap proposals for db-mcp.",
            user_prompt=_build_user_prompt(request),
            metadata={"model": self.model, "base_url": self.base_url},
        )

    def run(self, request: ProviderRequest) -> ProviderResponse:
        api_key = os.environ.get(self.api_key_env, "").strip() or None
        if api_key is None and not self.base_url:
            raise RuntimeError(
                f"Missing provider API key in env var {self.api_key_env!r}"
            )
        provider = OpenAIProvider(base_url=self.base_url, api_key=api_key)
        model = OpenAIModel(self.model, provider=provider)
        agent = Agent(
            model=model,
            system_prompt=request.system_prompt,
            output_type=InsiderProposalBundle,
        )
        try:
            result = agent.run_sync(request.user_prompt)
        except Exception as exc:
            raise RuntimeError(f"OpenAI-compatible insider run failed: {exc}") from exc

        bundle = result.output
        usage = result.usage()
        return ProviderResponse(
            raw_text=bundle.model_dump_json(indent=2),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost_usd=None,
            metadata={
                "bundle": bundle.model_dump(mode="json"),
                "base_url": self.base_url,
                "provider": "openai-compatible",
            },
        )

    def parse(self, response: ProviderResponse) -> InsiderProposalBundle:
        bundle = response.metadata.get("bundle")
        if isinstance(bundle, dict):
            return InsiderProposalBundle.model_validate(bundle)
        return _parse_bundle_text(response.raw_text)


class ClaudeCodeInsiderProvider(InsiderProvider):
    """Claude Code CLI-backed insider backend using existing local auth state."""

    def __init__(self, *, model: str, cli_binary: str = "claude"):
        self.model = model
        self.cli_binary = cli_binary

    def prepare(self, request: InsiderRunRequest) -> ProviderRequest:
        return ProviderRequest(
            system_prompt="You produce structured bootstrap proposals for db-mcp.",
            user_prompt=_build_user_prompt(request),
            metadata={
                "model": self.model,
                "cli_binary": self.cli_binary,
                "json_schema": InsiderProposalBundle.model_json_schema(),
                "connection_path": request.connection_path,
            },
        )

    def run(self, request: ProviderRequest) -> ProviderResponse:
        json_schema = (
            request.metadata.get("json_schema") or InsiderProposalBundle.model_json_schema()
        )
        connection_path = str(request.metadata.get("connection_path") or ".")
        command = [
            self.cli_binary,
            "--print",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(json_schema, separators=(",", ":")),
            "--model",
            self.model,
            "--permission-mode",
            "bypassPermissions",
            "--",
            request.user_prompt,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=connection_path,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Claude Code CLI not found: {self.cli_binary!r}"
            ) from exc
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(
                "Claude Code insider run failed"
                + (f": {stderr}" if stderr else f" with exit code {result.returncode}")
            )
        return ProviderResponse(
            raw_text=(result.stdout or "").strip(),
            metadata={"stderr": result.stderr or "", "returncode": result.returncode},
        )

    def parse(self, response: ProviderResponse) -> InsiderProposalBundle:
        return _parse_bundle_text(response.raw_text)


def build_provider(
    *,
    provider: str,
    model: str,
    api_key_env: str,
    base_url: str | None = None,
) -> InsiderProvider:
    """Return the configured insider provider."""
    if provider == "openai-compatible":
        return OpenAICompatibleInsiderProvider(
            model=model,
            api_key_env=api_key_env,
            base_url=base_url,
        )
    if provider == "claude-code":
        return ClaudeCodeInsiderProvider(model=model)
    raise ValueError(f"Unsupported insider provider: {provider}")
