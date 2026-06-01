# Feature Specification: CSV Upload & Validation Service (Module 8)

**Feature Branch**: `011-csv-upload-validation`

**Created**: 2026-05-29

**Last Amended**: 2026-05-29

**Status**: Draft

**Input**: User description: "Module 8 — CSV Upload & Validation Service. A service that handles upload, structural validation, parsing, and Utterance-row persistence of CSV test files. Validates UTF-8 encoding, required `utteranceText` / `testId` / `password` columns, non-empty values; parses rows into Utterance entities (system-generated UUID `utteranceId`, FK to jobId, original text, row index); updates the Job's `totalUtteranceCount`. Rejects uploads to non-draft jobs and enforces a configurable max file-size limit. Returns a summary response."

> **Parent context**: This module is the producer of `Utterance` rows for the data layer (Module 2 = `specs/009-data-model-persistence`) and the consumer of the CSV the wizard's Step 2 (`specs/003-job-creation-wizard` → `FR-005`) hands it. It is bracketed by parent `FR-002` (CSV schema rule) and parent `FR-003` (validation gate before job start). Parent-spec premises apply: single-user, no auth. Per parent `FR-010` and the user's `010 Q2` decision (re-confirmed in this spec's `Clarifications` Q1), passwords are **in-memory only, never persisted**, and the raw CSV file is **not retained** on disk in any form. The Module 8 input's directives to "encrypt and persist passwords on Utterance" and to "store the original uploaded CSV file as an immutable binary artifact" were explicitly NOT applied. Module 8 surfaces parsed passwords to the orchestrator (Module 10 = `012`) via an in-memory mechanism only. Module 8's "Module 2" reference maps to our `009-`; "system-generated UUID utteranceId" is consistent with `009 FR-002` and Module 6's `006 FR-002`; `rowIndex` is **1-based** per `009 R2 Q2`. The CSV column name is `utteranceText` (lock-step alignment across `001 FR-002`, `006 FR-002`, `009 FR-002` landed in this spec's session). The user's "Module 8" maps to our `011-` directory by the convention used for Modules 2/3/4/7 → 009/010/007/008. **Reshape note (2026-05-29):** With the connector framework now defining a remote HTTP service model (`007`), the **`password` column is no longer unconditionally required**. Whether a given upload must populate `password` depends on the **selected connector's `expectsPerRowPassword` flag** (declared on the `ConnectorRegistration` per `013`). When the flag is `true`, `password` is a required column and non-empty per row; when `false`, `password` is optional (the column MAY be present but is ignored; if absent entirely, the upload still proceeds). The orchestrator (`012`) consumes the in-memory password store only when `expectsPerRowPassword` is `true`; in the `false` case the store is not populated for that Job's rows. The per-row eviction discipline still applies whenever a password IS in the store.

## Clarifications

### Session 2026-05-29

- Q: Module 8 repeats the same three directives Module 3 already settled in `010 Q2` (persist encrypted passwords; retain raw CSV file as immutable binary; reference file in-place instead of copying). Are you reversing the just-made `010 Q2` decision? → A: **No — honor `010 Q2`.** Passwords stay in-memory only (parent `FR-010`); raw CSV file is NOT retained on disk (no in-place reference, no copy); Module 4's encryption utility remains scoped to config-level secrets only. Module 8 surfaces parsed passwords to downstream consumers (the orchestrator, Module 10) via an in-memory mechanism whose exact shape is plan-level. The Utterance entity does NOT acquire an `encryptedPassword` column. The Job entity does NOT acquire a file-path reference to the original CSV. Job-resumability for credential-bearing rows after a process restart remains forbidden by parent `FR-010a`. (This is the user's third consistent vote for the same answer in this session — the in-memory-only rule is settled.)

### Session 2026-05-29 (Round 2)

- Q: What happens when the tester re-uploads a CSV to a draft Job that already has Utterance rows (e.g., they went Back from Step 4 to Step 2 in the wizard)? → A: **Replace-on-upload.** The second upload atomically (a) deletes all prior Utterance rows for that Job (with cascade per `009 FR-010`), (b) clears prior in-memory password store entries for that Job per `FR-015`, then (c) applies the new file exactly as a fresh upload (validate, parse, persist new rows, repopulate the in-memory store, reset `Job.totalUtteranceCount` and `Job.sourceCSVFilename`). The whole replace-then-apply runs as a single atomic operation; failure at any point leaves the prior state intact. Matches `003 FR-019`'s "edits that logically invalidate later data discard that data" pattern.
- Q: When are entries in the in-memory password store cleared? → A: **Per-row eviction (primary) + Job-terminal backstop + process-exit clear (always).** Each (jobId, utteranceId) → password entry MUST be removed from the store immediately after the orchestrator's per-row connector HTTP call for that row returns — success or failure, doesn't matter. The Job-terminal backstop (clear all of the Job's remaining entries when the Job reaches `completed` / `failed` / `cancelled`) catches rows that were never invoked (e.g., cancelled-before-process rows from `009 FR-003a`). The process-exit clear is the final safety net. Tightest credential exposure window achievable without changing the in-memory-only model.

### Session 2026-05-29 (Reshape)

- Q: Is the `password` column unconditionally required in every uploaded CSV? → A: **No — conditional on the selected connector's `expectsPerRowPassword` flag.** Per the 2026-05-29 connector-framework reshape (`007`), each registered connector declares whether it expects a per-row password (managed in `013`'s CRUD UI). When `expectsPerRowPassword == true`, the upload MUST contain a `password` column AND every data row's `password` value MUST be non-empty — Module 8 rejects the upload otherwise. When `false`, the `password` column is optional (it MAY be present and is then preserved as metadata per `FR-008`, but it MAY also be entirely absent without causing validation failure). The wizard's Step 3 selection drives this; the wizard's Step-2/Step-3 coordination is per `003 FR-005` (authoritative) and the re-validation rule on connector-change is per `003 FR-018`. At commit time, Module 8 reads the selected connector's flag from the Draft Job's snapshot (per parent `FR-023` / `009`) — NOT from the live registry.
- Q: How does the in-memory password store behave for jobs against a connector with `expectsPerRowPassword == false`? → A: **The store is not populated for that Job's rows.** When `false`, Module 8 does not extract or stage any password values; the orchestrator (`012`) reads the same flag from the Job snapshot and omits the `password` field from each connector HTTP body. Per-row eviction is a no-op for these jobs (nothing to evict). Job-terminal backstop and process-exit clear MUST still run defensively.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload a valid CSV and create Utterance rows end-to-end (Priority: P1)

A tester on the wizard's Step 2 selects a well-formed CSV from their local filesystem and uploads it to the harness. The service reads the file, validates it has UTF-8 encoding, the required columns (`utteranceText` and `testId` always, plus `password` when the Draft Job's snapshotted connector has `expectsPerRowPassword == true`), and non-empty values per row. It generates a UUID `utteranceId` for each row, persists an Utterance entity per data row (the password column, if present, stays in memory only — NOT persisted), records the `Job.sourceCSVFilename` and `Job.totalUtteranceCount`, and returns a summary. The wizard advances to Step 3.

