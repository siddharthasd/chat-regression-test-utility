"""US6 cross-cutting masking-rules test framework (FR-008 through FR-016).

This module is the cross-spec contract gate. The enforcement code lives in:
  - 011 (CSV upload — in-memory password store, conditional column)
  - 007 (connector wire-protocol HTTP body forwarding)
  - 004 (detail view — no password column at all)
  - 005 (export — no password column at all, not even masked)

All tests in this file are marked xfail because the enforcement code does not
exist yet on this branch. When 011/007/004/005 are implemented downstream,
each test should flip to passing — that's the contract.

The known-distinctive password used throughout: DEADBEEF-PWD-12345
"""

from __future__ import annotations

from pathlib import Path

import pytest

KNOWN_PASSWORD = "DEADBEEF-PWD-12345"
KNOWN_TESTID = "tester-alice"


pytestmark = pytest.mark.xfail(
    reason=(
        "enforcement code lives in 011/007/004/005; these tests will pass once "
        "those specs are implemented downstream. The framework is in place as "
        "a cross-spec contract gate."
    ),
    strict=False,
    run=True,
)


def _run_job_with_known_password() -> Path:
    """Simulate a job run that exercises every leak surface.

    Pseudo-flow (commented out until 011/007/012 land):
      1. Upload a CSV containing KNOWN_TESTID + KNOWN_PASSWORD via 011's
         upload endpoint, against a connector registration with
         expectsPerRowPassword=True.
      2. Start the job via 003's wizard; the orchestrator (012) runs the
         per-row pipeline: password lookup → connector HTTP POST → eviction
         → contract validation → evaluator HTTP POST → result validation
         → persist.
      3. Return the path to the SQLite database file used by the run.

    Today: raises NotImplementedError so the test fails predictably (the
    xfail marker converts this to an expected failure).
    """
    raise NotImplementedError(
        "Cross-spec dependencies (011 CSV upload, 007 connector HTTP, "
        "012 orchestrator) are not implemented yet."
    )


def _generate_export(format: str) -> bytes:
    """Generate an export of the completed job (CSV / JSON / zip)."""
    raise NotImplementedError(
        "Export generation depends on 005 results-export module."
    )


def _render_detail_view_row(row_id: str) -> str:
    """Render a row from the detail view's Results Table (HTML)."""
    raise NotImplementedError(
        "Detail view rendering depends on 004 job-detail-view module."
    )


def _capture_logs() -> str:
    """Capture all log output from the run."""
    raise NotImplementedError(
        "Log capture depends on 012 orchestrator emitting structured logs."
    )


def test_password_not_in_db() -> None:
    """SC-007 / FR-010: the SQLite database file contains zero bytes of the
    known password value after a job run that included it on every row.

    IMPLEMENTER NOTE (when 011/009 land): the encoding sweep below covers
    UTF-8 (SQLite's default for TEXT columns). Future evolution might
    store passwords in alternate encodings (UTF-16, base64, hex)
    accidentally — extend the assertion to grep for each variant if
    relevant. For v1, UTF-8 is the only realistic leak vector since
    SQLite + Python both default to UTF-8.
    """
    db_path = _run_job_with_known_password()
    raw_bytes = db_path.read_bytes()
    # UTF-8 byte sequence — covers SQLite TEXT, BLOB-storing-text, and
    # JSON-stringified values.
    assert KNOWN_PASSWORD.encode("utf-8") not in raw_bytes, (
        f"Password {KNOWN_PASSWORD!r} found in database file (UTF-8 form) — "
        f"violates FR-010 (passwords MUST be in-memory only)."
    )
    # Defensive: also check UTF-16 in case any code path converts.
    assert KNOWN_PASSWORD.encode("utf-16") not in raw_bytes, (
        f"Password {KNOWN_PASSWORD!r} found in database file (UTF-16 form)."
    )


