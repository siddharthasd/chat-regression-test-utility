"""Auth-header builder tests (US3, FR-007a-d/FR-008)."""

from __future__ import annotations

import base64

import pytest

from harness.connector import build_auth_headers


def test_none_adds_no_header() -> None:
    assert build_auth_headers({"mode": "none"}) == {}


def test_bearer() -> None:
    assert build_auth_headers({"mode": "bearer", "credential": "tok"}) == {
        "Authorization": "Bearer tok"
    }


def test_api_key_header() -> None:
    headers = build_auth_headers(
        {"mode": "api-key-header", "headerName": "X-Api-Key", "credential": "k"}
    )
    assert headers == {"X-Api-Key": "k"}


def test_basic() -> None:
    headers = build_auth_headers({"mode": "basic", "username": "u", "password": "p"})
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"u:p").decode("ascii")


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError):
        build_auth_headers({"mode": "oauth2"})
