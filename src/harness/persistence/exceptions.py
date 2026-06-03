"""Custom exceptions raised by the persistence layer (data-model.md table).

All inherit from ``HarnessPersistenceError`` so callers may catch the whole
family. Messages are actionable and name the offending entity/field per the
009 spec's "refuse with an actionable error" requirements.
"""

from __future__ import annotations


class HarnessPersistenceError(Exception):
    """Base class for all persistence-layer errors."""


class HarnessDatabaseTooNewError(HarnessPersistenceError):
    """DB schema revision is newer than the installed harness (FR-016)."""

    def __init__(self) -> None:
        super().__init__("database newer than this harness version; upgrade harness")


class HarnessKeyMismatchError(HarnessPersistenceError):
    """Fernet decryption failed — wrong or missing machine-local key (FR-008)."""

    def __init__(self) -> None:
        super().__init__("machine-local key missing or wrong")


class JobNotFoundError(HarnessPersistenceError):
    """No Job exists for the given id."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Job not found: {job_id!r}")


class JobNotDeletableError(HarnessPersistenceError):
    """Delete attempted on a Job whose status is not deletable (FR-011)."""

    def __init__(self, job_id: str, status: str) -> None:
        self.job_id = job_id
        self.status = status
        super().__init__(
            f"Job {job_id!r} cannot be deleted in status {status!r}; "
            "only draft, failed, or cancelled jobs are deletable"
        )


class SnapshotImmutableError(HarnessPersistenceError):
    """Write attempted on a snapshot field after the Job left draft (FR-005)."""

    def __init__(self, job_id: str, field: str) -> None:
        self.job_id = job_id
        self.field = field
        super().__init__(
            f"Field {field!r} on Job {job_id!r} is immutable past draft status"
        )


class UtteranceImmutableError(HarnessPersistenceError):
    """Write attempted on an Utterance after the parent Job left draft (FR-006)."""

    def __init__(self, utterance_id: str, field: str) -> None:
        self.utterance_id = utterance_id
        self.field = field
        super().__init__(
            f"Field {field!r} on Utterance {utterance_id!r} is immutable "
            "past the parent job's draft status"
        )


class InvalidTransitionError(HarnessPersistenceError):
    """Status transition attempted from an invalid source state."""

    def __init__(self, job_id: str, from_status: str, to_status: str) -> None:
        self.job_id = job_id
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Job {job_id!r} cannot transition from {from_status!r} to {to_status!r}"
        )


class MissingSnapshotFieldError(HarnessPersistenceError):
    """draft→queued gate: a required snapshot id is null/empty (FR-007a)."""

    def __init__(self, job_id: str, field: str) -> None:
        self.job_id = job_id
        self.field = field
        super().__init__(
            f"Job {job_id!r} cannot be queued: required field {field!r} is not set"
        )


class InactiveRegistrationError(HarnessPersistenceError):
    """draft→queued gate: a snapshotted registration is missing/archived (FR-007a)."""

    def __init__(self, job_id: str, reg_type: str, reg_id: str) -> None:
        self.job_id = job_id
        self.reg_type = reg_type
        self.reg_id = reg_id
        super().__init__(
            f"Job {job_id!r} cannot be queued: {reg_type} {reg_id!r} is not an "
            "active (non-archived) registration"
        )
