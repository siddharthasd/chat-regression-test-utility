# Feature Specification: Data Model & Persistence Layer (Module 2)

**Feature Branch**: `009-data-model-persistence`

**Created**: 2026-05-29

**Last Amended**: 2026-05-29

**Status**: Draft

**Input**: User description: "Module 2 — Data Model & Persistence Layer. Core entities (Job, Utterance, EvaluationResult), repository/data-access layer with CRUD per entity, versioned schema migrations, job configuration snapshots immutable after job start. Uploaded CSV file linked to the job. SQLAlchemy + SQLite + Alembic. `harnessVersion` on Job. DB file location configurable, default `~/.harness/data.db`. Symmetric encryption utility for the password field with a machine-local key."

> **Parent context**: This module is the persistence foundation underneath every other module. Job (with its config snapshots and lifecycle state) and per-row Utterance and EvaluationResult all live here. The Module 2 input had several phrases that conflicted with established parent-spec decisions; those were resolved before writing this spec (see `Clarifications`). Parent-spec premises apply: single-user, no auth. Per Round 3 (driven by Module 3), `Job.createdBy` is now a real persisted field — OS-derived per parent `FR-026`. Per Round 4 (cross-spec user-feedback removal), the `TesterFeedback` entity that earlier rounds defined here has been **dropped entirely** — the user-feedback (thumbs-up/down) feature is not part of v1. Module 4's encryption utility (`specs/007-connector-framework` → `FR-013`–`FR-017`) and parent `FR-023a` define how stored auth credentials are encrypted at rest; this module USES that utility but does NOT introduce its own. Per-row CSV `password` is NOT persisted in any form (parent `FR-010`); the Module 2 input's `encryptedPassword` field on Utterance was dropped by explicit decision (2026-05-29). The job lifecycle (`draft → queued → running → cancelling → completed / failed / cancelled`) is the parent's canonical enum; the Module 2 input's `[Draft, Configured, Running, Completed, CompletedWithErrors, Failed]` was dropped — `Configured` is not a defined state, `CompletedWithErrors` is a UI label per Module 13. The user's module number "Module 2" maps to our `009-` directory by the convention used for Modules 4 → 007, 7 → 008. Implementation choices (SQLAlchemy / SQLite / Alembic) are treated as plan-level decisions — this spec describes the data shape and persistence behavior, not the library binding.

## Clarifications

### Session 2026-05-29

- Q: The Module 2 input adds `encryptedPassword` to Utterance and says the uploaded CSV is stored as an immutable binary artifact. Both override parent `FR-010` (in-memory only, never persisted). Honor or override? → A: **Honor parent `FR-010`.** Per-row CSV `password` is NOT persisted in any form, in any table, encrypted or otherwise. The raw uploaded CSV file is NOT retained on disk as a binary artifact — that would persist passwords. The Utterance entity stores only the persisted-row data (utterance + testId + other CSV columns minus `password`). The "download original CSV" affordance reconstructs from those rows per `specs/004-job-detail-view` → `FR-006`. Module 4's encryption utility remains scoped to **config-level secrets only**, per its `FR-019`. Job resumability for credential-bearing rows after a restart remains forbidden by parent `FR-010a`.
- Q: The Module 2 input's Job status enum is `[Draft, Configured, Running, Completed, CompletedWithErrors, Failed]`. The parent spec's canonical enum is `[draft, queued, running, cancelling, completed, failed, cancelled]` with `CompletedWithErrors` as a derived UI label. Which wins? → A: **Parent's canonical enum.** Job.status is stored as one of `draft / queued / running / cancelling / completed / failed / cancelled` (lowercase). `Configured` is dropped (not a defined lifecycle state — the wizard moves `draft → queued` directly on Start). `CompletedWithErrors` is dropped from the stored enum (it is a UI label derived at render time from `status == completed && failedCount > 0`, per `002 FR-005` / `004 FR-005`).

### Session 2026-05-29 (Round 2)

- Q: How are cancelled-but-never-processed rows tracked at the data layer? → A: **Create EvaluationResult stubs for every Utterance that was queued-but-never-processed when the parent Job goes terminal-cancelled.** Each stub carries `errorStatus = "cancelled"`, `errorStage = null` (no real failure stage — the row never ran), and `null` for `rawChatbotResponse`, `normalizedContract`, `evaluationVerdict`, `evaluationScores`, `metadata`, `harnessAnnotations`. EvaluationResult becomes the single source of truth for per-row terminal state — every row in any terminal Job has exactly one EvaluationResult. Definitions: `processedCount` = count of EvaluationResults whose `errorStatus IN (null, "failed")`; `failedCount` = count of EvaluationResults whose `errorStatus = "failed"`. Implicit cancelled count = `totalUtteranceCount − processedCount`. Stub creation MUST be performed atomically with the Job's `cancelling → cancelled` transition.
- Q: Is `Utterance.rowIndex` 0-based or 1-based? → A: **1-based.** Row 1 = the first data row of the uploaded CSV. Matches spreadsheet convention; reads naturally in any tester-facing surface (dashboard, detail view, export, error messages). The data layer enforces 1-based numbering at insert time; consumers can rely on `rowIndex >= 1` for every persisted Utterance.

### Session 2026-05-29 (Round 3 — revision driven by Module 3)

- Q: Module 3 (`specs/010-tester-identity`) re-introduces OS-derived attribution. Should `Job.createdBy` and `TesterFeedback.feedbackBy` be added to the data layer? → A: **Yes** (partial). Add `createdBy` to the Job entity (`FR-001`); auto-populated from the parent harness's OS-resolved tester identity (parent `FR-026`) at write time. Immutable past Job creation. This reverses the Q1 ("Honor parent FR-010") clarification's implicit precedent that no creator field exists — the password-persistence rule stays, but the creator-attribution rule is now ADDITIVE. *(Originally this Q also added `feedbackBy` to TesterFeedback; per Round 4 below the TesterFeedback entity was dropped entirely, so `feedbackBy` is no longer part of the data model.)*

### Session 2026-05-29 (Round 4 — user-feedback feature removed)

