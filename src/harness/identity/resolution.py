"""OS-derived tester-identity resolution (010 FR-001).

Resolves the tester identity through a documented fallback chain:
    1. os.getlogin()
    2. getpass.getuser()
    3. "unknown-user" default

Returns a frozen `TesterIdentity` dataclass carrying the resolved value and a
diagnostic `resolution_source` field indicating which step succeeded.

NOTE on logging: the diagnostic log lines emitted here fire BEFORE the
structlog `bind_contextvars(tester_identity=...)` binding lands (US4 T028),
so these startup lines lack the `tester_identity` field. This is an
acknowledged exemption from FR-006 / SC-005 ("no mid-process drift") for the
resolution-phase log lines only; all post-binding log lines carry the field.
Uses stdlib `logging` for the same reason — structlog isn't configured yet.
"""

from __future__ import annotations

import getpass
import logging
import os
from dataclasses import dataclass
from typing import Literal

_logger = logging.getLogger(__name__)


ResolutionSource = Literal[
    "os.getlogin",
    "getpass.getuser",
    "unknown-user-default",
    "stub",  # Reserved for test fixtures only — see contracts/identity-context-api.md.
]


@dataclass(frozen=True)
class TesterIdentity:
    """Immutable value object carrying the resolved tester identity.

    Attributes:
        value: The OS-derived account name (e.g., "alice", "siddhartha.dhamankar")
            or the literal "unknown-user" fallback. Never null, never empty.
        resolution_source: Which step of the fallback chain produced the value.
            The "stub" variant is reserved for test fixtures.
    """

    # Suppress pytest's "cannot collect test class" warning: the class name
    # starts with "Test" so pytest's default `python_classes = Test*` matches
    # it, then complains it can't collect because dataclass generates an
    # __init__. `__test__ = False` tells pytest to skip it explicitly.
    __test__ = False

    value: str
    resolution_source: ResolutionSource


def resolve_tester_identity() -> TesterIdentity:
    """Resolve the tester identity per FR-001's three-step fallback chain.

    Returns:
        A TesterIdentity instance with a non-empty `value` and a
        `resolution_source` indicating which step succeeded.

    Side effects:
        Emits at most one diagnostic log line (info-level for fallback to
        getpass.getuser; warning-level for the unknown-user default).
    """
    # Narrow exception types: `os.getlogin()` raises `OSError` (most platforms);
    # `getpass.getuser()` raises `KeyError` (no pwd entry / missing env vars)
    # or `ImportError` (no `pwd` module — Windows Python without optional deps).
    # Catching `Exception` more broadly would swallow programming errors like
    # `TypeError` from a botched monkeypatch.

    # Step 1: os.getlogin
    try:
        candidate = os.getlogin()
    except OSError:
        candidate = ""
    if candidate and candidate.strip():
        return TesterIdentity(value=candidate.strip(), resolution_source="os.getlogin")

    # Step 2: getpass.getuser fallback
    try:
        candidate = getpass.getuser()
    except (KeyError, ImportError, OSError):
        candidate = ""
    if candidate and candidate.strip():
        _logger.info(
            "identity resolution: os.getlogin failed; using getpass.getuser=%s",
            candidate.strip(),
        )
        return TesterIdentity(value=candidate.strip(), resolution_source="getpass.getuser")

    # Step 3: unknown-user default
    _logger.warning(
        "identity resolution: both os.getlogin and getpass.getuser failed; "
        "defaulting to 'unknown-user'"
    )
    return TesterIdentity(value="unknown-user", resolution_source="unknown-user-default")
