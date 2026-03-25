"""Gold execution and deterministic scoring."""

from __future__ import annotations

import json
import re
from typing import Any

from db_mcp.benchmark.models import BenchmarkCase, ScoreResult


def execute_gold_sql(connector, case: BenchmarkCase) -> list[dict[str, Any]]:
    """Execute gold SQL for a benchmark case."""
    return connector.execute_sql(case.gold_sql)


def _apply_normalization(value: Any, ops: list[str]) -> Any:
    if isinstance(value, str):
        result = value
        for op in ops:
            if op == "strip":
                result = result.strip()
            elif op == "lower":
                result = result.lower()
            elif op == "collapse_whitespace":
                result = re.sub(r"\s+", " ", result).strip()
        return result
    if isinstance(value, list):
        return [_apply_normalization(item, ops) for item in value]
    if isinstance(value, dict):
        return {key: _apply_normalization(val, ops) for key, val in value.items()}
    return value


def _first_scalar(rows: list[dict[str, Any]]) -> Any:
    if not rows:
        return None
    first_row = rows[0]
    if not first_row:
        return None
    return next(iter(first_row.values()))


def _rows_as_canonical_set(rows: list[dict[str, Any]], ops: list[str]) -> list[str]:
    normalized = [_apply_normalization(row, ops) for row in rows]
    return sorted(json.dumps(row, sort_keys=True, default=str) for row in normalized)


def _canonicalize_set_values(values: list[Any], ops: list[str]) -> list[str]:
    return sorted(
        json.dumps(_apply_normalization(item, ops), default=str)
        for item in values
    )


def _normalize_numeric_text(value: str) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", value)


def _scalar_exact_match(
    expected: Any,
    answer_value: Any,
    answer_text: str,
    ops: list[str],
) -> tuple[bool, Any, str]:
    actual = _apply_normalization(answer_value, ops)
    if actual == expected:
        return True, actual, ""

    if not isinstance(expected, str):
        candidates: list[Any] = []
        if isinstance(actual, dict):
            candidates.extend(actual.values())
        elif isinstance(actual, list):
            candidates.extend(actual)
        if any(candidate == expected for candidate in candidates):
            return True, actual, "matched_via_object_fields"
        return False, actual, ""

    candidates: list[Any] = []
    if isinstance(actual, dict):
        for key in ("answer", "name", "title", "full_name"):
            if key in actual:
                candidates.append(actual[key])
        first_name = actual.get("first_name")
        last_name = actual.get("last_name")
        if isinstance(first_name, str) and isinstance(last_name, str):
            candidates.append(f"{first_name} {last_name}".strip())
        candidates.extend(value for value in actual.values() if isinstance(value, str))
    elif isinstance(actual, list):
        candidates.extend(item for item in actual if isinstance(item, str))

    if any(candidate == expected for candidate in candidates):
        return True, actual, "matched_via_object_fields"

    normalized_text = _apply_normalization(answer_text, ops)
    if isinstance(normalized_text, str) and expected in normalized_text:
        return True, actual, "matched_via_answer_text"

    return False, actual, ""


def score_case(
    case: BenchmarkCase,
    expected_rows: list[dict[str, Any]],
    answer_payload: dict,
) -> ScoreResult:
    """Score one answer against the gold result for a case."""
    status = answer_payload.get("status")
    answer_value = answer_payload.get("answer_value")
    answer_text = answer_payload.get("answer_text", "")
    ops = case.normalization

    if status != "answered":
        return ScoreResult(
            case_id=case.id,
            comparison=case.comparison,
            correct=False,
            expected=expected_rows,
            actual=answer_payload,
            details=f"status={status}",
        )

    if case.comparison == "scalar_exact":
        expected = _apply_normalization(_first_scalar(expected_rows), ops)
        correct, actual, details = _scalar_exact_match(expected, answer_value, answer_text, ops)
        return ScoreResult(
            case_id=case.id,
            comparison=case.comparison,
            correct=correct,
            expected=expected,
            actual=actual,
            details=details,
        )

    if case.comparison == "scalar_numeric_tolerance":
        expected = float(_first_scalar(expected_rows))
        actual = float(answer_value)
        tolerance = case.tolerance or 0.0
        return ScoreResult(
            case_id=case.id,
            comparison=case.comparison,
            correct=abs(actual - expected) <= tolerance,
            expected=expected,
            actual=actual,
            details=f"tolerance={tolerance}",
        )

    if case.comparison == "rowset_unordered":
        expected = _rows_as_canonical_set(expected_rows, ops)
        answer_rows = answer_payload.get("answer_rows")
        if isinstance(answer_rows, list):
            actual_rows = answer_rows
        elif isinstance(answer_value, list):
            actual_rows = answer_value
        elif isinstance(answer_value, dict):
            actual_rows = [answer_value]
        else:
            actual_rows = []
        actual = _rows_as_canonical_set(actual_rows, ops)
        return ScoreResult(
            case_id=case.id,
            comparison=case.comparison,
            correct=actual == expected,
            expected=expected,
            actual=actual,
        )

    if case.comparison == "set_unordered":
        expected = sorted(
            json.dumps(_apply_normalization(next(iter(row.values())), ops), default=str)
            for row in expected_rows
        )
        candidate_value_sets: list[list[Any]] = []
        if isinstance(answer_value, list):
            candidate_value_sets.append(answer_value)
        elif isinstance(answer_value, dict):
            candidate_value_sets.append(list(answer_value.keys()))
            candidate_value_sets.append(list(answer_value.values()))
        else:
            candidate_value_sets.append([answer_value])

        actual = _canonicalize_set_values(candidate_value_sets[0], ops)
        correct = actual == expected
        details = ""
        for index, candidate_values in enumerate(candidate_value_sets[1:], start=1):
            candidate_actual = _canonicalize_set_values(candidate_values, ops)
            if candidate_actual == expected:
                actual = candidate_actual
                correct = True
                details = f"matched_via_candidate_set_{index}"
                break
        return ScoreResult(
            case_id=case.id,
            comparison=case.comparison,
            correct=correct,
            expected=expected,
            actual=actual,
            details=details,
        )

    if case.comparison == "contains_text":
        expected = str(_apply_normalization(_first_scalar(expected_rows), ops) or "")
        actual = str(_apply_normalization(answer_text, ops))
        correct = expected in actual
        details = ""
        if not correct:
            normalized_expected = _normalize_numeric_text(expected)
            normalized_actual = _normalize_numeric_text(actual)
            correct = normalized_expected in normalized_actual
            if correct:
                details = "matched_via_numeric_text_normalization"
        return ScoreResult(
            case_id=case.id,
            comparison=case.comparison,
            correct=correct,
            expected=expected,
            actual=actual,
            details=details,
        )

    raise ValueError(f"Unsupported comparison mode: {case.comparison}")