- Q: Should the `TesterFeedback` entity (and the user-feedback feature in general) remain in v1? → A: **No — removed entirely.** Driven by the cross-spec user-feedback removal. The TesterFeedback entity is dropped: `FR-004` removed, `FR-010` / `FR-012` cascade rules no longer mention it, `FR-021` no longer enforces `feedbackId` uniqueness, the entity list drops it, `SC-001` / `SC-006` are reworded to drop the per-job feedback row count. The data layer has only three persisted entities in v1: Job, Utterance, EvaluationResult. The harness has no in-memory feedback either; the feature is fully out.

### Session 2026-05-29 (Reshape — remote-service architecture)

- Q: With connectors and evaluators reshaped to remote HTTP services managed by CRUD modules (`013`, `014`), what changes in the data layer? → A: Two changes:
  1. **Two new persisted entities** join the data layer: `ConnectorRegistration` and `EvaluationAgentRegistration` (see `FR-001a` and `FR-001b` below). Each carries the registered endpoint configuration (URL, auth descriptor, timeout, plus connector-specific `expectsPerRowPassword` flag or evaluator-specific `declaredScoringDimensions` list), an `archived` flag (for soft-delete per `013`/`014`), audit timestamps, and a harness-assigned immutable id. Credential ciphertext within `authDescriptor` is encrypted at rest using Module 4's utility (same encryption story as the config snapshots).
  2. **Job's snapshot fields are restructured.** The previously-opaque `connectorConfigSnapshot` and `evaluationAgentConfigSnapshot` JSON blobs are replaced by explicit named snapshot columns on the Job entity. The orchestrator (`012 FR-004`) and the wizard (`003 FR-009`/`FR-012`) reference these by name. See `FR-001`'s updated field list. The encryption-at-rest rule (`FR-008`) continues to apply to the credential subfields within the snapshotted `authDescriptor` exactly as it does on the registration.
  
  The data layer now has **five persisted entities in v1**: Job, Utterance, EvaluationResult, ConnectorRegistration, EvaluationAgentRegistration. (The `TesterFeedback` entity remains removed per Round 4.) Snapshot immutability rules in `FR-005` are extended from the prior set `{connectorConfigSnapshot, evaluationAgentConfigSnapshot, totalUtteranceCount, harnessVersion, sourceCSVFilename}` to the new set: 6 connector snapshot columns (`connectorId`, `connectorName`, `connectorEndpointUrl`, `connectorAuthDescriptor`, `connectorTimeoutSeconds`, `connectorExpectsPerRowPassword`) + 6 evaluator snapshot columns (`evaluationAgentId`, `evaluationAgentName`, `evaluatorEndpointUrl`, `evaluatorAuthDescriptor`, `evaluatorTimeoutSeconds`, `evaluatorDeclaredScoringDimensions`) + `totalUtteranceCount` + `harnessVersion` + `sourceCSVFilename` — for a total of 15 immutable-past-`draft` fields. `createdBy` and `createdAt` remain immutable-from-creation (a stricter rule, unchanged by the reshape).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create, configure, snapshot, and run a job through its full lifecycle (Priority: P1)

The wizard creates a Job in `draft` status (just name + description). As the tester progresses through Steps 2–4 of the wizard, the harness writes to the Utterance table (one row per CSV row, minus `password`), persists the connector identity + config snapshot and the evaluation-agent identity + config snapshot onto the Job, and stores aggregate counts (`totalUtteranceCount`, etc.). On Start (Step 5), the Job transitions to `queued`; the snapshots become immutable; the orchestrator picks the job up and transitions it to `running`; per-row EvaluationResults accumulate as the orchestrator processes Utterances; counters update; the Job reaches a terminal status. This story exercises every entity in this module under normal conditions.

**Why this priority**: This is the entire purpose of the persistence layer. Every other module depends on it. It is the MVP slice of Module 2.

**Independent Test**: With stub implementations of the wizard, connector framework, evaluation framework, and orchestrator, write fixtures that exercise the full data-flow: create a draft Job, write 5 Utterances to it, snapshot a connector + evaluator config (with at least one secret field per snapshot), transition to `queued`, write 5 EvaluationResults (mix of success and `failed` rows with different `errorStage` values). Verify (a) every entity is persisted with the expected fields, (b) snapshots are byte-identical to the stored copies regardless of whether the registry's underlying connector/evaluator has changed in the meantime, (c) the Job's aggregate counts match the EvaluationResults, (d) the secret fields in the snapshots are not visible in plaintext on disk.

**Acceptance Scenarios**:

