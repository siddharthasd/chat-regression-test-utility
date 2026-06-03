---
description: "Task list for Data Model & Persistence Layer (Module 2)"
---

# Tasks: Data Model & Persistence Layer (Module 2)

**Input**: Design documents from `specs/009-data-model-persistence/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R12) ✅, data-model.md ✅, contracts/ (repository-api.md, encryption-utility-api.md) ✅

**Tests**: INCLUDED. The spec defines an "Independent Test" per user story and the plan carries explicit FR→test and SC→test matrices, so test tasks are first-class here.

**Branch base**: `009` is rebased onto `012` (canonical specs) with the `010` foundation grafted (`pyproject.toml`, `src/harness/` skeleton incl. empty `persistence/__init__.py`, `bootstrap.py`, `tests/`). All paths below are relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 for user-story phases; Setup/Foundational/Polish carry no story label

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Bring the new runtime dependencies and the persistence package scaffold into the grafted foundation.

- [X] T001 Add runtime deps `sqlalchemy>=2.0`, `alembic>=1.13`, `cryptography>=42.0` to `[project].dependencies` in `pyproject.toml` (per research R12)
- [X] T002 Create the persistence package scaffold: `src/harness/persistence/models/__init__.py`, `src/harness/persistence/repositories/__init__.py`, `src/harness/persistence/migrations/versions/.gitkeep` (note `src/harness/persistence/__init__.py` already exists as an empty stub)
- [X] T003 [P] Create `alembic.ini` at repo root with `script_location = src/harness/persistence/migrations` and a placeholder `sqlalchemy.url` (overridden at runtime by `init_db`), per research R3
- [X] T004 Reinstall editable to pick up new deps and confirm imports resolve: `python -m pip install -e ".[dev]"` (verification gate before any code task)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared ORM core, engine/session machinery, encryption utility, migration chain, and test fixtures that every user story builds on.

**⚠️ CRITICAL**: No user-story phase can begin until this phase is complete.

- [X] T005 [P] Define `Base = DeclarativeBase()` in `src/harness/persistence/base.py` (research R1)
- [X] T006 [P] Define `JobStatus` `StrEnum` (`draft/queued/running/cancelling/completed/failed/cancelled`) plus the `error_status` / 9-value `error_stage` constants in `src/harness/persistence/enums.py`
- [X] T007 [P] Define all custom exceptions (`HarnessDatabaseTooNewError`, `HarnessKeyMismatchError`, `JobNotFoundError`, `JobNotDeletableError`, `SnapshotImmutableError`, `UtteranceImmutableError`, `InvalidTransitionError`, `MissingSnapshotFieldError`, `InactiveRegistrationError`) in `src/harness/persistence/exceptions.py` (per data-model.md exceptions table)
- [X] T008 [P] Create `Job` model (all 15 immutable snapshot cols + runtime counters + `created_by`/`created_at`) in `src/harness/persistence/models/job.py` (FR-001)
- [X] T009 [P] Create `Utterance` model — UUID PK, `job_id` FK `ON DELETE CASCADE`, 1-based `row_index`, `extra_metadata` JSON, **no password column** — in `src/harness/persistence/models/utterance.py` (FR-002)
- [X] T010 [P] Create `EvaluationResult` model — UUID PK, `utterance_id` FK UNIQUE `ON DELETE CASCADE`, JSON payload cols, `error_status`/`error_stage`/`error_details` — in `src/harness/persistence/models/evaluation_result.py` (FR-003)
- [X] T011 [P] Create `ConnectorRegistration` model in `src/harness/persistence/models/connector_registration.py` (FR-001a)
- [X] T012 [P] Create `EvaluationAgentRegistration` model in `src/harness/persistence/models/evaluator_registration.py` (FR-001b)
- [X] T013 Wire relationships + cascade (`Job`↔`Utterance` `cascade="all, delete-orphan"`; `Utterance`↔`EvaluationResult` `uselist=False`) and re-export all 5 models in `src/harness/persistence/models/__init__.py` (depends on T008–T012; data-model.md Relationships)
- [X] T014 Implement `src/harness/persistence/engine.py`: `create_engine`, PRAGMA `@event.listens_for(..., "connect")` listener (WAL/foreign_keys=ON/synchronous=NORMAL/busy_timeout=5000, R2), `SessionLocal = sessionmaker(expire_on_commit=False)` + `get_session()` context manager (R6), `_ensure_directory` (FR-018), and `HARNESS_DB_PATH` resolution defaulting to `~/.harness/data.db` (FR-017)
- [X] T015 [P] Implement `src/harness/persistence/encryption.py`: `get_or_create_key` (key-file priority `HARNESS_KEY_FILE` → `%LOCALAPPDATA%`/`~/.harness/master.key`, `0o600`, `O_CREAT|O_EXCL`, module lock), `encrypt_credential`, `decrypt_credential` (raises `HarnessKeyMismatchError` with the verbatim message) per encryption-utility-api.md + R4
- [X] T016 Create Alembic `src/harness/persistence/migrations/env.py` (`target_metadata = Base.metadata`, applies the R2 PRAGMAs) + `script.py.mako` (research R3)
- [X] T017 Author initial migration `src/harness/persistence/migrations/versions/0001_initial_schema.py` creating all 5 entity tables + the single-row `schema_version` sentinel (FR-013)
- [X] T018 Implement `init_db(db_path)` in `src/harness/persistence/engine.py`: ensure dir, build engine, compare current vs head revision, `upgrade(head)` when DB older/fresh, raise `HarnessDatabaseTooNewError` ("database newer than this harness version; upgrade harness") when DB newer (R3; FR-014/FR-016) — gating behavior verified later in US5
- [X] T019 Wire `init_db()` into `src/harness/bootstrap.py` immediately after `initialize_harness` (plan Structure)
- [X] T020 Add `db_engine` (session-scoped in-memory SQLite with migrations applied once) + `db_session` (function-scoped `begin_nested` savepoint rollback) fixtures to `tests/conftest.py` (research R11)
- [X] T021 [P] Model unit tests in `tests/unit/persistence/test_models.py`: field defaults, FK references, `Utterance` has no `password`/`encryptedPassword` column (introspect `__table__.columns`), `test_db_path_configurable`, `test_db_parent_dir_created` (FR-001..003, FR-017/018; SC-011)
- [X] T022 [P] Encryption unit tests in `tests/unit/persistence/test_encryption.py`: round-trip, non-deterministic ciphertext, key-missing → `HarnessKeyMismatchError`, `test_password_not_in_db`, `test_credential_encrypted_at_rest` (FR-008/009; SC-004/005)

**Checkpoint**: Schema, engine, encryption, migrations, and fixtures all in place — user-story phases can begin.

---

## Phase 3: User Story 1 — Full job lifecycle across every entity (Priority: P1) 🎯 MVP

**Goal**: Create a draft Job, write Utterances, snapshot connector + evaluator config (with encrypted secrets), transition draft→queued→running→terminal, accumulate EvaluationResults, and keep aggregate counters correct.

**Independent Test**: Fixtures create a draft Job, write 5 Utterances, snapshot a connector + evaluator (≥1 secret each), transition to `queued`, write 5 EvaluationResults (mix of success/`failed`); verify every entity persists with expected fields, counts match, and secret fields are not plaintext on disk.

### Implementation for User Story 1

- [X] T023 [P] [US1] `ConnectorRegistrationRepository` in `src/harness/persistence/repositories/connector_registration.py`: `create` (encrypt credential subfields), `get`, `get_active`, `get_auth_descriptor_decrypted`, `update` (re-encrypt on change), `archive`, `restore`, `hard_delete` (contract; R9)
- [X] T024 [P] [US1] `EvaluationAgentRegistrationRepository` in `src/harness/persistence/repositories/evaluator_registration.py`: symmetric to T023 + `get_declared_dimensions` (contract)
- [X] T025 [US1] `JobRepository` in `src/harness/persistence/repositories/job.py`: `create_draft` (stamp `harness_version` via `importlib.metadata.version("harness")`), `get`, `get_by_status`, `set_connector_snapshot`, `set_evaluator_snapshot`, `set_csv_metadata`, `increment_processed_count`, `increment_failed_count` (contract; R5) — snapshot setters write during `draft`; immutability guard added in US2
- [X] T026 [P] [US1] `UtteranceRepository` in `src/harness/persistence/repositories/utterance.py`: `bulk_create` (assign UUIDs, enforce 1-based `row_index`), `get_by_job_ordered`, `count_by_job` (contract)
- [X] T027 [P] [US1] `EvaluationResultRepository` in `src/harness/persistence/repositories/evaluation_result.py`: `create`, `get_by_utterance`, `get_by_job` (JOIN to Utterance) (contract)
- [X] T028 [US1] Add happy-path status transitions to `JobRepository` (`transition_to_queued` [gate added in US2], `transition_to_running`, `transition_to_completed`, `transition_to_failed`, `transition_to_cancelling`) raising `InvalidTransitionError` on a wrong source state, in `src/harness/persistence/repositories/job.py` (contract)
- [X] T029 [US1] Re-export the 5 repositories in `src/harness/persistence/repositories/__init__.py` and `SessionLocal`/`get_session` in `src/harness/persistence/__init__.py`

### Tests for User Story 1

- [X] T030 [P] [US1] `tests/unit/persistence/test_repositories/test_connector_registration_repository.py` + `test_evaluator_registration_repository.py`: create/encrypt, `get_active`, decrypt round-trip, update re-encrypt, archive/restore
- [X] T031 [P] [US1] `tests/unit/persistence/test_repositories/test_job_repository.py`: `create_draft` defaults + `harness_version` stamp, `get_by_status`, snapshot setters, counter increments, transition happy paths
- [X] T032 [P] [US1] `tests/unit/persistence/test_repositories/test_utterance_repository.py` + `test_evaluation_result_repository.py`: `bulk_create` ordering + 1-based invariant, `create` result, one-result-per-utterance uniqueness
- [X] T033 [US1] `tests/integration/test_lifecycle.py::test_full_lifecycle`: draft→queued→running→completed with 5 Utterances + 5 EvaluationResults, counters match rows, secrets absent in plaintext (SC-001)

**Checkpoint**: MVP — the persistence layer round-trips a full job under normal conditions.

---

## Phase 4: User Story 2 — Snapshot immutability protects historical interpretability (Priority: P1)

**Goal**: Once a Job leaves `draft`, all snapshot fields and Utterance identity fields are frozen; the draft→queued transition enforces the registered-selection gate.

**Independent Test**: Start a Job with `endpoint=A`; change the registry to `endpoint=B`; read the Job's snapshot and confirm it still reads `A`. Attempt post-draft writes to snapshot/Utterance fields and confirm each is refused.

### Implementation for User Story 2

- [X] T034 [US2] Add snapshot immutability guard to `JobRepository` setters (`set_connector_snapshot`/`set_evaluator_snapshot`/`set_csv_metadata` and any snapshot-field write): raise `SnapshotImmutableError(job_id, field)` when `status != DRAFT`; enforce `created_by`/`created_at` as always-immutable, in `src/harness/persistence/repositories/job.py` (FR-005)
- [X] T035 [US2] Add the FR-007a selection gate to `JobRepository.transition_to_queued`: `with_for_update` lock, `MissingSnapshotFieldError` for null `connector_id`/`evaluation_agent_id`, `InactiveRegistrationError` for missing/archived registrations, in `src/harness/persistence/repositories/job.py` (R10; FR-007a)
- [X] T036 [US2] Add Utterance immutability guard to `UtteranceRepository` write paths: raise `UtteranceImmutableError` when parent Job `status != DRAFT`, in `src/harness/persistence/repositories/utterance.py` (FR-006)

### Tests for User Story 2

- [X] T037 [P] [US2] `test_job_repository.py::test_immutability_*`, `test_transition_gate_*` (missing-field + inactive-registration), `test_snapshot_isolation` (SC-002)
- [X] T038 [P] [US2] `test_utterance_repository.py::test_immutability_*` (SC-002)
- [X] T039 [US2] `tests/integration/test_lifecycle.py::test_snapshot_isolation`: registry edit after job start does not alter the persisted snapshot (SC-003)

**Checkpoint**: Started jobs are forensically stable; the data layer is the immutability backstop.

---

## Phase 5: User Story 3 — Cascade delete + status-gated delete (Priority: P2)

**Goal**: Deleting a `draft`/`failed`/`cancelled` Job cascades atomically to its Utterances and EvaluationResults; the four non-deletable statuses are refused; the bulk "clear failed and cancelled" action is atomic; cancellation creates per-row stubs.

**Independent Test**: One Job in each of the 7 states — verify the 3 deletable states succeed and cascade, the 4 non-deletable states are refused. Cancel a `cancelling` Job and confirm every un-processed Utterance gets exactly one `cancelled` stub atomically.

### Implementation for User Story 3

- [X] T040 [US3] `JobRepository.delete`: status gate `{draft, failed, cancelled}`, ORM cascade (+ `PRAGMA foreign_keys=ON`), `JobNotDeletableError`/`JobNotFoundError`, in `src/harness/persistence/repositories/job.py` (FR-010/011; R7)
- [X] T041 [US3] `JobRepository.delete_all_failed_and_cancelled`: snapshot the qualifying id-set inside the transaction before deleting, cascade each, return count, in `src/harness/persistence/repositories/job.py` (FR-012; R7)
- [X] T042 [US3] `UtteranceRepository.delete_by_job` (cascades EvaluationResults, draft-gated) in `src/harness/persistence/repositories/utterance.py` (contract; for `011` replace-on-upload)
- [X] T043 [US3] `JobRepository.transition_to_cancelled` + `EvaluationResultRepository.bulk_create_stubs`: atomic `cancelling→cancelled` with a `cancelled` stub for every Utterance lacking a result, in `repositories/job.py` and `repositories/evaluation_result.py` (FR-003a; R8)

### Tests for User Story 3

- [X] T044 [P] [US3] `tests/integration/test_cascade_delete.py`: `test_cascade_atomic`, `test_status_gate_*` (all 7 states), `test_bulk_delete_*` (SC-006/007)
- [X] T045 [P] [US3] `test_job_repository.py::test_cancellation_stubs_*`: every queued Utterance gets exactly one stub; atomic with the transition (FR-003a)

**Checkpoint**: Deletion and cancellation semantics are enforced at the only correct layer.

---

## Phase 6: User Story 4 — Survive a harness restart with consistent state (Priority: P2)

**Goal**: Cross-entity writes are atomic; a crash mid-transaction leaves the DB in its pre-transaction state; orphaned `running` jobs are queryable for reconciliation; uniqueness/referential constraints hold.

**Independent Test**: Inject a failure between two writes in one transaction → neither persists. Query `get_by_status("running")` → orphaned job returned. Attempt a duplicate `utterance_id` / a second EvaluationResult per Utterance → refused.

### Implementation for User Story 4

- [X] T046 [US4] Confirm/expose the transactional contract for cross-entity writes: ensure `get_session()` (from T014) wraps `session.begin()`-style atomicity and that `JobRepository.get_by_status` serves the orphan-reconciliation query; document the pattern in `src/harness/persistence/__init__.py` module docstring (FR-019/020/022)

### Tests for User Story 4

- [X] T047 [P] [US4] `tests/integration/test_lifecycle.py::test_crash_mid_transaction`: exception between two same-transaction writes → both rolled back (SC-008)
- [X] T048 [P] [US4] `tests/integration/test_lifecycle.py::test_orphaned_running_query`: `get_by_status("running")` returns the orphaned Job (FR-022)
- [X] T049 [P] [US4] `tests/unit/persistence/test_repositories/test_evaluation_result_repository.py::test_unique_constraint`: second EvaluationResult per Utterance refused (FR-021)

**Checkpoint**: The data layer is crash-consistent and constraint-safe.

---

## Phase 7: User Story 5 — Migrate the schema across releases without data loss (Priority: P2)

**Goal**: Startup applies pending migrations in order; a failed migration leaves the file untouched and refuses start; a DB newer than the harness refuses start; new optional columns read as null on old rows.

**Independent Test**: Populate a v1 DB, apply a v2 migration adding an optional EvaluationResult column; v1 rows remain queryable (new col null), v2 rows can populate it.

### Implementation for User Story 5

- [X] T050 [US5] Verify/finish `init_db`'s DB-too-new path raises `HarnessDatabaseTooNewError` with the verbatim message and the older/fresh path runs `upgrade(head)` before any other access, in `src/harness/persistence/engine.py` (FR-014/016; built in T018)
- [X] T051 [P] [US5] Add a second migration fixture `src/harness/persistence/migrations/versions/0002_add_optional_column.py` (adds a nullable EvaluationResult column) to exercise the migration path (FR-016)

### Tests for User Story 5

- [X] T052 [P] [US5] `tests/integration/test_migrations.py`: `test_schema_version_*` (sentinel present), `test_startup_migration_*` (older DB upgraded), `test_db_too_new_raises`, `test_partial_migration_rollback`, old rows read new optional col as null (FR-013/014/015/016; SC-009/010)

**Checkpoint**: The migration mechanism exists from v1 with somewhere for v2 to land.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T053 [P] `python -m ruff check src tests --fix`; resolve remaining findings
- [X] T054 `python -m pytest --cov=harness --cov-report=term-missing`; confirm no regression in the grafted 010 tests and adequate `persistence/` coverage
- [X] T055 [P] Execute `specs/009-data-model-persistence/quickstart.md` end-to-end; file any discrepancy as a follow-up task
- [X] T056 [P] Verify the plan's FR→File and SC matrices: every FR has an implementation file and a passing test
- [X] T057 [P] Confirm the `CLAUDE.md` SPECKIT marker still points at `specs/009-data-model-persistence/plan.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)** → no deps; start immediately.
- **Foundational (P2)** → depends on Setup; **blocks all user stories**.
- **US1 (P3)** → depends on Foundational. The MVP.
- **US2 (P4)** → depends on Foundational; **extends US1's** `JobRepository`/`UtteranceRepository` (T034–T036 modify files created in T025/T026/T028).
- **US3 (P5)** → depends on Foundational; adds delete/cancel methods to the same repository files.
- **US4 (P6)** → depends on Foundational; largely verification over the R6 transactional contract.
- **US5 (P7)** → depends on Foundational (the migration chain); independent of US1–US4.
- **Polish (P8)** → depends on all targeted stories.

