"""ConnectorRegistrationRepository tests (US1): create/encrypt, active, decrypt, update, archive."""

from __future__ import annotations

import pytest

from harness.persistence.repositories import ConnectorRegistrationRepository


def _data(**over):
    base = {
        "display_name": "My Connector",
        "endpoint_url": "https://conn.test",
        "auth_descriptor": {"mode": "bearer", "credential": "SECRET-TOKEN-123"},
    }
    base.update(over)
    return base


def test_create_assigns_id_and_defaults(db_session) -> None:
    repo = ConnectorRegistrationRepository(db_session)
    reg = repo.create(_data())
    assert reg.connector_id
    assert reg.timeout_seconds == 30
    assert reg.expects_per_row_password is False
    assert reg.archived is False


def test_create_encrypts_credential_subfield(db_session) -> None:
    repo = ConnectorRegistrationRepository(db_session)
    reg = repo.create(_data())
    # Stored ciphertext must not equal the plaintext secret.
    assert reg.auth_descriptor["credential"] != "SECRET-TOKEN-123"
    assert reg.auth_descriptor["mode"] == "bearer"


def test_get_auth_descriptor_decrypted_round_trips(db_session) -> None:
    repo = ConnectorRegistrationRepository(db_session)
    reg = repo.create(_data())
    decrypted = repo.get_auth_descriptor_decrypted(reg.connector_id)
    assert decrypted["credential"] == "SECRET-TOKEN-123"


def test_get_active_excludes_archived(db_session) -> None:
    repo = ConnectorRegistrationRepository(db_session)
    a = repo.create(_data(display_name="A"))
    b = repo.create(_data(display_name="B"))
    repo.archive(b.connector_id)
    active_ids = {r.connector_id for r in repo.get_active()}
    assert a.connector_id in active_ids
    assert b.connector_id not in active_ids


def test_update_reencrypts_changed_descriptor(db_session) -> None:
    repo = ConnectorRegistrationRepository(db_session)
    reg = repo.create(_data())
    repo.update(
        reg.connector_id,
        {"auth_descriptor": {"mode": "bearer", "credential": "NEW-TOKEN-999"}},
    )
    assert repo.get_auth_descriptor_decrypted(reg.connector_id)["credential"] == "NEW-TOKEN-999"


def test_archive_then_restore(db_session) -> None:
    repo = ConnectorRegistrationRepository(db_session)
    reg = repo.create(_data())
    repo.archive(reg.connector_id)
    assert repo.get(reg.connector_id).archived is True
    repo.restore(reg.connector_id)
    assert repo.get(reg.connector_id).archived is False
    assert repo.get(reg.connector_id).archived_at is None


def test_hard_delete(db_session) -> None:
    repo = ConnectorRegistrationRepository(db_session)
    reg = repo.create(_data())
    repo.hard_delete(reg.connector_id)
    assert repo.get(reg.connector_id) is None


def test_missing_connector_raises(db_session) -> None:
    repo = ConnectorRegistrationRepository(db_session)
    with pytest.raises(ValueError):
        repo.get_auth_descriptor_decrypted("nope")