1. **Given** the wizard creates a Job in `draft` status, **When** the data layer persists it, **Then** the Job record carries `jobId`, `jobName`, `description` (or null), `createdAt`, `status == draft`, `harnessVersion`, and null/zero placeholders for everything else.
2. **Given** the tester crosses Step 2, **When** the harness writes Utterances, **Then** N Utterance records appear, each carrying `utteranceId` (system-generated UUID, globally unique per Module 6 `FR-002`), `jobId`, `utteranceText`, `rowIndex`, `testId`, and any other persisted CSV columns. None carries a password column or value, regardless of whether the original CSV had one.
3. **Given** the tester completes Steps 3 and 4, **When** the snapshots are persisted onto the Job, **Then** the full set of connector and evaluator snapshot fields (`connectorId`, `connectorName`, `connectorEndpointUrl`, `connectorAuthDescriptor`, `connectorTimeoutSeconds`, `connectorExpectsPerRowPassword`, plus the symmetric `evaluator*` / `evaluationAgent*` fields per `FR-001`) are populated; credential subfields within both `authDescriptor` values are encrypted at rest using Module 4's machine-local key utility (parent `FR-023a`).
4. **Given** Job status is `draft`, **When** the wizard transitions to `queued` on Start, **Then** all snapshot fields and the `totalUtteranceCount` field become immutable; subsequent writes to those fields MUST be refused at the data-layer boundary.
5. **Given** the orchestrator processes Utterances, **When** each row's EvaluationResult is persisted, **Then** the record carries `resultId`, `utteranceId`, `testId` (denormalized for indexing), `rawChatbotResponse` (JSON), `normalizedContract` (JSON conforming to Module 6's schema), `evaluationAgentId`, `evaluationVerdict` (from the agent's payload per `008 FR-003`), `evaluationScores` (JSON array from the agent's payload), `metadata` (JSON object from the agent's payload), `harnessAnnotations` (JSON — the harness-derived block per `008 FR-005a`), `errorStatus`, `errorStage`, `errorDetails`, `evaluationTimestamp`. The Job's `processedCount` and `failedCount` update accordingly.

---

### User Story 2 - Snapshot immutability protects historical interpretability (Priority: P1)

After a Job has started, the connector identity, the connector config snapshot, the evaluator identity, the evaluator config snapshot, the `totalUtteranceCount`, the `harnessVersion`, and the row-level identity fields (`utteranceId`, `rowIndex`, `testId`, `utteranceText`) are immutable. Subsequent registry edits (e.g., upgrading the connector in place) do not retroactively alter a previously-started job's snapshot. This is the parent's `FR-023` made operational at the data layer.

**Why this priority**: Without immutability, results are not interpretable historically — a tester triaging a failure three weeks later can't be sure what config was in use. Equal-priority with US1 because the invariant is foundational.

**Independent Test**: Start a Job with a known connector config (`endpoint=https://A`). After the job runs to completion, change the connector's registry entry to use `endpoint=https://B`. Read the completed Job's persisted snapshot from the data layer; verify the snapshot still says `endpoint=https://A` (the value at job-creation time), NOT `endpoint=https://B`.

**Acceptance Scenarios**:

1. **Given** a Job whose status has transitioned past `draft` (i.e., `queued`/`running`/terminal/cancelling), **When** any harness module attempts to write to any field listed in `FR-005`'s immutability set (which includes all `connector*` and `evaluator*` / `evaluationAgent*` snapshot fields, `totalUtteranceCount`, `harnessVersion`, and `sourceCSVFilename`), **Then** the data layer MUST refuse the write with an actionable error naming the immutable field. (Writes to `status`, `startedAt`, `completedAt`, `processedCount`, `failedCount` remain allowed — they are runtime state, not snapshot state.)
2. **Given** a Job whose status has transitioned past `draft`, **When** any harness module attempts to alter `utteranceText`, `rowIndex`, `testId`, or `utteranceId` on any Utterance belonging to that Job, **Then** the data layer MUST refuse the write.
3. **Given** the underlying registry entry for a connector or evaluator that a started Job snapshotted is later modified, **When** the Job's snapshot is read, **Then** the read returns the originally-snapshotted values, NOT the registry's current values.

---

### User Story 3 - Cascade delete a job and its rows; protect non-deletable statuses (Priority: P2)

Per parent `FR-001` (`draft` jobs deletable) and `FR-001a` (`failed` and `cancelled` jobs deletable), a deletion request flows through the data layer. The layer cascades the delete to every Utterance and every EvaluationResult belonging to the deleted Job. A deletion request against a Job in `completed`, `queued`, `running`, or `cancelling` status is refused — these states are explicitly non-deletable.

**Why this priority**: Deletion is a real productivity requirement (especially for the dashboard's "Clear all failed and cancelled" bulk action per `005`). Equal-priority with US4 because the data layer is the only place to enforce the cascade and the status-gate correctly.

**Independent Test**: With one Job in each of the seven lifecycle states, attempt a delete on each. Verify the three deletable states (`draft`, `failed`, `cancelled`) succeed and cascade; the four non-deletable states (`queued`, `running`, `cancelling`, `completed`) are refused with an actionable error.

**Acceptance Scenarios**:

1. **Given** a Job in `draft`, `failed`, or `cancelled` status with N Utterances and M EvaluationResults, **When** the data layer is asked to delete the Job, **Then** the Job and all N + M dependent records are removed atomically (all-or-nothing). After the operation, queries for any of those records by id return "not found."
2. **Given** a Job in `completed`, `queued`, `running`, or `cancelling` status, **When** the data layer is asked to delete it, **Then** the request is refused with a clear error naming the status and the rule.
3. **Given** the dashboard's "Clear all failed and cancelled" bulk action (`specs/002-dashboard-job-listing` → `FR-010c`) is invoked, **When** the data layer executes the bulk delete, **Then** every Job currently in `failed` or `cancelled` is deleted (with its cascading rows), in a single atomic operation, and no other Job is affected.

---

### User Story 4 - Survive a harness restart with a consistent persisted state (Priority: P2)

The harness process is killed (crash, OS reboot, manual `Ctrl-C` mid-job). On restart, the data layer's state is consistent: every Job is in a definite status; orphaned `running` jobs are reconciled per parent `FR-022` (the layer doesn't fix them itself but provides the queries the orchestrator needs); every persisted record is queryable. No partial writes have left the database in a corrupted state.

**Why this priority**: A regression-test tool that loses or corrupts data on a restart is unusable. Equal-priority with US3 because both are foundational durability stories.

**Independent Test**: Mid-write to EvaluationResult, kill the harness process (or simulate via an injected exception). On restart, query the data layer; verify (a) the database file is readable, (b) no partial EvaluationResult records exist (the in-flight write was either fully committed or fully rolled back), (c) all other records are intact and queryable.

**Acceptance Scenarios**:

1. **Given** a write that crosses multiple entities (e.g., writing an EvaluationResult while also updating the parent Job's `processedCount`), **When** the harness process dies between the two writes, **Then** on restart either both writes are present or neither is — never one without the other.
2. **Given** a Job whose persisted status is `running` when the harness restarts (i.e., orphaned), **When** the orchestrator queries the data layer for jobs in `running` status, **Then** the orphaned Job is returned so the orchestrator can reconcile it per parent `FR-022`.

---

### User Story 5 - Migrate the schema across harness releases without data loss (Priority: P2)

A new harness release introduces a schema change (e.g., a new optional column on EvaluationResult to capture a new harness annotation). The migration runs on tester upgrade, transforms the existing data in place, and the prior jobs remain queryable in the new schema. A migration that fails leaves the data file untouched and the harness refuses to start until the migration is resolved.

**Why this priority**: Without migrations, every schema change is a data loss event. Lower priority than US1–US4 because v1 starts with a single schema; migrations only become exercised on the second release. But the migration mechanism MUST exist from v1 so the second release has somewhere to land.

**Independent Test**: Start with a database populated from v1 schema. Apply a v2 migration that adds an optional column to EvaluationResult. Verify all v1 records remain queryable with the new column reading as null/default; new v2 records can populate the new column.

**Acceptance Scenarios**:

1. **Given** an existing database file at version N, **When** a harness release at version N+1 starts, **Then** the data layer detects the version gap and applies the relevant migration(s) before any other module reads or writes.
2. **Given** a migration that fails partway, **When** the failure is detected, **Then** the database file is left at its pre-migration state (no partial migration committed) and the harness refuses to proceed with an actionable error including the migration name and failure cause.
3. **Given** a database file at a SCHEMA version newer than the running harness (e.g., tester downgrades), **When** the harness starts, **Then** it refuses to proceed and surfaces an actionable "database newer than this harness version; upgrade harness" error rather than risking data corruption.

---

### Edge Cases

- The configured DB file path's parent directory does not exist on first run — the data layer MUST create it (with OS-appropriate permissions) and then create the DB file. If creation fails (permission denied, disk full), the harness MUST refuse to start with an actionable error.
- The configured DB file path is read-only — the harness MUST detect this at startup and refuse to start with an actionable error before any module attempts a write.
- The DB file is moved to a different machine without the machine-local encryption key — read of any encrypted credential subfield will fail with the "machine-local key missing or wrong" error per parent `FR-023a` and `specs/007-connector-framework` → `FR-016`. Job execution requiring those credentials manifests as per-row `connector_auth` / `evaluator_auth` failures rather than a pre-row Job-level failure (the orchestrator attempts each row independently per the 2026-05-29 Reshape clarification in `012`). Non-secret data (utterance text, normalized contracts, evaluation results without credentials) remains readable.
- A JSON-valued column (`connectorAuthDescriptor`, `evaluatorAuthDescriptor`, `rawChatbotResponse`, `normalizedContract`, `evaluationScores`, `metadata`, `harnessAnnotations`, `evaluatorDeclaredScoringDimensions`) happens to contain very large content (multi-megabyte payload from a verbose chatbot or evaluator) — no size cap is enforced in v1; rows persist as-is. UI/export modules handle truncation for display.
- Two EvaluationResults somehow end up with the same `utteranceId` (orchestrator bug, race condition, restart-then-retry) — the data layer's uniqueness constraint MUST prevent this; the second write is refused. The orchestrator MUST surface a clear error rather than silently overwriting.
- Concurrent writes from multiple harness processes pointed at the same DB file — out of scope for v1 (single-user, single-process tool); behavior is undefined.
- A Job is deleted while the orchestrator is mid-write to one of its rows — the cascade-delete and the write race; the data layer MUST either reject the write (post-delete) or reject the delete (pre-write) — never produce orphaned rows. The exact ordering policy is plan-level; the spec requires only that no orphaned rows result.
- A new schema migration introduces a NOT-NULL column without a default on a table that has existing rows — the migration MUST either supply a default OR fail at write-attempt with an actionable error; it MUST NOT leave the database in a non-startable state.
- A migration is interrupted mid-execution by a power loss — on restart, the database MUST be either fully pre-migration or fully post-migration (no half-migrated tables). The migration runner is responsible for atomicity (in practice: wrap each migration in a transaction where the storage engine supports it).
- The Utterance table's `utteranceText` column needs to round-trip non-UTF-8 characters that the original CSV happened to contain (rare but possible) — persisting and retrieving MUST be lossless at the byte level.

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
  - `status` — one of the **canonical lifecycle enum values**: `draft`, `queued`, `running`, `cancelling`, `completed`, `failed`, `cancelled`. (Lowercase. The Module 2 input's `Configured` and `CompletedWithErrors` are NOT lifecycle values — `Configured` does not exist as a state; `CompletedWithErrors` is a UI label per `002 FR-005` derived from `status == completed && failedCount > 0`.)
  - `connectorId` — string, the harness-assigned immutable id of the `ConnectorRegistration` chosen at job-creation time, snapshotted per parent `FR-023`. Foreign-key-style reference into the `ConnectorRegistration` table (no enforced foreign-key constraint, since hard-delete is gated by the existence of historical job references per `013 FR-019` — the FK reference is forensic/lookup-only). Used by `012 FR-004` as the snapshot anchor. Immutable past `draft`.
  - `connectorName` — string, the registration's `displayName` snapshotted at job-creation time (per `003 FR-009`). Per the 2026-05-29 reshape, this is NOT tester-editable in the wizard — it is a verbatim snapshot of the registration's `displayName`. Surfaces in the dashboard's Connector column (`002 FR-003`), the detail view's Metadata Panel (`004 FR-003`), and the export's job metadata block (`005 FR-005`). Immutable past `draft`.
  - `connectorEndpointUrl` — string, the registration's `endpointUrl` snapshotted at job-creation time. Used by `012 FR-011` step 2 to construct the per-row connector HTTP request. Immutable past `draft`.
  - `connectorAuthDescriptor` — JSON, the registration's `authDescriptor` snapshotted at job-creation time. Carries `mode` (`none` / `bearer` / `api-key-header` / `basic`) plus the mode-specific subfields (`headerName` cleartext for `api-key-header`; `username` cleartext for `basic`; credential ciphertext encrypted at rest per parent `FR-023a` and `FR-008` of this spec). Immutable past `draft`.
  - `connectorTimeoutSeconds` — integer, the registration's `timeoutSeconds` snapshotted at job-creation time. Used by `012 FR-011` step 2 to enforce per-row HTTP timeout. Immutable past `draft`.
  - `connectorExpectsPerRowPassword` — boolean, the registration's `expectsPerRowPassword` flag snapshotted at job-creation time. Used by `012 FR-011` step 1 (password lookup gating) and `011 FR-006`/`FR-009` (CSV column-requirement gating). Immutable past `draft`.
  - `evaluationAgentId` — string, the harness-assigned immutable id of the `EvaluationAgentRegistration` chosen at job-creation time, snapshotted per parent `FR-023`. Same FK pattern as `connectorId`. Immutable past `draft`.
  - `evaluationAgentName` — string, the registration's `displayName` snapshotted at job-creation time (per `003 FR-012`). NOT tester-editable in the wizard. Surfaces in the detail view's Metadata Panel and export's job metadata block. Immutable past `draft`.
  - `evaluatorEndpointUrl` — string, the registration's `endpointUrl` snapshotted at job-creation time. Used by `012 FR-011` step 5 to construct the per-row evaluator HTTP request. Immutable past `draft`.
  - `evaluatorAuthDescriptor` — JSON, the registration's `authDescriptor` snapshotted at job-creation time. Same shape as `connectorAuthDescriptor`. Credential ciphertext encrypted at rest. Immutable past `draft`.
  - `evaluatorTimeoutSeconds` — integer, the registration's `timeoutSeconds` snapshotted at job-creation time. Used by `012 FR-011` step 5 to enforce per-row HTTP timeout. Immutable past `draft`.
  - `evaluatorDeclaredScoringDimensions` — JSON array of strings, the registration's `declaredScoringDimensions` snapshotted at job-creation time (ordered list per `014 FR-011`). Used by `012 FR-011` step 7 to compute `harnessAnnotations.unexpected_score_dimensions` and by the detail view (`004`) / export (`005`) to render columns in canonical order. Immutable past `draft`.
  - `sourceCSVFilename` — string, the filename of the CSV the tester uploaded at Step 2. Stored as a string label only; the raw file content is NOT retained on disk (per `Clarifications` Q1).
  - `totalUtteranceCount` — integer, count of Utterances bound to this Job. Immutable past `draft`.
  - `processedCount` — integer, count of EvaluationResults belonging to this Job whose `errorStatus IN (null, "failed")` — i.e., rows that the orchestrator actually invoked the connector on (regardless of outcome). Cancelled-before-process rows (whose EvaluationResult stub has `errorStatus = "cancelled"`, per `FR-003a`) are NOT included here. Mutable; updated as rows complete.
  - `failedCount` — integer, count of EvaluationResults belonging to this Job whose `errorStatus = "failed"`. Mutable; updated as rows complete. (Cancelled-before-process rows are NOT counted as failures — they have `errorStatus = "cancelled"`, which is distinct from `"failed"`.)
  - `harnessVersion` — string, the harness's semantic version (or build identifier) at the moment the Job was created. Immutable past `draft`. Stamped at creation for forensic/forward-compatibility purposes. Surfaced on the dashboard (per `002 FR-003`).
  - `errorDetails` — string, nullable. Null while the Job is still progressing or has reached `completed` / `cancelled` terminal status. Populated when the Job's terminal status is `failed`: by the orchestrator's orphan-reconciliation pass (per `012 FR-002`, e.g. `"harness restarted while job was running"`) or by the orchestrator's fatal-pre-row-error handling (per `012 FR-017`, e.g. `"connector no longer registered"` / `"machine-local key missing or wrong"` / `"credentials no longer in memory — re-upload CSV"`). Mutable while the Job is non-terminal; immutable once a terminal status is reached. Distinct from the per-row `EvaluationResult.errorDetails` (which captures row-level failure detail per `FR-003`).
- **FR-002**: The data layer MUST define an **Utterance** entity carrying at minimum:
  - `utteranceId` — primary key, globally unique (UUID), system-generated at row creation. MUST match the `utteranceId` field of Module 6's Standard Evaluation Contract.
  - `jobId` — foreign key to Job, NOT NULL. ON DELETE CASCADE.
  - `utteranceText` — string, the utterance text from the CSV's `utteranceText` column (same name end-to-end: CSV column, DB column, contract field, export field).
  - `rowIndex` — integer, **1-based**, the row's position in the source CSV. The first data row is `rowIndex = 1`, the second is `2`, etc. (`rowIndex` is independent of the CSV file's header row — only data rows are indexed.) Every persisted Utterance MUST have `rowIndex >= 1`; consumers may rely on this invariant.
  - `testId` — string, NOT NULL, from the CSV's `testId` column.
  - Additional per-row metadata columns from the CSV — stored as JSON or as a sibling table; plan-level shape. MUST preserve any non-required CSV columns verbatim (per parent `FR-002`).
  - **The Utterance entity MUST NOT have a `password` column, an `encryptedPassword` column, or any other persisted representation of the CSV `password` value.** Per parent `FR-010`, passwords are in-memory only.
  - Past `draft` job status, the Utterance row MUST be immutable (no edits to `utteranceText`, `rowIndex`, `testId`).
- **FR-003**: The data layer MUST define an **EvaluationResult** entity carrying at minimum (this entity is the persisted per-row trace — it collapses what parent `001` historically called `Connector Invocation` and `Evaluation Result` into a single record, and uses the same name as Module 7's `evaluate()` return type since the agent's payload fields are inline columns here):
  - `resultId` — primary key, globally unique (UUID).
  - `utteranceId` — foreign key to Utterance, NOT NULL, with a uniqueness constraint (at most one EvaluationResult per Utterance). ON DELETE CASCADE.
  - `testId` — string, denormalized from Utterance for indexing and per-`testId` filtering.
  - `rawChatbotResponse` — JSON / text, the raw HTTP response body returned by the connector service for diagnostic purposes (captured regardless of whether the body validates against the contract schema). Per the 2026-05-29 reshape the field name is retained for cross-spec stability even though the connector service — not the chatbot — is what the harness directly observes; treat the value as "whatever bytes the connector service sent back." Nullable if the connector failed at the transport / response layer before returning a body.
  - `normalizedContract` — JSON, the Standard Evaluation Contract instance returned by the connector service (per `007 FR-003`) after harness-side validation against the bundled schema (per `006 FR-008`). Nullable if validation failed (the offending body remains in `rawChatbotResponse` for diagnosis).
  - `evaluationAgentId` — string, echoed from the agent's payload (per `008 FR-003`). For rows that failed before evaluation, populated from the Job's snapshotted `evaluationAgentId` so the column is never null on persisted rows.
  - `evaluationVerdict` — string, the agent's emitted verdict (per `008 FR-003` / `FR-004`). One of `pass` / `fail` / `warn`, or null if the row failed before evaluation.
  - `evaluationScores` — JSON array, the agent's emitted scores payload — ordered collection of `{parameter_name, score, reasoning}` entries per parent `FR-008a` / `008 FR-005`. Nullable if the row failed before evaluation.
  - `metadata` — JSON object, the agent's emitted free-form `metadata` (per `008 FR-003`). Nullable if the row failed before evaluation.
  - `harnessAnnotations` — JSON, the harness-derived annotation block per `008 FR-005a` (e.g., `unexpected_score_dimensions`). Nullable / empty object when nothing to annotate. Distinct from `metadata` (which is agent-owned).
  - `errorStatus` — string, nullable. Null when the row succeeded end-to-end. When non-null, one of: `failed` (the orchestrator invoked the connector on this row but the row didn't complete cleanly — see `errorStage` for where it broke), `cancelled` (the row was cancelled before the orchestrator could invoke the connector on it; see `FR-003a` for the stub-creation rule).
  - `errorStage` — string, nullable. Null when the row succeeded. When non-null, one of the nine values defined by the canonical enum in `012`'s 2026-05-29 Reshape clarification (per `012 FR-012`): `connector_transport`, `connector_response`, `connector_normalization`, `connector_auth`, `evaluator_transport`, `evaluator_response`, `evaluator_result`, `evaluator_auth`, `password_lookup`. (The earlier draft of this field defined a three-value enum `connector` / `normalization` / `evaluation`; that taxonomy was superseded by the reshape's finer set. Cross-spec references to the old three values should be read as the prefix-matching group in the new enum: `connector` → `connector_*`, `normalization` → `connector_normalization`, `evaluation` → `evaluator_*`. The `password_lookup` stage has no legacy equivalent — the in-memory password store didn't exist in the pre-reshape design.)
  - `errorDetails` — text, nullable. Free-form error detail captured by the orchestrator for failed rows. Distinct from `Job.errorDetails` (which is a job-level error sink populated only when the Job's terminal status is `failed`, per `FR-001`).
  - `evaluationTimestamp` — datetime, ISO-8601. For successful rows, the value the agent emitted (per `008 FR-003`); for rows that failed before reaching the agent or were cancelled-before-process, the moment the harness recorded the terminal per-row state. This is the canonical timestamp for the EvaluationResult row; there is no separate harness-side persistence timestamp.
- **FR-001a**: The data layer MUST define a **ConnectorRegistration** entity carrying at minimum:
  - `connectorId` — primary key, harness-assigned immutable string (UUID or display-name-slug + uniquifier per `013`). Once assigned, never changes; once a registration is hard-deleted, the id is NEVER recycled (per `013 FR-020`).
  - `displayName` — string, NOT NULL, tester-supplied via `013`'s CRUD form. Not constrained to be unique; the wizard disambiguates by appending `connectorId` tail (per `013`'s display rules).
  - `description` — string, nullable, tester-supplied.
  - `endpointUrl` — string, NOT NULL, the URL of the remote connector service. Validated as syntactically well-formed `http://` or `https://` at write time per `013 FR-004`.
  - `authDescriptor` — JSON, the auth mode and credential structure per `013 FR-005`. Credential subfields (bearer token, api-key-header value, basic password) are encrypted at rest per `FR-008` of this spec. Plaintext-cleartext subfields (`mode`, `api-key-header` name, basic username) remain in plaintext.
  - `timeoutSeconds` — integer, per-row HTTP timeout in seconds. Plan-defined valid range; default 30 (per `013 FR-002`).
  - `expectsPerRowPassword` — boolean, NOT NULL, default `false`. When `true`, the wizard and CSV upload module (`011`) require a populated `password` column for every row; the orchestrator (`012`) forwards the per-row password in connector HTTP body.
  - `archived` — boolean, NOT NULL, default `false`. Soft-delete flag per `013 FR-014`. Archived registrations do NOT appear in the wizard's Step 3 dropdown but MAY appear in the registry-management UI's `Archived` / `All` filter.
  - `createdAt` — datetime, ISO-8601, set at registration creation.
  - `updatedAt` — datetime, ISO-8601, bumped on every edit / archive / restore operation.
  - `archivedAt` — datetime, nullable. Null when `archived == false`; set when `archived` flips to `true`; cleared (or paralleled by a `restoredAt` field — plan-level) when restored.
  
  All fields except `connectorId`, `createdAt`, and `archived` are mutable via `013`'s CRUD operations. `connectorId` is immutable from creation. `createdAt` is immutable from creation. `archived` is mutable (Archive / Restore). The full record is snapshotted onto each Job at job-creation time per `FR-001`'s `connector*` fields.
- **FR-001b**: The data layer MUST define an **EvaluationAgentRegistration** entity carrying at minimum:
  - `evaluationAgentId` — primary key, harness-assigned immutable string (same pattern as `ConnectorRegistration.connectorId`). Never recycled.
  - `displayName` — string, NOT NULL, tester-supplied via `014`'s CRUD form.
  - `description` — string, NOT NULL (evaluator descriptions are operationally important per `014 FR-002`).
  - `endpointUrl` — string, NOT NULL.
  - `authDescriptor` — JSON, same shape and encryption rules as `ConnectorRegistration.authDescriptor`.
  - `timeoutSeconds` — integer. Default 60 (evaluators typically take longer than connectors per `014 FR-002`).
  - `declaredScoringDimensions` — JSON array of strings, ordered. MAY be empty array (for purely-verdict-based evaluators). Names are trimmed of whitespace on save per `014 FR-008`.
  - `archived` — boolean, NOT NULL, default `false`. Same soft-delete semantics as `ConnectorRegistration.archived`.
  - `createdAt`, `updatedAt`, `archivedAt` — same semantics as `ConnectorRegistration`.
  
  Snapshotted onto each Job at job-creation time per `FR-001`'s `evaluator*` / `evaluationAgent*` fields.
- **FR-003a**: When a Job transitions from `cancelling` to terminal `cancelled` (per parent `FR-024`'s soft-cancel sequence), the data layer MUST create an **EvaluationResult stub** for every Utterance belonging to the Job that does NOT yet have an EvaluationResult. Each stub MUST carry:
  - `errorStatus = "cancelled"` (per `FR-003`'s enum).
  - `errorStage = null` (the row was never invoked; there is no failure stage).
  - `null` for `rawChatbotResponse`, `normalizedContract`, `evaluationVerdict`, `evaluationScores`, `metadata`, `harnessAnnotations`.
  - `evaluationTimestamp` = the moment the stub is written (i.e., the moment of `cancelling → cancelled` transition).
  
  Stub creation MUST be atomic with the Job's status transition — either every queued Utterance gets a stub AND the Job's status flips to `cancelled`, or neither happens. After the transition completes, every Utterance in the Job MUST have exactly one EvaluationResult (whether real or stub), making EvaluationResult the single source of truth for per-row terminal state. **Note:** stub creation runs ONLY on the `cancelling → cancelled` transition. The orphan-reconciliation path (`012 FR-002`) transitions orphaned `cancelling` Jobs to `failed` (not `cancelled`) and does NOT create stubs; any rows that were neither processed nor stubbed before the harness crash remain absent from the EvaluationResult table for that Job, mirroring any other `failed` Job's incomplete-processing state.
- **FR-004**: *(Removed in Round 4 — see `Clarifications`. Previously defined a `TesterFeedback` entity supporting the per-row thumbs-up/down feature. The feature was removed entirely; this entity is not part of the v1 data model.)*

#### Snapshot immutability

- **FR-005**: The data layer MUST enforce that the following Job fields are **immutable past the `draft` status**: `connectorId`, `connectorName`, `connectorEndpointUrl`, `connectorAuthDescriptor`, `connectorTimeoutSeconds`, `connectorExpectsPerRowPassword`, `evaluationAgentId`, `evaluationAgentName`, `evaluatorEndpointUrl`, `evaluatorAuthDescriptor`, `evaluatorTimeoutSeconds`, `evaluatorDeclaredScoringDimensions`, `totalUtteranceCount`, `harnessVersion`, `sourceCSVFilename`. Any write to these fields when the Job's current `status` is NOT `draft` MUST be refused with an actionable error. Additionally, `createdBy` and `createdAt` are **immutable from the moment of Job creation** (not just past `draft`) — there is no point in the lifecycle at which they should change.
- **FR-006**: The data layer MUST enforce that the following Utterance fields are **immutable past the parent Job's `draft` status**: `utteranceText`, `rowIndex`, `testId`, `utteranceId`. (`jobId` is also immutable, trivially, since changing it would re-parent the row.)
- **FR-007**: The data layer MUST NOT enforce immutability on runtime-state fields: `Job.status`, `Job.startedAt`, `Job.completedAt`, `Job.processedCount`, `Job.failedCount`, and the entire EvaluationResult table. These are expected to change over the Job's lifecycle.
- **FR-007a**: The data layer MUST enforce parent `001 FR-027`'s registered-selection gate at the `draft → queued` transition (defense-in-depth, in case the wizard's enforcement at Step 3 / Step 4 is bypassed). The transition MUST be refused with an actionable error when ANY of the following hold: (a) `Job.connectorId` is null or empty; (b) `Job.evaluationAgentId` is null or empty; (c) the snapshotted `Job.connectorId` does not currently resolve to an active (`archived = false`) `ConnectorRegistration` per `FR-001a`; (d) the snapshotted `Job.evaluationAgentId` does not currently resolve to an active (`archived = false`) `EvaluationAgentRegistration` per `FR-001b`. This complements `FR-005`'s immutability rule (which gates post-`draft` writes) with a gate on the transition itself. The wizard MUST enforce the same conditions at Step 3 / Step 4 (per `003 FR-007` / `FR-010`) and at Step 5's Start Job control (per `003 FR-015`); the data-layer enforcement here is the backstop.

#### Encryption at rest (config-level secrets only)

- **FR-008**: Credential subfields within `authDescriptor` (whether on the Job's snapshotted `connectorAuthDescriptor` / `evaluatorAuthDescriptor` or on the live `ConnectorRegistration` / `EvaluationAgentRegistration` records) MUST be encrypted at rest using the harness's existing machine-local symmetric key utility (Module 4 `FR-013`–`FR-017`, parent `FR-023a`). This module does NOT introduce its own encryption utility; it consumes Module 4's. The encryption boundary is per-credential-subfield, not whole-descriptor; non-secret subfields (`mode`, `api-key-header` name, basic-auth `username`) remain in plaintext for readability and queryability. The same ciphertext that is encrypted on the registration is copied verbatim into the Job's snapshot (the wizard does NOT re-encrypt — per `003 FR-009`); both rows decrypt with the same machine-local key at HTTP-call time.
- **FR-009**: The data layer MUST NEVER attempt to encrypt or store the per-row CSV `password` value, even in encrypted form. Per parent `FR-010`, the per-row password is in-memory only; no Utterance column, no separate sidecar table, no audit log captures it. This is verifiable by inspecting the database file's bytes for any known-distinctive password value (must produce zero matches).

#### Cascading delete + status-gated delete

- **FR-010**: Deletion of a Job MUST cascade to delete every Utterance with matching `jobId` and every EvaluationResult linked to those Utterances (via `utteranceId`). The cascade MUST be atomic — either all rows are deleted or none.
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
- **FR-020**: Cross-entity writes that conceptually belong together (e.g., writing an EvaluationResult while incrementing the parent Job's `processedCount`) MUST be performed in a single atomic transaction — either both writes commit or neither does. A harness crash mid-transaction MUST leave the database in its pre-transaction state.
- **FR-021**: The data layer MUST enforce the documented uniqueness and referential-integrity constraints (unique `utteranceId`, unique `resultId` per `utteranceId`, valid foreign-key references). Violations MUST be refused at the boundary, not silently overwritten or ignored.
- **FR-022**: The data layer MUST be the single source of truth for persisted state. Modules MUST NOT bypass it to read or write the database file directly.

### Key Entities *(include if feature involves data)*

- **Job**: The container for one regression run. See `FR-001` for the full field list. Carries lifecycle state, the snapshotted connector + evaluator configuration (endpoint, auth, timeout, expects-per-row-password / declared scoring dimensions), aggregate counters, and the harness version that created it.
- **Utterance**: One persisted row from the source CSV (one per CSV data row at job-creation time). See `FR-002`. Stores the input data minus `password`.
- **EvaluationResult**: The per-row trace of what happened when the orchestrator processed an Utterance — connector output, normalized contract instance, evaluator output, error state. See `FR-003`. At most one per Utterance.
- **ConnectorRegistration**: A persisted record describing a remote connector service known to the harness, managed by the CRUD module `013`. See `FR-001a`. Snapshotted onto each Job at job-creation time.
- **EvaluationAgentRegistration**: A persisted record describing a remote evaluator service known to the harness, managed by the CRUD module `014`. See `FR-001b`. Snapshotted onto each Job at job-creation time.
- **Schema Version**: A single-row table managed by the migration mechanism only. Tracks the schema generation the database file currently conforms to. Application modules do not read or write this directly.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Creating a draft Job, advancing it through the wizard, transitioning to `queued`, processing N rows, and reaching a terminal status results in: exactly one Job record, exactly N Utterance records, exactly N EvaluationResult records (mix of success and failure), and aggregate counters on the Job matching the rows — verifiable by counting rows in each table after an end-to-end test run.
- **SC-002**: For any started Job, mutating any field listed in `FR-005` or `FR-006` is observably refused — verifiable by attempting the mutation and inspecting the data-layer's error response.
- **SC-003**: A registry edit to a connector or evaluator that a started Job snapshotted does NOT change the Job's snapshot — verifiable by mutating the registry between Job creation and Job read, and confirming the snapshot's persisted value remains the original.
- **SC-004**: No persisted byte of the database file contains a per-row CSV password value, encrypted or otherwise — verifiable by inserting a known-distinctive password (e.g., `"DEADBEEF-PWD-12345"`) into a job's CSV, running the job to completion, and grepping the database file for that exact string (must produce zero matches).
- **SC-005**: Credential subfields within the Job's snapshotted `connectorAuthDescriptor` and `evaluatorAuthDescriptor` (and within the live `ConnectorRegistration.authDescriptor` / `EvaluationAgentRegistration.authDescriptor`) are encrypted at rest — verifiable by inserting a known-distinctive credential (bearer token / api-key value / basic password), persisting the registration, snapshotting it onto a Job, and grepping the database file for that exact string (must produce zero matches). The same value MUST decrypt cleanly when the orchestrator constructs the auth header at HTTP-call time.
- **SC-006**: Deleting a Job in `draft`, `failed`, or `cancelled` status removes all its Utterances and EvaluationResults in a single atomic operation — verifiable by counting rows before and after the delete in each table.
- **SC-007**: Deleting a Job in `queued`, `running`, `cancelling`, or `completed` status is refused at the data layer — verifiable by enumerating each of the four non-deletable statuses and attempting deletion (the three deletable statuses `draft` / `failed` / `cancelled` are covered by `SC-006`).
- **SC-008**: After a simulated harness crash mid-transaction, the database file is queryable and contains either all writes from the in-flight transaction or none — verifiable by injecting a failure between two writes that belong to the same transaction and inspecting the data afterward.
- **SC-009**: A migration that fails partway leaves the database file at its pre-migration state — verifiable by deliberately introducing a failure in a test migration and inspecting the schema version and table contents afterward.
- **SC-010**: Starting the harness against a database file at a newer schema version than the harness knows produces a clear "database newer than harness" error before any read or write — verifiable by manually writing a future schema-version value into the version table and attempting startup.
- **SC-011**: The default database location is `~/.harness/data.db`; the location is overridable by configuration; if the configured location's parent directory does not exist, the harness creates it on first run — verifiable by running the harness with and without the configuration knob set and against a non-existent parent directory.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, single-process, local-only. Concurrency from multiple harness processes against the same database file is out of scope for v1.
- The encryption utility for stored auth credentials is defined and provided by Module 4 (`specs/007-connector-framework` → `FR-013`–`FR-017`); this module consumes it but does NOT redefine or duplicate it.
- The per-row CSV `password` is governed by parent `FR-010`: in-memory only, never persisted. The Module 2 input's `encryptedPassword` field on Utterance is intentionally absent (`Clarifications` Q1). Job resumability for credential-bearing rows after restart remains forbidden by parent `FR-010a`.
- The Job status enum is the parent's canonical seven-value set (`Clarifications` Q2). `CompletedWithErrors` is a UI label per Module 13, not a stored value.
- Implementation choices for the database engine, ORM library, migration framework, and repository pattern shape are plan-level (the user mentioned SQLAlchemy / SQLite / Alembic; this spec describes data shape and persistence behavior, leaving the binding to the plan).
- The raw uploaded CSV file is NOT retained on disk as a binary artifact — only the persisted rows (Utterances) capture its contents minus `password`. The `Job.sourceCSVFilename` field captures only the filename string for tester-facing display.
- "Globally unique within the harness installation" means UUID-style ids that don't collide across jobs. Cross-installation uniqueness is out of scope.
- "Cascade delete" extends through Job → Utterance → EvaluationResult. There is no other multi-level cascade in v1's data model.
- Schema versioning starts at version `1` with the initial harness release. Future releases publishing a v2 schema MUST also publish a v1→v2 migration before they ship.
- The shape of JSON-valued snapshot columns (`connectorAuthDescriptor`, `evaluatorAuthDescriptor`, `evaluatorDeclaredScoringDimensions`, `evaluationScores`, `metadata`, `harnessAnnotations`, `rawChatbotResponse`, `normalizedContract`) is governed by the producing module's spec (`007` / `008` for descriptors and contract; `008` for scoring dimensions and result fields; `006` for the contract schema). The data layer just stores valid JSON. Post-2026-05-29 reshape, there is no "connector-declared config JSON Schema" concept — connector and evaluator services no longer ship a config schema; the registration's column set is fixed by `FR-001a` / `FR-001b`.
- **Snapshot field naming convention (asymmetric, intentional)**: The connector-side snapshot fields on Job all use the `connector*` prefix (`connectorId`, `connectorName`, `connectorEndpointUrl`, `connectorAuthDescriptor`, `connectorTimeoutSeconds`, `connectorExpectsPerRowPassword`). The evaluator-side snapshot fields use `evaluationAgent*` for the identity / display-name fields (`evaluationAgentId`, `evaluationAgentName`) — matching the registry entity name `EvaluationAgentRegistration` — and `evaluator*` for the configuration fields (`evaluatorEndpointUrl`, `evaluatorAuthDescriptor`, `evaluatorTimeoutSeconds`, `evaluatorDeclaredScoringDimensions`). This asymmetry is the canonical naming, propagated to `001` (Key Entities), `004 FR-003` (Metadata Panel), `005 FR-005` (export job-metadata block), and `012 FR-004` (orchestrator snapshot read). Downstream consumers MUST use the exact names as written here.
- The `harnessVersion` field stamps the harness's own version (whatever the project's release tag is at the moment of job creation). The mapping between Python package version, Git tag, and the value stored in `harnessVersion` is plan-level.
