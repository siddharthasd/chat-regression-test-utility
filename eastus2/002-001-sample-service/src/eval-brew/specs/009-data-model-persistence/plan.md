# Implementation Plan: Data Model & Persistence Layer (Module 2)

**Branch**: `009-data-model-persistence` | **Date**: 2026-06-02 | **Spec**: `specs/009-data-model-persistence/spec.md`

**Input**: Feature specification from `specs/009-data-model-persistence/spec.md`

## Summary

`009` is the persistence foundation every other module depends on. Five SQLAlchemy 2.0 ORM entities (`Job`, `Utterance`, `EvaluationResult`, `ConnectorRegistration`, `EvaluationAgentRegistration`) plus a `SchemaVersion` sentinel; five repository classes with full CRUD; a versioned Alembic migration chain with startup gating; a machine-local Fernet encryption utility for `authDescriptor` credential subfields; and the `init_db()` bootstrap that applies pending migrations or refuses start if the on-disk schema is newer than the installed harness. This spec also brings `sqlalchemy`, `alembic`, and `cryptography` into the runtime dependency graph (deferred from `010` per that spec's R9).

Inherits the project-wide foundation from `010`: Python 3.11+, `src/harness/` single-package layout, `pyproject.toml`, `pytest` + `ruff` toolchain.

## Technical Context

**Language/Version**: Python 3.11+ (inherited).

**Primary Dependencies** (new in this spec):
- `sqlalchemy>=2.0` — ORM with type-annotated `mapped_column` / `Mapped[T]` style.
- `alembic>=1.13` — Migration runner + autogenerate against `Base.metadata`.
- `cryptography>=42.0` — Fernet symmetric encryption for `authDescriptor` credential subfields.
- `importlib.metadata` (stdlib) — `version("harness")` for `Job.harnessVersion` stamping.

**Dev dependencies**: no additions beyond `010`'s baseline. The test-DB pattern (in-memory SQLite + savepoint-rollback) is implemented inline.

**Storage**: SQLite at `~/.harness/data.db` (default; overridable via `HARNESS_DB_PATH` env var). WAL mode, `foreign_keys=ON`, `synchronous=NORMAL`, `busy_timeout=5000` applied at connection time via SQLAlchemy event listener.

**Testing**: session-scoped in-memory SQLite engine with all Alembic migrations applied once; function-scoped savepoint (`begin_nested`) rollback for data isolation between tests.

**Target Platform**: Windows + macOS + Linux. Fernet key at `~/.harness/master.key` (Windows: `%LOCALAPPDATA%\harness\master.key`).

**Performance Goals**: Migration startup < 200ms for a fresh install; per-repository call < 50ms at the 1,000-row design target.

**Constraints**: All reads/writes go through the repository layer (no raw SQL outside migration files). No SQLAlchemy event listeners for business-rule enforcement.

## Constitution Check

Unfilled template — GATE: PASS by vacuous quantification (same as `010`).

## Project Structure

### Documentation (this feature)

```text
specs/009-data-model-persistence/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 (R1–R12)
├── data-model.md        # Phase 1 — entity definitions, relationships, state machines
├── quickstart.md        # Phase 1 — end-to-end verification
├── contracts/
│   ├── repository-api.md          # Public surface of the five repository classes
│   └── encryption-utility-api.md  # encrypt_credential / decrypt_credential contract
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (not created by this plan)
```

### Source Code

```text
pyproject.toml                        # Add sqlalchemy, alembic, cryptography to [project]
alembic.ini                           # Alembic config at repo root
src/
└── harness/
    ├── bootstrap.py                  # Add init_db() call (after initialize_harness)
    ├── persistence/
    │   ├── __init__.py               # Re-exports: SessionLocal, get_session
    │   ├── base.py                   # DeclarativeBase + Base
    │   ├── engine.py                 # create_engine() + init_db() startup migration
    │   ├── encryption.py             # encrypt_credential() / decrypt_credential() / key mgmt
    │   ├── models/
    │   │   ├── __init__.py           # Re-exports all five model classes
    │   │   ├── job.py                # Job (large — all 12 snapshot cols + runtime counters)
    │   │   ├── utterance.py
    │   │   ├── evaluation_result.py
    │   │   ├── connector_registration.py
    │   │   └── evaluator_registration.py
    │   ├── repositories/
    │   │   ├── __init__.py           # Re-exports all five repository classes
    │   │   ├── job.py                # JobRepository (create_draft, transition_*, delete, bulk_delete)
    │   │   ├── utterance.py          # UtteranceRepository (bulk insert, get_by_job_ordered)
    │   │   ├── evaluation_result.py  # EvaluationResultRepository (create, bulk_insert, get_by_job)
    │   │   ├── connector_registration.py
    │   │   └── evaluator_registration.py
    │   └── migrations/
    │       ├── env.py                # Alembic env — imports Base.metadata
    │       ├── script.py.mako
    │       └── versions/
    │           └── 0001_initial_schema.py   # All 5 entities + SchemaVersion table

tests/
├── conftest.py                       # Add db_engine (session-scoped) + db_session (savepoint fixture)
├── unit/
│   └── persistence/
│       ├── test_models.py            # Field defaults, FK references, immutability constraints
│       ├── test_encryption.py        # Round-trip, key-missing error, no plaintext in DB
│       └── test_repositories/
│           ├── __init__.py
│           ├── test_job_repository.py
│           ├── test_utterance_repository.py
│           ├── test_evaluation_result_repository.py
│           ├── test_connector_registration_repository.py
│           └── test_evaluator_registration_repository.py
└── integration/
    ├── test_lifecycle.py             # draft→queued→running→completed/failed/cancelled
    ├── test_migrations.py            # startup gating, DB-too-new, partial-rollback
    └── test_cascade_delete.py        # cascade, status gates, bulk delete
```

**Structure Decision**: `src/harness/persistence/` sub-package. Repositories are thin wrappers over SQLAlchemy sessions; no ORM event listeners for business logic.

## FR → File Coverage Matrix

| FR | Implementation file | Verifying test |
|---|---|---|
| `FR-001` (Job entity) | `persistence/models/job.py` | `unit/persistence/test_models.py::test_job_*` |
| `FR-001a` (ConnectorRegistration) | `persistence/models/connector_registration.py` | `unit/persistence/test_models.py::test_connector_reg_*` |
| `FR-001b` (EvaluationAgentRegistration) | `persistence/models/evaluator_registration.py` | `unit/persistence/test_models.py::test_evaluator_reg_*` |
| `FR-002` (Utterance) | `persistence/models/utterance.py` | `unit/persistence/test_models.py::test_utterance_*` |
| `FR-003` (EvaluationResult) | `persistence/models/evaluation_result.py` | `unit/persistence/test_models.py::test_eval_result_*` |
| `FR-003a` (cancellation stubs) | `persistence/repositories/job.py::transition_to_cancelled` | `test_job_repository.py::test_cancellation_stubs_*` |
| `FR-004` (removed) | (confirmed absent) | verified by absence |
| `FR-005` (snapshot immutability) | `persistence/repositories/job.py` all write paths | `test_job_repository.py::test_immutability_*` |
| `FR-006` (Utterance immutability) | `persistence/repositories/utterance.py` | `test_utterance_repository.py::test_immutability_*` |
| `FR-007` (mutable runtime fields) | `persistence/repositories/job.py` status/counter update paths | `integration/test_lifecycle.py` |
| `FR-007a` (draft→queued gate) | `persistence/repositories/job.py::transition_to_queued` | `test_job_repository.py::test_transition_gate_*` |
| `FR-008` (credential encryption) | `persistence/encryption.py` + repository write paths | `unit/persistence/test_encryption.py` |
| `FR-009` (no password persistence) | (architectural — absence-verified) | `unit/persistence/test_encryption.py::test_password_not_in_db` |
| `FR-010` (cascade delete) | `persistence/repositories/job.py::delete` | `integration/test_cascade_delete.py::test_cascade_*` |
| `FR-011` (status-gated delete) | `persistence/repositories/job.py::delete` | `integration/test_cascade_delete.py::test_status_gate_*` |
| `FR-012` (bulk delete) | `persistence/repositories/job.py::delete_all_failed_and_cancelled` | `integration/test_cascade_delete.py::test_bulk_delete_*` |
| `FR-013` (schema version table) | `persistence/migrations/env.py` + `engine.py` | `integration/test_migrations.py::test_schema_version_*` |
| `FR-014` (startup migration gating) | `persistence/engine.py::init_db` | `integration/test_migrations.py::test_startup_migration_*` |
| `FR-015` (migration atomicity) | Alembic migration files | `integration/test_migrations.py::test_partial_migration_rollback` |
| `FR-016` (refuse if DB newer) | `persistence/engine.py::init_db` (DB-too-new path) | `integration/test_migrations.py::test_db_too_new_raises` |
| `FR-017` (configurable DB path) | `persistence/engine.py::init_db` | `unit/persistence/test_models.py::test_db_path_configurable` |
| `FR-018` (parent dir creation) | `persistence/engine.py::_ensure_directory` | `unit/persistence/test_models.py::test_db_parent_dir_created` |
| `FR-019`–`FR-022` (query/atomicity/integrity/single-source) | All repository methods | `integration/test_lifecycle.py` |

## SC Verification Matrix

| SC | Verification path |
|---|---|
| `SC-001` | `integration/test_lifecycle.py::test_full_lifecycle` |
| `SC-002` | `test_job_repository.py::test_immutability_*` |
| `SC-003` | `test_job_repository.py::test_snapshot_isolation` |
| `SC-004` | `unit/persistence/test_encryption.py::test_password_not_in_db` |
| `SC-005` | `unit/persistence/test_encryption.py::test_credential_encrypted_at_rest` |
| `SC-006` | `integration/test_cascade_delete.py::test_cascade_atomic` |
| `SC-007` | `integration/test_cascade_delete.py::test_status_gate_*` |
| `SC-008` | `integration/test_lifecycle.py::test_crash_mid_transaction` |
| `SC-009` | `integration/test_migrations.py::test_partial_migration_rollback` |
| `SC-010` | `integration/test_migrations.py::test_db_too_new_raises` |
| `SC-011` | `unit/persistence/test_models.py::test_db_path_*` |

## Branch-Staleness Note

Same as `010`: cross-spec citations to `003 FR-009`/`FR-012`, `007 FR-013`–`FR-017`, `011 FR-015`, `012 FR-004`, `013 FR-002`/`FR-005`, `014 FR-002`/`FR-005` resolve against the canonical post-reshape state on the `012` branch. Implementation work typically done on a branch rebased onto `012`.

## Complexity Tracking

| Element | Justification |
|---|---|
| 5 entity classes | Spec defines all five; none can be folded |
| Alembic migration chain | FR-013–FR-016 explicitly require versioned migrations and startup gating |
| Fernet per-subfield encryption | FR-008 + parent FR-023a mandate at-rest encryption with machine-local key; over-encrypting whole JSON blob hides non-secret fields |
| Savepoint-based test isolation | Needed for test independence without per-test migration cost |
