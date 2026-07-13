# Phase 0 Research: Data Model & Persistence Layer (Module 2)

**Date**: 2026-06-02
**Plan**: `specs/009-data-model-persistence/plan.md`
**Spec**: `specs/009-data-model-persistence/spec.md`

Resolves all `NEEDS CLARIFICATION` and dependency-choice questions from the plan's Technical Context. Each decision below is directly codeable — the implementer should not need additional research.

---

## R1: ORM Mapping Style

**Decision**: SQLAlchemy 2.0 type-annotated declarative style using `DeclarativeBase`, `Mapped[T]`, and `mapped_column()` throughout. A single shared `Base = DeclarativeBase()` in `src/harness/persistence/base.py`; all five entity classes (plus `SchemaVersion`) inherit from it.

- Non-null string columns: `Mapped[str]`
- Nullable columns: `Mapped[Optional[str]]`
- JSON columns: `mapped_column(JSON)` — SQLAlchemy stores as TEXT in SQLite and handles `json.dumps`/`json.loads` transparently.
- Enum values (Job `status`): `mapped_column(String(20))` storing the lowercase string; a Python `enum.StrEnum` enforces valid values at the application boundary (avoids SQLite enum-migration pain).
- Primary keys: `mapped_column(String(36), primary_key=True)` (UUID strings).
- Relationships: declared with `relationship(..., cascade="all, delete-orphan")` for cascade-delete chains.

**Rationale**: The 2.0 annotated style gives full static-type-checker coverage (mypy/pyright infer column types directly from `Mapped[str]` annotations) with no runtime overhead over the legacy style. `expire_on_commit=False` on `sessionmaker` prevents SQLAlchemy from re-querying every attribute after a commit — important in the orchestrator's hot path.

**Alternatives considered**:
- **Legacy `Column()` / `relationship()` (SQLAlchemy 1.x style)**: Fully functional but produces no type inference. The 2.0 annotated style is a strict superset.
- **SQLAlchemy Core (Table + insert/select, no ORM)**: Rejected — verbose for five entities; session-level identity map and cascade relationships become manual bookkeeping.

---

## R2: Database Engine Configuration

