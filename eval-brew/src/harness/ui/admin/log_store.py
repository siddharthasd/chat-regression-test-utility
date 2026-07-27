"""In-process log store for the admin Logs screen.

Two independent deques (fixed capacity 50) hold recent records:
  - _errors  : captured from the harness logging hierarchy at ERROR+
  - _audits  : emitted explicitly by admin action routes

Both deques are appendleft so index 0 is always the most-recent entry.
Data is in-memory only and resets when the process restarts.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime

_CAPACITY = 50


@dataclass(frozen=True)
class ErrorEntry:
    timestamp: str
    level: str
    logger: str
    message: str


@dataclass(frozen=True)
class AuditEntry:
    timestamp: str
    actor: str
    action: str
    detail: str


_errors: deque[ErrorEntry] = deque(maxlen=_CAPACITY)
_audits: deque[AuditEntry] = deque(maxlen=_CAPACITY)


class _ErrorHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _errors.appendleft(
                ErrorEntry(
                    timestamp=datetime.fromtimestamp(record.created, UTC).strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    ),
                    level=record.levelname,
                    logger=record.name,
                    message=record.getMessage(),
                )
            )
        except Exception:  # noqa: BLE001
            pass  # never raise from inside a log handler


def install() -> None:
    """Attach the error-capture handler to the harness logger. Idempotent."""
    harness_logger = logging.getLogger("harness")
    for existing in harness_logger.handlers:
        if isinstance(existing, _ErrorHandler):
            return
    harness_logger.addHandler(_ErrorHandler(level=logging.ERROR))


def record_audit(actor: str, action: str, detail: str = "") -> None:
    _audits.appendleft(
        AuditEntry(
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            actor=actor,
            action=action,
            detail=detail,
        )
    )


def recent_errors(n: int = 10) -> list[ErrorEntry]:
    return list(_errors)[:n]


def recent_audits(n: int = 10) -> list[AuditEntry]:
    return list(_audits)[:n]
