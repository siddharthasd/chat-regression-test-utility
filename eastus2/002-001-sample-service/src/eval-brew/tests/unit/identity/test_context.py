"""US1 tests — IdentityContext singleton invariants (FR-002, FR-003).

Verifies:
  - current() raises RuntimeError before _initialize_once()
  - _initialize_once raises RuntimeError on second call
  - current() returns the identical instance across multiple reads (no drift)
  - The public API exposes no setter / mutate / override surface (FR-003 / SC-010)
"""

from __future__ import annotations

import pytest

from harness.identity.context import IdentityContext
from harness.identity.resolution import TesterIdentity


@pytest.fixture(autouse=True)
def reset_identity_context() -> None:
    """Reset the singleton's class state between tests so each test runs clean."""
    yield
    IdentityContext._resolved = None


def test_current_raises_before_init() -> None:
    IdentityContext._resolved = None

    with pytest.raises(RuntimeError, match="not.*initialized|before initialization"):
        IdentityContext.current()


def test_initialize_once_succeeds() -> None:
    identity = TesterIdentity(value="alice", resolution_source="os.getlogin")

    IdentityContext._initialize_once(identity)

    assert IdentityContext.current() is identity


def test_initialize_once_raises_on_second_call() -> None:
    identity_a = TesterIdentity(value="alice", resolution_source="os.getlogin")
    identity_b = TesterIdentity(value="bob", resolution_source="os.getlogin")

    IdentityContext._initialize_once(identity_a)

    with pytest.raises(RuntimeError, match="already initialized"):
        IdentityContext._initialize_once(identity_b)


def test_no_drift_within_process() -> None:
    """SC-001: multiple reads return the identical Python object reference."""
    identity = TesterIdentity(value="alice", resolution_source="os.getlogin")
    IdentityContext._initialize_once(identity)

    first = IdentityContext.current()
    second = IdentityContext.current()
    third = IdentityContext.current()

    assert first is second is third
    assert first.value == "alice"


def test_no_setter() -> None:
    """FR-003 / SC-010: the public API exposes only `current()` — no setter,
    no mutator, no override.

    Positive-form assertion (more robust than blacklisting substrings):
    enumerate the full public attribute set and assert it matches the
    allowlist exactly. Any new public attribute requires a deliberate
    update to this test — that's the gate.

    The real enforcement for "production code MUST NOT write to
    `_resolved`" is the ruff SLF lint rule + per-line noqa allowlist
    (see pyproject.toml + bootstrap.py). This test is the API-surface
    introspection check.
    """
    public_attrs = {name for name in dir(IdentityContext) if not name.startswith("_")}

    # The class exposes exactly `current` as its public API. Methods inherited
    # from `object` (mro, __class__, etc.) are all dunder-prefixed, so they're
    # filtered out by the underscore check.
    expected_public_attrs = {"current"}

    assert public_attrs == expected_public_attrs, (
        f"IdentityContext public surface drifted from the allowlist. "
        f"Expected {expected_public_attrs}, got {public_attrs}. "
        f"Any new public attribute on this class needs explicit review "
        f"against FR-003 (no override surface)."
    )
