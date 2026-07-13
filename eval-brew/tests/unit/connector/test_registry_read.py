"""ConnectorRegistryReader tests (US2, FR-009-011, SC-003)."""

from __future__ import annotations

from harness.connector import ConnectorRegistryReader
from harness.persistence.repositories import ConnectorRegistrationRepository


def _make(db_session, name: str, *, archived: bool = False, expects: bool = False):
    repo = ConnectorRegistrationRepository(db_session)
    reg = repo.create(
        {
            "display_name": name,
            "description": f"{name} desc",
            "endpoint_url": "https://c.test",
            "auth_descriptor": {"mode": "none"},
            "expects_per_row_password": expects,
        }
    )
    if archived:
        repo.archive(reg.connector_id)
    return reg


def test_list_active_excludes_archived(db_session) -> None:
    active = _make(db_session, "A")
    gone = _make(db_session, "B", archived=True)
    ids = {e.connector_id for e in ConnectorRegistryReader(db_session).list_active()}
    assert active.connector_id in ids
    assert gone.connector_id not in ids


def test_list_entry_minimal_tuple(db_session) -> None:
    reg = _make(db_session, "C", expects=True)
    entries = ConnectorRegistryReader(db_session).list_active()
    entry = next(e for e in entries if e.connector_id == reg.connector_id)
    assert entry.display_name == "C"
    assert entry.description == "C desc"
    assert entry.expects_per_row_password is True


def test_get_returns_full_record(db_session) -> None:
    reg = _make(db_session, "D")
    full = ConnectorRegistryReader(db_session).get(reg.connector_id)
    assert full.endpoint_url == "https://c.test"
    assert full.auth_descriptor["mode"] == "none"


def test_identical_data_all_callers(db_session) -> None:
    reg = _make(db_session, "E")
    reader_a = ConnectorRegistryReader(db_session)
    reader_b = ConnectorRegistryReader(db_session)
    via_a = reader_a.get(reg.connector_id).connector_id
    via_b = reader_b.get(reg.connector_id).connector_id
    assert via_a == via_b == reg.connector_id
