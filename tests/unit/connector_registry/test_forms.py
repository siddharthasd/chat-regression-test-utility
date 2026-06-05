"""parse_connector_form tests (US1, FR-004/005)."""

from __future__ import annotations

from harness.connector_registry import parse_connector_form


def _form(**over) -> dict:
    base = {
        "display_name": "C",
        "endpoint_url": "https://c.test",
        "auth_mode": "none",
        "timeout_seconds": "30",
    }
    base.update(over)
    return base


def test_valid_none_mode() -> None:
    payload, errors = parse_connector_form(_form())
    assert errors == {}
    assert payload["auth_descriptor"] == {"mode": "none"}
    assert payload["timeout_seconds"] == 30


def test_missing_display_name() -> None:
    _, errors = parse_connector_form(_form(display_name=""))
    assert "display_name" in errors


def test_bad_url() -> None:
    _, errors = parse_connector_form(_form(endpoint_url="not-a-url"))
    assert "endpoint_url" in errors


def test_timeout_out_of_range() -> None:
    _, errors = parse_connector_form(_form(timeout_seconds="999"))
    assert "timeout_seconds" in errors


def test_bearer_requires_token() -> None:
    _, errors = parse_connector_form(_form(auth_mode="bearer"))
    assert "token" in errors


def test_bearer_descriptor() -> None:
    payload, errors = parse_connector_form(_form(auth_mode="bearer", token="tok"))
    assert errors == {}
    assert payload["auth_descriptor"] == {"mode": "bearer", "credential": "tok"}


def test_api_key_requires_both_fields() -> None:
    _, errors = parse_connector_form(_form(auth_mode="api-key-header"))
    assert "header_name" in errors
    assert "header_value" in errors


def test_basic_descriptor() -> None:
    payload, errors = parse_connector_form(_form(auth_mode="basic", username="u", password="p"))
    assert errors == {}
    assert payload["auth_descriptor"] == {"mode": "basic", "username": "u", "password": "p"}


def test_require_credential_false_skips_secret() -> None:
    payload, errors = parse_connector_form(_form(auth_mode="bearer"), require_credential=False)
    assert errors == {}  # token not required when editing without replace
    assert payload["auth_descriptor"]["mode"] == "bearer"


def test_client_credentials_descriptor() -> None:
    payload, errors = parse_connector_form(
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


def test_client_credentials_requires_token_url_and_client_id_and_secret() -> None:
    _, errors = parse_connector_form(_form(auth_mode="client-credentials"))
    assert "token_url" in errors
    assert "client_id" in errors
    assert "client_secret" in errors


def test_client_credentials_rejects_bad_token_url() -> None:
    _, errors = parse_connector_form(
        _form(auth_mode="client-credentials", token_url="nope", client_id="c", client_secret="s")
    )
    assert "token_url" in errors


def test_client_credentials_omits_blank_scope_audience() -> None:
    payload, errors = parse_connector_form(
        _form(
            auth_mode="client-credentials",
            token_url="https://idp.test/token",
            client_id="cid",
            client_secret="sec",
        )
    )
    assert errors == {}
    assert "scope" not in payload["auth_descriptor"]
    assert "audience" not in payload["auth_descriptor"]


def test_client_credentials_secret_optional_without_replace() -> None:
    payload, errors = parse_connector_form(
        _form(auth_mode="client-credentials", token_url="https://idp.test/token", client_id="cid"),
        require_credential=False,
    )
    assert errors == {}  # secret not required when editing without replace
    assert payload["auth_descriptor"]["clientSecret"] == ""
