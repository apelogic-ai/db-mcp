"""Provider interface and first concrete provider for the insider agent."""

from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


class AnthropicInsiderProvider(InsiderProvider):
    """Minimal Anthropic-backed provider implementation using HTTP."""

    def __init__(self, *, model: str, api_key_env: str):
        self.model = model
        self.api_key_env = api_key_env

    def prepare(self, request: InsiderRunRequest) -> ProviderRequest:
        return ProviderRequest(
            system_prompt="You produce structured bootstrap proposals for db-mcp.",
            user_prompt=_build_user_prompt(request),
            metadata={"model": self.model},
        )

    def run(self, request: ProviderRequest) -> ProviderResponse:
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"Missing provider API key in env var {self.api_key_env!r}")
        body = {
            "model": self.model,
            "max_tokens": 4000,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
        }
        raw = json.dumps(body).encode("utf-8")
        http_request = Request(
            url="https://api.anthropic.com/v1/messages",
            data=raw,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic request failed: {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Anthropic request failed: {exc}") from exc

        text_parts = []
        for item in payload.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        usage = payload.get("usage", {}) or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        estimated_cost = None
        if input_tokens is not None or output_tokens is not None:
            estimated_cost = 0.0
        return ProviderResponse(
            raw_text="\n".join(text_parts).strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
            metadata=payload,
        )

    def parse(self, response: ProviderResponse) -> InsiderProposalBundle:
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


def build_provider(*, provider: str, model: str, api_key_env: str) -> InsiderProvider:
    """Return the configured insider provider."""
    if provider == "anthropic":
        return AnthropicInsiderProvider(model=model, api_key_env=api_key_env)
    if provider == "claude-code":
        return ClaudeCodeInsiderProvider(model=model)
    raise ValueError(f"Unsupported insider provider: {provider}")
