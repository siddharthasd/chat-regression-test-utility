"""CSV upload service integration tests (US1-US5 + Polish). Per-test isolated DB + store."""

from __future__ import annotations

import codecs
import os

import pytest

from harness import password_store
from harness.csv_upload import ErrorCategory, process_upload
from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import JobRepository, UtteranceRepository


@pytest.fixture
def db(tmp_path):
    from harness.persistence import engine

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()
    password_store._reset_for_tests()
    yield tmp_path
    password_store._reset_for_tests()


def _draft_job(*, expects_password=False, status=JobStatus.DRAFT) -> str:
    with get_session() as session:
        job = JobRepository(session).create_draft("up", None, "tester")
        job.connector_expects_per_row_password = expects_password
        job.status = status.value
        return job.job_id


def _write(tmp_path, name, content: str | bytes) -> str:
    p = tmp_path / name
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    return str(p)


def _rows(job_id):
    with get_session() as session:
        return UtteranceRepository(session).get_by_job_ordered(job_id)


def _job(job_id):
    with get_session() as session:
        return JobRepository(session).get(job_id)


# --------------------------------------------------------------------------- US1
def test_happy_path_with_passwords(db) -> None:
    job_id = _draft_job(expects_password=True)
    csv = "utteranceText,testId,password\n" + "".join(
        f"u{i},t{i % 2},DEADBEEF-PWD-{i}\n" for i in range(5)
    )
    path = _write(db, "good.csv", csv)
    result = process_upload(job_id, path)

    assert result.success
    assert result.utterances_created == 5
    assert result.distinct_test_ids == 2
    assert result.warnings == []

    rows = _rows(job_id)
    assert [r.row_index for r in rows] == [1, 2, 3, 4, 5]
    assert len({r.utterance_id for r in rows}) == 5
    job = _job(job_id)
    assert job.total_utterance_count == 5
    assert job.source_csv_filename == "good.csv"

    # passwords reachable via the in-memory store...
    assert password_store.get(job_id, rows[0].utterance_id) == "DEADBEEF-PWD-0"
    # ...but zero password bytes in the DB file (SC-005).
    db_bytes = (db / "up.db").read_bytes()
    assert b"DEADBEEF-PWD-0" not in db_bytes


def test_happy_path_without_password_column(db) -> None:
    job_id = _draft_job(expects_password=False)
    path = _write(db, "nopw.csv", "utteranceText,testId\nhi,t1\nbye,t2\n")
    result = process_upload(job_id, path)

    assert result.success and result.utterances_created == 2
    assert _job(job_id).total_utterance_count == 2
    assert password_store.job_has_entries(job_id) is False  # store unpopulated


# --------------------------------------------------------------------------- US2
def test_missing_password_column_rejected_no_persistence(db) -> None:
    job_id = _draft_job(expects_password=True)
    path = _write(db, "bad.csv", "utteranceText,testId\nhi,t1\n")
    result = process_upload(job_id, path)

    assert not result.success
    assert ErrorCategory.MISSING_COLUMN in {e.category for e in result.errors}
    assert _rows(job_id) == []
    assert _job(job_id).total_utterance_count is None
    assert _job(job_id).source_csv_filename is None


def test_empty_value_rejected(db) -> None:
    job_id = _draft_job()
    path = _write(db, "empty.csv", "utteranceText,testId\nhi,t1\nbye,\n")
    result = process_upload(job_id, path)
    assert not result.success
    empties = [e for e in result.errors if e.category == ErrorCategory.EMPTY_VALUE]
    assert empties and empties[0].row == 2 and empties[0].column == "testId"
    assert _rows(job_id) == []


def test_bad_encoding_rejected(db) -> None:
    job_id = _draft_job()
    path = _write(db, "enc.csv", b"\xff\xfeutteranceText,testId\nhi,t1\n")
    result = process_upload(job_id, path)
    assert not result.success
    assert ErrorCategory.ENCODING in {e.category for e in result.errors}
    assert _rows(job_id) == []


# --------------------------------------------------------------------------- US3
def test_non_draft_job_rejected(db) -> None:
    path = _write(db, "ok.csv", "utteranceText,testId\nhi,t1\n")
    for status in (
        JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING,
        JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED,
    ):
        job_id = _draft_job(status=status)
        result = process_upload(job_id, path)
        assert not result.success
        assert ErrorCategory.JOB_NOT_DRAFT in {e.category for e in result.errors}
        assert _rows(job_id) == []


def test_job_not_found(db) -> None:
    path = _write(db, "ok.csv", "utteranceText,testId\nhi,t1\n")
    result = process_upload("nope", path)
    assert ErrorCategory.JOB_NOT_FOUND in {e.category for e in result.errors}


# --------------------------------------------------------------------------- US4
def test_oversized_rejected_before_read(db) -> None:
    job_id = _draft_job()
    path = _write(db, "big.csv", "utteranceText,testId\n" + "hi,t1\n" * 500)
    result = process_upload(job_id, path, max_bytes=64)
    assert not result.success
    size_errs = [e for e in result.errors if e.category == ErrorCategory.SIZE_EXCEEDED]
    assert size_errs and "64" in size_errs[0].message
    assert _rows(job_id) == []


def test_under_limit_proceeds(db) -> None:
    job_id = _draft_job()
    path = _write(db, "small.csv", "utteranceText,testId\nhi,t1\n")
    assert process_upload(job_id, path, max_bytes=10_000).success


# --------------------------------------------------------------------------- US5
def test_edge_cases_end_to_end(db) -> None:
    job_id = _draft_job()
    raw = codecs.BOM_UTF8 + (
        'utteranceText,testId\n'
        '"multi\nline 🚀",t1\n'
        'café,t2\n'
        ',\n'
        ',\n'
    ).encode()
    path = _write(db, "edge.csv", raw)
    result = process_upload(job_id, path)

    assert result.success
    assert result.utterances_created == 2  # blanks excluded
    assert any("blank" in w for w in result.warnings)
    rows = _rows(job_id)
    assert rows[0].utterance_text == "multi\nline 🚀"  # lossless round-trip
    assert rows[1].utterance_text == "café"


# --------------------------------------------------------------------------- Polish
def test_replace_on_reupload(db) -> None:
    job_id = _draft_job(expects_password=True)
    path_a = _write(db, "a.csv", "utteranceText,testId,password\na1,t1,PW-A-1\na2,t1,PW-A-2\n")
    path_b = _write(db, "b.csv", "utteranceText,testId,password\nb1,t9,PW-B-1\n")

    assert process_upload(job_id, path_a).success
    first_ids = {r.utterance_id for r in _rows(job_id)}
    assert process_upload(job_id, path_b).success

    rows = _rows(job_id)
    assert [r.utterance_text for r in rows] == ["b1"]
    assert _job(job_id).total_utterance_count == 1
    assert _job(job_id).source_csv_filename == "b.csv"
    # no A traces in the store: old keys gone, only the new row staged
    assert not any(password_store.get(job_id, uid) for uid in first_ids)
    assert password_store.get(job_id, rows[0].utterance_id) == "PW-B-1"
