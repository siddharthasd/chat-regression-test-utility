"""Job Creation Wizard Flask UI integration tests (US1-US5 + Polish). Per-test isolated DB."""

from __future__ import annotations

import io

import pytest

from harness import password_store
from harness.persistence import get_session
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    EvaluationAgentRegistrationRepository,
    JobRepository,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "ui.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "ui.key"))
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "ui.db")
    password_store._reset_for_tests()
    from harness.ui import create_app

    yield create_app().test_client()
    password_store._reset_for_tests()


@pytest.fixture
def enqueue_spy(monkeypatch):
    calls = []
    monkeypatch.setattr("harness.ui.wizard.routes.enqueue_job", lambda job_id: calls.append(job_id))
    return calls


def _seed_connector(*, expects=False, name="Conn", auth=None) -> str:
    with get_session() as session:
        reg = ConnectorRegistrationRepository(session).create(
            {
                "display_name": name,
                "endpoint_url": "https://conn.test/api",
                "auth_descriptor": auth or {"mode": "none"},
                "timeout_seconds": 30,
                "expects_per_row_password": expects,
            }
        )
        return reg.connector_id


def _seed_evaluator(name="Eval") -> str:
    with get_session() as session:
        reg = EvaluationAgentRegistrationRepository(session).create(
            {
                "display_name": name,
                "description": "scores things",
                "endpoint_url": "https://eval.test/api",
                "auth_descriptor": {"mode": "none"},
                "timeout_seconds": 60,
                "declared_scoring_dimensions": ["relevance", "tone"],
            }
        )
        return reg.evaluation_agent_id


def _create_job(client, name="My Job") -> str:
    resp = client.post("/jobs", data={"job_name": name})
    assert resp.status_code == 302
    # Location: /jobs/<id>/step2
    return resp.headers["Location"].split("/jobs/")[1].split("/")[0]


def _upload(client, job_id, csv: str):
    return client.post(
        f"/jobs/{job_id}/step2",
        data={"csv_file": (io.BytesIO(csv.encode()), "rows.csv")},
        content_type="multipart/form-data",
    )


_GOOD_CSV = "utteranceText,testId\nhi,t1\nbye,t2\nhola,t1\n"


def _job(job_id):
    with get_session() as session:
        return JobRepository(session).get(job_id)


# --------------------------------------------------------------------------- US1
def test_create_to_start_happy_path(client, enqueue_spy) -> None:
    conn_id = _seed_connector()
    agent_id = _seed_evaluator()

    job_id = _create_job(client, "Regression run")
    assert _upload(client, job_id, _GOOD_CSV).status_code == 302
    assert client.post(f"/jobs/{job_id}/step3", data={"connector_id": conn_id}).status_code == 302
    assert client.post(
        f"/jobs/{job_id}/step4", data={"evaluation_agent_id": agent_id}
    ).status_code == 302

    start = client.post(f"/jobs/{job_id}/start")
    assert start.status_code == 302
    assert start.headers["Location"].endswith(f"/jobs/{job_id}/started")

    job = _job(job_id)
    assert job.status == "queued"
    assert job.started_at is not None
    assert enqueue_spy == [job_id]  # SC-008: engine signalled

    # SC-011: snapshot byte-equal to the registration at snapshot time.
    with get_session() as session:
        reg = ConnectorRegistrationRepository(session).get(conn_id)
        assert job.connector_endpoint_url == reg.endpoint_url
        assert job.connector_auth_descriptor == reg.auth_descriptor
        assert job.connector_name == reg.display_name


def test_create_requires_name(client) -> None:
    resp = client.post("/jobs", data={"job_name": "  "})
    assert resp.status_code == 400
    assert "required" in resp.get_data(as_text=True)


# --------------------------------------------------------------------------- US2
def test_resume_opens_at_lowest_incomplete_step(client) -> None:
    _seed_connector()
    _seed_evaluator()
    job_id = _create_job(client)
    _upload(client, job_id, _GOOD_CSV)  # Steps 1+2 done; 3 next

    resp = client.get(f"/jobs/{job_id}")
    assert resp_step(resp) == 3


