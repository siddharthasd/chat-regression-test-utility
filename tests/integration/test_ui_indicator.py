"""US3 integration tests — 'Logged in as: <user>' UI indicator (FR-005).

Verifies the indicator is present on every UI page, non-interactive, and
XSS-safe (the tester identity rendered as text, never as HTML).

Until 002 / 003 / 004 implement actual routes, the test uses a small stub
blueprint that exercises Jinja's render-template path with the indicator
included. The same context processor that wires the indicator into real
pages also wires it into this stub — so this test verifies the wiring
mechanism end-to-end.
"""

from __future__ import annotations

import pytest
from flask import Flask, render_template_string

from harness.ui import create_app
from harness.ui.context_processors import inject_tester_identity


@pytest.fixture
def app(stub_identity) -> Flask:
    """Yield a Flask app with the stub identity and a tiny test blueprint."""
    stub_identity.with_identity("alice")
    app = create_app()
    app.testing = True

    @app.route("/test-page")
    def _test_page() -> str:
        # Mirrors the structure real pages will use: the partial template is
        # rendered via {% include %} in the base layout. For this test we
        # inline the partial's render directly.
        return render_template_string(
            "<html><body><main>page body</main>"
            "{% include '_logged_in_as.html' %}"
            "</body></html>"
        )

    @app.route("/another-page")
    def _another_page() -> str:
        return render_template_string(
            "<html><body><h1>Another</h1>"
            "{% include '_logged_in_as.html' %}"
            "</body></html>"
        )

    return app


def test_indicator_present_on_every_page(app: Flask) -> None:
    """FR-005 / SC-004 wiring verification.

    NOTE: This test exercises 2 stub routes. Real FR-005 acceptance — "indicator
    on dashboard / wizard / detail view" — lands when 002 / 003 / 004 are
    implemented and the test grows to parametrize over those real routes.
    Today this test verifies the wiring mechanism (context processor +
    template partial) end-to-end against the Flask test client.
    """
    client = app.test_client()

    for route in ("/test-page", "/another-page"):
        response = client.get(route)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Logged in as: alice" in body, (
            f"Indicator missing from {route}: response body did not contain "
            f"'Logged in as: alice'."
        )


def test_indicator_is_non_interactive(app: Flask) -> None:
    """FR-005: indicator MUST be read-only (no <a> / <button> / form controls)."""
    client = app.test_client()
    response = client.get("/test-page")
    body = response.get_data(as_text=True)

    # The indicator's surrounding markup should not be interactive.
    # We grab the snippet around 'Logged in as' and assert no anchor / button / form tag.
    idx = body.find("Logged in as:")
    assert idx != -1
    surrounding = body[max(0, idx - 100) : idx + 200]
    for forbidden in ("<a ", "<a>", "<button", "<form", "<input"):
        assert forbidden not in surrounding, (
            f"Indicator surrounding markup contains interactive element {forbidden!r}: "
            f"{surrounding!r}"
        )


def test_indicator_escapes_html_chars(stub_identity) -> None:
    """SC-010 / XSS-safety: a malicious-looking identity string is escaped."""
    stub_identity.with_identity("<script>alert(1)</script>")
    app = create_app()
    app.testing = True

    @app.route("/xss-test")
    def _xss_test() -> str:
        return render_template_string(
            "<html><body>{% include '_logged_in_as.html' %}</body></html>"
        )

    client = app.test_client()
    response = client.get("/xss-test")
    body = response.get_data(as_text=True)

    # The raw <script> tag MUST NOT appear (Jinja auto-escapes <, >, &).
    assert "<script>alert(1)</script>" not in body
    # The escaped form MUST appear (so the tester can still SEE the literal
    # string they configured, just rendered safely as text).
    assert "&lt;script&gt;" in body or "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_context_processor_returns_identity(stub_identity) -> None:
    """Unit-style: the context processor function returns the right dict shape."""
    stub_identity.with_identity("bob")

    result = inject_tester_identity()

    assert result == {"tester_identity": "bob"}
