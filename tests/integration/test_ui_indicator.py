"""US3 integration tests — 'Logged in as: <user>' UI indicator (FR-005).

Verifies the indicator is present on real pages, non-interactive, and
XSS-safe (the tester identity rendered as text, never as HTML).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from harness.ui import create_app


@pytest.fixture
def client(tmp_path, monkeypatch, stub_identity):
    """Yield a TestClient with alice as the stub identity."""
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "ui.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "ui.key"))
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "ui.db")
    stub_identity.with_identity("alice")
    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def test_indicator_present_on_dashboard(client) -> None:
    """FR-005 / SC-004: 'Logged in as: alice' appears on the dashboard page."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "Logged in as: alice" in body, (
        "Indicator missing from dashboard: response body did not contain "
        "'Logged in as: alice'."
    )


def test_indicator_is_non_interactive(client) -> None:
    """FR-005: indicator MUST be read-only (no <a> / <button> / form controls)."""
    response = client.get("/")
    body = response.text

    idx = body.find("Logged in as:")
    assert idx != -1
    surrounding = body[max(0, idx - 100) : idx + 200]
    for forbidden in ("<a ", "<a>", "<button", "<form", "<input"):
        assert forbidden not in surrounding, (
            f"Indicator surrounding markup contains interactive element {forbidden!r}: "
            f"{surrounding!r}"
        )


def test_indicator_escapes_html_chars(tmp_path, monkeypatch, stub_identity) -> None:
    """SC-010 / XSS-safety: a malicious-looking identity string is escaped."""
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "ui.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "ui.key"))
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "ui.db")
    stub_identity.with_identity("<script>alert(1)</script>")
    xss_client = TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)

    response = xss_client.get("/")
    body = response.text

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body or "alert" not in body
