# Feature Specification: Results Export Service (Module 14)

**Feature Branch**: `005-results-export`

**Created**: 2026-05-28

**Last Amended**: 2026-06-01

**Status**: Draft

**Input**: User description: "Module 14 — Results Export Service. A backend service and a UI control on the Job Detail View that lets the tester download a complete export of a job's results — every per-utterance trace plus job-level metadata — as a downloadable file in the format the tester selects (CSV, JSON, or both bundled in a zip). The export is generated on-demand at click time, always reflecting the latest persisted data. The download is delivered through the browser's standard file-download path."

> **Parent context**: This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Its UI control lives on the Job Detail View defined in `specs/004-job-detail-view/spec.md`. This spec extends parent `FR-015` (the harness-level export requirement) and re-uses parent `FR-009` (what's persisted per row) and parent `FR-008a` (the standardized scores payload shape). Parent-spec premises apply unchanged: single-user, no auth. Round 3 re-introduced `createdBy` in the job-metadata block (driven by Module 3). Round 5 then removed user-feedback (thumbs-up/down) from the harness entirely (see `Clarifications`); the export no longer contains any `userFeedback*` fields. The Module 14 input's mention of `CompletedWithErrors` as a status was resolved to its established meaning: a UI label for `status == completed && failed_count > 0`, not a real lifecycle state — the trigger gate is simply `status == completed`, with the broader scope clarified below.

## Clarifications

### Session 2026-05-28

- Q: Which job statuses should have the Download Results control available? → A: **Any job that has at least one persisted Utterance**. That is: `completed`, `failed`, `cancelled`, `running`, and `cancelling`. Jobs in `draft` or `queued` status have no rows and no export. For non-terminal jobs (`running`, `cancelling`), the export is a snapshot-at-click-time, partial-annotated — consistent with the Job Detail View's `FR-006a` source-CSV download semantics.
- Q: Module 14 says "two formats selectable by the user" but parent `FR-015` originally said "always a zip with both CSV and JSON". Which wins? → A: Selectable wins. The tester picks one of three forms at click time: CSV only, JSON only, or zip containing both. Parent `FR-015` was amended in lock-step (see parent `Clarifications`). The three-way choice is a small selector co-located with the Download Results control.
- Q: How is the file delivered to the tester's machine? → A: Standard HTTP browser download. The Flask process streams the export file body in the response; the browser's own Save dialog handles destination selection. The harness does NOT write to a server-side directory like `~/.harness/exports/`. The Module 14 input's mention of "a file picker or a known output directory" was resolved to browser-native download; no filesystem permissions, no path leakage, no destination management in the harness.

### Session 2026-05-28 (Round 2)

- Q: How is job-level metadata carried inside the CSV export? → A: **Repeated columns.** Every data row carries every job-metadata field as its own column alongside the per-row columns. Produces a single rectangular dataset that pandas / Excel / any standard CSV reader handles with zero special configuration. Concatenating exports from multiple jobs into one analysis is trivial. The "leading header section" and "two-files-in-a-zip" alternatives in `FR-007` are dropped.
- Q: When the tester clicks Download Results with a filter or search active on the Detail View's Results Table, does the export reflect the filter or all rows? → A: **Always all persisted rows of the job.** Filters and search on the Detail View are for in-page browsing only; the export is *about the job*, not *about the view*. Matches the 004 R3 precedent (Metadata Panel counts are job-level, not filtered) and parent `FR-015`'s "complete results export of any job" wording. Tester subsets the data post-export in their analysis tool if needed.

### Session 2026-05-29 (Round 3 — revision driven by Module 3)

- Q: Module 3 (`specs/010-tester-identity`) re-introduces an OS-derived `Job.createdBy` field. Does the export include it? → A: **Yes.** `createdBy` is added to the job-metadata block alongside `createdAt` / `startedAt` / `completedAt` / `status` / etc. Per-row records do NOT carry a per-row `createdBy` (the OS user is the same for the whole job). The pre-spec note in this spec's `Parent context` that said "no `createdBy` in job metadata" is reversed.

### Session 2026-05-29 (Round 4 — user-feedback feature removed)

- Q: Should the per-row user-feedback (thumbs-up/down) feature remain in v1 exports? → A: **No — removed entirely.** Driven by the parent-spec Round on user-feedback removal. The export no longer carries any `userFeedbackValue` / `userFeedbackTimestamp` / `userFeedbackBy` fields per row. User Story 3 (re-export after feedback) is removed. The `Results Export` entity no longer sources from `Tester Feedback` (which itself is removed from the data model). `SC-006` and the `FR-003` "reflect any feedback" wording are dropped.

### Session 2026-05-29 (Reshape)

- Q: The 2026-05-29 architecture reshape moved connectors and evaluators to remote HTTP services managed by CRUD modules (`013`/`014`), restructured the Job snapshot from opaque blobs into named columns, refined the `errorStage` enum from three values to nine, and removed the per-job tester-editable name override. What changes for the export? → A: **Six semantic adjustments, no UI control changes:**
  1. The job-metadata block's connector/evaluator name fields (`connectorName`, `evaluationAgentName`) are **verbatim snapshots** of the selected registration's `displayName` (per `001 FR-023` / `009 FR-001`) — not tester-supplied per-job values.
  2. The opaque `connectorConfig` / `evaluationAgentConfig` blob fields are replaced by the canonical named snapshot columns from `009 FR-001`: `connectorEndpointUrl`, `connectorAuthDescriptor`, `connectorTimeoutSeconds`, `connectorExpectsPerRowPassword` on the connector side; `evaluatorEndpointUrl`, `evaluatorAuthDescriptor`, `evaluatorTimeoutSeconds`, `evaluatorDeclaredScoringDimensions` on the evaluator side.
  3. The masking target within `authDescriptor` is precisely the **credential subfield** (bearer token / api-key value / basic-auth password ciphertext); cleartext subfields (`mode`, `headerName`, basic-auth `username`) display normally. Same rule as `004 FR-005`.
  4. The per-row block's `errorStage` field uses the **nine-value enum** per `012 FR-012` / `009 FR-003` (`connector_transport` / `connector_response` / `connector_normalization` / `connector_auth` / `evaluator_transport` / `evaluator_response` / `evaluator_result` / `evaluator_auth` / `password_lookup`), superseding the three-value taxonomy.
  5. The CSV's `evaluationScores` columns and the JSON's `evaluationScores` array order MUST follow the Job's snapshotted `evaluatorDeclaredScoringDimensions` order (per `008 FR-005a` + `004 FR-007b`) so cross-job concatenation and column alignment are stable across runs against the same registration.
  6. `harnessAnnotations` (per `008 FR-005a`) MUST be expressed visibly in the export — a dedicated JSON key, a CSV column, or equivalent — so the soft-warning data (e.g., `unexpected_score_dimensions`) reaches downstream analysis tools. Parallel to `004 FR-007c`'s in-UI visibility rule.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Export a completed job's results in the format I need (Priority: P1)

A QA tester finishes a regression run, opens the Job Detail View, picks an export format (CSV, JSON, or both-as-zip), and clicks Download Results. The harness generates the export on the fly from the latest persisted data and the browser saves the file. The tester opens the file in their tool of choice (spreadsheet for CSV, scripting for JSON) to triage or compare against a baseline.

**Why this priority**: This is the entire purpose of Module 14. Without it, the tester has no way to take results out of the harness. It is the MVP slice.

**Independent Test**: With a completed job containing at least 10 rows (mix of successful and `failed` per-row statuses across multiple `errorStage` values), click Download Results once for each of the three formats. Verify (a) each format produces a valid file that opens without error in its native tool, (b) every persisted row is represented exactly once, (c) the job-level metadata block is present and accurate, (d) credential subfields in `connectorAuthDescriptor` and `evaluatorAuthDescriptor` are fully masked, identical in form to the Detail View per `004 FR-005`.

**Acceptance Scenarios**:

1. **Given** a completed job with N persisted rows, **When** the tester picks CSV and clicks Download Results, **Then** the browser downloads a CSV file whose data rows correspond one-to-one to the job's N rows, with the canonical column set populated per row and the job-level metadata fields carried as repeated columns (per Round-2 clarification + `FR-007`).
2. **Given** the same job, **When** the tester picks JSON and clicks Download Results, **Then** the browser downloads a single JSON file with a top-level object containing the job-level metadata and a `rows` array of length N, each entry containing every persisted field for that row in nested (lossless) form.
3. **Given** the same job, **When** the tester picks "Both (zip)" and clicks Download Results, **Then** the browser downloads a single zip file containing one CSV and one JSON file, each independently equivalent to scenarios 1 and 2.

---

### User Story 2 - Export the partial state of a still-running job (Priority: P2)

A tester monitoring a long-running job wants a snapshot of what's been processed so far — to share with a colleague, to feed into a script that watches for regressions, or to triage a failure pattern emerging mid-run. They open the Job Detail View and click Download Results while the job is still in `running` (or `cancelling`). The harness produces an export reflecting only the rows persisted up to that moment, clearly annotated as a partial snapshot.

**Why this priority**: Real-world QA workflows include mid-run inspection. Equal-priority with the re-export story because both deliver value on top of P1 without depending on each other.

**Independent Test**: Start a long-enough job (so it's observably `running` for several seconds). Click Download Results once mid-run; verify the file (a) contains only rows persisted up to that moment, (b) is annotated as partial (filename suffix and/or inline marker naming the job's status and row count at click time), (c) is otherwise structurally valid for its format.

**Acceptance Scenarios**:

1. **Given** a job in `running` status with K rows persisted at click time, **When** the tester clicks Download Results, **Then** the export contains exactly K rows; the file is annotated as partial (filename includes `partial`, and inline marker names the job's status and row count at download time).
2. **Given** a job in `cancelling` status, **When** the tester clicks Download Results, **Then** the export reflects whatever has been persisted to that moment, also partial-annotated. The export's existence does not delay or interfere with the cancellation sequence.

---

### User Story 3 - Re-export to capture row data persisted after the prior download (Priority: P2)

A tester takes an early export of a running job, then later (after more rows complete) re-exports. The new file reflects the latest persisted state — no stale cache, no pre-generated artifact. (An earlier version of this story focused on feedback-edit re-export; the feedback feature was removed in Round 4 — see `Clarifications`.)

**Why this priority**: The Module 14 input is explicit that the link must remain available permanently and the export must always reflect the latest data. Equal-priority with the partial-snapshot story because both are independently testable on top of P1.

**Independent Test**: Start a job, take an export mid-run (partial), wait for more rows to complete, take an export again; verify the second file contains the additional rows.

**Acceptance Scenarios**:

1. **Given** a job whose first export the tester has already taken, **When** additional rows complete (or no rows complete) and the tester re-clicks Download Results, **Then** the second export reflects the latest persisted state — including any newly-persisted rows.
2. **Given** any export click, **When** the harness generates the file, **Then** the file is produced on-demand from the current persisted state — no cached artifact is reused, no pre-generated file exists.

---

### User Story 4 - Export the persisted state of a failed or cancelled job for triage (Priority: P3)

A tester investigating a job that failed mid-run (or was cancelled) wants to ship the entire trace to a colleague, file a bug, or feed it into a comparison script. They open the failed/cancelled job's Detail View and click Download Results. The export contains every row persisted before the failure or cancellation — including the per-row error detail and the stage at which each failing row failed.

**Why this priority**: Failed and cancelled jobs are exactly the jobs whose results are most worth sharing for triage. Lower priority than the running-snapshot story because it's the same mechanism plus terminal-state context — once US1 and US2 work, this story is largely a no-extra-effort beneficiary.

**Independent Test**: With one job in `failed` status (some rows succeeded, some failed at different stages) and one in `cancelled` status (some rows completed before cancel), click Download Results for each. Verify every persisted row appears, with the row's error stage and detail intact for `failed` rows.

**Acceptance Scenarios**:

1. **Given** a `failed` or `cancelled` job with persisted rows, **When** the tester clicks Download Results, **Then** the export includes every persisted row with its complete per-row state (input, raw response if reached, normalized contract if reached, evaluation result if reached, error stage and error detail for `failed` rows).
2. **Given** a `draft` or `queued` job (no rows persisted), **When** the tester views the Detail View, **Then** the Download Results control is hidden or disabled with an explanatory tooltip ("No rows to export yet"), and no export endpoint accepts requests for that job id.

---

### Edge Cases

- A job whose persisted row count is very large (at or near the parent spec's 1,000-row design target) is exported — the harness streams the response without buffering the entire payload in memory; the browser's download begins promptly.
- The tester clicks Download Results, then immediately clicks it again before the first download finishes (double-click or rapid retry) — both requests succeed and produce equivalent (or near-equivalent if rows arrived between them) snapshots; neither corrupts the other.
- The job is deleted (via the Detail View's Delete control, `004 FR-019`) between the Download click and the harness generating the file — the request fails with an actionable status code and an explanatory message; no partial or empty file is downloaded.
- The selected format is CSV and a row's `rawChatbotResponse` or `evaluationScores` contains characters that need CSV escaping (commas, quotes, newlines, embedded JSON) — the values are correctly quoted/escaped so the output is a valid CSV.
- The selected format is CSV and a row's normalized response text or per-score `reasoning` strings (inside `evaluationScores` entries) are multi-paragraph — newlines inside the value are preserved (CSV-quoted) so the value round-trips losslessly through a standard CSV reader.
- The selected format is JSON and the row's `rawChatbotResponse` is itself stringified JSON in the database — the export presents it as a nested JSON object (parsed back into structure), not as a quoted string, so the JSON file is hierarchical end-to-end. If parsing fails (corrupt persisted value), the field is included as a string with an `_unparseable: true` sibling marker.
- The snapshotted `connectorAuthDescriptor` / `evaluatorAuthDescriptor` carries an encrypted credential subfield — the export presents the credential subfield as a fully-masked placeholder per `FR-011`, while cleartext subfields (`mode`, `headerName`, basic-auth `username`) display normally. The decrypted credential plaintext MUST never appear in the export in any form, regardless of format.
- The job's snapshotted `ConnectorRegistration` or `EvaluationAgentRegistration` has since been archived in `013` / `014` (per `013 FR-014` / `014 FR-019`) — the export still renders the snapshotted columns from the Job record (per parent `FR-023`); no separate "registration archived" annotation is required in the export. Hard-delete is blocked by `013 FR-019` / `014 FR-024`, so the "registration entirely gone" case cannot occur in normal operation.
- The tester picks "Both (zip)" but the zip would be very large — the harness still streams the zip on the fly; no max-size cap is enforced in v1.
- A `running` job has zero rows persisted yet (just-started) — the Download Results control is hidden or disabled the same way it is for `draft`/`queued` (no rows to export). It becomes available once at least one row is persisted.
- The harness process is shut down while a download is streaming — the browser surfaces the resulting connection error; no partial file is treated as a successful download.
- The tester downloads an export, the harness restarts, and the tester re-clicks Download — the new export is computed fresh and is equivalent to the prior one (modulo any new rows persisted in between).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a **Download Results** control on the Job Detail View (`specs/004-job-detail-view`) for any job whose persisted row count is greater than zero. The control MUST be hidden or disabled (with an explanatory tooltip) for jobs in `draft` or `queued` status, and for any job whose persisted row count is zero.
- **FR-002**: The Download Results control MUST let the tester pick the output format at click time. Three forms MUST be offered: **CSV** (a single `.csv` file), **JSON** (a single `.json` file), and **Both (zip)** (a single `.zip` containing one CSV and one JSON, each independently valid). The default selection is plan-level.
- **FR-003**: On activation, the harness MUST generate the export on-demand from the latest persisted state of the job. No pre-generated file MUST be reused; no cache MUST short-circuit the read. The export MUST always reflect any new rows persisted since the previous download.
- **FR-004**: The export MUST be delivered to the tester via a standard HTTP file download (the response body is the file content; the response carries appropriate `Content-Type` and `Content-Disposition: attachment; filename=...` for the chosen format). The harness MUST NOT write to a server-side filesystem directory on the tester's machine. Destination selection is handled by the browser's native Save dialog.
- **FR-005**: For every export, the file (or each file in the zip) MUST contain a **job-level metadata block** including the following fields, sourced from the Job's persisted state (`009 FR-001`):
  - `jobId`, `jobName`, `description` (or empty)
  - **`createdBy`** (the persisted `Job.createdBy`, OS-derived per parent `FR-026`)
  - `createdAt`, `startedAt` (or empty), `completedAt` (or empty)
  - `status` (the lifecycle status at click time)
  - `harnessVersion` (the harness version stamped at job-creation time, per `009 FR-001`)
  - `sourceCSVFilename` (the basename string of the originally-uploaded CSV)
  - `errorDetails` (job-level, populated only when `status == failed`, per `009 FR-001`)
  - `connectorId` (the harness-assigned id of the snapshotted `ConnectorRegistration`)
  - `connectorName` (the **verbatim snapshot** of the selected `ConnectorRegistration.displayName` at job-creation time, per `001 FR-023` / `009 FR-001` — NOT a tester-supplied per-job value)
  - `connectorEndpointUrl`, `connectorAuthDescriptor` (with the credential subfield fully masked per `FR-011`; cleartext subfields `mode` / `headerName` / basic-auth `username` display normally), `connectorTimeoutSeconds`, `connectorExpectsPerRowPassword`
  - `evaluationAgentId` (the harness-assigned id of the snapshotted `EvaluationAgentRegistration`)
  - `evaluationAgentName` (the verbatim snapshot of the selected `EvaluationAgentRegistration.displayName`, NOT tester-supplied)
  - `evaluatorEndpointUrl`, `evaluatorAuthDescriptor` (credential subfield masked), `evaluatorTimeoutSeconds`, `evaluatorDeclaredScoringDimensions` (ordered list)
  - `totalUtteranceCount`, `processedCount`, `failedCount`
  - `exportedAt` (the timestamp of this export generation)
- **FR-006**: For every export, the file (or the rows file in the zip) MUST contain a **per-row block** with one entry per persisted Utterance. Each entry MUST carry: `utteranceId`, `rowIndex`, `utteranceText`, `testId`, `rawChatbotResponse` (the raw HTTP body the connector service returned, captured for diagnosis per `009 FR-003` — full structured payload when JSON), `normalizedContract` (the validated Standard Evaluation Contract instance per `007 FR-003` / `006 FR-008`; null if validation failed at `connector_normalization`), `evaluationVerdict` (closed enum `pass` / `fail` / `warn` per `008 FR-004`), `evaluationScores` (the standardized `{parameter_name, score, reasoning}` array from parent `FR-008a` — each entry's per-score `reasoning` is included as part of the structure; per-dimension ordering follows the snapshotted `evaluatorDeclaredScoringDimensions` per `FR-006a`), `metadata` (the evaluator's emitted `metadata` per `008 FR-003`), `harnessAnnotations` (the harness-derived block per `008 FR-005a`, MUST be expressed as a dedicated key / column even when empty so downstream tools can rely on its presence — empty object `{}` or empty CSV cell is valid), `evaluationAgentId` (denormalized from the Job snapshot for per-row traceability, per `009 FR-003`), `errorStatus` (null when the row succeeded; otherwise one of `failed` or `cancelled` per `009 FR-003`), `errorStage` (null when no failure; otherwise one of the canonical nine values per `012 FR-012` / `009 FR-003`: `connector_transport`, `connector_response`, `connector_normalization`, `connector_auth`, `evaluator_transport`, `evaluator_response`, `evaluator_result`, `evaluator_auth`, `password_lookup`), `errorDetails` (null when no failure), and `evaluationTimestamp`. The export MUST NOT contain a `password` column or any password value in any form — not masked, not `[MASKED]`, not null-stubbed; the column is omitted entirely (per parent `FR-010` + parent's password-export clarification). The export MUST NOT contain any `userFeedback*` field — the feedback feature was removed in Round 4. The export MUST NOT contain a top-level `evaluationReasoning` / `reasoning` field — the top-level `reasoning` field was removed from the EvaluationResult shape in Round 3 (per `008 FR-003`); per-score reasoning is included inside `evaluationScores` entries.
- **FR-006a**: Canonical ordering for `evaluationScores` entries within each per-row block: the entries MUST be sorted/positioned to match the Job's snapshotted `evaluatorDeclaredScoringDimensions` order (per `008 FR-005a` + `004 FR-007b`). For the CSV format specifically: when `evaluationScores` is flattened to one column per dimension (rather than JSON-stringified per `FR-008`), the column header order MUST match the snapshotted declared-dimensions list. For the JSON format: the array order in the per-row entry MUST follow the snapshotted list. Score entries whose `parameter_name` is not in the declared list (i.e., would also appear in `harnessAnnotations.unexpected_score_dimensions`) MUST appear after all declared-dimension entries, in the order the evaluator emitted them. This guarantees that two exports of the same registration's outputs concatenate trivially at the spreadsheet/dataframe level.
- **FR-007**: For the CSV format specifically: the job-level metadata MUST be carried as **repeated columns** — every data row MUST include every job-metadata field from `FR-005` as its own column alongside the per-row columns from `FR-006`. The result MUST be a single rectangular dataset readable by any standard CSV reader (pandas, Excel, csv.DictReader, etc.) with zero special configuration — no skip-rows, no out-of-band metadata, no multiple sheets. Concatenating two CSV exports from different jobs MUST produce a valid CSV without column-alignment work.
- **FR-008**: For the CSV format specifically: nested structured fields (`rawChatbotResponse`, `evaluationScores`) MUST be JSON-stringified into a single cell, with proper CSV escaping (quotes, embedded commas, embedded newlines all preserved losslessly).
- **FR-009**: For the JSON format specifically: the file MUST be a single top-level JSON object with two keys: `job` (the job-level metadata) and `rows` (an array of per-row entries). Nested structured fields (`rawChatbotResponse`, `evaluationScores`) MUST be included as native JSON structures (parsed back to objects/arrays if persisted as serialized strings); see edge case for parse-failure handling.
- **FR-010**: For any export, the file MUST be annotated as a **partial snapshot** when the job's status at click time is non-terminal (`running` or `cancelling`). The annotation MUST appear (a) in the filename (e.g., suffix `-partial`) and (b) inline within the file (a `partial: true` field in JSON; a header-row marker naming the status and row count in CSV). This mirrors `004 FR-006a` for the source-CSV download.
- **FR-011**: The credential subfield within the snapshotted `connectorAuthDescriptor` and `evaluatorAuthDescriptor` (bearer token / api-key value / basic-auth password) MUST be rendered in the export as a fully-masked placeholder, identical in form to the Detail View's `004 FR-005`. Cleartext subfields of the auth descriptor (`mode`, `api-key-header` name, basic-auth `username`) MUST appear in the clear — they are not secrets. The decrypted credential plaintext MUST NEVER appear in any export, in any format, in any form (per parent `FR-023a` + `007 FR-015`'s "decrypted plaintext NEVER in exports" rule).
- **FR-012**: The Download Results control MUST remain available indefinitely after a job reaches a terminal state — there is no expiry, no retention window, no "download exhausted" state. Every click MUST trigger a fresh on-demand generation.
- **FR-013**: For jobs at or below the parent spec's 1,000-row design target, the harness MUST begin streaming the response (i.e., the browser's download begins) within 2 seconds of the click, and MUST stream the body without buffering the entire payload in memory.
- **FR-014**: If the job is deleted (via the Detail View's Delete control or any other surface) between the Download Results click and the harness beginning to stream, the request MUST fail with a clear error response and the browser MUST NOT receive a partial or empty file.
- **FR-015**: The export MUST be triggerable only by a tester action on the Detail View. There MUST NOT be a programmatic auto-export, a scheduled export, or a "download on completion" hook in v1.
- **FR-016**: The export MUST always include every persisted Utterance for the job, regardless of any filter, search, or sort active on the Detail View's Results Table at click time. The Detail View's filter/search state MUST NOT influence the export's row set in any way. Consistent with parent `FR-015` ("complete results export of any job") and with the precedent that the Job Metadata Panel's counts are job-level rather than view-level (`specs/004-job-detail-view` → `FR-003` / `FR-014a`).

### Key Entities *(include if feature involves data)*

- **Results Export**: A read-time artifact. Sourced from one `Job` (per `009 FR-001`) + the Job's snapshotted connector and evaluator columns (which were themselves copied from the selected `ConnectorRegistration` and `EvaluationAgentRegistration` per parent `FR-023` and `009 FR-001a` / `FR-001b` at job-creation time) + all of the Job's persisted Utterances + each row's EvaluationResult (per `009 FR-003`). Format is one of: single CSV, single JSON, or zip-of-both. Carries: a job-level metadata block (see `FR-005`) and a per-row block (see `FR-006`). Always generated on-demand; never cached or pre-built.
- **Export Format Selection** *(transient, client-side)*: The tester's chosen format at click time. Not persisted; resets on page reload.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any job with at least one persisted row, the tester can produce a complete export in their chosen format in exactly two actions from the Detail View (select format, click Download Results) — verifiable by enumerating the steps.
- **SC-002**: An export of a 1,000-row job begins streaming to the browser within 2 seconds of the click.
- **SC-003**: For any persisted row, every field listed in `FR-006` appears in the export's per-row block, with the row's actual values — verifiable by exporting a job and matching every row's fields against the database row by row.
- **SC-004**: The export's job-level metadata matches the persisted `Job` snapshot exactly (per `009 FR-001`), including the `status` field as it stood at click time and the `exportedAt` timestamp matching the click time within 1 second — verifiable by comparing the metadata block to the database snapshot.
- **SC-005**: Secret-declared connector and evaluator config fields are verifiable as never appearing in plaintext in any export — verifiable by exporting a job with at least one secret-declared field in each config and grepping the output (CSV and JSON) for the underlying secret value (must produce zero matches).
- **SC-006**: A re-export of the same job after additional rows have been persisted reflects those new rows exactly — verifiable by diffing two exports taken before and after additional row completion.
- **SC-007**: An export of a non-terminal (`running` or `cancelling`) job is annotated as partial in both the filename and inline marker — verifiable by inspecting the file metadata and content.
- **SC-008**: For jobs in `draft` or `queued` status (no rows), the Download Results control is unavailable — verifiable by enumerating the seven lifecycle statuses and observing the control's state for each.
- **SC-009**: A CSV export round-trips losslessly through a standard CSV reader: every row's `utteranceText`, `rawChatbotResponse`, `normalizedContract`, and `evaluationScores` value is recoverable byte-for-byte after read (including the per-score `reasoning` strings nested inside each `evaluationScores` entry) — verifiable by exporting, parsing with a stock CSV library, and comparing each cell.
- **SC-010**: A JSON export of any job parses without error as a single top-level JSON object with `job` and `rows` keys — verifiable by piping to `JSON.parse` (or equivalent) and asserting the schema.
- **SC-011**: When the job is deleted between click and stream-start, the resulting browser experience is a clear error (not a partial file or a silent no-op) — verifiable by triggering the race and observing the response.

## Assumptions

- This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md`. The parent's single-user / no-auth / localhost model applies. Per Round 3, `createdBy` IS in the job-metadata block (OS-derived per parent `FR-026`). Per Round 4, no `userFeedback*` fields are in the export — the feedback feature was removed entirely.
- The Job Detail View (`specs/004-job-detail-view`) is the only surface that hosts the Download Results control in v1. No download from the dashboard, no programmatic API surface, no scheduled export.
- The CSV layout is fixed at "repeated columns": every data row carries every job-metadata field. See `FR-007`. This trades a small amount of file size for zero-configuration pandas/Excel compatibility and trivial cross-job concatenation.
- The default format selection (CSV vs. JSON vs. Both) is a plan-level UX detail. The spec only requires that all three be offered at click time.
- Secret-field masking format in the export uses the same approach as the Detail View (`004 FR-005`: fully-masked placeholder, no in-export reveal mechanism). The export inherits the Detail View's choice rather than redefining it.
- The "Module 13's source-CSV download" (`004 FR-006`) and "Module 14's results export" are two distinct downloadable artifacts on the same page. The source-CSV download is the reconstructed input rows; the results export is the input + outputs + evaluations. Both controls coexist on the Detail View; neither replaces the other.
- The CSV format's character set is UTF-8 (matching the parent spec's CSV-upload expectation). Byte-order-mark inclusion is plan-level.
- The export's file naming convention (e.g., `<jobName>-<exportedAt>.csv` vs. `<jobId>-results.csv`) is plan-level; the spec only requires that `partial` appears in the filename when applicable and that the filename is recognizably tied to the source job.
- Re-running a job or copy-creating a new job from an export is out of scope for v1 (consistent with the parent's "no first-class retry" decision).
- Audit-logging of who downloaded what and when is out of scope — there is no "who" (single-user), and download events are not tracked in v1.
