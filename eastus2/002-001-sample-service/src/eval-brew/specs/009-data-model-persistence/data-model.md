# Phase 1 Data Model: Data Model & Persistence Layer (Module 2)

**Date**: 2026-06-02
**Plan**: `specs/009-data-model-persistence/plan.md`

---

## Entities and ORM Models

All five entity models inherit from `Base = DeclarativeBase()` in `src/harness/persistence/base.py`. Column names below are the Python attribute names (SQLAlchemy maps these to equivalent SQL column names using its default snake_case convention). The `SchemaVersion` sentinel table is managed by Alembic only.

---

### `Job` (`persistence/models/job.py`)

The central entity. All snapshot fields are immutable past `draft`.

| Attribute | Type | Notes |
|---|---|---|
| `job_id` | `Mapped[str]` PK | UUID string |
| `job_name` | `Mapped[str]` | Non-empty |
| `description` | `Mapped[Optional[str]]` | |
| `status` | `Mapped[str]` | `JobStatus` StrEnum: `draft/queued/running/cancelling/completed/failed/cancelled` |
| `created_by` | `Mapped[str]` | OS-derived; immutable from creation |
| `created_at` | `Mapped[datetime]` | UTC; immutable from creation |
| `started_at` | `Mapped[Optional[datetime]]` | Null while draft |
| `completed_at` | `Mapped[Optional[datetime]]` | Null until terminal |
| `harness_version` | `Mapped[str]` | Immutable past draft |
| `source_csv_filename` | `Mapped[Optional[str]]` | Basename only; immutable past draft |
| `error_details` | `Mapped[Optional[str]]` | Job-level failure message; populated only when status==failed |
| `connector_id` | `Mapped[Optional[str]]` | Snapshot; immutable past draft |
| `connector_name` | `Mapped[Optional[str]]` | Snapshot; immutable past draft |
| `connector_endpoint_url` | `Mapped[Optional[str]]` | Snapshot; immutable past draft |
| `connector_auth_descriptor` | `Mapped[Optional[dict]]` (JSON) | Verbatim ciphertext from registration; immutable past draft |
| `connector_timeout_seconds` | `Mapped[Optional[int]]` | Snapshot; immutable past draft |
| `connector_expects_per_row_password` | `Mapped[Optional[bool]]` | Snapshot; immutable past draft |
| `evaluation_agent_id` | `Mapped[Optional[str]]` | Snapshot; immutable past draft |
| `evaluation_agent_name` | `Mapped[Optional[str]]` | Snapshot; immutable past draft |
| `evaluator_endpoint_url` | `Mapped[Optional[str]]` | Snapshot; immutable past draft |
| `evaluator_auth_descriptor` | `Mapped[Optional[dict]]` (JSON) | Verbatim ciphertext; immutable past draft |
| `evaluator_timeout_seconds` | `Mapped[Optional[int]]` | Snapshot; immutable past draft |
| `evaluator_declared_scoring_dimensions` | `Mapped[Optional[list]]` (JSON) | Ordered list of strings; immutable past draft |
| `total_utterance_count` | `Mapped[Optional[int]]` | Immutable past draft |
| `processed_count` | `Mapped[int]` default=0 | Mutable; count of EvaluationResults with errorStatus IN (null, "failed") |
| `failed_count` | `Mapped[int]` default=0 | Mutable; count of EvaluationResults with errorStatus="failed" |

**Relationships**:
- `utterances = relationship(Utterance, cascade="all, delete-orphan", back_populates="job")`

**Immutability enforcement**: `JobRepository` checks `job.status != JobStatus.DRAFT` before writing any snapshot column and raises `SnapshotImmutableError`. `created_by` and `created_at` are enforced as always-immutable by the repository's `create_draft()` being the only writer.

---

### `Utterance` (`persistence/models/utterance.py`)

| Attribute | Type | Notes |
|---|---|---|
| `utterance_id` | `Mapped[str]` PK | UUID string |
| `job_id` | `Mapped[str]` FK(`job.job_id`) | `ON DELETE CASCADE` |
| `utterance_text` | `Mapped[str]` | |
| `row_index` | `Mapped[int]` | 1-based |
| `test_id` | `Mapped[str]` | |
| `extra_metadata` | `Mapped[Optional[dict]]` (JSON) | Additional CSV columns verbatim |

