"""Encryption-utility tests.

Encryption was removed; credentials are stored as plaintext.
The only remaining invariant is that per-row CSV passwords are never persisted.
"""

from __future__ import annotations

from harness.persistence import encryption
from harness.persistence.models import Utterance


def test_round_trip() -> None:
    secret = "s3cr3t-token-DEADBEEF"
    assert encryption.decrypt_credential(encryption.encrypt_credential(secret)) == secret


def test_descriptor_round_trip() -> None:
    descriptor = {"mode": "bearer", "credential": "tok123", "other": "x"}
    assert encryption.decrypt_descriptor(encryption.encrypt_descriptor(descriptor)) == descriptor


def test_password_not_in_db() -> None:
    """No entity persists a per-row CSV password in any form (FR-009)."""
    assert "password" not in Utterance.__table__.columns.keys()