### Critical path

Setup → Foundational → US1 → (US2, US3, US4, US5 can interleave) → Polish.

### Within each story

Models → repositories → transitions/guards → integration tests. Run `pytest` after each phase checkpoint.

---

## Parallel Opportunities

- **Setup**: T003 ‖ (T001/T002 touch shared files first).
- **Foundational**: T005–T012 are all different files → fully parallel; T015 (encryption) ‖ the model work. T013 waits on the 5 models; T014/T018 are same-file (sequential). T021 ‖ T022.
- **US1**: T023 ‖ T024 ‖ T026 ‖ T027 (distinct repo files); T025/T028 share `job.py` (sequential). Tests T030 ‖ T031 ‖ T032.
- **US2/US3**: test tasks within each story are [P]; implementation tasks touching `job.py` are sequential.
- **Across stories**: once Foundational is done, US5 can be built entirely in parallel with US1–US4 (separate migration/test files).

### Parallel example — Foundational models

```text
Task: "Create Job model in src/harness/persistence/models/job.py"           (T008)
Task: "Create Utterance model in .../models/utterance.py"                    (T009)
Task: "Create EvaluationResult model in .../models/evaluation_result.py"     (T010)
Task: "Create ConnectorRegistration model in .../models/connector_registration.py" (T011)
Task: "Create EvaluationAgentRegistration model in .../models/evaluator_registration.py" (T012)
```

---

## Implementation Strategy

### MVP first (US1)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **STOP & VALIDATE** `test_lifecycle.py::test_full_lifecycle`. This is a demoable persistence layer.

### Incremental delivery

US1 (round-trip) → US2 (immutability backstop) → US3 (delete/cancel) → US4 (durability) → US5 (migrations) → Polish. Each phase ends at a green checkpoint without breaking prior phases.

---

## Notes

- `[P]` = different files, no incomplete dependency. Tasks editing the same file (notably `repositories/job.py` across US1/US2/US3, and `engine.py` T014/T018) are intentionally sequential.
- All reads/writes go through the repository layer (no raw SQL outside migration files); no ORM event listeners for business rules (plan Constraints, R7/R10).
- Commit after each task or logical group. Stop at any checkpoint to validate a story independently.