**NO `password` column** — enforced by the model having no such attribute; the absence is verified by a test that introspects `Utterance.__table__.columns`.

**Relationships**:
- `job = relationship(Job, back_populates="utterances")`
- `evaluation_result = relationship(EvaluationResult, uselist=False, cascade="all, delete-orphan", back_populates="utterance")`

**Immutability past draft**: `UtteranceRepository` raises `UtteranceImmutableError` on any write attempt when the parent job's status != DRAFT.

---

### `EvaluationResult` (`persistence/models/evaluation_result.py`)

| Attribute | Type | Notes |
|---|---|---|
| `result_id` | `Mapped[str]` PK | UUID string |
| `utterance_id` | `Mapped[str]` FK(`utterance.utterance_id`) UNIQUE | `ON DELETE CASCADE`; uniqueness constraint (at most 1 result per utterance) |
| `test_id` | `Mapped[str]` | Denormalized from Utterance for filtering |
| `raw_chatbot_response` | `Mapped[Optional[dict]]` (JSON) | Connector HTTP body; null if transport/auth failed |
| `normalized_contract` | `Mapped[Optional[dict]]` (JSON) | Validated contract instance; null if connector_normalization failed |
| `evaluation_agent_id` | `Mapped[Optional[str]]` | Echoed from evaluator response; or from Job snapshot if row failed pre-evaluation |
| `evaluation_verdict` | `Mapped[Optional[str]]` | `pass`/`fail`/`warn`; null if row failed before evaluation |
| `evaluation_scores` | `Mapped[Optional[list]]` (JSON) | Ordered `[{parameter_name, score, reasoning}]`; null if failed pre-evaluation |
| `metadata` | `Mapped[Optional[dict]]` (JSON) | Evaluator-emitted free-form; null if failed pre-evaluation |
| `harness_annotations` | `Mapped[Optional[dict]]` (JSON) | Harness-derived (e.g., `{unexpected_score_dimensions: [...]}`) |
| `error_status` | `Mapped[Optional[str]]` | `null` / `"failed"` / `"cancelled"` |
| `error_stage` | `Mapped[Optional[str]]` | One of 9 canonical values per `012 FR-012` / `009 FR-003` |
| `error_details` | `Mapped[Optional[str]]` | Per-row failure detail. Distinct from `Job.error_details` (job-level). |
| `evaluation_timestamp` | `Mapped[datetime]` | UTC; set by orchestrator or at stub-creation time |

**`error_stage` allowed values** (the canonical 9-value enum):
`connector_transport`, `connector_response`, `connector_normalization`, `connector_auth`, `evaluator_transport`, `evaluator_response`, `evaluator_result`, `evaluator_auth`, `password_lookup`

**Relationships**:
- `utterance = relationship(Utterance, back_populates="evaluation_result")`

---

### `ConnectorRegistration` (`persistence/models/connector_registration.py`)

| Attribute | Type | Notes |
|---|---|---|
| `connector_id` | `Mapped[str]` PK | Harness-assigned UUID; immutable |
| `display_name` | `Mapped[str]` | Tester-supplied |
| `description` | `Mapped[Optional[str]]` | Optional per `013 FR-002` |
| `endpoint_url` | `Mapped[str]` | |
| `auth_descriptor` | `Mapped[dict]` (JSON) | `{mode, [headerName?], [credential? (ciphertext)], [username?]}` |
| `timeout_seconds` | `Mapped[int]` | Default 30 per `013 FR-002` |
| `expects_per_row_password` | `Mapped[bool]` | Default False |
| `archived` | `Mapped[bool]` | Default False |
| `created_at` | `Mapped[datetime]` | UTC; immutable |
| `updated_at` | `Mapped[datetime]` | Updated on every write |
| `archived_at` | `Mapped[Optional[datetime]]` | Set when archived; cleared on restore |