**Why this priority**: Without this, no job can be created. It is the MVP slice of Module 8 and the gating step between job creation (`003 FR-004`) and connector/evaluator configuration.

**Independent Test**: For a Job in `draft` status whose snapshotted connector has `expectsPerRowPassword == true`, prepare a 5-row CSV with header `utteranceText,testId,password` and known data (e.g., 2 distinct testIds, 1 utterance repeated under 2 testIds, no empty values). Submit it via the upload endpoint. Verify: (a) the response is a success summary indicating 5 utterances created, 0 warnings; (b) the Utterance table has exactly 5 rows linked to the jobId, each with a unique UUID and `rowIndex` 1–5; (c) the Job's `totalUtteranceCount` equals 5 and `sourceCSVFilename` equals the uploaded file's basename; (d) the SQLite database file contains zero bytes of the known password values when grepped (per `009 SC-004`). For a Job whose snapshotted connector has `expectsPerRowPassword == false`, repeat with a CSV that omits the `password` column entirely and verify the same outcomes (a)–(c) hold, plus (d) the in-memory password store remains unpopulated for this job's rows.

**Acceptance Scenarios**:

1. **Given** a CSV with N valid rows submitted for a Job in `draft` status, **When** Module 8 processes the upload, **Then** N Utterance rows are persisted with `jobId` matching the target Job, fresh UUID `utteranceId` values, `rowIndex` running 1..N, `utteranceText` matching `utteranceText` per row, `testId` matching `testId` per row, and NO persisted representation of `password` regardless of whether the CSV carried a `password` column.
2. **Given** the upload completes successfully, **When** the response is returned to the wizard, **Then** the response indicates the count of utterances created (N), the count of warnings (typically 0), and a status field indicating success. The wizard's Step 2 "Next" control becomes enabled (per `003 FR-005`).
3. **Given** the upload completes, **When** the Job is read from the data layer, **Then** `Job.totalUtteranceCount == N` and `Job.sourceCSVFilename` equals the uploaded file's basename (e.g., `"regression-2026-05.csv"`, NOT the absolute path).
4. **Given** the upload completes successfully, **When** the parsed `password` values are inspected post-upload, **Then** they are accessible to the orchestrator at job-execution time via an in-memory mechanism, but they appear nowhere in the persisted Utterance rows, nowhere in the database file's bytes, and nowhere in the harness's exports or logs (per parent `FR-010`).

