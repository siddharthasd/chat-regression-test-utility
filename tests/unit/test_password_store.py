"""In-memory password store unit tests (012 FR-015/FR-022)."""

from __future__ import annotations

import pytest

from harness import password_store


@pytest.fixture(autouse=True)
def _clean_store():
    password_store._reset_for_tests()
    yield
    password_store._reset_for_tests()


def test_put_get_round_trip() -> None:
    password_store.put("job1", "utt1", "s3cret")
    assert password_store.get("job1", "utt1") == "s3cret"


def test_get_absent_returns_none() -> None:
    assert password_store.get("job1", "missing") is None


def test_evict_removes_entry() -> None:
    password_store.put("job1", "utt1", "s3cret")
    password_store.evict("job1", "utt1")
    assert password_store.get("job1", "utt1") is None


def test_evict_absent_is_noop() -> None:
    password_store.evict("job1", "nope")  # must not raise
    assert password_store.get("job1", "nope") is None


def test_job_has_entries() -> None:
    assert password_store.job_has_entries("job1") is False
    password_store.put("job1", "utt1", "x")
    assert password_store.job_has_entries("job1") is True


def test_clear_job_isolates_other_jobs() -> None:
    password_store.put("jobA", "utt1", "a")
    password_store.put("jobB", "utt1", "b")
    password_store.clear_job("jobA")
    assert password_store.job_has_entries("jobA") is False
    assert password_store.get("jobB", "utt1") == "b"  # cross-job isolation (FR-022)
