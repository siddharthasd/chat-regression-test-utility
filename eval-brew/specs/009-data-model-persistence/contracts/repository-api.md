# Contract: Repository Public API

**Module**: `harness.persistence.repositories`
**Stability**: Internal-stable — consumed by `003` (wizard), `011` (CSV upload), `012` (orchestrator), `013` (connector CRUD), `014` (evaluator CRUD), and all UI modules.

All repository classes accept a SQLAlchemy `Session` at construction. Callers manage session lifetime (context-managed `Session` from `SessionLocal`). All write operations MUST be called within an active transaction (`session.begin()` or `session.begin_nested()`).

---

## `JobRepository(session: Session)`

```python
def create_draft(name: str, description: str | None, created_by: str) -> Job
    # Creates a Job in DRAFT status. Stamps harness_version from importlib.metadata.
    # Raises: nothing (name uniqueness is NOT enforced in v1).

def get(job_id: str) -> Job | None
    # Returns Job or None.

def get_by_status(status: str) -> list[Job]
    # Returns all Jobs with the given status string.

def transition_to_queued(job_id: str) -> None
    # DRAFT → QUEUED. Runs FR-007a selection gate.
    # Raises: JobNotFoundError, InvalidTransitionError, MissingSnapshotFieldError,
    #         InactiveRegistrationError.

def transition_to_running(job_id: str) -> None
    # QUEUED → RUNNING.
    # Raises: JobNotFoundError, InvalidTransitionError.

def transition_to_completed(job_id: str) -> None
    # RUNNING → COMPLETED. Sets completed_at.
    # Raises: JobNotFoundError, InvalidTransitionError.

def transition_to_failed(job_id: str, error_details: str) -> None
    # RUNNING/QUEUED/CANCELLING → FAILED. Sets completed_at + error_details.
    # Raises: JobNotFoundError, InvalidTransitionError.

def transition_to_cancelling(job_id: str) -> None
    # RUNNING/QUEUED → CANCELLING.
    # Raises: JobNotFoundError, InvalidTransitionError.

def transition_to_cancelled(job_id: str) -> None
    # CANCELLING → CANCELLED. Creates EvaluationResult stubs atomically (FR-003a).
    # Raises: JobNotFoundError, InvalidTransitionError.

def set_connector_snapshot(job_id: str, registration: ConnectorRegistration) -> None
    # Copies registration fields onto Job's connector_* snapshot columns.
    # Raises: JobNotFoundError, SnapshotImmutableError (if status != DRAFT).

def set_evaluator_snapshot(job_id: str, registration: EvaluationAgentRegistration) -> None
    # Symmetric to set_connector_snapshot.

def set_csv_metadata(job_id: str, filename: str, row_count: int) -> None
    # Sets source_csv_filename + total_utterance_count. Status MUST be DRAFT.
    # Raises: JobNotFoundError, SnapshotImmutableError.

def increment_processed_count(job_id: str) -> None
    # Atomically increments processed_count by 1.

def increment_failed_count(job_id: str) -> None
    # Atomically increments failed_count by 1.

def delete(job_id: str) -> None
    # Cascades Utterance + EvaluationResult. Status MUST be in {draft, failed, cancelled}.
    # Raises: JobNotFoundError, JobNotDeletableError.

def delete_all_failed_and_cancelled() -> int
    # Bulk deletes all FAILED and CANCELLED jobs. Returns count deleted.
    # Atomic: snapshots qualifying set inside the transaction before deleting.
```

---

## `UtteranceRepository(session: Session)`

```python
def bulk_create(job_id: str, rows: list[UtteranceCreateData]) -> list[Utterance]
    # UtteranceCreateData = TypedDict with utterance_text, test_id, row_index, extra_metadata.
    # Inserts all rows atomically. Assigns UUID utterance_ids.
    # Raises: SnapshotImmutableError if parent job status != DRAFT.

def get_by_job_ordered(job_id: str) -> list[Utterance]
    # Returns all Utterances for a job ordered by row_index ASC.

def delete_by_job(job_id: str) -> int
    # Deletes all Utterances for a job (cascades EvaluationResult). Returns count.
    # Used by 011's replace-on-upload semantics (FR-018a).
    # Raises: SnapshotImmutableError if parent job status != DRAFT.

def count_by_job(job_id: str) -> int
```

---

## `EvaluationResultRepository(session: Session)`

```python
def create(result: EvaluationResultCreateData) -> EvaluationResult
    # EvaluationResultCreateData covers all non-PK fields.

def bulk_create_stubs(utterance_ids: list[str], agent_id: str, timestamp: datetime) -> int
    # Called by JobRepository.transition_to_cancelled for the cancellation-stub path.
    # Uses bulk INSERT for performance; returns count inserted.

def get_by_utterance(utterance_id: str) -> EvaluationResult | None

def get_by_job(job_id: str) -> list[EvaluationResult]
    # Via JOIN to Utterance.job_id.
```

---

## `ConnectorRegistrationRepository(session: Session)`

```python
def create(data: ConnectorRegistrationCreateData) -> ConnectorRegistration
    # Encrypts credential subfields in auth_descriptor before persisting.
    # Assigns UUID connector_id.

def get(connector_id: str) -> ConnectorRegistration | None
    # Returns raw record (with ciphertext in auth_descriptor).

def get_active() -> list[ConnectorRegistration]
    # Returns all non-archived registrations. Used by wizard Step 3 dropdown.

def get_auth_descriptor_decrypted(connector_id: str) -> dict
    # Returns auth_descriptor with credential subfields decrypted.
    # Raises: HarnessKeyMismatchError on decryption failure.

def update(connector_id: str, data: ConnectorRegistrationUpdateData) -> ConnectorRegistration
    # Re-encrypts credential subfields if auth_descriptor changes.
    # Raises: connector not found.

def archive(connector_id: str) -> None
    # Sets archived=True, archived_at=now. Idempotent.

def restore(connector_id: str) -> None
    # Sets archived=False, archived_at=None.

def hard_delete(connector_id: str) -> None
    # Permanently removes. MUST be called only after caller verifies no historical
    # Jobs reference this connector_id (per 013 FR-019). Does not enforce this
    # itself — that gate lives in the application layer (013's CRUD UI).
    # Raises: connector not found.
```

---

## `EvaluationAgentRegistrationRepository(session: Session)`

Symmetric to `ConnectorRegistrationRepository` with `evaluation_agent_id` as PK and `get_active()` used by wizard Step 4 dropdown. Additional method:

```python
def get_declared_dimensions(evaluation_agent_id: str) -> list[str]
    # Returns the declaredScoringDimensions list for the given registrar.
    # Used by 004 (detail view pre-render) and 005 (export column order).
```

---

## Invariants

1. All `create_*` methods assign a fresh UUID4 PK if none is provided.
2. `created_at` is always set to `datetime.utcnow()` at creation; never writable by the caller.
3. `updated_at` is bumped on every write for the two registration entities.
4. Credential subfields in `auth_descriptor` are NEVER returned in plaintext by any read method except `get_auth_descriptor_decrypted()`. All other methods return the raw JSON with ciphertext intact.
5. No repository method logs or prints credential values.
