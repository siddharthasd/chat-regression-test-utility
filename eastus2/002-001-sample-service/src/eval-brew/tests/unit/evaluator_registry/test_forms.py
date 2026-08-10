"""parse_evaluator_form + dimension tests (US1/US3, FR-002/004/005/007-011)."""

from __future__ import annotations

from harness.evaluator_registry import parse_evaluator_form
from harness.evaluator_registry.forms import duplicate_dimensions, parse_dimensions, parse_thresholds_field


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
    payload, _ = parse_evaluator_form(
        _form(dimensions="c\na\nb", score_scale_min="0", score_scale_max="1")
    )
    assert payload["declared_scoring_dimensions"] == ["c", "a", "b"]  # SC-011


def test_dimensions_trim_and_drop_blanks() -> None:
    payload, _ = parse_evaluator_form(
        _form(dimensions="  a  \n\n   \n b \n", score_scale_min="0", score_scale_max="1")
    )
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


# ------------------------------------------------------------------ client-credentials
def test_client_credentials_descriptor() -> None:
    payload, errors = parse_evaluator_form(
        _form(
            auth_mode="client-credentials",
            token_url="https://idp.test/token",
            client_id="cid",
            client_secret="sec",
            scope="a b",
            audience="aud",
        )
    )
    assert errors == {}
    assert payload["auth_descriptor"] == {
        "mode": "client-credentials",
        "tokenUrl": "https://idp.test/token",
        "clientId": "cid",
        "clientSecret": "sec",
        "scope": "a b",
        "audience": "aud",
    }


def test_client_credentials_requires_token_url_client_id_secret() -> None:
    _, errors = parse_evaluator_form(_form(auth_mode="client-credentials"))
    assert "token_url" in errors
    assert "client_id" in errors
    assert "client_secret" in errors


def test_client_credentials_secret_optional_without_replace() -> None:
    payload, errors = parse_evaluator_form(
        _form(auth_mode="client-credentials", token_url="https://idp.test/token", client_id="cid"),
        require_credential=False,
    )
    assert errors == {}
    assert payload["auth_descriptor"]["clientSecret"] == ""


# ------------------------------------------------------------------ FR-001/002/005/006/007 scale
def test_eleven_dimensions_rejected() -> None:
    dims = "\n".join(f"dim{i}" for i in range(11))
    _, errors = parse_evaluator_form(_form(dimensions=dims))
    assert "dimensions" in errors
    assert "11" in errors["dimensions"]


def test_duplicate_dimensions_blocked() -> None:
    _, errors = parse_evaluator_form(_form(dimensions="a\nb\na"))
    assert "dimensions" in errors
    assert "'a'" in errors["dimensions"]


def test_one_dim_missing_scale_requires_both() -> None:
    _, errors = parse_evaluator_form(_form(dimensions="accuracy"))
    assert "score_scale_min" in errors
    assert "score_scale_max" in errors


def test_zero_dims_missing_scale_accepted() -> None:
    payload, errors = parse_evaluator_form(_form(dimensions=""))
    assert "score_scale_min" not in errors
    assert "score_scale_max" not in errors
    assert payload["declared_scoring_dimensions"] == []


def test_scale_min_equal_max_rejected() -> None:
    _, errors = parse_evaluator_form(
        _form(dimensions="accuracy", score_scale_min="5", score_scale_max="5")
    )
    assert "score_scale_min" in errors


def test_scale_min_greater_than_max_rejected() -> None:
    _, errors = parse_evaluator_form(
        _form(dimensions="accuracy", score_scale_min="10", score_scale_max="0")
    )
    assert "score_scale_min" in errors


def test_non_numeric_scale_field_rejected() -> None:
    _, errors = parse_evaluator_form(
        _form(dimensions="accuracy", score_scale_min="abc", score_scale_max="1")
    )
    assert "score_scale_min" in errors


def test_valid_scale_in_payload() -> None:
    payload, errors = parse_evaluator_form(
        _form(dimensions="accuracy", score_scale_min="0", score_scale_max="10")
    )
    assert errors == {}
    assert payload["score_scale_min"] == 0.0
    assert payload["score_scale_max"] == 10.0


def test_zero_scale_min_accepted() -> None:
    payload, errors = parse_evaluator_form(
        _form(dimensions="accuracy", score_scale_min="0", score_scale_max="1")
    )
    assert errors == {}
    assert payload["score_scale_min"] == 0.0
    assert payload["score_scale_max"] == 1.0


# ── BL-004: scoring threshold form parsing ────────────────────────────────────

def test_valid_thresholds_parsed_to_payload() -> None:
    raw = '{"accuracy": {"pass": 0.80, "warn": 0.60}}'
    thresholds, err = parse_thresholds_field(raw)
    assert err is None
    assert thresholds == {"accuracy": {"pass": 0.80, "warn": 0.60}}


def test_invalid_json_returns_error() -> None:
    _, err = parse_thresholds_field("{bad json}")
    assert err is not None and "Invalid JSON" in err


def test_pass_le_warn_returns_error() -> None:
    raw = '{"accuracy": {"pass": 0.50, "warn": 0.80}}'
    _, err = parse_thresholds_field(raw)
    assert err is not None and "pass" in err and "warn" in err


def test_blank_thresholds_returns_none_no_error() -> None:
    thresholds, err = parse_thresholds_field("   ")
    assert thresholds is None and err is None


def test_missing_warn_key_returns_error() -> None:
    raw = '{"accuracy": {"pass": 0.80}}'
    _, err = parse_thresholds_field(raw)
    assert err is not None and "warn" in err
