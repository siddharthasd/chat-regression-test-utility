"""EvaluationResult validation + annotation tests (US1 FR-005b; US3 FR-005a)."""

from __future__ import annotations

from harness.evaluator import compute_harness_annotations, validate_evaluation_result


def _good(uid: str = "u-1", dims: tuple[str, ...] = ("relevance",)) -> dict:
    return {
        "utteranceId": uid,
        "evaluationAgentId": "mock-evaluator",
        "evaluationTimestamp": "2026-06-04T12:00:00Z",
        "evaluationScores": [
            {"parameter_name": d, "score": 0.5, "reasoning": "ok"} for d in dims
        ],
        "evaluationVerdict": "pass",
        "metadata": {},
    }


def _problems(body: dict, uid: str = "u-1") -> list[str]:
    return validate_evaluation_result(body, expected_utterance_id=uid)


# ------------------------------------------------------------------ FR-005b
def test_valid_result_has_no_problems() -> None:
    assert validate_evaluation_result(_good(), expected_utterance_id="u-1") == []


def test_non_object_rejected() -> None:
    assert validate_evaluation_result([1, 2, 3], expected_utterance_id="u-1")


def test_missing_field_named() -> None:
    body = _good()
    del body["evaluationVerdict"]
    assert any("evaluationVerdict" in p for p in _problems(body))


def test_utterance_id_mismatch_rejected() -> None:
    problems = validate_evaluation_result(_good(uid="OTHER"), expected_utterance_id="u-1")
    assert any("utteranceId" in p for p in problems)


def test_bad_verdict_rejected() -> None:
    body = _good()
    body["evaluationVerdict"] = "inconclusive"
    assert any("evaluationVerdict" in p for p in _problems(body))


def test_bad_scores_entry_rejected() -> None:
    body = _good()
    body["evaluationScores"] = [{"parameter_name": "x", "score": 0.1}]  # missing reasoning
    assert any("reasoning" in p for p in _problems(body))


def test_bad_timestamp_rejected() -> None:
    body = _good()
    body["evaluationTimestamp"] = "not-a-date"
    assert any("ISO-8601" in p for p in _problems(body))


def test_wrong_type_scores_rejected() -> None:
    body = _good()
    body["evaluationScores"] = "notanarray"
    assert any("evaluationScores" in p for p in _problems(body))


def test_agent_id_mismatch_not_rejected() -> None:
    body = _good()
    body["evaluationAgentId"] = "some-other-id"  # soft warning, not a reject
    assert _problems(body) == []


def test_empty_scores_valid() -> None:
    body = _good()
    body["evaluationScores"] = []
    assert _problems(body) == []


# ------------------------------------------------------------------ US3 annotations
def test_annotations_empty_when_aligned() -> None:
    scores = [{"parameter_name": "a", "score": 1, "reasoning": "r"}]
    assert compute_harness_annotations(scores, ["a", "b"]) == {"unexpected_score_dimensions": []}


def test_annotations_lists_unexpected_first_seen_order() -> None:
    scores = [
        {"parameter_name": "a", "score": 1, "reasoning": "r"},
        {"parameter_name": "z", "score": 1, "reasoning": "r"},
        {"parameter_name": "z", "score": 1, "reasoning": "r"},
    ]
    assert compute_harness_annotations(scores, ["a"]) == {"unexpected_score_dimensions": ["z"]}
