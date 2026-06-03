"""US2 integration test — Job.createdBy auto-stamping (FR-004).

Verifies the API surface 010 provides for 003's wizard Step 1 Next to consume:
calling the "create draft job" code path with an active IdentityContext stamps
the resolved tester identity onto Job.createdBy.

Uses a stub Job repository (the real one lives in 009 / not implemented yet).
Uses a `_test_wizard_step1_handler` helper that mirrors what 003's eventual
Step 1 Next will do. Helper + stub repo will be deleted when 003 lands and the
real handler + 009's JobRepository replace them.
"""

from __future__ import annotations

from harness.identity import IdentityContext
from tests.conftest import StubJobRepository


def _test_wizard_step1_handler(
    repo: StubJobRepository, name: str, description: str | None = None
) -> dict:
    """Mirrors what 003's wizard Step 1 Next handler will eventually do.

    Reads the active tester identity from the IdentityContext singleton, then
    calls the repository's create_draft method with the resolved value stamped
    on Job.createdBy. Delete this helper when 003 implements the real handler.
    """
    created_by = IdentityContext.current().value
    return repo.create_draft(name=name, description=description, createdBy=created_by)


def test_job_createdBy_stamps_identity_alice(
    stub_identity, stub_job_repository: StubJobRepository
) -> None:
    """Given the OS-derived tester identity is 'alice', When the wizard creates
    a Draft Job on Step 1, Then Job.createdBy == 'alice'."""
    stub_identity.with_identity("alice")

    _test_wizard_step1_handler(stub_job_repository, name="My regression run")

    assert len(stub_job_repository.created_jobs) == 1
    assert stub_job_repository.created_jobs[0]["createdBy"] == "alice"
    assert stub_job_repository.created_jobs[0]["jobName"] == "My regression run"


def test_job_createdBy_stamps_identity_bob(
    stub_identity, stub_job_repository: StubJobRepository
) -> None:
    """The stamping is per-process-identity, not per-call resolution.

    A second process running as 'bob' creates a job with createdBy='bob';
    Job.createdBy reflects whatever the IdentityContext holds at the moment
    of the call.
    """
    stub_identity.with_identity("bob")

    _test_wizard_step1_handler(stub_job_repository, name="Bob's run", description="trial")

    assert stub_job_repository.created_jobs[0]["createdBy"] == "bob"
    assert stub_job_repository.created_jobs[0]["description"] == "trial"


def test_job_createdBy_stamps_unknown_user_default(
    stub_identity, stub_job_repository: StubJobRepository
) -> None:
    """Degraded resolution still stamps; the 'unknown-user' literal propagates."""
    stub_identity.with_identity("unknown-user")

    _test_wizard_step1_handler(stub_job_repository, name="Headless CI run")

    assert stub_job_repository.created_jobs[0]["createdBy"] == "unknown-user"


def test_job_createdBy_immutable_across_two_jobs(
    stub_identity, stub_job_repository: StubJobRepository
) -> None:
    """Two job creations within the same process get the same createdBy value
    (no drift, mirrors SC-001).
    """
    stub_identity.with_identity("alice")

    _test_wizard_step1_handler(stub_job_repository, name="First run")
    _test_wizard_step1_handler(stub_job_repository, name="Second run")

    assert len(stub_job_repository.created_jobs) == 2
    assert all(job["createdBy"] == "alice" for job in stub_job_repository.created_jobs)