---

### User Story 2 - Reject malformed CSV with actionable per-row errors (Priority: P1)

A tester uploads a CSV with structural problems — wrong encoding, missing required column, empty cells in required columns, malformed CSV syntax. Module 8 catches these at validation time, returns a clearly-structured error response naming the specific rows and columns at fault, and persists NOTHING (no Utterance rows, no `Job.totalUtteranceCount` mutation, no `sourceCSVFilename` mutation). The wizard's Step 2 stays put — Next does not arm.

**Why this priority**: Validation is what makes the upload step a contract. Without it, malformed CSVs would silently propagate corrupt rows into Utterance/EvaluationResult later. Equal-priority with US1 because both are required for the upload step to be trustworthy.

**Independent Test**: Submit three CSVs in sequence to a Job whose snapshotted connector has `expectsPerRowPassword == true`: (a) wrong-encoding CSV (e.g., UTF-16 BOM where UTF-8 is required), (b) CSV missing the `password` column, (c) CSV where row 3 has an empty `testId`. For each, verify: (i) the response is a validation-error structure naming the specific issue (encoding name, missing column name, or row/column path), (ii) the Utterance table for that jobId remains empty, (iii) Job.totalUtteranceCount remains 0 / unmutated, (iv) Job.sourceCSVFilename remains null / unmutated.

**Acceptance Scenarios**:

1. **Given** a CSV that is not valid UTF-8, **When** Module 8 attempts to decode it, **Then** the upload is rejected; the response names "encoding" as the failure category and identifies the encoding actually detected (or the position of the first invalid byte); no Utterance rows are persisted.
2. **Given** a CSV whose header row is missing one or more of the required columns (`utteranceText` and `testId` always, plus `password` when the snapshotted connector's `expectsPerRowPassword == true`), **When** Module 8 parses the header, **Then** the upload is rejected; the response names "missing required column(s)" with the specific column name(s); no rows are persisted.
3. **Given** a CSV where one or more data rows have empty values in a required column, **When** Module 8 parses the rows, **Then** the upload is rejected; the response includes one error entry per offending row with the row number (1-based) and the offending column name. No partial state is persisted — either every row is valid and all get persisted, or none does.
4. **Given** any upload that fails validation, **When** the response is returned, **Then** the response indicates failure unambiguously (e.g., a non-success status field and an `errors` array) and the wizard surfaces the per-row detail to the tester. The wizard's Next control remains disabled.

---

### User Story 3 - Reject upload when Job is not in `draft` status (Priority: P2)

The wizard's Step 2 should only invoke Module 8 when the parent Job is in `draft`. But the service still defends in depth: any upload request for a Job in any non-draft status (`queued`/`running`/`cancelling`/`completed`/`failed`/`cancelled`) is rejected at the service boundary with an actionable error naming the current status.

**Why this priority**: Belt-and-braces over the wizard's UI logic. Equal-priority with US4 because both are guardrails against bad state mutation.

**Independent Test**: For a Job in each of the six non-draft statuses, submit a valid CSV upload. Verify each is rejected with a status-violation error; the existing Utterance rows for that Job (if any) are unmodified; `Job.totalUtteranceCount` and `sourceCSVFilename` are unmodified.

**Acceptance Scenarios**:

1. **Given** a Job whose current status is NOT `draft`, **When** Module 8 receives an upload request for that jobId, **Then** the upload is rejected with an error naming the current status; no rows are persisted; the Job's state is unmutated.
2. **Given** a Job that transitions from `draft` to `queued` DURING an in-flight upload (race condition), **When** Module 8 attempts to commit the parsed Utterance rows, **Then** the commit is refused (per `009 FR-005`'s snapshot-immutability rules) and the entire upload is rolled back atomically.

---

### User Story 4 - Reject upload exceeding the configured max file size (Priority: P2)

The harness has a configurable max-file-size limit. An upload whose size exceeds the limit is rejected BEFORE the harness reads or parses the file contents (to avoid memory exhaustion on a runaway upload). The error response names the configured limit and the actual file size.

**Why this priority**: Defends against accidental or malicious oversized inputs. Equal-priority with US3.

**Independent Test**: Configure the limit to a low value (e.g., 1 MiB). Submit a 2 MiB CSV. Verify: rejected with a size-violation error; the response includes both the configured limit and the actual file size; no parsing occurred (verifiable via no Utterance rows and unchanged Job state).

**Acceptance Scenarios**:

1. **Given** a configured max-file-size limit of M bytes and an upload of N > M bytes, **When** Module 8 receives the upload, **Then** the upload is rejected with an error naming both M and N; the file is not read further beyond the metadata needed to determine its size.
2. **Given** a configured max-file-size limit of M bytes and an upload of N ≤ M bytes, **When** Module 8 receives the upload, **Then** the upload proceeds normally to validation.

---

### User Story 5 - Handle CSV encoding and parsing edge cases without data loss (Priority: P2)

Real CSVs in the wild have warts — UTF-8 BOM, embedded newlines inside quoted values, trailing blank lines, Unicode utterance content. Module 8 handles these cases robustly: BOM is stripped silently, quoted multi-line values are preserved end-to-end, trailing blank rows are skipped (with a warning rather than a failure), Unicode is round-tripped losslessly through the database.

**Why this priority**: Real testers will hit these cases on day one. Without robust handling, the spec's "5-minute first job" promise (`001 SC-001`) falls apart.

**Independent Test**: Submit a CSV that exercises every edge: BOM at start, one row with a quoted multi-line utterance, two trailing blank rows, and one utterance containing emoji and non-ASCII Unicode. Verify: (a) BOM is silently stripped, (b) the multi-line value is persisted byte-equal to the source, (c) the trailing blank rows are skipped with a warning entry in the summary response (not an error), (d) the Unicode utterance round-trips losslessly through the database.

**Acceptance Scenarios**:

1. **Given** a CSV that begins with a UTF-8 BOM (`﻿`), **When** Module 8 reads the file, **Then** the BOM is silently stripped before column-name parsing; no warning is needed.
2. **Given** a CSV where a data row's `utteranceText` value is a quoted multi-line string (RFC 4180-style escaping), **When** Module 8 parses, **Then** the resulting Utterance's `utteranceText` carries the full value with embedded newlines preserved.
3. **Given** a CSV that ends with one or more entirely-blank lines (empty rows after the last data row), **When** Module 8 parses, **Then** those blank lines are silently skipped (not treated as missing-value errors); the summary response includes a `warnings` entry naming the skipped-blank-row count.
4. **Given** a CSV whose values contain non-ASCII Unicode (emoji, accented characters, non-Latin scripts), **When** Module 8 persists Utterance rows, **Then** the value reads back from the database byte-equal to the input (lossless UTF-8 round-trip).

---

### Edge Cases

- An upload is submitted to a job that does not exist (bad jobId) — reject with a "job not found" error; the harness has no record of any such jobId so no state-mutation risk.
- The uploaded CSV has the required columns AND additional columns the harness doesn't know about — accept; the extra columns are preserved as per-row metadata (per `009 FR-002`'s "additional per-row metadata columns"). The exact storage shape (JSON blob vs. sibling table) is plan-level per `009 FR-002`.
- The uploaded CSV's data-row count is zero (header-only file) — reject with a "no data rows" error; the user got the structure right but supplied no work to do.
- The uploaded CSV has duplicate header column names — reject with a "duplicate column" error; ambiguity is not silently tolerated.
- The uploaded CSV has the required columns but their position varies (e.g., `password,testId,utteranceText` order) — accept; column position is irrelevant, the header row is the source of truth for column identity.
- The uploaded CSV's required-column NAMES have surrounding whitespace (e.g., `" utteranceText "` instead of `"utteranceText"`) — Module 8 SHOULD trim whitespace from header names before comparison; a `"utteranceText "` header MUST match the required `"utteranceText"`.
- The uploaded CSV uses a non-comma delimiter (semicolon, tab) — reject; v1 supports only comma-delimited CSVs. A plan-level enhancement could detect the delimiter, but it's out of scope for v1.
- The uploaded file path doesn't exist on the local filesystem — reject before reading with a "file not accessible" error.
- The uploaded file exists but is not readable (permission denied) — reject with a "file not readable" error.
- The CSV contains a row where the `password` value is exactly the string `[MASKED]` (the masking placeholder from `010 FR-013`) — accept; Module 8 does not interpret `[MASKED]` specially. If a tester accidentally re-uploaded a previously-exported (masked) file, the resulting job will fail at execution time when the connector receives the literal `[MASKED]` and the chatbot rejects it. Module 8 does not detect this.
- The CSV has very long `utteranceText` values (e.g., multi-paragraph user input) — accept; no size cap on individual cells in v1. Downstream UI/export modules handle truncation for display.
- Two concurrent uploads target the same draft jobId — the data layer (`009`) enforces atomic commits; one upload's rows will commit fully and the other will see a conflict. Plan-level which one wins.
- The upload submission and the Job's `cancelling → cancelled` transition race — the Job's status change MUST be detected before the upload commits; if the Job is no longer `draft` at commit time, the upload is rolled back per US3 scenario 2.
- A CSV row has more or fewer columns than the header — reject with a "row N has C columns, expected H" error.
- The harness process restarts between upload completion and Job start — the persisted Utterance rows survive, BUT the in-memory password store is gone. The Job is left in `draft` with rows persisted but no credentials available; per parent `FR-010a`, the tester must re-upload the CSV to continue. (Module 8 does not orchestrate the re-upload UX; that's the wizard's responsibility per `003`.)

## Requirements *(mandatory)*

### Functional Requirements

#### Upload + size gate

- **FR-001**: The service MUST accept upload requests carrying: (a) a target `jobId`, (b) a reference to a CSV file (local path or uploaded stream — the API surface is plan-level), (c) sufficient identification for the tester's session (in v1 there's no auth, so this is just process context). The service MUST validate the inbound `jobId` exists in the data layer and the file is reachable before any further work.
- **FR-002**: The service MUST enforce a **configurable maximum file size limit**. The limit's value (in bytes) MUST be a harness configuration knob (with a sensible default — plan-level, e.g., 50 MiB). The size check MUST happen BEFORE the file is read/parsed (the service inspects metadata, not content, to determine size). An upload exceeding the limit MUST be rejected with an error response naming both the configured limit and the actual file size; the file MUST NOT be read further.
- **FR-003**: The service MUST reject uploads for jobs whose current status is NOT `draft`. The check MUST be performed before reading the file contents AND re-validated at commit time (per `009 FR-005`'s snapshot-immutability rules). The rejection response MUST name the current status.

#### Decoding + structural validation

- **FR-004**: The service MUST decode the file as UTF-8. A leading UTF-8 BOM MUST be silently stripped before header parsing. Files that are not valid UTF-8 MUST be rejected with an error naming "encoding" as the failure category and identifying the position or nature of the encoding violation.
- **FR-005**: The service MUST parse the file as comma-delimited CSV (RFC 4180-style). Non-comma delimiters (semicolon, tab) MUST be rejected as unsupported in v1; the error response MAY hint at the expected delimiter. Quoted values containing embedded newlines or embedded commas MUST be preserved end-to-end (lossless RFC-4180 parsing).
- **FR-006**: The service MUST recognize the following required header columns: `utteranceText`, `testId`. The `password` column is **conditionally required**: required when the upload targets a Draft Job whose snapshotted connector's `expectsPerRowPassword == true`, optional otherwise (see the 2026-05-29 Reshape clarification). Header-name comparison MUST be case-sensitive but MUST trim surrounding whitespace from each header before comparison (e.g., `" utteranceText"` matches `"utteranceText"`). Missing required columns MUST be rejected with an error naming each missing column. Duplicate header columns MUST be rejected. If `password` is present in the header but the snapshotted connector's `expectsPerRowPassword == false`, the column is accepted and its values are preserved as per-row metadata per `FR-008`; if it is present AND the flag is `true`, it's a required column subject to `FR-009`'s non-empty validation.
- **FR-007**: The required columns MAY appear in any order in the CSV header — column position is irrelevant; column identity comes from the header row only.
- **FR-008**: Additional columns beyond the required three MUST be accepted. Their values MUST be preserved as per-row metadata on the Utterance entity (per `009 FR-002`'s "additional per-row metadata columns" — concrete storage shape is plan-level).

#### Per-row validation

- **FR-009**: For each data row, the service MUST validate that the required columns all have **non-empty** values. The required columns are `utteranceText` and `testId` always, plus `password` when the snapshotted connector's `expectsPerRowPassword == true` (per `FR-006`'s conditional requirement). Whitespace-only values count as empty. Any row with one or more empty required values MUST cause the entire upload to fail with an error response listing one entry per offending row (with 1-based row number and the offending column name(s)).
- **FR-010**: The service MUST validate that every data row has exactly the same column count as the header. Rows with too many or too few columns MUST cause the upload to fail with an error naming the offending row and the expected vs. observed column count.
- **FR-011**: Entirely-blank trailing lines (rows whose every cell is empty) MUST be silently skipped — they MUST NOT be counted as data rows and MUST NOT trigger validation errors. The summary response MUST include a warning entry naming the count of skipped blank rows.
- **FR-012**: The service MUST NOT perform any validation of `testId` / `password` against any external system. Validation is purely structural — column presence and non-emptiness. If credentials are wrong, the connector will surface that at execution time per `007 FR-003` and parent `FR-017`'s per-row failure mechanism.

#### Per-row persistence + counts

- **FR-013**: For every valid data row, the service MUST create one Utterance entity in the data layer (`009 FR-002`) carrying:
  - `utteranceId` — system-generated UUID v4 (or equivalent globally-unique identifier per `006 FR-002`).
  - `jobId` — the upload's target jobId (FK).
  - `utteranceText` — the row's `utteranceText` value, byte-equal to the source.
  - `rowIndex` — 1-based row index in the source CSV, counting only data rows (header is row 0, first data row is `rowIndex = 1`). Per `009 FR-002`.
  - `testId` — the row's `testId` value.
  - Additional metadata columns — preserved as per-row metadata per `FR-008`.
- **FR-014**: The service MUST NOT persist the row's `password` value in any form on the Utterance entity, in the database, or in any other persistent store. The Utterance entity MUST NOT carry an `encryptedPassword` column. This is the operational form of parent `FR-010`.
- **FR-015**: When the upload's target Draft Job has a snapshotted connector with `expectsPerRowPassword == true`, the service MUST surface the parsed `password` values to the orchestrator (`012`) via an **in-memory mechanism** — a process-scoped store keyed by `(jobId, utteranceId) → password` is the canonical pattern; the exact shape (function call, in-process service object, DI binding) is plan-level. The store MUST NOT be backed by disk. The store MUST be inaccessible to non-harness processes. When `expectsPerRowPassword == false`, the store MUST NOT be populated for this Job's rows (there is no password to stage).

  **Lifecycle rules** (in order of expected effect on each entry):

  - **Per-row eviction (primary)** — The orchestrator (`012`) MUST remove a row's `(jobId, utteranceId)` entry from the store **immediately after** its connector HTTP call for that row returns, regardless of whether the call succeeded or failed (per `012 FR-011` step 3). The entry's password MUST NOT be retained for retry, comparison, or any subsequent use.
  - **Job-terminal backstop** — When a Job transitions to `completed` / `failed` / `cancelled`, the store MUST clear all remaining entries keyed by that Job's `jobId`. This covers rows that were never invoked (e.g., cancelled-before-process rows per `009 FR-003a`) and is the safety net if per-row eviction misses any.
  - **Process-exit clear (always)** — On harness process shutdown, the entire store MUST be cleared. (For most languages this is automatic via garbage collection of process-scoped state; the spec just requires the harness MUST NOT serialize the store to disk on shutdown.)
  
  After these rules, any given `(jobId, utteranceId)` entry's lifetime in memory is bounded by: from upload completion to the orchestrator's per-row connector HTTP return — and never longer.
- **FR-016**: If the upload validates and parses successfully, the service MUST update the target Job's `totalUtteranceCount` to the count of valid data rows committed. Per `009 FR-005`, this field is immutable past `draft`; the data layer enforces the immutability check at commit time.
- **FR-017**: The service MUST update the target Job's `sourceCSVFilename` to the **basename** of the uploaded file (not the full path). E.g., for upload path `/Users/alice/Documents/regression-may.csv`, store `sourceCSVFilename = "regression-may.csv"`. This is the only persisted reference to the original file; per `010 FR-011`, the file content itself is NOT retained.
- **FR-018**: The persistence of Utterance rows + Job counter updates + filename update + in-memory password store population MUST be atomic — either all of (a) all N Utterance rows persisted, (b) `Job.totalUtteranceCount = N`, (c) `Job.sourceCSVFilename = <basename>`, (d) when the snapshotted connector's `expectsPerRowPassword == true`, the in-memory password store contains exactly the N (jobId, utteranceId) → password entries for the new rows (when `false`, the store remains unchanged for this Job per `FR-015`), all commit together, OR none of them does. Partial state from a failed upload MUST NOT leak into the data layer OR into the in-memory password store.
- **FR-018a**: When the upload targets a draft Job that **already has Utterance rows** from a prior successful upload (i.e., the tester re-uploads via wizard Back navigation or equivalent), the operation MUST execute as **atomic replace**: (a) delete all prior Utterance rows belonging to the Job (cascade per `009 FR-010` removes their EvaluationResults too), (b) clear all prior in-memory password store entries keyed by the Job's `jobId`, (c) apply the new upload's validation + parsing + persistence per `FR-013`–`FR-018`. The combined delete-then-apply MUST be a single atomic transaction; failure at any point leaves the prior state intact and surfaces an actionable error. There is no "append" mode; a second upload always replaces. This matches `003 FR-019`'s "edits that logically invalidate later data discard that data" pattern.

#### Response shape

- **FR-019**: On successful upload, the service MUST return a summary response carrying at minimum: (a) a success status indicator, (b) the count of Utterance rows created, (c) the count of distinct `testId` values seen across the rows (per `003 FR-006`'s "distinct-testId count" requirement), (d) an array of warnings (e.g., skipped-blank-row count). The exact response format (JSON shape, HTTP status) is plan-level; the spec only requires the named fields are present.
- **FR-020**: On validation failure, the service MUST return a structured error response carrying at minimum: (a) a failure status indicator, (b) a per-error array where each entry carries the error category (encoding / missing-column / empty-value / row-column-mismatch / file-not-accessible / size-exceeded / job-not-draft / etc.), the affected row number (1-based, when applicable), the affected column name (when applicable), and a human-readable description. The response MUST be detailed enough for the wizard's Step 2 UI to render per-row error messages directly to the tester (per `003 FR-005`).

### Key Entities *(include if feature involves data)*

- **Upload Request** *(transient)*: An inbound upload bundle carrying jobId + file reference + tester session context. Lives only for the duration of one upload attempt.
- **CSV Parse Result** *(transient, in-memory)*: The intermediate state between "file read" and "Utterance rows committed". Carries: the validated header row, an ordered list of parsed data rows (each with `utteranceText` / `testId` / `password` (when present per the conditional rule) / extra-metadata), and a warnings list. Lives only for the duration of one upload attempt; discarded after commit (the `password` values, when present, transition into the in-memory password store per `FR-015`).
- **In-Memory Password Store** *(process-scoped, plan-level shape)*: A process-resident keyed lookup that maps `(jobId, utteranceId) → password` for the lifetime of the harness process (or shorter, on Job completion). The orchestrator (`012-job-execution-engine`) reads from this store at per-row execution time per `012 FR-011` step 1. NEVER backed by disk. NEVER visible to non-harness processes. The exact implementation (Python dict in a service object, async-safe shared state, etc.) is plan-level.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A 100-row CSV with valid structure uploads and creates exactly 100 Utterance rows linked to the target Job, with `rowIndex` running 1..100, in under 5 seconds on a typical tester laptop — verifiable by automated test against a fixture CSV.
- **SC-002**: A CSV that violates ANY validation rule (encoding, missing column, empty value, row-column mismatch) is rejected with a per-error array; no Utterance rows are persisted; `Job.totalUtteranceCount` remains at its pre-upload value — verifiable by attempting each invalid case and inspecting the database.
- **SC-003**: A CSV exceeding the configured max-file-size limit is rejected BEFORE its content is read — verifiable by attempting an oversized upload and confirming (a) the rejection response carries the configured limit and the actual size, (b) no file-content was loaded into memory beyond what's needed for the metadata size check.
- **SC-004**: An upload for a Job in any non-draft status is rejected with an actionable error; the target Job's state is unmutated — verifiable by attempting an upload to a Job in each of the six non-draft statuses.
- **SC-005**: After a successful upload, the SQLite database file contains zero bytes of the uploaded passwords' plaintext values — verifiable by inserting a known-distinctive password (e.g., `"DEADBEEF-PWD-12345"`) in a CSV row and grepping the database file post-upload for that exact string (must produce zero matches). Identical to `009 SC-004` but reaffirmed here.
- **SC-006**: After a successful upload against a Job whose snapshotted connector has `expectsPerRowPassword == true`, the parsed `password` values are reachable to the orchestrator via the in-memory mechanism and NOT reachable from any other surface (no exports, no UI, no logs, no database file) — verifiable by a test that exercises the orchestrator's read path AND grep-tests each non-orchestrator surface for the known-distinctive password value.
- **SC-007**: A CSV containing entirely-blank trailing rows is accepted; the count of skipped blank rows appears as a warning in the summary response; the Utterance row count matches the count of non-blank data rows — verifiable by submitting a fixture CSV with N data rows + K trailing blank rows and observing the response.
- **SC-008**: A CSV containing UTF-8 BOM, embedded newlines in quoted values, and non-ASCII Unicode in `utteranceText` is parsed losslessly — verifiable by submitting a fixture and confirming the persisted `utteranceText` round-trips byte-equal to the input.
- **SC-009**: `Job.sourceCSVFilename` after a successful upload equals the basename of the uploaded file (not the absolute path) — verifiable by SQL inspection.
- **SC-010**: The upload is atomic — failing any single validation step or any commit step leaves the database in its pre-upload state (no partial Utterance rows, no partial counter update, no partial filename update) AND leaves the in-memory password store in its pre-upload state (no leaked entries from the failed upload) — verifiable by injecting a failure at various stages and inspecting both the database and the in-memory store afterward.
- **SC-011**: A re-upload to a draft Job that already has Utterance rows atomically replaces the prior rows (and password-store entries, when the snapshotted connector's `expectsPerRowPassword == true`) with the new upload's data — verifiable by uploading CSV `A.csv` to a draft Job (creating N_A rows; plus N_A store entries when the flag is true), then uploading `B.csv` to the same Job, then inspecting both the database and the in-memory store: exactly N_B rows (plus N_B store entries when the flag is true) from `B.csv`, with no traces of `A.csv` remaining anywhere.
- **SC-012**: For any row whose orchestrator connector HTTP call has returned (success or failure), no trace of its password remains in the in-memory store — verifiable by instrumenting the store with a probe that asserts no entry exists for any `(jobId, utteranceId)` whose connector HTTP call has returned.
- **SC-013**: For any Job in a terminal status, no trace of any of its rows' passwords remains in the in-memory store — verifiable by probing the store immediately after a Job-terminal transition for any of the three terminal statuses (completed, failed, cancelled).

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, no auth.
- Module 8 is invoked exclusively by the wizard's Step 2 (`003 FR-005`). There is no separate CLI / API surface for CSV uploads in v1.
- The persistence layer (Module 2 = `specs/009-data-model-persistence`) owns the Utterance entity definition; Module 8 just produces conforming rows. Data-layer rules (immutability past `draft`, cascade delete, no password persistence) apply automatically.
- The in-memory password store (`FR-015`) is implemented as a process-scoped data structure; the exact location (in a service object, on the Flask app context, etc.) is plan-level. Multi-process operation is out of scope per parent.
- Module 8 does NOT implement the wizard's UX layer (file picker, drag-drop, progress bar). It implements only the validation + parsing + persistence service that the wizard's Step 2 invokes.
- Module 8 does NOT implement encryption-at-rest for any field. Parent `FR-023a`'s config-secret encryption is Module 4's responsibility; the `password` here is in-memory only and never gets encrypted (no need).
- The configured max-file-size default (e.g., 50 MiB) is a plan-level choice. The spec only requires the value be a configuration knob and that the default be sensible for the parent's 1,000-row design target plus realistic per-cell payloads.
- The detection of "encoding violation" position (per `FR-004`) is best-effort; the spec only requires identifying the failure unambiguously, not pinpointing the byte offset.
- The `[MASKED]` literal showing up as a `password` value (e.g., from a re-uploaded export) is NOT detected — Module 8 treats it as opaque and the connector will surface authentication failure at execution time. Detecting this pattern is out of scope.
- Multi-delimiter CSV parsing (semicolon, tab) and Excel-specific quirks (e.g., the `Sep=` directive line) are out of scope for v1.
- Module 10 (Job Execution Engine, `specs/012-job-execution-engine`) is the in-memory password store's consumer per `012 FR-011`. The exact handoff mechanism is plan-level — Module 8 just produces, Module 10 consumes.
