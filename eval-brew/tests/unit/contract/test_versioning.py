"""Versioning tests (US4): numeric gate, determinism, additive vs breaking policy.

Covers FR-006/007/011/015/016 and SC-004/006/007/009.
"""

from __future__ import annotations

import copy

import pytest

from harness.contract import ViolationKind, validate_contract
from harness.contract import validation as validation_mod


def _good() -> dict:
    return {
        "contractVersion": "1",
        "utteranceId": "u-1",
        "utteranceText": "hi",
        "testId": "row-1",
        "conversationContext": None,
        "connectorId": "conn-abc",
        "timestamp": "2026-06-03T12:00:00Z",
        "chatbotResponse": {
            "rawPayload": {},
            "normalizedText": "hello",
            "agentChain": [],
            "metadata": {},
        },
    }


def test_version_greater_rejected_names_both() -> None:
    instance = _good()
    instance["contractVersion"] = "2"
    result = validate_contract(instance)
    assert result.valid is False
    v = next(v for v in result.violations if v.kind is ViolationKind.VERSION_OUT_OF_RANGE)
    assert "2" in v.message and "1" in v.message
    assert "update the harness" in v.message.lower()


def test_numeric_not_lexicographic(monkeypatch: pytest.MonkeyPatch) -> None:
    # With a bundled version of 2: "10" must be rejected (10 > 2) and "2" accepted.
    # Lexicographic comparison would wrongly accept "10" (since "10" < "2").
    monkeypatch.setattr(validation_mod, "BUNDLED_CONTRACT_VERSION", 2)

    at_10 = _good()
    at_10["contractVersion"] = "10"
    assert validate_contract(at_10).valid is False

    at_2 = _good()
    at_2["contractVersion"] = "2"
    assert validate_contract(at_2).valid is True


def test_older_version_accepted() -> None:
    # An instance below the bundled version still conforms (FR-006/FR-015).
    monkeypatch_bundled = _good()
    monkeypatch_bundled["contractVersion"] = "1"  # bundled is 1; equal accepted
    assert validate_contract(monkeypatch_bundled).valid is True


def test_determinism() -> None:
    instance = _good()
    del instance["utteranceId"]
    instance["timestamp"] = "nope"
    first = validate_contract(instance)
    second = validate_contract(copy.deepcopy(instance))
    assert first == second  # same flag, same violation list (order/content/count)


# --------------------------------------------------------------------------- #
# Versioning policy (FR-006 / FR-007) — codified dev-time check (SC-006/007).  #
# A test-local breaking-change detector standing in for the review checklist.  #
# --------------------------------------------------------------------------- #


def _is_breaking_change(
    old_props: dict, new_props: dict, old_required: set, new_required: set
) -> bool:
    """True iff the change requires a contractVersion bump (FR-007)."""
    # Removed or renamed field (a removal shows as a key missing from new).
    if set(old_props) - set(new_props):
        return True
    # Type changed on a retained field.
    for name in set(old_props) & set(new_props):
        if old_props[name].get("type") != new_props[name].get("type"):
            return True
    # A previously-optional field made required.
    if (new_required - old_required) - (set(new_props) - set(old_props)):
        return True
    return False


def test_additive_no_bump() -> None:
    old = {"a": {"type": "string"}}
    new = {"a": {"type": "string"}, "b": {"type": "string"}}  # added optional field
    assert _is_breaking_change(old, new, {"a"}, {"a"}) is False


def test_breaking_change_policy() -> None:
    base = {"a": {"type": "string"}, "b": {"type": "string"}}
    retyped = {"a": {"type": "integer"}, "b": {"type": "string"}}
    removed = {"a": {"type": "string"}}
    assert _is_breaking_change(base, removed, {"a"}, {"a"}) is True  # removed field
    assert _is_breaking_change(base, retyped, set(), set()) is True  # type changed
    assert _is_breaking_change(base, base, {"a"}, {"a", "b"}) is True  # made required