**Decision**: Apply four SQLite PRAGMAs at every new connection via a `@event.listens_for(engine, "connect")` listener that runs them on the raw `sqlite3.Connection`:

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=5000")
```

- `WAL`: Write-Ahead Logging allows concurrent reads while one writer is active. Relevant even in single-process use because Flask's dev server may open a background read and the orchestrator may open a second connection.
- `foreign_keys=ON`: SQLite does NOT enforce FK constraints by default. Without this, `ON DELETE CASCADE` on `Utterance.job_id` and `EvaluationResult.utterance_id` is silently ignored — orphaned rows accumulate. **Must be set per-connection** (not stored in the database file).
- `synchronous=NORMAL`: Skips the post-WAL-write fsync while still syncing on WAL checkpoint — safe for a developer tool (power-loss between checkpoint and next sync could lose the last WAL frame but not corrupt the database). `FULL` is the default but too slow for the 1,000-row design target. `OFF` is rejected as it risks corruption.
- `busy_timeout=5000`: Retries for up to 5 seconds before raising `OperationalError: database is locked`. Guards against WAL-checkpoint lock windows.

**Alternatives considered**:
- Setting connection args via `create_engine(..., connect_args={"...": "..."})`: Only passes through Python `sqlite3` module kwargs, not PRAGMA strings — the event listener is the correct approach.
- `journal_mode=DELETE` (default): Readers block writers; WAL is strictly better.

---

## R3: Alembic Integration

**Decision**:
- `alembic.ini` at repository root.
- Migrations at `src/harness/persistence/migrations/`, standard layout (`env.py`, `script.py.mako`, `versions/`).
- `env.py` sets `target_metadata = Base.metadata` for `--autogenerate` support.
- `init_db(db_path)` in `persistence/engine.py` handles startup migration at bootstrap time.

**Startup logic** (`init_db`):
1. Ensure parent directory exists (FR-018).
2. Create engine with PRAGMA listener.
3. Read `current_revision` via `MigrationContext.configure(conn).get_current_revision()` — `None` for a brand-new DB.
4. Read `head_revision` from the Alembic script directory.
5. If `current == head`: return engine (up to date).
6. If `current` is a descendant of `head` (i.e., DB was written by a newer harness): raise `HarnessDatabaseTooNewError` — propagates to `bootstrap.py` which logs via structlog and exits nonzero before Flask starts (FR-016).
7. Otherwise: run `alembic.command.upgrade(cfg, "head")` (FR-014).

The `HarnessDatabaseTooNewError` message matches the spec's verbatim wording: `"database newer than this harness version; upgrade harness"`.

Migration files are named `0001_initial_schema.py`, `0002_...`, etc. for human readability.

**Alternatives considered**:
- `alembic.ini` inside `src/harness/persistence/`: Rejected — Alembic's CLI (`alembic upgrade head`) works from the repo root without a `--config` flag when `alembic.ini` is at the root.
- Custom schema-version table + hand-written comparison logic: Rejected — Alembic's revision graph already handles ordering, branching, and partial-failure detection.

---

## R4: Encryption Utility

**Decision**: `cryptography>=42.0` with **Fernet** symmetric encryption. Machine-local key stored as a 44-character URL-safe-base64 string in a plain text file:

- **Windows**: `%LOCALAPPDATA%\harness\master.key` (fallback: `~\.harness\master.key`).
- **macOS/Linux**: `~/.harness/master.key`.
- Override: `HARNESS_KEY_FILE` environment variable.

Key file created with mode `0o600` (owner-read-only) on first use via `os.open(..., os.O_CREAT | os.O_EXCL, 0o600)` + `os.fdopen`.

Public API (`src/harness/persistence/encryption.py`):

```python
def encrypt_credential(plaintext: str) -> str:   # reads key lazily; returns ciphertext str
def decrypt_credential(ciphertext: str) -> str    # raises HarnessKeyMismatchError on InvalidToken
def get_or_create_key() -> bytes                  # load from file or generate + write
```

Encryption boundary is **per-credential-subfield** within `authDescriptor` JSON (not the whole blob). The `mode`, `headerName`, and `username` subfields remain plaintext; only `token` (bearer), `apiKeyValue` (api-key-header), and `password` (basic-auth) are Fernet-encrypted before the JSON column is written.

Key file absence at startup defers the error to the first credential operation (`decrypt_credential` raises `HarnessKeyMismatchError`). First write auto-generates and persists the key.

**Alternatives considered**:
- **PyNaCl / libsodium secretbox**: Stronger, but C-extension with more complex Windows packaging. Fernet (AES-128-CBC + HMAC-SHA256) is sufficient for credential-at-rest on a developer's machine.
- **AES-GCM via `cryptography.hazmat`**: More control; but Fernet's `MultiFernet` key-rotation hook is a useful future-proofing affordance that hazmat primitives require manual nonce/tag management for.
- **OS keychain via `keyring` library**: Ideal for credential storage but requires a dep, OS-specific service entries, and headless-server workarounds. Too heavy for v1.

---

## R5: Repository Pattern

**Decision**: One repository class per entity, all accepting a SQLAlchemy `Session` at construction (dependency-injected, not self-managed). Five classes in `src/harness/persistence/repositories/`.

`JobRepository.create_draft()` signature — compatible with the existing `StubJobRepository` in `tests/conftest.py`:

```python
def create_draft(
    self,
    name: str,
    description: str | None,
    created_by: str,
) -> Job:
    ...  # harnessVersion populated from importlib.metadata.version("harness")
