"""Evaluator Registry Flask UI integration tests (US1-US6). Per-test isolated DB."""

from __future__ import annotations

import os

import pytest

from harness.evaluator_registry import EvaluatorRegistryService
from harness.persistence import get_session
from harness.persistence.repositories import JobRepository


@pytest.fixture
def ui_client():
    from harness.persistence import engine

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()  # per-test isolation (create_app won't re-init; see 013)
    from harness.ui import create_app
    from starlette.testclient import TestClient

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def _create(client, **over):
    data = {
        "display_name": "Eval",
        "description": "scores stuff",
        "endpoint_url": "https://e.test",
        "auth_mode": "none",
        "timeout_seconds": "60",
        "dimensions": "relevance\ngroundedness",
    }
    data.update(over)
    return client.post("/evaluators", data=data, follow_redirects=True)


def _agent_id(name: str) -> str:
    with get_session() as session:
        regs = EvaluatorRegistryService(session).list_registrations(filter="all", q=name)
        return regs[0].evaluation_agent_id


def test_create_then_listed_with_dimension_preview(ui_client) -> None:
    resp = _create(ui_client, display_name="MyEval", dimensions="a\nb\nc\nd")
    assert resp.status_code == 200
    listing = ui_client.get("/evaluators").text
    assert "MyEval" in listing
    assert "+ 1 more" in listing  # 4 dims → preview shows first 3 + "+ 1 more"


def test_description_required_blocks(ui_client) -> None:
    data = {
        "display_name": "X",
        "description": "",
        "endpoint_url": "https://e",
        "auth_mode": "none",
        "timeout_seconds": "60",
    }
    resp = ui_client.post("/evaluators", data=data)
    assert resp.status_code == 400
    assert "Description is required" in resp.text


def test_credential_never_rendered_plaintext(ui_client) -> None:
    _create(ui_client, display_name="Secret", auth_mode="bearer", token="DEADBEEF-EVAL-99")
    aid = _agent_id("Secret")
    assert "DEADBEEF-EVAL-99" not in ui_client.get("/evaluators").text
    assert "DEADBEEF-EVAL-99" not in ui_client.get(f"/evaluators/{aid}/edit").text


def test_edit_updates_dimensions(ui_client) -> None:
    _create(ui_client, display_name="ToEdit", dimensions="a\nb")
    aid = _agent_id("ToEdit")
    resp = ui_client.post(
        f"/evaluators/{aid}",
        data={
            "display_name": "ToEdit",
            "description": "scores stuff",
            "endpoint_url": "https://e.test",
            "auth_mode": "none",
            "timeout_seconds": "60",
            "dimensions": "x\ny\nz",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with get_session() as session:
        reg = EvaluatorRegistryService(session).get(aid)
        assert reg.declared_scoring_dimensions == ["x", "y", "z"]


def test_archive_hides_from_active(ui_client) -> None:
    _create(ui_client, display_name="ToArchive")
    aid = _agent_id("ToArchive")
    ui_client.post(f"/evaluators/{aid}/archive", follow_redirects=True)
    assert "ToArchive" not in ui_client.get("/evaluators?filter=active").text
    assert "ToArchive" in ui_client.get("/evaluators?filter=archived").text


def test_hard_delete_blocked_when_referenced(ui_client) -> None:
    _create(ui_client, display_name="Referenced")
    aid = _agent_id("Referenced")
    with get_session() as session:
        reg = EvaluatorRegistryService(session).get(aid)
        jobs = JobRepository(session)
        job = jobs.create_draft("J", None, "u")
        jobs.set_evaluator_snapshot(job.job_id, reg)
    resp = ui_client.post(f"/evaluators/{aid}/delete")
    assert resp.status_code == 409
    assert "referenced by" in resp.text


def test_test_connection_returns_fragment_no_persist(ui_client) -> None:
    resp = ui_client.post(
        "/evaluators/test-connection",
        data={"endpoint_url": "http://127.0.0.1:1/", "auth_mode": "none", "timeout_seconds": "1"},
    )
    assert resp.status_code == 200
    assert "test-result" in resp.text
    with get_session() as session:
        assert EvaluatorRegistryService(session).list_registrations(filter="all") == []
