"""Helpers for loading business rules from multiple vault file shapes."""

from __future__ import annotations

import re
from typing import Any

from db_mcp_models import (
    BoundaryMode,
    CandidateRule,
    PromptInstructions,
    SemanticPolicy,
    TimeWindowPolicy,
    UnitConversionPolicy,
)

_TEXT_KEYS = ("rule", "rule_text", "text", "description", "summary", "note")
_IEC_GB_RE = re.compile(r"1\s*GB\s*=\s*(\d+)\s*bytes", re.IGNORECASE)
_IEC_TB_RE = re.compile(r"1\s*TB\s*=\s*(\d+)\s*bytes", re.IGNORECASE)


def extract_business_rule_texts(payload: Any) -> list[str]:
    """Extract business-rule strings from canonical and ad hoc YAML payloads."""

    def _extract(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, list):
            rules: list[str] = []
            for item in value:
                rules.extend(_extract(item))
            return rules
        if isinstance(value, dict):
            if "rules" in value:
                return _extract(value.get("rules"))
            for key in _TEXT_KEYS:
                if key in value:
                    return _extract(value.get(key))
        return []

    deduped: list[str] = []
    seen: set[str] = set()
    for rule in _extract(payload):
        normalized = rule.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(rule)
    return deduped


def prompt_instructions_from_payload(provider_id: str, payload: Any) -> PromptInstructions:
    """Build PromptInstructions from canonical or legacy/custom YAML payloads."""
    if isinstance(payload, dict):
        candidate_rules: list[CandidateRule] = []
        for candidate in payload.get("candidate_rules", []) or []:
            if not isinstance(candidate, dict):
                continue
            try:
                candidate_rules.append(CandidateRule.model_validate(candidate))
            except Exception:
                continue

        return PromptInstructions(
            version=str(payload.get("version", "1.0.0")),
            provider_id=str(payload.get("provider_id", provider_id)),
            rules=extract_business_rule_texts(payload),
            candidate_rules=candidate_rules,
        )

    return PromptInstructions(
        provider_id=provider_id,
        rules=extract_business_rule_texts(payload),
    )


def compile_semantic_policy(provider_id: str, payload: Any) -> SemanticPolicy:
    """Compile executable semantic policy facts from business-rule text."""
    rules = extract_business_rule_texts(payload)

    time_windows: list[TimeWindowPolicy] = []
    time_window_by_key: dict[tuple[tuple[str, ...], bool, BoundaryMode], TimeWindowPolicy] = {}
    gb_divisor: int | None = None
    tb_divisor: int | None = None
    ending_on_inclusive = False

    for rule in rules:
        normalized = rule.casefold()

        if "period ending on x is inclusive of day x" in normalized:
            ending_on_inclusive = True

        if (
            "for daily_stats tables with date column" in normalized
            and "window ending on x" in normalized
        ):
            key = (
                ("daily_stats",),
                ending_on_inclusive or "date <= date 'x'" in normalized,
                BoundaryMode.EXCLUSIVE_UPPER_BOUND,
            )
            if key not in time_window_by_key:
                time_window_by_key[key] = TimeWindowPolicy(
                    applies_to=list(key[0]),
                    end_inclusive=key[1],
                    end_parameter_mode=key[2],
                )

        if gb_divisor is None:
            match = _IEC_GB_RE.search(rule)
            if match:
                gb_divisor = int(match.group(1))
        if tb_divisor is None:
            match = _IEC_TB_RE.search(rule)
            if match:
                tb_divisor = int(match.group(1))

    time_windows.extend(time_window_by_key.values())
    unit_conversion = None
    if gb_divisor is not None or tb_divisor is not None:
        unit_conversion = UnitConversionPolicy(
            gb_divisor=gb_divisor,
            tb_divisor=tb_divisor,
        )

    return SemanticPolicy(
        provider_id=provider_id,
        time_windows=time_windows,
        unit_conversion=unit_conversion,
    )