```

Returns the ORM `Job` instance (not a dict — callers upgrade from `.dict-key` access to `.attribute` access, which is a strict improvement). Session lifetime is managed by the caller (Flask request context or CLI command) via a context-managed `Session` from `sessionmaker`. No `UnitOfWork` wrapper in v1.

**Alternatives considered**:
- **Single `UnitOfWork` with sub-repositories**: Premature for five entities. Can be layered on later.
- **Generic `Repository[T]` base**: Per-entity query methods differ enough (e.g., `JobRepository.get_by_status()` vs. `UtteranceRepository.get_by_job_id_ordered()`) that a generic base saves little while obscuring intent.

---

## R6: Atomicity for Multi-Entity Writes

**Decision**: One SQLAlchemy `Session` per logical operation, managed as a nested context manager:

```python
with SessionLocal() as session:
    with session.begin():           # starts txn; commits on exit, rolls back on exception
        job_repo = JobRepository(session)
        result_repo = EvaluationResultRepository(session)
        result_repo.create(...)
        job_repo.increment_processed_count(job_id)
```

`SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)`.

Flask uses a per-request `scoped_session` cleaned up in `teardown_appcontext`. CLI uses a plain context-managed `Session`.

**Alternatives considered**:
- **Per-operation session**: Breaks cross-entity atomicity; rejected by FR-020.
- **Single long-lived session for process lifetime**: Identity-map bloat; a failed operation poisons the session for all subsequent ones.

---

## R7: Status-Gated Delete + Cascade

**Decision**: Status-gate enforcement lives at the **repository layer** (not ORM event listeners). `JobRepository.delete(job_id)` checks `Job.status` in `{draft, failed, cancelled}` within the same transaction as the DELETE before proceeding. ORM cascade (`cascade="all, delete-orphan"` + `PRAGMA foreign_keys=ON`) handles the Utterance → EvaluationResult propagation at the SQLite level for performance.

`JobNotDeletableError(job_id, current_status)` raised for non-deletable statuses.
`JobNotFoundError(job_id)` raised for missing jobs.

Bulk delete (`delete_all_failed_and_cancelled`) snapshots the qualifying id-set inside the transaction before deleting to avoid including jobs that transition into `failed`/`cancelled` mid-operation (FR-012 atomicity requirement).

**Alternatives considered**:
- **`@event.listens_for(Session, "before_delete")` listener**: Opaque and hard to unit-test. Explicit repository check is preferred.
- **Database CHECK constraint**: SQLite CHECK constraints cannot reference other tables; cannot enforce cross-entity gates.

---

## R8: Cancellation Stubs (FR-003a)

**Decision**: `JobRepository.transition_to_cancelled(job_id)` implements the atomic `cancelling → cancelled` + stub creation in a single session transaction:

1. `SELECT ... FOR UPDATE` to lock the Job row.
2. Verify `status == CANCELLING`; raise `InvalidTransitionError` otherwise.
3. Query Utterances with no linked EvaluationResult via `~Utterance.evaluation_result.has()`.
4. Bulk-insert stubs (threshold > 500: use `session.execute(insert(EvaluationResult), [...])` for performance; otherwise `session.add` per stub).
5. Update `job.status = CANCELLED`, `job.completed_at = now`.

The `~Utterance.evaluation_result.has()` ORM expression translates to `NOT EXISTS (SELECT 1 FROM evaluation_result WHERE utterance_id = ...)`.

**Alternatives considered**:
- **Raw SQL `INSERT INTO ... SELECT ...`**: Bypasses ORM event hooks; viable for very large jobs but less auditable.
- **Separate "cancelled" boolean on Utterance**: Rejected — EvaluationResult is the spec-mandated single source of truth.

---

## R9: Snapshot Encryption Implementation

**Decision**: The spec interpretation is confirmed: encryption/decryption touches **only** the live `ConnectorRegistration` and `EvaluationAgentRegistration` records. The Job snapshot columns (`connectorAuthDescriptor`, `evaluatorAuthDescriptor`) store the **verbatim ciphertext** copied from the registration at job-creation time — the wizard does NOT re-encrypt (per `003 FR-009`).

- **Encrypt-on-save**: `ConnectorRegistrationRepository.create()` and `.update()` call `encrypt_credential()` on each secret subfield of the `authDescriptor` dict before serializing to JSON.
- **Decrypt-on-read**: The orchestrator (or `harness info` equivalent for credentials) calls a `get_auth_descriptor_decrypted()` method that calls `decrypt_credential()` on ciphertext subfields. General data-layer reads return the raw JSON with ciphertext intact (the UI renders masked placeholders per parent FR-023a).
- **Job snapshot copy**: `JobRepository.set_snapshot()` copies `registration.auth_descriptor` JSON column value as-is (already ciphertext) into `Job.connector_auth_descriptor`. No re-encryption.

If the machine-local key is rotated, both the registration ciphertext and all job snapshots become undecryptable simultaneously — consistent with the spec's "DB moved to different machine" edge case.

**Alternatives considered**:
- **Re-encrypt at snapshot time with a job-specific key**: Unnecessary complexity for a single-user local tool.
- **Store credentials only on registration, dereference at orchestrator time**: Breaks snapshot immutability (archived/edited registrations would change historical job behavior). Rejected by FR-005.

---

## R10: Draft→Queued Selection Gate (FR-007a)

**Decision**: Gate enforced inside `JobRepository.transition_to_queued(job_id)` (not an ORM event listener). Runs within the same transaction as the status update:

```python
def transition_to_queued(self, job_id: str) -> None:
    job = self._session.get(Job, job_id, with_for_update=True)
    # Check connectorId populated
    if not job.connector_id:
        raise MissingSnapshotFieldError(job_id, "connectorId")
    # Check evaluationAgentId populated
    if not job.evaluation_agent_id:
        raise MissingSnapshotFieldError(job_id, "evaluationAgentId")
    # Check connector is currently active (not archived)
    connector = self._session.get(ConnectorRegistration, job.connector_id)
    if connector is None or connector.archived:
        raise InactiveRegistrationError(job_id, "connector", job.connector_id)
    # Check evaluator is currently active
    agent = self._session.get(EvaluationAgentRegistration, job.evaluation_agent_id)
    if agent is None or agent.archived:
        raise InactiveRegistrationError(job_id, "evaluationAgent", job.evaluation_agent_id)
    job.status = JobStatus.QUEUED
    job.started_at = datetime.utcnow()
