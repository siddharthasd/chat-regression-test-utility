"""ConnectorRegistryService tests (US1/2/3/5)."""

from __future__ import annotations

import pytest

from harness.connector_registry import ConnectorRegistryService, RegistrationInUseError
from harness.persistence.repositories import JobRepository


def _payload(**over) -> dict:
    base = {
        "display_name": "C",
        "description": None,
        "endpoint_url": "https://c.test",
        "auth_descriptor": {"mode": "bearer", "credential": "SEKRIT"},
        "timeout_seconds": 30,
        "expects_per_row_password": False,
    }
    base.update(over)
    return base


# ------------------------------------------------------------------ US1
def test_create_encrypts_and_persists(db_session) -> None:
    svc = ConnectorRegistryService(db_session)
    reg = svc.create(_payload())
    assert reg.connector_id
    assert reg.auth_descriptor["credential"] != "SEKRIT"  # encrypted at rest
    assert svc.get_auth_descriptor_decrypted(reg.connector_id)["credential"] == "SEKRIT"


# ------------------------------------------------------------------ US2
def test_update_preserves_ciphertext_without_replace(db_session) -> None:
    svc = ConnectorRegistryService(db_session)
    reg = svc.create(_payload())
    before = reg.auth_descriptor["credential"]
    svc.update(
        reg.connector_id,
        _payload(display_name="C2", auth_descriptor={"mode": "bearer", "credential": ""}),
        replace_credential=False,
    )
    after = svc.get(reg.connector_id)
    assert after.display_name == "C2"
    assert after.auth_descriptor["credential"] == before  # unchanged ciphertext


def test_update_replace_reencrypts(db_session) -> None:
    svc = ConnectorRegistryService(db_session)
    reg = svc.create(_payload())
    svc.update(
        reg.connector_id,
        _payload(auth_descriptor={"mode": "bearer", "credential": "NEWTOKEN"}),
        replace_credential=True,
    )
    assert svc.get_auth_descriptor_decrypted(reg.connector_id)["credential"] == "NEWTOKEN"


def test_mode_change_discards_old_credential(db_session) -> None:
    svc = ConnectorRegistryService(db_session)
    reg = svc.create(_payload())  # bearer
    svc.update(
        reg.connector_id,
        _payload(auth_descriptor={"mode": "basic", "username": "u", "password": "pw"}),
        replace_credential=False,  # mode change forces re-encrypt regardless
    )
    desc = svc.get_auth_descriptor_decrypted(reg.connector_id)
    assert desc["mode"] == "basic"
    assert desc["password"] == "pw"
    assert "credential" not in desc  # old bearer credential discarded


# ------------------------------------------------------------------ US3
def test_archive_and_restore(db_session) -> None:
    svc = ConnectorRegistryService(db_session)
    reg = svc.create(_payload())
    svc.archive(reg.connector_id)
    assert svc.get(reg.connector_id).archived is True
    svc.restore(reg.connector_id)
    assert svc.get(reg.connector_id).archived is False


# ------------------------------------------------------------------ US4 (list/filter/search)
def test_list_filters_and_search(db_session) -> None:
    svc = ConnectorRegistryService(db_session)
    svc.create(_payload(display_name="Apple"))
    banana = svc.create(_payload(display_name="Banana"))
    svc.archive(banana.connector_id)
    active = [r.display_name for r in svc.list_registrations(filter="active")]
    assert active == ["Apple"]
    assert [r.display_name for r in svc.list_registrations(filter="archived")] == ["Banana"]
    all_names = {r.display_name for r in svc.list_registrations(filter="all")}
    assert all_names == {"Apple", "Banana"}
    assert [r.display_name for r in svc.list_registrations(filter="all", q="app")] == ["Apple"]


# ------------------------------------------------------------------ US5 (hard-delete gating)
def test_hard_delete_when_unreferenced(db_session) -> None:
    svc = ConnectorRegistryService(db_session)
    reg = svc.create(_payload())
    svc.hard_delete(reg.connector_id)
    assert svc.get(reg.connector_id) is None


def test_hard_delete_blocked_when_referenced(db_session) -> None:
    svc = ConnectorRegistryService(db_session)
    reg = svc.create(_payload())
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    jobs.set_connector_snapshot(job.job_id, reg)  # job.connector_id == reg.connector_id
    with pytest.raises(RegistrationInUseError):
        svc.hard_delete(reg.connector_id)
    assert svc.get(reg.connector_id) is not None  # still there