def test_password_not_in_export_csv() -> None:
    """SC-008 / FR-013: CSV export does NOT contain the password column or
    any password value (column absent entirely, not masked).
    """
    _run_job_with_known_password()
    csv_bytes = _generate_export("csv")
    assert KNOWN_PASSWORD.encode("utf-8") not in csv_bytes
    assert b"password" not in csv_bytes.lower(), (
        "Export CSV contains a 'password' column header — violates FR-013 "
        "(the column MUST be entirely absent, not present-but-masked)."
    )


def test_password_not_in_export_json() -> None:
    """SC-008 / FR-013: JSON export does NOT contain a password field or value."""
    _run_job_with_known_password()
    json_bytes = _generate_export("json")
    assert KNOWN_PASSWORD.encode("utf-8") not in json_bytes
    assert b'"password"' not in json_bytes, (
        "Export JSON contains a 'password' key — violates FR-013 "
        "(the field MUST be entirely absent, not present-but-masked)."
    )


def test_no_password_column_in_detail_view() -> None:
    """FR-013 / 004 FR-007: the detail view's Results Table has no password
    column at all (the canonical column set excludes it).
    """
    _run_job_with_known_password()
    rendered_html = _render_detail_view_row("row-1")
    assert KNOWN_PASSWORD not in rendered_html, (
        "Password leaked into detail view rendering."
    )
    # No password-related markup at all (not even a masked placeholder)
    assert "password" not in rendered_html.lower(), (
        "Detail view contains a 'password' label/column — violates FR-013 "
        "(no password presence at all, not even masked)."
    )


def test_password_not_in_logs() -> None:
    """SC-009 / FR-013: no log line emitted during the run contains the
    known password value (even at debug level).
    """
    _run_job_with_known_password()
    log_output = _capture_logs()
    assert KNOWN_PASSWORD not in log_output, (
        f"Password {KNOWN_PASSWORD!r} appeared in log output — violates FR-013 "
        f"(per-row debug logs MAY include testId but MUST exclude password)."
    )


def test_testid_present_in_persistence() -> None:
    """FR-014 (positive assertion): testId IS persisted and surfaces in the
    detail view / export / logs (NEVER masked).
    """
    _run_job_with_known_password()
    rendered_html = _render_detail_view_row("row-1")
    assert KNOWN_TESTID in rendered_html, (
        f"testId {KNOWN_TESTID!r} missing from detail view — violates FR-014 "
        f"(testId MUST flow through the full traceability chain in plaintext)."
    )

    csv_bytes = _generate_export("csv")
    assert KNOWN_TESTID.encode("utf-8") in csv_bytes


def test_bundled_mock_connector_does_not_echo_password() -> None:
    """FR-016 / 007 FR-018-FR-022: the bundled mock connector service MUST
    NOT echo the per-row password value in any field of its HTTP response.

    IMPLEMENTER NOTE (when 007's mock service lands): this test will:
      1. POST to the mock connector endpoint with body
         {testId: KNOWN_TESTID, utteranceText: "hello", password: KNOWN_PASSWORD}.
      2. Capture the response body.
      3. Assert KNOWN_PASSWORD does not appear in any field of the response
         (including the contract's rawPayload, metadata, normalizedText).
    """
    # Calls a helper that doesn't exist yet — xfail framework handles this.
    response_body = _post_to_mock_connector(
        testId=KNOWN_TESTID, utteranceText="hello", password=KNOWN_PASSWORD
    )
    assert KNOWN_PASSWORD not in response_body, (
        "Bundled mock connector service echoed the password in its response — "
        "violates FR-016 (connectors MUST NOT echo per-row credentials)."
    )


def _post_to_mock_connector(*, testId: str, utteranceText: str, password: str) -> str:
    """POST to the bundled mock connector service. Returns the response body."""
    raise NotImplementedError(
        "Bundled mock connector service (007 FR-018-FR-022) not yet implemented."
    )
