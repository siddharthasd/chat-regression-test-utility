"""US6 cross-cutting masking-rules test (FR-008 through FR-016).

The cross-spec contract gate, now wired to the real surfaces (011 upload + the
in-memory password store, 012 orchestrator, 007 connector HTTP, 004 detail view,
005 export). A single real job run carries the known-distinctive password
DEADBEEF-PWD-12345 + testId tester-alice through every leak surface; each test
asserts the password never escapes while the testId flows through in plaintext.

Note on two assertions vs the original scaffold: the export legitimately carries
`connectorExpectsPerRowPassword` (005 FR-005) and the detail metadata panel shows
a "Per-row password" flag label (004 FR-003) — both contain the substring
"password" by design. The real FR-013 intent is "no password VALUE and no
password COLUMN", so those checks assert exactly that (no column literally named
`password`, value absent) rather than a blanket substring ban.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import threading
from types import SimpleNamespace

import httpx
import pytest

from harness import password_store
from harness.connector import mock as conn_mock
from harness.csv_upload import process_upload
from harness.evaluator import mock as ev_mock
from harness.orchestrator import run_job
from harness.persistence import get_session
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    EvaluationAgentRegistrationRepository,
    JobRepository,
)

KNOWN_PASSWORD = "DEADBEEF-PWD-12345"
KNOWN_TESTID = "tester-alice"


def _serve(server) -> tuple[threading.Thread, str]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return thread, f"http://{host}:{port}/"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """Run one real job carrying the known password through the full pipeline."""
    tmp = tmp_path_factory.mktemp("masking")
    db_path = tmp / "masking.db"

    from harness.persistence import engine

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    eng = engine.init_db()
    password_store._reset_for_tests()

    connector = conn_mock.make_server(mode="ok")
    evaluator = ev_mock.make_server(mode="ok")
    _, conn_url = _serve(connector)
    _, eval_url = _serve(evaluator)

    # Capture all log output across upload + run (root at DEBUG).
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    prev_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        with get_session() as session:
            conn_reg = ConnectorRegistrationRepository(session).create(
                {
                    "display_name": "MaskConn",
                    "endpoint_url": conn_url,
                    "auth_descriptor": {"mode": "none"},
                    "timeout_seconds": 30,
                    "expects_per_row_password": True,
                }
            )
            eval_reg = EvaluationAgentRegistrationRepository(session).create(
                {
                    "display_name": "MaskEval",
                    "description": "d",
                    "endpoint_url": eval_url,
                    "auth_descriptor": {"mode": "none"},
                    "timeout_seconds": 60,
                    "declared_scoring_dimensions": ["relevance"],
                }
            )
            jobs = JobRepository(session)
            job = jobs.create_draft("Masking Job", None, "alice")
            jobs.set_connector_snapshot(job.job_id, conn_reg)
            jobs.set_evaluator_snapshot(job.job_id, eval_reg)
            job_id = job.job_id

        csv_path = tmp / "in.csv"
        csv_path.write_text(
            f"utteranceText,testId,password\nhello,{KNOWN_TESTID},{KNOWN_PASSWORD}\n",
            encoding="utf-8",
        )
        assert process_upload(job_id, str(csv_path)).success
        with get_session() as session:
            JobRepository(session).transition_to_queued(job_id)
        run_job(job_id)
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_level)

    # Flush WAL so any persisted bytes land in the main db file before we grep it.
    with eng.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")

    from harness.ui import create_app

    from starlette.testclient import TestClient
    client = TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)
    yield SimpleNamespace(
        db_path=db_path, job_id=job_id, logs=log_buf.getvalue(), client=client, conn_url=conn_url
    )

    connector.shutdown()
    evaluator.shutdown()
    password_store._reset_for_tests()


def _export(run, fmt: str) -> bytes:
    return run.client.get(f"/jobs/{run.job_id}/export?format={fmt}").content


def _detail_results_section(run) -> str:
    """The Results Table section of the detail page (excludes the metadata panel,
    which legitimately shows a 'Per-row password' config-flag label)."""
    html = run.client.get(f"/jobs/{run.job_id}/detail").text
    # Split at the results card header — everything after it is the utterance table.
    marker = "Result Explorer"
    assert marker in html, f"Could not find '{marker}' landmark in detail page HTML"
    return html.split(marker, 1)[1]


def test_password_not_in_db(run) -> None:
    """FR-010: the database file contains zero bytes of the password value."""
    raw_bytes = run.db_path.read_bytes()
    assert KNOWN_PASSWORD.encode("utf-8") not in raw_bytes, (
        f"Password {KNOWN_PASSWORD!r} found in database file (UTF-8) — "
        "violates FR-010 (passwords MUST be in-memory only)."
    )
    assert KNOWN_PASSWORD.encode("utf-16") not in raw_bytes, (
        f"Password {KNOWN_PASSWORD!r} found in database file (UTF-16 form)."
    )


def test_password_not_in_export_csv(run) -> None:
    """FR-013: CSV export carries no password value and no column named `password`."""
    csv_bytes = _export(run, "csv")
    assert KNOWN_PASSWORD.encode("utf-8") not in csv_bytes
    header = next(csv.reader(io.StringIO(csv_bytes.decode("utf-8"))))
    assert "password" not in [h.strip().lower() for h in header], (
        "Export CSV has a column literally named 'password' — violates FR-013 "
        "(no password column; `connectorExpectsPerRowPassword` is a config flag, not a secret)."
    )


def test_password_not_in_export_json(run) -> None:
    """FR-013: JSON export carries no password value and no `password` key."""
    json_bytes = _export(run, "json")
    assert KNOWN_PASSWORD.encode("utf-8") not in json_bytes
    assert b'"password"' not in json_bytes, (
        "Export JSON contains a 'password' key — violates FR-013."
    )


def test_no_password_column_in_detail_view(run) -> None:
    """004 FR-007: the Results Table has no password value and no password column."""
    section = _detail_results_section(run)
    assert KNOWN_PASSWORD not in section, "Password leaked into the detail view's results table."
    assert "password" not in section.lower(), (
        "Detail view results table contains a 'password' column/label — violates FR-013."
    )


def test_password_not_in_logs(run) -> None:
    """FR-013: no log line emitted during the run contains the password value."""
    assert KNOWN_PASSWORD not in run.logs, (
        f"Password {KNOWN_PASSWORD!r} appeared in log output — violates FR-013."
    )


def test_testid_present_in_persistence(run) -> None:
    """FR-014: testId IS persisted and surfaces in the detail view + export (never masked)."""
    assert KNOWN_TESTID in _detail_results_section(run), (
        f"testId {KNOWN_TESTID!r} missing from the detail view — violates FR-014."
    )
    assert KNOWN_TESTID.encode("utf-8") in _export(run, "csv")


def test_bundled_mock_connector_does_not_echo_password(run) -> None:
    """FR-016 / 007: the bundled mock connector MUST NOT echo the password."""
    response = httpx.post(
        run.conn_url,
        json={"testId": KNOWN_TESTID, "utteranceText": "hello", "password": KNOWN_PASSWORD},
    )
    assert KNOWN_PASSWORD not in response.text, (
        "Bundled mock connector echoed the password in its response — violates FR-016."
    )
