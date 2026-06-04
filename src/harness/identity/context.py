"""IdentityContext singleton (010 FR-002 / FR-003).

Process-scoped holder for the resolved TesterIdentity. Initialized once at app
startup via `_initialize_once()`; read-only thereafter via `current()`.

Invariants (per contracts/identity-context-api.md):
  1. Single initialization: `_initialize_once()` raises on the second call.
  2. No re-resolution: there is no public re-resolve method; `_resolved` is the
     single source of truth.
  3. No override surface: the public API exposes only `current()`. The class
     attribute `_resolved` IS writable (test fixtures depend on this), but
     production code MUST NOT write to it directly — CI/lint gates this per
     plan.md's SC-010 verification path.
  4. No drift: two reads of `current()` return the identical Python object.
"""

from __future__ import annotations

from harness.identity.resolution import TesterIdentity


class IdentityContext:
    """Process-scoped singleton for the resolved tester identity."""

    # Module-level mutable storage. Written exactly once per process by
    # _initialize_once(). Test fixtures write directly to this (via monkeypatch)
    # — see contracts/identity-context-api.md for the documented hatch.
    _resolved: TesterIdentity | None = None

    @classmethod
    def current(cls) -> TesterIdentity:
        """Return the resolved TesterIdentity.

        Raises:
            RuntimeError: if called before `_initialize_once()` has run.
                Indicates a startup-ordering bug; the app factory MUST
                initialize the context as the first action. The exception
                message is the exact string the contract pins (see
                contracts/identity-context-api.md) — consumers MAY rely
                on string-matching the literal text.
        """
        if cls._resolved is None:
            raise RuntimeError("IdentityContext accessed before initialization")
        return cls._resolved

    @classmethod
    def _initialize_once(cls, identity: TesterIdentity) -> None:
        """Set the resolved identity exactly once per process.

        Args:
            identity: The TesterIdentity to install.

        Raises:
            RuntimeError: if called more than once in the same process.
                The exception message is the exact string the contract
                pins — does NOT leak the previously-resolved value, since
                this pattern will be reused for modules where the value
                IS sensitive.
        """
        if cls._resolved is not None:
            raise RuntimeError("IdentityContext already initialized")
        cls._resolved = identity