def test_archived_connector_requires_reselect(client) -> None:
    conn_id = _seed_connector(name="WillArchive")
    _seed_evaluator()
    job_id = _create_job(client)
    _upload(client, job_id, _GOOD_CSV)
    client.post(f"/jobs/{job_id}/step3", data={"connector_id": conn_id})

    # Archive the selected connector after it was snapshotted.
    with get_session() as session:
        ConnectorRegistrationRepository(session).get(conn_id).archived = True

    # Resume now treats Step 3 as incomplete (snapshot references an archived reg).
    assert resp_step(client.get(f"/jobs/{job_id}")) == 3
    body = client.get(f"/jobs/{job_id}/step5").get_data(as_text=True)
    assert "no longer available" in body


# --------------------------------------------------------------------------- US3
def test_back_and_change_connector_replaces_snapshot(client) -> None:
    conn_a = _seed_connector(name="A")
    conn_b = _seed_connector(name="B")
    agent_id = _seed_evaluator()
    job_id = _create_job(client)
    _upload(client, job_id, _GOOD_CSV)
    client.post(f"/jobs/{job_id}/step3", data={"connector_id": conn_a})
    client.post(f"/jobs/{job_id}/step4", data={"evaluation_agent_id": agent_id})

    # Back to Step 3, choose B.
    client.post(f"/jobs/{job_id}/step3", data={"connector_id": conn_b})
    job = _job(job_id)
    assert job.connector_id == conn_b  # snapshot replaced
    assert job.evaluation_agent_id == agent_id  # evaluator preserved


# --------------------------------------------------------------------------- US4
def test_malformed_csv_blocks_advance(client) -> None:
    _seed_connector()
    job_id = _create_job(client)
    resp = _upload(client, job_id, "utteranceText,testId\nhi,\n")  # empty testId
    assert resp.status_code == 400
    assert "testId" in resp.get_data(as_text=True)
    assert _job(job_id).total_utterance_count is None  # nothing persisted


# --------------------------------------------------------------------------- US5
def test_empty_connector_registry_affordance(client) -> None:
    job_id = _create_job(client)
    _upload(client, job_id, _GOOD_CSV)
    body = client.get(f"/jobs/{job_id}/step3").get_data(as_text=True)
    assert "Register a connector" in body
    assert "/connectors/new" in body


def test_empty_evaluator_registry_affordance(client) -> None:
    conn_id = _seed_connector()
    job_id = _create_job(client)
    _upload(client, job_id, _GOOD_CSV)
    client.post(f"/jobs/{job_id}/step3", data={"connector_id": conn_id})
    body = client.get(f"/jobs/{job_id}/step4").get_data(as_text=True)
    assert "Register an evaluator" in body
    assert "/evaluators/new" in body


# --------------------------------------------------------------------------- Polish
def test_no_credential_rendered_on_review(client) -> None:
    conn_id = _seed_connector(
        name="Secret", auth={"mode": "bearer", "credential": "SUPER-SECRET-TOKEN-9"}
    )
    agent_id = _seed_evaluator()
    job_id = _create_job(client)
    _upload(client, job_id, _GOOD_CSV)
    client.post(f"/jobs/{job_id}/step3", data={"connector_id": conn_id})
    client.post(f"/jobs/{job_id}/step4", data={"evaluation_agent_id": agent_id})

    body = client.get(f"/jobs/{job_id}/step5").get_data(as_text=True)
    assert "SUPER-SECRET-TOKEN-9" not in body
    assert "bearer" in body  # mode label is shown


def test_password_connector_bounces_to_reupload(client) -> None:
    conn_id = _seed_connector(expects=True, name="NeedsPw")
    _seed_evaluator()
    job_id = _create_job(client)
    _upload(client, job_id, _GOOD_CSV)  # no password column -> store empty

    resp = client.post(f"/jobs/{job_id}/step3", data={"connector_id": conn_id})
    assert resp.status_code == 302
    assert "/step2" in resp.headers["Location"]  # bounced back to re-upload


def resp_step(resp) -> int:
    """Extract the step number from a resume redirect's Location."""
    assert resp.status_code == 302
    return int(resp.headers["Location"].rstrip("/").split("step")[-1])
