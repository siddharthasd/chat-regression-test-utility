"""Encryption-utility tests: round-trip, non-determinism, key-mismatch, at-rest.

Covers FR-008/FR-009, SC-004/SC-005.
"""

from __future__ import annotations

import pytest

from harness.persistence import encryption
from harness.persistence.exceptions import HarnessKeyMismatchError
from harness.persistence.models import Utterance


@pytest.fixture
def isolated_key(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Give each test a fresh key file + cleared in-process key cache."""
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "master.key"))
    encryption._reset_key_cache_for_tests()
    yield tmp_path
    encryption._reset_key_cache_for_tests()


def test_round_trip(isolated_key) -> None:
    secret = "s3cr3t-token-DEADBEEF"
    assert encryption.decrypt_credential(encryption.encrypt_credential(secret)) == secret


def test_ciphertext_is_non_deterministic(isolated_key) -> None:
    a = encryption.encrypt_credential("same-input")
    b = encryption.encrypt_credential("same-input")
    assert a != b  # Fernet includes a random IV


def test_credential_encrypted_at_rest(isolated_key) -> None:
    secret = "DISTINCTIVE-CRED-12345"
    ciphertext = encryption.encrypt_credential(secret)
    assert secret not in ciphertext


def test_key_missing_or_wrong_raises(isolated_key, monkeypatch, tmp_path) -> None:
    ciphertext = encryption.encrypt_credential("value")
    # Rotate to a different key file → decryption must fail with the canonical error.
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "other.key"))
    encryption._reset_key_cache_for_tests()
    with pytest.raises(HarnessKeyMismatchError, match="machine-local key missing or wrong"):
        encryption.decrypt_credential(ciphertext)


def test_key_file_created_with_owner_only_perms(isolated_key, tmp_path) -> None:
    import os
    import stat

    encryption.encrypt_credential("x")
    key_path = tmp_path / "master.key"
    assert key_path.exists()
    if os.name != "nt":  # POSIX permission bits only meaningful off Windows
        mode = stat.S_IMODE(key_path.stat().st_mode)
        assert mode == 0o600


def test_password_not_in_db() -> None:
    """No entity persists a per-row CSV password in any form (FR-009)."""
    assert "password" not in Utterance.__table__.columns.keys()