```

`with_for_update=True` pessimistic lock prevents a concurrent archive of the registration from racing between the check and the commit.

**Alternatives considered**:
- **SQLAlchemy event listener**: Too broad (fires on every flush), produces opaque errors, hard to unit-test.
- **Database trigger**: SQLite triggers can't easily surface structured application errors.

---

## R11: Test Database Pattern

**Decision**: **In-memory SQLite (`:memory:`) with Alembic migrations applied once at session scope; function-scoped savepoint rollback for data isolation.**

```python
@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    _apply_pragmas(engine)
    alembic_cfg = _build_alembic_cfg_for_engine(engine)
    command.upgrade(alembic_cfg, "head")
    yield engine
    engine.dispose()

@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        session.begin_nested()   # savepoint
        yield session
        session.rollback()       # undo test writes; schema intact
```

Migrations run once per pytest session (fast). Data resets between tests without schema recreation.

**Alternatives considered**:
- **`tmpdir`-based file DB per test**: Correct but slow (per-test migration cost) and adds filesystem I/O. Rejected.
- **`pytest-alembic` package**: A thin wrapper around this pattern. Adds a dependency for marginal benefit; the inline pattern above is simple enough to own directly.

---

## R12: Dependency Additions

**Decision**: Apply to `pyproject.toml`:

**Runtime additions** (`[project] dependencies`):
```
sqlalchemy>=2.0
alembic>=1.13
cryptography>=42.0
```

**No new dev deps** beyond `010`'s baseline. The test-DB pattern (R11) is inline; `pytest-alembic` is NOT added.

**`alembic.ini`** committed at repository root. Initial migration `versions/0001_initial_schema.py` covers all five entity tables + `schema_version` sentinel.

| Package | Min version | Reason |
|---|---|---|
| `sqlalchemy` | `>=2.0` | ORM + type-annotated `mapped_column` API |
| `alembic` | `>=1.13` | Migration runner; 1.13 fixes SQLite autogenerate edge cases |
| `cryptography` | `>=42.0` | Fernet + AES-GCM; latest stable as of 2025 with no active CVEs |

---

*All NEEDS CLARIFICATION items resolved. This document is the implementation contract for spec 009; a developer can begin coding directly from these decisions.*