**Credential subfields encrypted** per R4/R9: `auth_descriptor["credential"]` (bearer, api-key) or `auth_descriptor["password"]` (basic) are Fernet-ciphertexts. The `mode`, `headerName`, `username` subfields are plaintext.

---

### `EvaluationAgentRegistration` (`persistence/models/evaluator_registration.py`)

| Attribute | Type | Notes |
|---|---|---|
| `evaluation_agent_id` | `Mapped[str]` PK | Harness-assigned UUID; immutable |
| `display_name` | `Mapped[str]` | |
| `description` | `Mapped[str]` | **Required** (not Optional) per `014 FR-002` |
| `endpoint_url` | `Mapped[str]` | |
| `auth_descriptor` | `Mapped[dict]` (JSON) | Same shape as ConnectorRegistration |
| `timeout_seconds` | `Mapped[int]` | Default 60 per `014 FR-002` |
| `declared_scoring_dimensions` | `Mapped[list]` (JSON) | Ordered list of strings; `[]` is valid |
| `archived` | `Mapped[bool]` | Default False |
| `created_at` | `Mapped[datetime]` | UTC; immutable |
| `updated_at` | `Mapped[datetime]` | |
| `archived_at` | `Mapped[Optional[datetime]]` | |

Intentional asymmetries vs. `ConnectorRegistration`: no `expects_per_row_password`; `description` is required not optional; `declared_scoring_dimensions` replaces nothing in connector.

---

## Relationships Summary

```text
Job (1) ──────────────────── (N) Utterance
                                     │
                                     │ (1:0-1)
                                     ▼
                              EvaluationResult

ConnectorRegistration   (referenced by Job.connector_id snapshot;
                         FK reference NOT enforced by DB constraint —
                         the snapshot is the Job's own copy)

EvaluationAgentRegistration  (same — snapshot pattern)
```

The `ConnectorRegistration` and `EvaluationAgentRegistration` are NOT FK-linked to `Job` at the database level because Jobs hold snapshots (not live references). Deleting a registration does not cascade to Jobs; instead, hard-delete is blocked by `013 FR-019` / `014 FR-024` at the application layer. The data layer enforces the selection gate via `FR-007a` (R10).

---

## State Transitions

### Job Status State Machine

```text
         wizard Step 5 "Start Job"
DRAFT ──────────────────────────────► QUEUED
                                        │
                                 orchestrator picks up
                                        │
                                        ▼
                                     RUNNING
                                    /       \
                 all rows done     /         \ tester cancels
                                  ▼           ▼
                              COMPLETED   CANCELLING
                              /     \          │ in-flight row finishes
                         (0 fails) (N fails)   │ stubs created atomically
                                              ▼
                                          CANCELLED
                 connect fails /
                 auth fails /
                 empty password store
                              ▼
                            FAILED
```

Terminal states: `completed`, `failed`, `cancelled`.
Deletable states: `draft`, `failed`, `cancelled` (per FR-011).

### `ConnectorRegistration` / `EvaluationAgentRegistration` Lifecycle

```text
ACTIVE ──── archive ──── ARCHIVED
  ▲                          │
  └──────── restore ─────────┘
  
ACTIVE ──── hard-delete ────► (gone; only when no historical Job references)
ARCHIVED ── hard-delete ────► (gone; only when no historical Job references)
```

---

## Custom Exceptions (defined in `persistence/exceptions.py`)

| Exception | When raised |
|---|---|
| `HarnessDatabaseTooNewError` | DB schema revision newer than installed harness |
| `HarnessKeyMismatchError` | Fernet decryption fails (wrong or missing key) |
| `JobNotFoundError(job_id)` | Job id not in DB |
| `JobNotDeletableError(job_id, status)` | Delete attempted on a non-deletable status |
| `SnapshotImmutableError(job_id, field)` | Write to snapshot field after draft |
| `UtteranceImmutableError(utterance_id, field)` | Write to Utterance field after draft |
| `InvalidTransitionError(job_id, from_status, to_status)` | Status transition from wrong state |
| `MissingSnapshotFieldError(job_id, field)` | draft→queued gate: null connector_id or agent_id |
| `InactiveRegistrationError(job_id, reg_type, reg_id)` | draft→queued gate: archived registration |
