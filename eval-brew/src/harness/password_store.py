"""In-memory per-row password store (011 FR-015; consumed by the orchestrator, 012).

A process-global, thread-safe mapping ``(job_id, utterance_id) -> password``.
Plaintext, in-memory only: never persisted, never encrypted, lost on process
exit. The orchestrator looks a password up immediately before the connector call
and evicts it immediately after (per-row eviction discipline, 012 FR-011). 011
(CSV upload) will be the producer; until it exists, tests populate the store
directly.

Keyed by ``(job_id, utterance_id)`` so concurrent jobs never collide (012 FR-022).
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_store: dict[tuple[str, str], str] = {}


def put(job_id: str, utterance_id: str, password: str) -> None:
    """Store (or overwrite) the plaintext password for one row."""
    with _lock:
        _store[(job_id, utterance_id)] = password


def get(job_id: str, utterance_id: str) -> str | None:
    """Return the row's password, or ``None`` if absent."""
    with _lock:
        return _store.get((job_id, utterance_id))


def evict(job_id: str, utterance_id: str) -> None:
    """Delete one row's entry; no-op if absent (012 FR-011 step 3)."""
    with _lock:
        _store.pop((job_id, utterance_id), None)


def clear_job(job_id: str) -> None:
    """Delete every entry for a job (terminal-transition cleanup, 012 FR-016/020)."""
    with _lock:
        for key in [k for k in _store if k[0] == job_id]:
            del _store[key]


def job_has_entries(job_id: str) -> bool:
    """True iff any entry exists for the job (US6 pre-row gate, 012 FR-017)."""
    with _lock:
        return any(k[0] == job_id for k in _store)


def _reset_for_tests() -> None:
    """Clear the entire store (test isolation only)."""
    with _lock:
        _store.clear()
