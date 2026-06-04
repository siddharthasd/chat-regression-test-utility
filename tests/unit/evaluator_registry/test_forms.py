"""parse_evaluator_form + dimension tests (US1/US3, FR-002/004/005/007-011)."""

from __future__ import annotations

from harness.evaluator_registry import parse_evaluator_form
from harness.evaluator_registry.forms import duplicate_dimensions, parse_dimensions


def _form(**over) -> dict:
    base = {
        "display_name": "E",
        "description": "scores relevance",
        "endpoint_url": "https://e.test",
        "auth_mode": "none",
        "timeout_seconds": "60",
    }
    base.update(over)
    return base


def test_valid_none_mode() -> None:
    payload, errors = parse_evaluator_form(_form())
    assert errors == {}
    assert payload["auth_descriptor"] == {"mode": "none"}
    assert payload["timeout_seconds"] == 60
    assert payload["declared_scoring_dimensions"] == []


def test_description_required() -> None:
    _, errors = parse_evaluator_form(_form(description=""))
    assert "description" in errors


def test_bad_url() -> None:
    _, errors = parse_evaluator_form(_form(endpoint_url="nope"))
    assert "endpoint_url" in errors


def test_timeout_out_of_range() -> None:
    _, errors = parse_evaluator_form(_form(timeout_seconds="9999"))
    assert "timeout_seconds" in errors


def test_bearer_requires_token() -> None:
    _, errors = parse_evaluator_form(_form(auth_mode="bearer"))
    assert "token" in errors


def test_basic_descriptor() -> None:
    payload, errors = parse_evaluator_form(_form(auth_mode="basic", username="u", password="p"))
    assert errors == {}
    assert payload["auth_descriptor"] == {"mode": "basic", "username": "u", "password": "p"}


# ------------------------------------------------------------------ US3 dimensions
def test_dimensions_order_preserved() -> None:
    payload, _ = parse_evaluator_form(_form(dimensions="c\na\nb"))
    assert payload["declared_scoring_dimensions"] == ["c", "a", "b"]  # SC-011


def test_dimensions_trim_and_drop_blanks() -> None:
    payload, _ = parse_evaluator_form(_form(dimensions="  a  \n\n   \n b \n"))
    assert payload["declared_scoring_dimensions"] == ["a", "b"]


def test_dimensions_empty_ok() -> None:
    payload, errors = parse_evaluator_form(_form(dimensions=""))
    assert errors == {}
    assert payload["declared_scoring_dimensions"] == []


def test_duplicate_dimensions_detected() -> None:
    assert duplicate_dimensions(["a", "b", "a"]) == ["a"]


def test_parse_dimensions_helper() -> None:
    assert parse_dimensions("x\n y \n\nz") == ["x", "y", "z"]


def test_require_credential_false_skips_secret() -> None:
    payload, errors = parse_evaluator_form(_form(auth_mode="bearer"), require_credential=False)
    assert errors == {}
    assert payload["auth_descriptor"]["mode"] == "bearer"
