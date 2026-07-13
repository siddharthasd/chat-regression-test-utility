"""EvaluationResult validation + harness annotation derivation (FR-003/004/005/005a/005b)."""

from __future__ import annotations

from datetime import datetime

from harness.evaluator.result import VERDICTS

_REQUIRED_FIELDS = (
    "utteranceId",
    "evaluationAgentId",
    "evaluationTimestamp",
    "evaluationScores",
    "evaluationVerdict",
    "metadata",
)


def _is_iso8601(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_evaluation_result(body: object, *, expected_utterance_id: str | None) -> list[str]:
    """Return a list of FR-005b problems (empty ⇒ valid). Never raises.

    `evaluationAgentId` mismatch is intentionally NOT a problem (soft warning).
    """
    if not isinstance(body, dict):
        return ["response body is not a JSON object"]

    problems: list[str] = []
    for field in _REQUIRED_FIELDS:
        if field not in body:
            problems.append(f"missing required field {field!r}")

    def _check_type(field: str, types: type | tuple[type, ...], label: str) -> bool:
        if field in body and not isinstance(body[field], types):
            problems.append(f"{field} must be {label}, got {type(body[field]).__name__}")
            return False
        return True

    _check_type("utteranceId", str, "a string")
    _check_type("evaluationAgentId", str, "a string")
    _check_type("evaluationTimestamp", str, "a string")
    _check_type("evaluationScores", list, "an array")
    _check_type("evaluationVerdict", str, "a string")
    _check_type("metadata", dict, "an object")

    uid = body.get("utteranceId")
    if isinstance(uid, str) and expected_utterance_id is not None and uid != expected_utterance_id:
        problems.append(
            f"utteranceId {uid!r} does not match the contract's {expected_utterance_id!r}"
        )

    verdict = body.get("evaluationVerdict")
    if isinstance(verdict, str) and verdict not in VERDICTS:
        problems.append(f"evaluationVerdict {verdict!r} is not one of pass/fail/warn")

    scores = body.get("evaluationScores")
    if isinstance(scores, list):
        for i, entry in enumerate(scores):
            if not isinstance(entry, dict):
                problems.append(f"evaluationScores[{i}] is not an object")
                continue
            if not isinstance(entry.get("parameter_name"), str):
                problems.append(f"evaluationScores[{i}].parameter_name must be a string")
            score = entry.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float, str)):
                problems.append(f"evaluationScores[{i}].score must be a number or string")
            if not isinstance(entry.get("reasoning"), str):
                problems.append(f"evaluationScores[{i}].reasoning must be a string")

    ts = body.get("evaluationTimestamp")
    if isinstance(ts, str) and not _is_iso8601(ts):
        problems.append(f"evaluationTimestamp {ts!r} is not a valid ISO-8601 datetime")

    return problems


def compute_harness_annotations(scores: list, declared_dimensions: list[str]) -> dict:
    """Derive harness annotations: parameter_names emitted but not declared (FR-005a)."""
    declared = set(declared_dimensions or [])
    unexpected: list[str] = []
    seen: set[str] = set()
    for entry in scores or []:
        if isinstance(entry, dict):
            name = entry.get("parameter_name")
            if isinstance(name, str) and name not in declared and name not in seen:
                unexpected.append(name)
                seen.add(name)
    return {"unexpected_score_dimensions": unexpected}
