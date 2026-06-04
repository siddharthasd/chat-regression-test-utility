"""validate_contract behaviour tests: US1 (accept), US2 (reject), US3 (extensibility).

Covers SC-001/002/003/005 and FR-004/013.
"""

from __future__ import annotations

import copy

from harness.contract import ViolationKind, validate_contract


def _good() -> dict:
    return {
        "contractVersion": "1",
        "utteranceId": "11111111-1111-4111-8111-111111111111",
        "utteranceText": "What is my balance?",
        "testId": "row-1",
        "conversationContext": None,
        "connectorId": "conn-abc",
        "timestamp": "2026-06-03T12:00:00Z",
        "chatbotResponse": {
            "rawPayload": {"text": "Your balance is $100."},
            "normalizedText": "Your balance is $100.",
            "agentChain": [],
            "metadata": {},
        },
    }


def _kinds(result) -> set[ViolationKind]:
    return {v.kind for v in result.violations}


def _paths(result) -> set[str]:
    return {v.field_path for v in result.violations}


# ------------------------------------------------------------------ US1
def test_conformant_instance_passes() -> None:
    result = validate_contract(_good())
    assert result.valid is True
    assert result.violations == []
    assert result.contract_version == "1"


def test_required_values_preserved() -> None:
    instance = _good()
    before = copy.deepcopy(instance)
    validate_contract(instance)
    assert instance == before  # validation does not mutate the input


# ------------------------------------------------------------------ US2
def test_missing_field_named() -> None:
    instance = _good()
    del instance["utteranceId"]
    result = validate_contract(instance)
    assert result.valid is False
    assert ViolationKind.MISSING in _kinds(result)
    assert any("utteranceId" in v.field_path for v in result.violations)


def test_type_mismatch_named() -> None:
    instance = _good()
    instance["chatbotResponse"]["normalizedText"] = 123  # should be string
    result = validate_contract(instance)
    assert result.valid is False
    v = next(v for v in result.violations if v.kind is ViolationKind.WRONG_TYPE)
    assert v.field_path == "chatbotResponse.normalizedText"
    assert "str" in (v.expected or "")
    assert v.observed == "int"


def test_timestamp_format_rejected() -> None:
    instance = _good()
    instance["timestamp"] = "not-a-date"
    result = validate_contract(instance)
    assert result.valid is False
    assert any(
        v.field_path == "timestamp" and v.kind is ViolationKind.BAD_FORMAT
        for v in result.violations
    )


def test_unix_epoch_timestamp_is_wrong_type() -> None:
    instance = _good()
    instance["timestamp"] = 1717416000  # integer, not an ISO string
    result = validate_contract(instance)
    assert result.valid is False
    assert any(
        v.field_path == "timestamp" and v.kind is ViolationKind.WRONG_TYPE
        for v in result.violations
    )


def test_password_forbidden_top_level() -> None:
    instance = _good()
    instance["password"] = "hunter2"
    result = validate_contract(instance)
    assert result.valid is False
    assert any(
        v.field_path == "password" and v.kind is ViolationKind.FORBIDDEN_FIELD
        for v in result.violations
    )


def test_password_forbidden_nested() -> None:
    instance = _good()
    instance["chatbotResponse"]["metadata"]["password"] = "secret"
    result = validate_contract(instance)
    assert result.valid is False
    assert "chatbotResponse.metadata.password" in _paths(result)


def test_non_object_input_does_not_crash() -> None:
    # Spec edge case: validating a non-contract object returns invalid, no raise.
    result = validate_contract(["not", "a", "contract"])
    assert result.valid is False
    assert result.contract_version is None


# ------------------------------------------------------------------ US3
def test_unknown_fields_ok() -> None:
    instance = _good()
    instance["someNewTopLevelField"] = 42
    instance["chatbotResponse"]["metadata"]["toolCallCount"] = 3
    result = validate_contract(instance)
    assert result.valid is True  # FR-005: unknown fields are conforming


def test_empty_agentchain_and_metadata_and_null_context_ok() -> None:
    instance = _good()
    instance["chatbotResponse"]["agentChain"] = []
    instance["chatbotResponse"]["metadata"] = {}
    instance["conversationContext"] = None
    assert validate_contract(instance).valid is True
