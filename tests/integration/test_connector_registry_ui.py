"""Connector Registry Flask UI integration tests (US1-US5).

Each test gets a fresh file DB + key (per-test isolation), driving the real app
via Flask's test client. Covers create/list/edit-masking/archive/hard-delete-gate.
"""

from __future__ import annotations

import pytest

from harness.connector_registry import ConnectorRegistryService
from harness.persistence import get_session
from harness.persistence.repositories import JobRepository


@pytest.fixture
def ui_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "ui.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "ui.key"))
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    # Force a fresh DB + rebind SessionLocal per test. create_app()'s
    # initialize_harness() early-returns once the identity singleton is set, so it
    # would NOT re-run init_db across tests — bind it explicitly here for isolation.
    engine.init_db(tmp_path / "ui.db")
    from harness.ui import create_app

    return create_app().test_client()


def _create(client, **over):
    data = {
        "display_name": "Conn",
        "endpoint_url": "https://c.test",
        "auth_mode": "none",
        "timeout_seconds": "30",
    }
    data.update(over)
    return client.post("/connectors", data=data, follow_redirects=True)


def _connector_id(name: str) -> str:
    with get_session() as session:
        regs = ConnectorRegistryService(session).list_registrations(filter="all", q=name)
        return regs[0].connector_id


# ------------------------------------------------------------------ US1
def test_create_then_listed(ui_client) -> None:
    resp = _create(ui_client, display_name="MyConn")
    assert resp.status_code == 200
    listing = ui_client.get("/connectors").get_data(as_text=True)
    assert "MyConn" in listing


def test_create_validation_error_blocks(ui_client) -> None:
    bad = {"display_name": "", "endpoint_url": "bad", "auth_mode": "none", "timeout_seconds": "30"}
    resp = ui_client.post("/connectors", data=bad)
    assert resp.status_code == 400
    body = resp.get_data(as_text=True).lower()
    assert "required" in body or "valid" in body


# ------------------------------------------------------------------ US2 / SC-002
def test_credential_never_rendered_plaintext(ui_client) -> None:
    _create(ui_client, display_name="Secret", auth_mode="bearer", token="DEADBEEF-12345")
    cid = _connector_id("Secret")
    assert "DEADBEEF-12345" not in ui_client.get("/connectors").get_data(as_text=True)
    assert "DEADBEEF-12345" not in ui_client.get(f"/connectors/{cid}/edit").get_data(as_text=True)


def test_edit_updates_display_name(ui_client) -> None:
    _create(ui_client, display_name="OldName")
    cid = _connector_id("OldName")
    resp = ui_client.post(
        f"/connectors/{cid}",
        data={
            "display_name": "NewName",
            "endpoint_url": "https://c.test",
            "auth_mode": "none",
            "timeout_seconds": "45",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    listing = ui_client.get("/connectors").get_data(as_text=True)
    assert "NewName" in listing
    assert "OldName" not in listing
    with get_session() as session:
        assert ConnectorRegistryService(session).get(cid).timeout_seconds == 45


# ------------------------------------------------------------------ US3 / US4
def test_archive_hides_from_active_filter(ui_client) -> None:
    _create(ui_client, display_name="ToArchive")
    cid = _connector_id("ToArchive")
    ui_client.post(f"/connectors/{cid}/archive", follow_redirects=True)
    assert "ToArchive" not in ui_client.get("/connectors?filter=active").get_data(as_text=True)
    assert "ToArchive" in ui_client.get("/connectors?filter=archived").get_data(as_text=True)


# ------------------------------------------------------------------ US5
def test_hard_delete_blocked_when_referenced(ui_client) -> None:
    _create(ui_client, display_name="Referenced")
    cid = _connector_id("Referenced")
    with get_session() as session:
        reg = ConnectorRegistryService(session).get(cid)
        jobs = JobRepository(session)
        job = jobs.create_draft("J", None, "u")
        jobs.set_connector_snapshot(job.job_id, reg)
    resp = ui_client.post(f"/connectors/{cid}/delete")
    assert resp.status_code == 409
    assert "referenced by" in resp.get_data(as_text=True)


def test_hard_delete_succeeds_when_unreferenced(ui_client) -> None:
    _create(ui_client, display_name="Disposable")
    cid = _connector_id("Disposable")
    resp = ui_client.post(f"/connectors/{cid}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert "Disposable" not in ui_client.get("/connectors?filter=all").get_data(as_text=True)


# ------------------------------------------------------------------ Test connection (SC-008)
def test_test_connection_returns_fragment_no_persist(ui_client) -> None:
    resp = ui_client.post(
        "/connectors/test-connection",
        data={"endpoint_url": "http://127.0.0.1:1/", "auth_mode": "none", "timeout_seconds": "1"},
    )
    assert resp.status_code == 200
    assert "test-result" in resp.get_data(as_text=True)
    # test-connection persists nothing — no registrations created
    with get_session() as session:
        assert ConnectorRegistryService(session).list_registrations(filter="all") == []
