"""US1 tests — OS-derived identity resolution chain (FR-001).

Covers the three acceptance scenarios:
  1. os.getlogin succeeds → resolution_source = "os.getlogin"
  2. os.getlogin raises, getpass.getuser succeeds → "getpass.getuser"
  3. Both fail → "unknown-user-default"
"""

from __future__ import annotations

import logging

import pytest

from harness.identity.resolution import TesterIdentity, resolve_tester_identity


def test_resolves_via_getlogin_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("harness.identity.resolution.os.getlogin", lambda: "alice")

    identity = resolve_tester_identity()

    assert isinstance(identity, TesterIdentity)
    assert identity.value == "alice"
    assert identity.resolution_source == "os.getlogin"


def test_falls_back_to_getpass_when_getlogin_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _raise_oserror() -> str:
        raise OSError("no controlling terminal")

    monkeypatch.setattr("harness.identity.resolution.os.getlogin", _raise_oserror)
    monkeypatch.setattr("harness.identity.resolution.getpass.getuser", lambda: "bob")

    with caplog.at_level(logging.INFO, logger="harness.identity.resolution"):
        identity = resolve_tester_identity()

    assert identity.value == "bob"
    assert identity.resolution_source == "getpass.getuser"
    # Diagnostic log at info level recording the fallback.
    assert any("getpass.getuser" in record.getMessage() for record in caplog.records)


def test_defaults_to_unknown_user_when_both_fail(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _raise_oserror() -> str:
        raise OSError("no controlling terminal")

    def _raise_keyerror() -> str:
        raise KeyError("no user info")

    monkeypatch.setattr("harness.identity.resolution.os.getlogin", _raise_oserror)
    monkeypatch.setattr("harness.identity.resolution.getpass.getuser", _raise_keyerror)

    with caplog.at_level(logging.WARNING, logger="harness.identity.resolution"):
        identity = resolve_tester_identity()

    assert identity.value == "unknown-user"
    assert identity.resolution_source == "unknown-user-default"
    # Diagnostic log at warning level.
    assert any("unknown-user" in record.getMessage() for record in caplog.records)


def test_empty_getlogin_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty / whitespace-only result is treated as a failure of the primary."""
    monkeypatch.setattr("harness.identity.resolution.os.getlogin", lambda: "   ")
    monkeypatch.setattr("harness.identity.resolution.getpass.getuser", lambda: "charlie")

    identity = resolve_tester_identity()

    assert identity.value == "charlie"
    assert identity.resolution_source == "getpass.getuser"


def test_tester_identity_is_frozen() -> None:
    """TesterIdentity instances are immutable (FR-002 read-only enforcement)."""
    from dataclasses import FrozenInstanceError

    identity = TesterIdentity(value="alice", resolution_source="os.getlogin")

    with pytest.raises(FrozenInstanceError):
        identity.value = "bob"  # type: ignore[misc]


def test_resolves_windows_domain_account_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec edge case (spec.md:127): domain-prefixed account names persist
    untruncated. Backslash is preserved through resolution."""
    monkeypatch.setattr(
        "harness.identity.resolution.os.getlogin", lambda: "CORP\\verylongusername.example"
    )

    identity = resolve_tester_identity()

    assert identity.value == "CORP\\verylongusername.example"
    assert identity.resolution_source == "os.getlogin"


def test_resolves_unicode_account_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec edge case: non-ASCII Unicode in account name flows through."""
    monkeypatch.setattr("harness.identity.resolution.os.getlogin", lambda: "αλίκη")

    identity = resolve_tester_identity()

    assert identity.value == "αλίκη"


def test_typeerror_in_monkeypatch_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Programming errors (TypeError) MUST propagate — they're not in the
    narrow exception set (OSError / KeyError / ImportError). This guards
    against accidentally swallowing real bugs."""

    def _bogus():
        raise TypeError("monkeypatch programming error")

    monkeypatch.setattr("harness.identity.resolution.os.getlogin", _bogus)

    with pytest.raises(TypeError):
        resolve_tester_identity()
