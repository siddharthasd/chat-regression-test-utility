# Feature Specification: Data Model & Persistence Layer (Module 2)

**Feature Branch**: `009-data-model-persistence`

**Created**: 2026-05-29

**Status**: Draft

**Input**: User description: "Module 2 — Data Model & Persistence Layer. Core entities (Job, Utterance, ExecutionResult), repository/data-access layer with CRUD per entity, versioned schema migrations, job configuration snapshots immutable after job start. Uploaded CSV file linked to the job. SQLAlchemy + SQLite + Alembic. `harnessVersion` on Job. DB file location configurable, default `~/.harness/data.db`. Symmetric encryption utility for the password field with a machine-local key."

> **Parent context**: This module is the persistence foundation underneath every other module. Job (with its config snapshots and lifecycle state), per-row Utterance and ExecutionResult, and TesterFeedback (the parent's `Tester Feedback` entity) all live here. The Module 2 input had several phrases that conflicted with established parent-spec decisions; those were resolved before writing this spec (see `Clarifications`). Parent-spec premises apply: single-user, no auth, no `createdBy`. Module 4's encryption utility (`specs/007-connector-framework` → `FR-015`–`FR-019`) and parent `FR-023a` define how config-level secrets are encrypted at rest; this module USES that utility but does NOT introduce its own. Per-row CSV `password` is NOT persisted in any form (parent `FR-010`); the Module 2 input's `encryptedPassword` field on Utterance was dropped by explicit decision (2026-05-29). The job lifecycle (`draft → queued → running → cancelling → completed / failed / cancelled`) is the parent's canonical enum; the Module 2 input's `[Draft, Configured, Running, Completed, CompletedWithErrors, Failed]` was dropped — `Configured` is not a defined state, `CompletedWithErrors` is a UI label per Module 13. The user's module number "Module 2" maps to our `009-` directory by the convention used for Modules 4 → 007, 7 → 008. Implementation choices (SQLAlchemy / SQLite / Alembic) are treated as plan-level decisions — this spec describes the data shape and persistence behavior, not the library binding.

## Clarifications

### Session 2026-05-29

- Q: The Module 2 input adds `encryptedPassword` to Utterance and says the uploaded CSV is stored as an immutable binary artifact. Both override parent `FR-010` (in-memory only, never persisted). Honor or override? → A: **Honor parent `FR-010`.** Per-row CSV `password` is NOT persisted in any form, in any table, encrypted or otherwise. The raw uploaded CSV file is NOT retained on disk as a binary artifact — that would persist passwords. The Utterance entity stores only the persisted-row data (utterance + testId + other CSV columns minus `password`). The "download original CSV" affordance reconstructs from those rows per `specs/004-job-detail-view` → `FR-006`. Module 4's encryption utility remains scoped to **config-level secrets only**, per its `FR-019`. Job resumability for credential-bearing rows after a restart remains forbidden by parent `FR-010a`.
- Q: The Module 2 input's Job status enum is `[Draft, Configured, Running, Completed, CompletedWithErrors, Failed]`. The parent spec's canonical enum is `[draft, queued, running, cancelling, completed, failed, cancelled]` with `CompletedWithErrors` as a derived UI label. Which wins? → A: **Parent's canonical enum.** Job.status is stored as one of `draft / queued / running / cancelling / completed / failed / cancelled` (lowercase). `Configured` is dropped (not a defined lifecycle state — the wizard moves `draft → queued` directly on Start). `CompletedWithErrors` is dropped from the stored enum (it is a UI label derived at render time from `status == completed && failed_count > 0`, per Module 13).

### Session 2026-05-29 (Round 2)

- Q: How are cancelled-but-never-processed rows tracked at the data layer? → A: **Create ExecutionResult stubs for every Utterance that was queued-but-never-processed when the parent Job goes terminal-cancelled.** Each stub carries `errorStatus = "cancelled"`, `errorStage = null` (no real failure stage — the row never ran), and `null` for `rawChatbotResponse`, `normalizedContract`, `evaluationResult`, `evaluationVerdict`, `harnessAnnotations`. ExecutionResult becomes the single source of truth for per-row terminal state — every row in any terminal Job has exactly one ExecutionResult. Definitions: `processedCount` = count of ExecutionResults whose `errorStatus IN (null, "failed")`; `failedCount` = count of ExecutionResults whose `errorStatus = "failed"`. Implicit cancelled count = `totalUtteranceCount − processedCount`. Stub creation MUST be performed atomically with the Job's `cancelling → cancelled` transition.
- Q: Is `Utterance.rowIndex` 0-based or 1-based? → A: **1-based.** Row 1 = the first data row of the uploaded CSV. Matches spreadsheet convention; reads naturally in any tester-facing surface (dashboard, detail view, export, error messages). The data layer enforces 1-based numbering at insert time; consumers can rely on `rowIndex >= 1` for every persisted Utterance.

### Session 2026-05-29 (Round 3 — revision driven by Module 3)

- Q: Module 3 (`specs/010-tester-identity`) re-introduces OS-derived attribution. Should `Job.createdBy` and `TesterFeedback.feedbackBy` be added to the data layer? → A: **Yes.** Add `createdBy` to the Job entity (`FR-001`) and `feedbackBy` to the TesterFeedback entity (`FR-004`). Both are auto-populated from the parent harness's OS-resolved tester identity (parent `FR-026`) at write time. Both are immutable past the row's creation (just like other identity fields). This reverses the Q1 ("Honor parent FR-010") clarification's implicit precedent that no creator field exists — the password-persistence rule stays, but the creator-attribution rule is now ADDITIVE.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create, configure, snapshot, and run a job through its full lifecycle (Priority: P1)

The wizard creates a Job in `draft` status (just name + description). As the tester progresses through Steps 2–4 of the wizard, the harness writes to the Utterance table (one row per CSV row, minus `password`), persists the connector identity + config snapshot and the evaluation-agent identity + config snapshot onto the Job, and stores aggregate counts (`totalUtteranceCount`, etc.). On Start (Step 5), the Job transitions to `queued`; the snapshots become immutable; the orchestrator picks the job up and transitions it to `running`; per-row ExecutionResults accumulate as the orchestrator processes Utterances; counters update; the Job reaches a terminal status. This story exercises every entity in this module under normal conditions.

**Why this priority**: This is the entire purpose of the persistence layer. Every other module depends on it. It is the MVP slice of Module 2.

**Independent Test**: With stub implementations of the wizard, connector framework, evaluation framework, and orchestrator, write fixtures that exercise the full data-flow: create a draft Job, write 5 Utterances to it, snapshot a connector + evaluator config (with at least one secret field per snapshot), transition to `queued`, write 5 ExecutionResults (mix of success and `failed` rows with different `errorStage` values), apply TesterFeedback to one row. Verify (a) every entity is persisted with the expected fields, (b) snapshots are byte-identical to the stored copies regardless of whether the registry's underlying connector/evaluator has changed in the meantime, (c) the Job's aggregate counts match the ExecutionResults, (d) the secret fields in the snapshots are not visible in plaintext on disk.

**Acceptance Scenarios**:

1. **Given** the wizard creates a Job in `draft` status, **When** the data layer persists it, **Then** the Job record carries `jobId`, `jobName`, `description` (or null), `createdAt`, `status == draft`, `harnessVersion`, and null/zero placeholders for everything else.
2. **Given** the tester crosses Step 2, **When** the harness writes Utterances, **Then** N Utterance records appear, each carrying `utteranceId` (system-generated UUID, globally unique per Module 6 `FR-002`), `jobId`, `originalText`, `rowIndex`, `testId`, and any other persisted CSV columns. None carries a password column or value, regardless of whether the original CSV had one.
3. **Given** the tester completes Steps 3 and 4, **When** the snapshots are persisted onto the Job, **Then** `connectorType`, `connectorConfigSnapshot`, `evaluationAgentId`, and `evaluationAgentConfigSnapshot` are populated; secret-declared fields within the snapshots are encrypted at rest using Module 4's machine-local key utility (parent `FR-023a`).
4. **Given** Job status is `draft`, **When** the wizard transitions to `queued` on Start, **Then** all snapshot fields and the `totalUtteranceCount` field become immutable; subsequent writes to those fields MUST be refused at the data-layer boundary.
5. **Given** the orchestrator processes Utterances, **When** each row's ExecutionResult is persisted, **Then** the record carries `resultId`, `utteranceId`, `testId` (denormalized for indexing), `rawChatbotResponse` (JSON), `normalizedContract` (JSON conforming to Module 6's schema), `evaluationResult` (JSON conforming to Module 7's shape), `evaluationVerdict` (denormalized from `evaluationResult.verdict`), `harnessAnnotations` (JSON — the harness-derived block per Module 7 `FR-005a`), `errorStatus`, `errorStage`, `errorDetails`, `executionTimestamp`. The Job's `processedCount` and `failedCount` update accordingly.

---

### User Story 2 - Snapshot immutability protects historical interpretability (Priority: P1)

After a Job has started, the connector identity, the connector config snapshot, the evaluator identity, the evaluator config snapshot, the `totalUtteranceCount`, the `harnessVersion`, and the row-level identity fields (`utteranceId`, `rowIndex`, `testId`, `originalText`) are immutable. Subsequent registry edits (e.g., upgrading the connector in place) do not retroactively alter a previously-started job's snapshot. This is the parent's `FR-023` made operational at the data layer.

**Why this priority**: Without immutability, results are not interpretable historically — a tester triaging a failure three weeks later can't be sure what config was in use. Equal-priority with US1 because the invariant is foundational.

**Independent Test**: Start a Job with a known connector config (`endpoint=https://A`). After the job runs to completion, change the connector's registry entry to use `endpoint=https://B`. Read the completed Job's persisted snapshot from the data layer; verify the snapshot still says `endpoint=https://A` (the value at job-creation time), NOT `endpoint=https://B`.

**Acceptance Scenarios**:

1. **Given** a Job whose status has transitioned past `draft` (i.e., `queued`/`running`/terminal/cancelling), **When** any harness module attempts to write to `connectorConfigSnapshot`, `evaluationAgentConfigSnapshot`, `connectorType`, `evaluationAgentId`, `totalUtteranceCount`, `harnessVersion`, or `sourceCSVFilename` on that Job, **Then** the data layer MUST refuse the write with an actionable error naming the immutable field. (Writes to `status`, `startedAt`, `completedAt`, `processedCount`, `failedCount` remain allowed — they are runtime state, not snapshot state.)
2. **Given** a Job whose status has transitioned past `draft`, **When** any harness module attempts to alter `originalText`, `rowIndex`, `testId`, or `utteranceId` on any Utterance belonging to that Job, **Then** the data layer MUST refuse the write.
3. **Given** the underlying registry entry for a connector or evaluator that a started Job snapshotted is later modified, **When** the Job's snapshot is read, **Then** the read returns the originally-snapshotted values, NOT the registry's current values.

---

### User Story 3 - Cascade delete a job and its rows; protect non-deletable statuses (Priority: P2)

Per parent `FR-001` (`draft` jobs deletable) and `FR-001a` (`failed` and `cancelled` jobs deletable), a deletion request flows through the data layer. The layer cascades the delete to every Utterance, every ExecutionResult, and every TesterFeedback belonging to the deleted Job. A deletion request against a Job in `completed`, `queued`, `running`, or `cancelling` status is refused — these states are explicitly non-deletable.

**Why this priority**: Deletion is a real productivity requirement (especially for the dashboard's "Clear all failed and cancelled" bulk action per `005`). Equal-priority with US4 because the data layer is the only place to enforce the cascade and the status-gate correctly.

**Independent Test**: With one Job in each of the seven lifecycle states, attempt a delete on each. Verify the four deletable states (`draft`, `failed`, `cancelled`) succeed and cascade; the three non-deletable states (`queued`, `running`, `cancelling`, `completed`) are refused with an actionable error.

**Acceptance Scenarios**:

1. **Given** a Job in `draft`, `failed`, or `cancelled` status with N Utterances, M ExecutionResults, and K TesterFeedback records, **When** the data layer is asked to delete the Job, **Then** the Job and all N + M + K dependent records are removed atomically (all-or-nothing). After the operation, queries for any of those records by id return "not found."
2. **Given** a Job in `completed`, `queued`, `running`, or `cancelling` status, **When** the data layer is asked to delete it, **Then** the request is refused with a clear error naming the status and the rule.
3. **Given** the dashboard's "Clear all failed and cancelled" bulk action (`specs/002-dashboard-job-listing` → `FR-010c`) is invoked, **When** the data layer executes the bulk delete, **Then** every Job currently in `failed` or `cancelled` is deleted (with its cascading rows), in a single atomic operation, and no other Job is affected.

---

### User Story 4 - Survive a harness restart with a consistent persisted state (Priority: P2)

The harness process is killed (crash, OS reboot, manual `Ctrl-C` mid-job). On restart, the data layer's state is consistent: every Job is in a definite status; orphaned `running` jobs are reconciled per parent `FR-022` (the layer doesn't fix them itself but provides the queries the orchestrator needs); every persisted record is queryable. No partial writes have left the database in a corrupted state.

**Why this priority**: A regression-test tool that loses or corrupts data on a restart is unusable. Equal-priority with US3 because both are foundational durability stories.

**Independent Test**: Mid-write to ExecutionResult, kill the harness process (or simulate via an injected exception). On restart, query the data layer; verify (a) the database file is readable, (b) no partial ExecutionResult records exist (the in-flight write was either fully committed or fully rolled back), (c) all other records are intact and queryable.

**Acceptance Scenarios**:

1. **Given** a write that crosses multiple entities (e.g., writing an ExecutionResult while also updating the parent Job's `processedCount`), **When** the harness process dies between the two writes, **Then** on restart either both writes are present or neither is — never one without the other.
2. **Given** a Job whose persisted status is `running` when the harness restarts (i.e., orphaned), **When** the orchestrator queries the data layer for jobs in `running` status, **Then** the orphaned Job is returned so the orchestrator can reconcile it per parent `FR-022`.

---

### User Story 5 - Migrate the schema across harness releases without data loss (Priority: P2)

A new harness release introduces a schema change (e.g., a new optional column on ExecutionResult to capture a new harness annotation). The migration runs on tester upgrade, transforms the existing data in place, and the prior jobs remain queryable in the new schema. A migration that fails leaves the data file untouched and the harness refuses to start until the migration is resolved.

**Why this priority**: Without migrations, every schema change is a data loss event. Lower priority than US1–US4 because v1 starts with a single schema; migrations only become exercised on the second release. But the migration mechanism MUST exist from v1 so the second release has somewhere to land.

**Independent Test**: Start with a database populated from v1 schema. Apply a v2 migration that adds an optional column to ExecutionResult. Verify all v1 records remain queryable with the new column reading as null/default; new v2 records can populate the new column.

**Acceptance Scenarios**:

1. **Given** an existing database file at version N, **When** a harness release at version N+1 starts, **Then** the data layer detects the version gap and applies the relevant migration(s) before any other module reads or writes.
2. **Given** a migration that fails partway, **When** the failure is detected, **Then** the database file is left at its pre-migration state (no partial migration committed) and the harness refuses to proceed with an actionable error including the migration name and failure cause.
3. **Given** a database file at a SCHEMA version newer than the running harness (e.g., tester downgrades), **When** the harness starts, **Then** it refuses to proceed and surfaces an actionable "database newer than this harness version; upgrade harness" error rather than risking data corruption.

---

### Edge Cases

- The configured DB file path's parent directory does not exist on first run — the data layer MUST create it (with OS-appropriate permissions) and then create the DB file. If creation fails (permission denied, disk full), the harness MUST refuse to start with an actionable error.
- The configured DB file path is read-only — the harness MUST detect this at startup and refuse to start with an actionable error before any module attempts a write.
- The DB file is moved to a different machine without the machine-local encryption key — read of any secret-declared config field will fail with the "machine-local key missing or wrong" error per parent `FR-023a` and `specs/007-connector-framework` → `FR-018`. Job execution requiring those secrets cannot proceed; the Job is marked `failed` with a clear error. Non-secret data (utterance text, normalized contracts, evaluation results without secrets) remains readable.
- A `connectorConfigSnapshot` or `evaluationAgentConfigSnapshot` happens to contain very large JSON content (e.g., an unusually long system prompt template) — no size cap is enforced in v1; storage just grows.
- A `rawChatbotResponse`, `normalizedContract`, or `evaluationResult` JSON value is very large (multi-megabyte payload from a verbose chatbot or evaluator) — no size cap is enforced in v1; rows persist as-is. UI/export modules handle truncation for display.
- Two ExecutionResults somehow end up with the same `utteranceId` (orchestrator bug, race condition, restart-then-retry) — the data layer's uniqueness constraint MUST prevent this; the second write is refused. The orchestrator MUST surface a clear error rather than silently overwriting.
- Concurrent writes from multiple harness processes pointed at the same DB file — out of scope for v1 (single-user, single-process tool); behavior is undefined.
- A Job is deleted while the orchestrator is mid-write to one of its rows — the cascade-delete and the write race; the data layer MUST either reject the write (post-delete) or reject the delete (pre-write) — never produce orphaned rows. The exact ordering policy is plan-level; the spec requires only that no orphaned rows result.
- A new schema migration introduces a NOT-NULL column without a default on a table that has existing rows — the migration MUST either supply a default OR fail at write-attempt with an actionable error; it MUST NOT leave the database in a non-startable state.
- A migration is interrupted mid-execution by a power loss — on restart, the database MUST be either fully pre-migration or fully post-migration (no half-migrated tables). The migration runner is responsible for atomicity (in practice: wrap each migration in a transaction where the storage engine supports it).
- The Utterance table's `originalText` column needs to round-trip non-UTF-8 characters that the original CSV happened to contain (rare but possible) — persisting and retrieving MUST be lossless at the byte level.

## Requirements *(mandatory)*

### Functional Requirements

#### Entity definitions

- **FR-001**: The data layer MUST define a **Job** entity carrying at minimum the following fields:
  - `jobId` — primary key, globally unique within the harness installation (UUID-style).
  - `jobName` — string, non-empty, tester-supplied at Step 1 of the wizard.
  - `description` — string, nullable, tester-supplied at Step 1.
  - `createdBy` — string, NOT NULL, auto-populated from the OS-derived tester identity (parent `FR-026`) at Job creation. Immutable past creation. NOT tester-editable. Defaults to `"unknown-user"` if OS resolution fails (per parent `FR-026`'s resolution chain). NOT a credential, NOT an authentication artifact — purely attribution.
  - `createdAt` — datetime, ISO-8601, set at Job creation.
  - `startedAt` — datetime, nullable. Null while `draft`; populated when the Job transitions to `queued`.
  - `completedAt` — datetime, nullable. Null until terminal status; populated when the Job reaches `completed`, `failed`, or `cancelled`.
  - `status` — one of the **canonical lifecycle enum values**: `draft`, `queued`, `running`, `cancelling`, `completed`, `failed`, `cancelled`. (Lowercase. The Module 2 input's `Configured` and `CompletedWithErrors` are NOT lifecycle values — `Configured` does not exist as a state; `CompletedWithErrors` is a UI label per Module 13 derived from `status == completed && failed_count > 0`.)
  - `connectorType` — string, the connector identity snapshotted at job-creation time per parent `FR-023`. Immutable past `draft`.
  - `connectorConfigSnapshot` — JSON, the connector's configuration snapshotted at job-creation time. Secret-declared fields within this JSON are encrypted at rest per parent `FR-023a` and Module 4's utility. Immutable past `draft`.
  - `evaluationAgentId` — string, the evaluator identity snapshotted at job-creation time. Immutable past `draft`.
  - `evaluationAgentConfigSnapshot` — JSON, the evaluator's configuration snapshotted at job-creation time. Secret-declared fields encrypted at rest. Immutable past `draft`.
  - `sourceCSVFilename` — string, the filename of the CSV the tester uploaded at Step 2. Stored as a string label only; the raw file content is NOT retained on disk (per `Clarifications` Q1).
  - `totalUtteranceCount` — integer, count of Utterances bound to this Job. Immutable past `draft`.
  - `processedCount` — integer, count of ExecutionResults belonging to this Job whose `errorStatus IN (null, "failed")` — i.e., rows that the orchestrator actually invoked the connector on (regardless of outcome). Cancelled-before-process rows (whose ExecutionResult stub has `errorStatus = "cancelled"`, per `FR-003a`) are NOT included here. Mutable; updated as rows complete.
  - `failedCount` — integer, count of ExecutionResults belonging to this Job whose `errorStatus = "failed"`. Mutable; updated as rows complete. (Cancelled-before-process rows are NOT counted as failures — they have `errorStatus = "cancelled"`, which is distinct from `"failed"`.)
  - `harnessVersion` — string, the harness's semantic version (or build identifier) at the moment the Job was created. Immutable past `draft`. Stamped at creation for forensic/forward-compatibility purposes.
- **FR-002**: The data layer MUST define an **Utterance** entity carrying at minimum:
  - `utteranceId` — primary key, globally unique (UUID), system-generated at row creation. MUST match the `utteranceId` field of Module 6's Standard Evaluation Contract.
  - `jobId` — foreign key to Job, NOT NULL. ON DELETE CASCADE.
  - `originalText` — string, the utterance text from the CSV's `utteranceText` column.
  - `rowIndex` — integer, **1-based**, the row's position in the source CSV. The first data row is `rowIndex = 1`, the second is `2`, etc. (`rowIndex` is independent of the CSV file's header row — only data rows are indexed.) Every persisted Utterance MUST have `rowIndex >= 1`; consumers may rely on this invariant.
  - `testId` — string, NOT NULL, from the CSV's `testId` column.
  - Additional per-row metadata columns from the CSV — stored as JSON or as a sibling table; plan-level shape. MUST preserve any non-required CSV columns verbatim (per parent `FR-002`).
  - **The Utterance entity MUST NOT have a `password` column, an `encryptedPassword` column, or any other persisted representation of the CSV `password` value.** Per parent `FR-010`, passwords are in-memory only.
  - Past `draft` job status, the Utterance row MUST be immutable (no edits to `originalText`, `rowIndex`, `testId`).
- **FR-003**: The data layer MUST define an **ExecutionResult** entity carrying at minimum:
  - `resultId` — primary key, globally unique (UUID).
  - `utteranceId` — foreign key to Utterance, NOT NULL, with a uniqueness constraint (at most one ExecutionResult per Utterance). ON DELETE CASCADE.
  - `testId` — string, denormalized from Utterance for indexing and per-`testId` filtering.
  - `rawChatbotResponse` — JSON, the connector's raw response payload (per Module 4 `FR-003` "RawResponse"). Nullable if the connector failed before producing one.
  - `normalizedContract` — JSON, the Standard Evaluation Contract instance produced by the connector (per Module 4 `FR-004`, conforming to the schema at `specs/006-evaluation-contract`). Nullable if normalization failed.
  - `evaluationResult` — JSON, the EvaluationResult produced by the evaluator (per Module 7 `FR-003`). Nullable if the row failed before evaluation.
  - `evaluationVerdict` — string, denormalized from `evaluationResult.verdict` for indexing and filter performance. One of `pass` / `fail` / `warn`, or null if the row failed before evaluation.
  - `harnessAnnotations` — JSON, the harness-derived annotation block per Module 7 `FR-005a` (e.g., `unexpected_score_dimensions`). Nullable / empty object when nothing to annotate.
  - `errorStatus` — string, nullable. Null when the row succeeded end-to-end. When non-null, one of: `failed` (the orchestrator invoked the connector on this row but the row didn't complete cleanly — see `errorStage` for where it broke), `cancelled` (the row was cancelled before the orchestrator could invoke the connector on it; see `FR-003a` for the stub-creation rule).
  - `errorStage` — string, nullable. Null when the row succeeded. When non-null, one of: `connector`, `normalization`, `evaluation` (per parent `FR-017`).
  - `errorDetails` — text, nullable. Free-form error detail captured by the orchestrator for failed rows.
  - `executionTimestamp` — datetime, ISO-8601, set when the ExecutionResult is persisted.
- **FR-003a**: When a Job transitions from `cancelling` to terminal `cancelled` (per parent `FR-024`'s soft-cancel sequence), the data layer MUST create an **ExecutionResult stub** for every Utterance belonging to the Job that does NOT yet have an ExecutionResult. Each stub MUST carry:
  - `errorStatus = "cancelled"` (per `FR-003`'s enum).
  - `errorStage = null` (the row was never invoked; there is no failure stage).
  - `null` for `rawChatbotResponse`, `normalizedContract`, `evaluationResult`, `evaluationVerdict`, `harnessAnnotations`.
  - `executionTimestamp` = the moment the stub is written (i.e., the moment of `cancelling → cancelled` transition).
  
  Stub creation MUST be atomic with the Job's status transition — either every queued Utterance gets a stub AND the Job's status flips to `cancelled`, or neither happens. After the transition completes, every Utterance in the Job MUST have exactly one ExecutionResult (whether real or stub), making ExecutionResult the single source of truth for per-row terminal state.
- **FR-004**: The data layer MUST define a **TesterFeedback** entity (the parent's `Tester Feedback` entity) carrying at minimum:
  - `feedbackId` — primary key, globally unique (UUID).
  - `utteranceId` — foreign key to Utterance, NOT NULL, with a uniqueness constraint (at most one TesterFeedback per Utterance — the spec's "replace prior feedback" rule from parent `FR-014`). ON DELETE CASCADE.
  - `feedbackValue` — enum: `thumbs_up`, `thumbs_down`. (No "cleared" value — clearing is deletion of the row per Module 13 `FR-010`.)
  - `feedbackBy` — string, NOT NULL, auto-populated from the OS-derived tester identity (parent `FR-026`) at write time. Captured per-feedback-write — if the tester clears and re-applies feedback later, the new row carries the OS identity at that moment. NOT tester-editable.
  - `feedbackTimestamp` — datetime, ISO-8601, set when feedback is applied.
  - Feedback is applied to an Utterance (the row), NOT to its ExecutionResult — a tester can apply feedback before or after evaluation completes, and the row's evaluation status is independent of feedback.

#### Snapshot immutability

- **FR-005**: The data layer MUST enforce that the following Job fields are **immutable past the `draft` status**: `connectorType`, `connectorConfigSnapshot`, `evaluationAgentId`, `evaluationAgentConfigSnapshot`, `totalUtteranceCount`, `harnessVersion`, `sourceCSVFilename`. Any write to these fields when the Job's current `status` is NOT `draft` MUST be refused with an actionable error. Additionally, `createdBy` and `createdAt` are **immutable from the moment of Job creation** (not just past `draft`) — there is no point in the lifecycle at which they should change.
- **FR-006**: The data layer MUST enforce that the following Utterance fields are **immutable past the parent Job's `draft` status**: `originalText`, `rowIndex`, `testId`, `utteranceId`. (`jobId` is also immutable, trivially, since changing it would re-parent the row.)
- **FR-007**: The data layer MUST NOT enforce immutability on runtime-state fields: `Job.status`, `Job.startedAt`, `Job.completedAt`, `Job.processedCount`, `Job.failedCount`, and the entire ExecutionResult / TesterFeedback tables. These are expected to change over the Job's lifecycle.

#### Encryption at rest (config-level secrets only)

- **FR-008**: Secret-declared fields within `connectorConfigSnapshot` and `evaluationAgentConfigSnapshot` MUST be encrypted at rest using the harness's existing machine-local symmetric key utility (Module 4 `FR-015`–`FR-019`, parent `FR-023a`). This module does NOT introduce its own encryption utility; it consumes Module 4's. The encryption boundary is per-field within the JSON snapshot, not whole-snapshot; non-secret fields in the same snapshot remain in plaintext for readability and queryability.
- **FR-009**: The data layer MUST NEVER attempt to encrypt or store the per-row CSV `password` value, even in encrypted form. Per parent `FR-010`, the per-row password is in-memory only; no Utterance column, no separate sidecar table, no audit log captures it. This is verifiable by inspecting the database file's bytes for any known-distinctive password value (must produce zero matches).

#### Cascading delete + status-gated delete

- **FR-010**: Deletion of a Job MUST cascade to delete every Utterance with matching `jobId`, every ExecutionResult linked to those Utterances (via `utteranceId`), and every TesterFeedback linked to those Utterances. The cascade MUST be atomic — either all rows are deleted or none.
- **FR-011**: The data layer MUST enforce status-gated deletion per parent `FR-001` and `FR-001a`: a Job in `draft`, `failed`, or `cancelled` status MAY be deleted; a Job in `queued`, `running`, `cancelling`, or `completed` status MUST NOT be deleted via this layer's deletion entry-point. Refusals MUST return a clear error naming the status.
- **FR-012**: The data layer MUST expose a **bulk deletion** entry-point for the dashboard's "Clear all failed and cancelled" action (`specs/002-dashboard-job-listing` → `FR-010c`). The operation MUST: (a) enumerate all Jobs in `failed` or `cancelled` status at execution time, (b) delete each with its full cascade, (c) execute atomically — either all qualifying jobs are deleted or none. Jobs that transition into `failed` or `cancelled` AFTER the operation starts MUST NOT be silently included.

#### Versioned schema + migrations

- **FR-013**: The data layer MUST have a **schema version** stored within the database file itself (in a dedicated single-row table). The version MUST be readable and writable by the migration mechanism only — application modules MUST NOT read or write the schema version directly.
- **FR-014**: On harness startup, the data layer MUST compare the database's stored schema version against the schema version embedded in the running harness binary:
  - **Equal** → proceed normally.
  - **DB older than harness** → run the pending migration(s) in order before any other module reads or writes; abort startup if any migration fails (database is left at its pre-failure state).
  - **DB newer than harness** → refuse to start with an actionable "database newer than this harness version; upgrade harness" error.
- **FR-015**: Migrations MUST be atomic where the storage engine supports atomic schema changes. If a migration cannot be made atomic, it MUST leave the database in a recoverable state on failure (the failed migration's name + any partial state's resolution path MUST be surfaced to the tester).
- **FR-016**: New optional columns added in later schema versions MUST be readable as `NULL` (or their declared default) when reading rows written under prior schema versions. Migrations MUST NOT silently drop or rename existing data.

#### Configurable storage location

- **FR-017**: The database file location MUST be configurable. The harness MUST read an OS-environment-variable-style configuration knob (or equivalent plan-defined mechanism) at startup; in its absence, the default location MUST be `~/.harness/data.db` (or the OS-equivalent user-data directory).
- **FR-018**: If the configured path's parent directory does not exist, the harness MUST create it (with OS-appropriate permissions) on first run. If creation or write fails, startup MUST abort with an actionable error.

#### Persistence behavior

- **FR-019**: The data layer MUST expose operations sufficient for every other harness module's needs: per-entity reads (by primary key + by foreign key + by filtered query), inserts, updates (subject to immutability rules), and the cascading deletes defined in `FR-010` / `FR-012`. The literal shape of these operations (repository pattern with named methods vs. ORM session vs. raw query interface) is plan-level.
- **FR-020**: Cross-entity writes that conceptually belong together (e.g., writing an ExecutionResult while incrementing the parent Job's `processedCount`) MUST be performed in a single atomic transaction — either both writes commit or neither does. A harness crash mid-transaction MUST leave the database in its pre-transaction state.
- **FR-021**: The data layer MUST enforce the documented uniqueness and referential-integrity constraints (unique `utteranceId`, unique `resultId` per `utteranceId`, unique `feedbackId` per `utteranceId`, valid foreign-key references). Violations MUST be refused at the boundary, not silently overwritten or ignored.
- **FR-022**: The data layer MUST be the single source of truth for persisted state. Modules MUST NOT bypass it to read or write the database file directly.

### Key Entities *(include if feature involves data)*

- **Job**: The container for one regression run. See `FR-001` for the full field list. Carries lifecycle state, configuration snapshots, aggregate counters, and the harness version that created it.
- **Utterance**: One persisted row from the source CSV (one per CSV data row at job-creation time). See `FR-002`. Stores the input data minus `password`.
- **ExecutionResult**: The per-row trace of what happened when the orchestrator processed an Utterance — connector output, normalized contract instance, evaluator output, error state. See `FR-003`. At most one per Utterance.
- **TesterFeedback**: An optional per-row tester verdict (thumbs-up / thumbs-down). See `FR-004`. At most one per Utterance; absence is the default and the "cleared" state.
- **Schema Version**: A single-row table managed by the migration mechanism only. Tracks the schema generation the database file currently conforms to. Application modules do not read or write this directly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Creating a draft Job, advancing it through the wizard, transitioning to `queued`, processing N rows, and reaching a terminal status results in: exactly one Job record, exactly N Utterance records, exactly N ExecutionResult records (mix of success and failure), at most N TesterFeedback records (whatever feedback was applied), and aggregate counters on the Job matching the rows — verifiable by counting rows in each table after an end-to-end test run.
- **SC-002**: For any started Job, mutating any field listed in `FR-005` or `FR-006` is observably refused — verifiable by attempting the mutation and inspecting the data-layer's error response.
- **SC-003**: A registry edit to a connector or evaluator that a started Job snapshotted does NOT change the Job's snapshot — verifiable by mutating the registry between Job creation and Job read, and confirming the snapshot's persisted value remains the original.
- **SC-004**: No persisted byte of the database file contains a per-row CSV password value, encrypted or otherwise — verifiable by inserting a known-distinctive password (e.g., `"DEADBEEF-PWD-12345"`) into a job's CSV, running the job to completion, and grepping the database file for that exact string (must produce zero matches).
- **SC-005**: Secret-declared fields within `connectorConfigSnapshot` and `evaluationAgentConfigSnapshot` are encrypted at rest — verifiable by inserting a known-distinctive secret config value, persisting the snapshot, and grepping the database file for that exact string (must produce zero matches). The same value MUST decrypt cleanly when the orchestrator invokes the connector or evaluator.
- **SC-006**: Deleting a Job in `draft`, `failed`, or `cancelled` status removes all its Utterances, ExecutionResults, and TesterFeedback records in a single atomic operation — verifiable by counting rows before and after the delete in each table.
- **SC-007**: Deleting a Job in `queued`, `running`, `cancelling`, or `completed` status is refused at the data layer — verifiable by enumerating the seven statuses and attempting deletion on each.
- **SC-008**: After a simulated harness crash mid-transaction, the database file is queryable and contains either all writes from the in-flight transaction or none — verifiable by injecting a failure between two writes that belong to the same transaction and inspecting the data afterward.
- **SC-009**: A migration that fails partway leaves the database file at its pre-migration state — verifiable by deliberately introducing a failure in a test migration and inspecting the schema version and table contents afterward.
- **SC-010**: Starting the harness against a database file at a newer schema version than the harness knows produces a clear "database newer than harness" error before any read or write — verifiable by manually writing a future schema-version value into the version table and attempting startup.
- **SC-011**: The default database location is `~/.harness/data.db`; the location is overridable by configuration; if the configured location's parent directory does not exist, the harness creates it on first run — verifiable by running the harness with and without the configuration knob set and against a non-existent parent directory.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, single-process, local-only. Concurrency from multiple harness processes against the same database file is out of scope for v1.
- The encryption utility for config-level secret fields is defined and provided by Module 4 (`specs/007-connector-framework` → `FR-015`–`FR-019`); this module consumes it but does NOT redefine or duplicate it.
- The per-row CSV `password` is governed by parent `FR-010`: in-memory only, never persisted. The Module 2 input's `encryptedPassword` field on Utterance is intentionally absent (`Clarifications` Q1). Job resumability for credential-bearing rows after restart remains forbidden by parent `FR-010a`.
- The Job status enum is the parent's canonical seven-value set (`Clarifications` Q2). `CompletedWithErrors` is a UI label per Module 13, not a stored value.
- Implementation choices for the database engine, ORM library, migration framework, and repository pattern shape are plan-level (the user mentioned SQLAlchemy / SQLite / Alembic; this spec describes data shape and persistence behavior, leaving the binding to the plan).
- The raw uploaded CSV file is NOT retained on disk as a binary artifact — only the persisted rows (Utterances) capture its contents minus `password`. The `Job.sourceCSVFilename` field captures only the filename string for tester-facing display.
- "Globally unique within the harness installation" means UUID-style ids that don't collide across jobs. Cross-installation uniqueness is out of scope.
- "Cascade delete" extends through Job → Utterance → ExecutionResult → TesterFeedback. There is no other multi-level cascade in v1's data model.
- Schema versioning starts at version `1` with the initial harness release. Future releases publishing a v2 schema MUST also publish a v1→v2 migration before they ship.
- The exact column types within the persisted JSON fields (e.g., `connectorConfigSnapshot.endpoint`) are NOT enforced by the data layer — they are governed by the connector's declared JSON Schema (Module 4) and the evaluator's declared JSON Schema (Module 7). The data layer just stores valid JSON.
- The `harnessVersion` field stamps the harness's own version (whatever the project's release tag is at the moment of job creation). The mapping between Python package version, Git tag, and the value stored in `harnessVersion` is plan-level.
