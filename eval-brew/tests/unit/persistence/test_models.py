"""Model-level tests: defaults, FK references/cascade, no-password column, db path.

Covers FR-001..003, FR-017/FR-018, SC-011.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from harness.persistence.engine import _ensure_directory, resolve_db_path
from harness.persistence.models import (
    ConnectorRegistration,
    EvaluationAgentRegistration,
    EvaluationResult,
    Job,
    Utterance,
)


def _make_job(job_id: str = "job-1", status: str = "draft") -> Job:
    return Job(
        job_id=job_id,
        job_name="My Job",
        status=status,
        created_by="alice",
        created_at=datetime.now(UTC),
        harness_version="0.1.0",
    )


def test_job_counter_defaults(db_session) -> None:
    job = _make_job()
    db_session.add(job)
    db_session.flush()
    fetched = db_session.get(Job, "job-1")
    assert fetched.processed_count == 0
    assert fetched.failed_count == 0
    assert fetched.description is None
    assert fetched.started_at is None


def test_utterance_has_no_password_column() -> None:
    columns = set(Utterance.__table__.columns.keys())
    assert "password" not in columns
    assert "encrypted_password" not in columns
    assert "encryptedPassword" not in columns


def test_fk_cascade_deletes_children(db_session) -> None:
    db_session.add(_make_job())
    utt = Utterance(
        utterance_id="utt-1",
        job_id="job-1",
        utterance_text="hello",
        row_index=1,
        test_id="t1",
    )
    db_session.add(utt)
    db_session.flush()
    db_session.add(
        EvaluationResult(
            result_id="res-1",
            utterance_id="utt-1",
            test_id="t1",
            evaluation_timestamp=datetime.now(UTC),
        )
    )
    db_session.flush()

    # ORM cascade (delete-orphan) + PRAGMA foreign_keys=ON removes children.
    db_session.delete(db_session.get(Job, "job-1"))
    db_session.flush()

    assert db_session.scalars(select(Utterance)).all() == []
    assert db_session.scalars(select(EvaluationResult)).all() == []


def test_evaluation_result_metadata_attribute_maps_to_metadata_column() -> None:
    # Attribute renamed to avoid Base.metadata clash, but SQL column is "metadata".
    assert "metadata" in EvaluationResult.__table__.columns.keys()
    assert EvaluationResult.result_metadata.property.columns[0].name == "metadata"


def test_registration_defaults(db_session) -> None:
    now = datetime.now(UTC)
    db_session.add(
        ConnectorRegistration(
            connector_id="c1",
            display_name="Conn",
            endpoint_url="https://example.test",
            auth_descriptor={"mode": "none"},
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        EvaluationAgentRegistration(
            evaluation_agent_id="e1",
            display_name="Eval",
            description="An evaluator",
            endpoint_url="https://example.test",
            auth_descriptor={"mode": "none"},
            created_at=now,
            updated_at=now,
        )
    )
    db_session.flush()
    conn = db_session.get(ConnectorRegistration, "c1")
    agent = db_session.get(EvaluationAgentRegistration, "e1")
    assert conn.timeout_seconds == 30
    assert conn.expects_per_row_password is False
    assert conn.archived is False
    assert agent.timeout_seconds == 60
    assert agent.declared_scoring_dimensions == []


def test_db_path_configurable(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    target = tmp_path / "custom" / "mydata.db"
    monkeypatch.setenv("HARNESS_DB_PATH", str(target))
    assert resolve_db_path() == target


def test_db_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_DB_PATH", raising=False)
    assert resolve_db_path().name == "data.db"
    assert resolve_db_path().parent.name == ".harness"


def test_db_parent_dir_created(tmp_path) -> None:
    target = tmp_path / "deeply" / "nested" / "data.db"
    assert not target.parent.exists()
    _ensure_directory(target)
    assert target.parent.exists()
