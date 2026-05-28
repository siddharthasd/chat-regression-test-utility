# Feature Specification: Results Export Service (Module 14)

**Feature Branch**: `005-results-export`

**Created**: 2026-05-28

**Status**: Draft

**Input**: User description: "Module 14 — Results Export Service. A backend service and a UI control on the Job Detail View that lets the tester download a complete export of a job's results — every per-utterance trace plus job-level metadata — as a downloadable file in the format the tester selects (CSV, JSON, or both bundled in a zip). The export is generated on-demand at click time, always reflecting the latest persisted data (including any feedback added after the job completed). The download is delivered through the browser's standard file-download path."

> **Parent context**: This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Its UI control lives on the Job Detail View defined in `specs/004-job-detail-view/spec.md`. This spec extends parent `FR-015` (the harness-level export requirement) and re-uses parent `FR-009` (what's persisted per row) and parent `FR-008a` (the standardized scores payload shape). Parent-spec premises apply unchanged: single-user, no auth, no `createdBy` field anywhere. The Module 14 input's mentions of `createdBy` (in job metadata) and `userFeedbackBy` (in row data) were dropped by explicit decision (2026-05-28); no creator/user concept exists in the harness. The Module 14 input's mention of `CompletedWithErrors` as a status was resolved to its established meaning: it is a UI label for `status == completed && failed_count > 0`, not a real lifecycle state — so the trigger gate is simply `status == completed`, with the broader scope clarified below.

## Clarifications

### Session 2026-05-28

- Q: Which job statuses should have the Download Results control available? → A: **Any job that has at least one persisted Test Case Row**. That is: `completed`, `failed`, `cancelled`, `running`, and `cancelling`. Jobs in `draft` or `queued` status have no rows and no export. For non-terminal jobs (`running`, `cancelling`), the export is a snapshot-at-click-time, partial-annotated — consistent with the Job Detail View's `FR-006a` source-CSV download semantics.
- Q: Module 14 says "two formats selectable by the user" but parent `FR-015` originally said "always a zip with both CSV and JSON". Which wins? → A: Selectable wins. The tester picks one of three forms at click time: CSV only, JSON only, or zip containing both. Parent `FR-015` was amended in lock-step (see parent `Clarifications`). The three-way choice is a small selector co-located with the Download Results control.
- Q: How is the file delivered to the tester's machine? → A: Standard HTTP browser download. The Flask process streams the export file body in the response; the browser's own Save dialog handles destination selection. The harness does NOT write to a server-side directory like `~/.harness/exports/`. The Module 14 input's mention of "a file picker or a known output directory" was resolved to browser-native download; no filesystem permissions, no path leakage, no destination management in the harness.

### Session 2026-05-28 (Round 2)

- Q: How is job-level metadata carried inside the CSV export? → A: **Repeated columns.** Every data row carries every job-metadata field as its own column alongside the per-row columns. Produces a single rectangular dataset that pandas / Excel / any standard CSV reader handles with zero special configuration. Concatenating exports from multiple jobs into one analysis is trivial. The "leading header section" and "two-files-in-a-zip" alternatives in `FR-007` are dropped.
- Q: When the tester clicks Download Results with a filter or search active on the Detail View's Results Table, does the export reflect the filter or all rows? → A: **Always all persisted rows of the job.** Filters and search on the Detail View are for in-page browsing only; the export is *about the job*, not *about the view*. Matches the 004 R3 precedent (Metadata Panel counts are job-level, not filtered) and parent `FR-015`'s "complete results export of any job" wording. Tester subsets the data post-export in their analysis tool if needed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Export a completed job's results in the format I need (Priority: P1)

A QA tester finishes a regression run, opens the Job Detail View, picks an export format (CSV, JSON, or both-as-zip), and clicks Download Results. The harness generates the export on the fly from the latest persisted data and the browser saves the file. The tester opens the file in their tool of choice (spreadsheet for CSV, scripting for JSON) to triage or compare against a baseline.

**Why this priority**: This is the entire purpose of Module 14. Without it, the tester has no way to take results out of the harness. It is the MVP slice.

**Independent Test**: With a completed job containing at least 10 rows (mix of `completed` and `failed` per-row statuses, at least one with feedback applied), click Download Results once for each of the three formats. Verify (a) each format produces a valid file that opens without error in its native tool, (b) every persisted row is represented exactly once, (c) the job-level metadata block is present and accurate, (d) secret fields in the connector and evaluator config are masked the same way as on the Detail View.

**Acceptance Scenarios**:

1. **Given** a completed job with N persisted rows, **When** the tester picks CSV and clicks Download Results, **Then** the browser downloads a CSV file whose data rows correspond one-to-one to the job's N rows, with the canonical column set populated per row and a header section (or repeated columns; format is plan-level) carrying the job-level metadata.
2. **Given** the same job, **When** the tester picks JSON and clicks Download Results, **Then** the browser downloads a single JSON file with a top-level object containing the job-level metadata and a `rows` array of length N, each entry containing every persisted field for that row in nested (lossless) form.
3. **Given** the same job, **When** the tester picks "Both (zip)" and clicks Download Results, **Then** the browser downloads a single zip file containing one CSV and one JSON file, each independently equivalent to scenarios 1 and 2.

---

### User Story 2 - Export the partial state of a still-running job (Priority: P2)

A tester monitoring a long-running job wants a snapshot of what's been processed so far — to share with a colleague, to feed into a script that watches for regressions, or to triage a failure pattern emerging mid-run. They open the Job Detail View and click Download Results while the job is still in `running` (or `cancelling`). The harness produces an export reflecting only the rows persisted up to that moment, clearly annotated as a partial snapshot.

**Why this priority**: Real-world QA workflows include mid-run inspection. Equal-priority with the post-feedback re-export story because both deliver value on top of P1 without depending on each other.

**Independent Test**: Start a long-enough job (so it's observably `running` for several seconds). Click Download Results once mid-run; verify the file (a) contains only rows persisted up to that moment, (b) is annotated as partial (filename suffix and/or inline marker naming the job's status and row count at click time), (c) is otherwise structurally valid for its format.

**Acceptance Scenarios**:

1. **Given** a job in `running` status with K rows persisted at click time, **When** the tester clicks Download Results, **Then** the export contains exactly K rows; the file is annotated as partial (filename includes `partial`, and inline marker names the job's status and row count at download time).
2. **Given** a job in `cancelling` status, **When** the tester clicks Download Results, **Then** the export reflects whatever has been persisted to that moment, also partial-annotated. The export's existence does not delay or interfere with the cancellation sequence.

---

### User Story 3 - Re-export a completed job after applying feedback (Priority: P2)

A tester reviewed a completed job, applied thumbs-up / thumbs-down feedback to several rows via the Detail View, and now wants a new export that includes that feedback. They click Download Results again. The new file reflects the latest feedback state — no stale cache, no pre-generated artifact.

**Why this priority**: The Module 14 input is explicit that the link must remain available permanently and the export must always reflect the latest data. Equal-priority with the partial-snapshot story because both are independently testable on top of P1.

**Independent Test**: With a completed job, download an export, apply or change feedback on at least two rows via Module 13, download an export again; verify the second file's feedback values match the just-applied state for those rows.

**Acceptance Scenarios**:

1. **Given** a completed job whose first export the tester has already taken, **When** the tester applies feedback to one or more rows via the Job Detail View and then re-clicks Download Results, **Then** the second export reflects the just-applied feedback values exactly.
2. **Given** any export click, **When** the harness generates the file, **Then** the file is produced on-demand from the current persisted state — no cached artifact is reused, no pre-generated file exists.

---

### User Story 4 - Export the persisted state of a failed or cancelled job for triage (Priority: P3)

A tester investigating a job that failed mid-run (or was cancelled) wants to ship the entire trace to a colleague, file a bug, or feed it into a comparison script. They open the failed/cancelled job's Detail View and click Download Results. The export contains every row persisted before the failure or cancellation — including the per-row error detail and the stage at which each failing row failed.

**Why this priority**: Failed and cancelled jobs are exactly the jobs whose results are most worth sharing for triage. Lower priority than the running-snapshot story because it's the same mechanism plus terminal-state context — once US1 and US2 work, this story is largely a no-extra-effort beneficiary.

**Independent Test**: With one job in `failed` status (some rows succeeded, some failed at different stages) and one in `cancelled` status (some rows completed before cancel), click Download Results for each. Verify every persisted row appears, with the row's error stage and detail intact for `failed` rows.

**Acceptance Scenarios**:

1. **Given** a `failed` or `cancelled` job with persisted rows, **When** the tester clicks Download Results, **Then** the export includes every persisted row with its complete per-row state (input, raw response if reached, normalized contract if reached, evaluation result if reached, error stage and error detail for `failed` rows, feedback if any).
2. **Given** a `draft` or `queued` job (no rows persisted), **When** the tester views the Detail View, **Then** the Download Results control is hidden or disabled with an explanatory tooltip ("No rows to export yet"), and no export endpoint accepts requests for that job id.

---

### Edge Cases

- A job whose persisted row count is very large (at or near the parent spec's 1,000-row design target) is exported — the harness streams the response without buffering the entire payload in memory; the browser's download begins promptly.
- The tester clicks Download Results, then immediately clicks it again before the first download finishes (double-click or rapid retry) — both requests succeed and produce equivalent (or near-equivalent if rows arrived between them) snapshots; neither corrupts the other.
- The job is deleted (via the Detail View's Delete control, `004 FR-019`) between the Download click and the harness generating the file — the request fails with an actionable status code and an explanatory message; no partial or empty file is downloaded.
- The selected format is CSV and a row's `rawChatbotResponse` or `evaluationScores` contains characters that need CSV escaping (commas, quotes, newlines, embedded JSON) — the values are correctly quoted/escaped so the output is a valid CSV.
- The selected format is CSV and a row's normalized response text or evaluation reasoning is multi-paragraph — newlines inside the value are preserved (CSV-quoted) so the value round-trips losslessly through a standard CSV reader.
- The selected format is JSON and the row's `rawChatbotResponse` is itself stringified JSON in the database — the export presents it as a nested JSON object (parsed back into structure), not as a quoted string, so the JSON file is hierarchical end-to-end. If parsing fails (corrupt persisted value), the field is included as a string with an `_unparseable: true` sibling marker.
- The connector or evaluator config in the metadata snapshot contains secret-declared fields — the export presents them as fully-masked placeholders in the same form as the Detail View (per `004 FR-005`). Secret values MUST never appear in the export in plaintext, regardless of format.
- The tester picks "Both (zip)" but the zip would be very large — the harness still streams the zip on the fly; no max-size cap is enforced in v1.
- A `running` job has zero rows persisted yet (just-started) — the Download Results control is hidden or disabled the same way it is for `draft`/`queued` (no rows to export). It becomes available once at least one row is persisted.
- The harness process is shut down while a download is streaming — the browser surfaces the resulting connection error; no partial file is treated as a successful download.
- The tester downloads an export, the harness restarts, and the tester re-clicks Download — the new export is computed fresh and is equivalent to the prior one (modulo any feedback changes that happened in between).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a **Download Results** control on the Job Detail View (`specs/004-job-detail-view`) for any job whose persisted row count is greater than zero. The control MUST be hidden or disabled (with an explanatory tooltip) for jobs in `draft` or `queued` status, and for any job whose persisted row count is zero.
- **FR-002**: The Download Results control MUST let the tester pick the output format at click time. Three forms MUST be offered: **CSV** (a single `.csv` file), **JSON** (a single `.json` file), and **Both (zip)** (a single `.zip` containing one CSV and one JSON, each independently valid). The default selection is plan-level.
- **FR-003**: On activation, the harness MUST generate the export on-demand from the latest persisted state of the job. No pre-generated file MUST be reused; no cache MUST short-circuit the read. The export MUST always reflect any feedback or new rows applied since the previous download.
- **FR-004**: The export MUST be delivered to the tester via a standard HTTP file download (the response body is the file content; the response carries appropriate `Content-Type` and `Content-Disposition: attachment; filename=...` for the chosen format). The harness MUST NOT write to a server-side filesystem directory on the tester's machine. Destination selection is handled by the browser's native Save dialog.
- **FR-005**: For every export, the file (or each file in the zip) MUST contain a **job-level metadata block** including: `jobId`, `jobName`, `description` (or empty), `createdAt`, `startedAt` (or empty), `completedAt` (or empty), `status` (the lifecycle status at click time), `connectorType`, `connectorConfig` (with secret-declared fields masked per `004 FR-005`), `evaluationAgentId`, `evaluationAgentConfig` (with secret-declared fields masked), `totalUtteranceCount`, `processedCount`, `failedCount`, and `exportedAt` (the timestamp of this export generation). The export MUST NOT contain a `createdBy` field — per parent precedent, no creator concept exists in the harness.
- **FR-006**: For every export, the file (or the rows file in the zip) MUST contain a **per-row block** with one entry per persisted Test Case Row. Each entry MUST carry: `utteranceId`, `rowIndex`, `utteranceText`, `testId`, `normalizedResponseText`, `rawChatbotResponse` (full structured payload), `evaluationVerdict`, `evaluationScores` (the standardized `{parameter_name, score, reasoning}` array from parent `FR-008a`), `evaluationReasoning`, `userFeedbackValue` (or empty: thumbs-up / thumbs-down / cleared), `userFeedbackTimestamp` (or empty), `errorStatus` (or empty: the per-row terminal status, e.g. `completed` or `failed`), `errorDetails` (or empty: the stage and captured error for `failed` rows per parent `FR-017`), and `executionTimestamp`. The export MUST NOT contain a `userFeedbackBy` field — no creator concept exists. The export MUST NOT contain any `password` value (parent `FR-010`).
- **FR-007**: For the CSV format specifically: the job-level metadata MUST be carried as **repeated columns** — every data row MUST include every job-metadata field from `FR-005` as its own column alongside the per-row columns from `FR-006`. The result MUST be a single rectangular dataset readable by any standard CSV reader (pandas, Excel, csv.DictReader, etc.) with zero special configuration — no skip-rows, no out-of-band metadata, no multiple sheets. Concatenating two CSV exports from different jobs MUST produce a valid CSV without column-alignment work.
- **FR-008**: For the CSV format specifically: nested structured fields (`rawChatbotResponse`, `evaluationScores`) MUST be JSON-stringified into a single cell, with proper CSV escaping (quotes, embedded commas, embedded newlines all preserved losslessly).
- **FR-009**: For the JSON format specifically: the file MUST be a single top-level JSON object with two keys: `job` (the job-level metadata) and `rows` (an array of per-row entries). Nested structured fields (`rawChatbotResponse`, `evaluationScores`) MUST be included as native JSON structures (parsed back to objects/arrays if persisted as serialized strings); see edge case for parse-failure handling.
- **FR-010**: For any export, the file MUST be annotated as a **partial snapshot** when the job's status at click time is non-terminal (`running` or `cancelling`). The annotation MUST appear (a) in the filename (e.g., suffix `-partial`) and (b) inline within the file (a `partial: true` field in JSON; a header-row marker naming the status and row count in CSV). This mirrors `004 FR-006a` for the source-CSV download.
- **FR-011**: Secret-declared fields in `connectorConfig` and `evaluationAgentConfig` MUST be rendered in the export as fully-masked placeholders, identical in form to the Detail View's `004 FR-005`. The underlying secret value MUST NOT appear in plaintext in any export, in any format, ever.
- **FR-012**: The Download Results control MUST remain available indefinitely after a job reaches a terminal state — there is no expiry, no retention window, no "download exhausted" state. Every click MUST trigger a fresh on-demand generation.
- **FR-013**: For jobs at or below the parent spec's 1,000-row design target, the harness MUST begin streaming the response (i.e., the browser's download begins) within 2 seconds of the click, and MUST stream the body without buffering the entire payload in memory.
- **FR-014**: If the job is deleted (via the Detail View's Delete control or any other surface) between the Download Results click and the harness beginning to stream, the request MUST fail with a clear error response and the browser MUST NOT receive a partial or empty file.
- **FR-015**: The export MUST be triggerable only by a tester action on the Detail View. There MUST NOT be a programmatic auto-export, a scheduled export, or a "download on completion" hook in v1.
- **FR-016**: The export MUST always include every persisted Test Case Row for the job, regardless of any filter, search, or sort active on the Detail View's Results Table at click time. The Detail View's filter/search state MUST NOT influence the export's row set in any way. Consistent with parent `FR-015` ("complete results export of any job") and with the precedent that the Job Metadata Panel's counts are job-level rather than view-level (`specs/004-job-detail-view` → `FR-003` / `FR-014a`).

### Key Entities *(include if feature involves data)*

- **Results Export**: A read-time artifact. Sourced from one Test Job + all of its persisted Test Case Rows + each row's Connector Invocation + each row's Evaluation Result + each row's Tester Feedback. Format is one of: single CSV, single JSON, or zip-of-both. Carries: a job-level metadata block (see `FR-005`) and a per-row block (see `FR-006`). Always generated on-demand; never cached or pre-built.
- **Export Format Selection** *(transient, client-side)*: The tester's chosen format at click time. Not persisted; resets on page reload.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any job with at least one persisted row, the tester can produce a complete export in their chosen format in exactly two actions from the Detail View (select format, click Download Results) — verifiable by enumerating the steps.
- **SC-002**: An export of a 1,000-row job begins streaming to the browser within 2 seconds of the click.
- **SC-003**: For any persisted row, every field listed in `FR-006` appears in the export's per-row block, with the row's actual values — verifiable by exporting a job and matching every row's fields against the database row by row.
- **SC-004**: The export's job-level metadata matches the persisted Test Job snapshot exactly, including the `status` field as it stood at click time and the `exportedAt` timestamp matching the click time within 1 second — verifiable by comparing the metadata block to the database snapshot.
- **SC-005**: Secret-declared connector and evaluator config fields are verifiable as never appearing in plaintext in any export — verifiable by exporting a job with at least one secret-declared field in each config and grepping the output (CSV and JSON) for the underlying secret value (must produce zero matches).
- **SC-006**: A re-export of the same job after applying or changing feedback on one or more rows reflects the new feedback values exactly — verifiable by diffing two exports taken before and after a feedback edit.
- **SC-007**: An export of a non-terminal (`running` or `cancelling`) job is annotated as partial in both the filename and inline marker — verifiable by inspecting the file metadata and content.
- **SC-008**: For jobs in `draft` or `queued` status (no rows), the Download Results control is unavailable — verifiable by enumerating the seven lifecycle statuses and observing the control's state for each.
- **SC-009**: A CSV export round-trips losslessly through a standard CSV reader: every row's `utteranceText`, `normalizedResponseText`, `evaluationReasoning`, `rawChatbotResponse`, and `evaluationScores` value is recoverable byte-for-byte after read — verifiable by exporting, parsing with a stock CSV library, and comparing each cell.
- **SC-010**: A JSON export of any job parses without error as a single top-level JSON object with `job` and `rows` keys — verifiable by piping to `JSON.parse` (or equivalent) and asserting the schema.
- **SC-011**: When the job is deleted between click and stream-start, the resulting browser experience is a clear error (not a partial file or a silent no-op) — verifiable by triggering the race and observing the response.

## Assumptions

- This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md`. The parent's single-user / no-auth / localhost model applies. There is no `createdBy` (job metadata) and no `userFeedbackBy` (row data) anywhere in the export.
- The Job Detail View (`specs/004-job-detail-view`) is the only surface that hosts the Download Results control in v1. No download from the dashboard, no programmatic API surface, no scheduled export.
- The CSV layout is fixed at "repeated columns": every data row carries every job-metadata field. See `FR-007`. This trades a small amount of file size for zero-configuration pandas/Excel compatibility and trivial cross-job concatenation.
- The default format selection (CSV vs. JSON vs. Both) is a plan-level UX detail. The spec only requires that all three be offered at click time.
- Secret-field masking format in the export uses the same approach as the Detail View (`004 FR-005`: fully-masked placeholder, no in-export reveal mechanism). The export inherits the Detail View's choice rather than redefining it.
- The "Module 13's source-CSV download" (`004 FR-006`) and "Module 14's results export" are two distinct downloadable artifacts on the same page. The source-CSV download is the reconstructed input rows; the results export is the input + outputs + evaluations + feedback. Both controls coexist on the Detail View; neither replaces the other.
- The CSV format's character set is UTF-8 (matching the parent spec's CSV-upload expectation). Byte-order-mark inclusion is plan-level.
- The export's file naming convention (e.g., `<jobName>-<exportedAt>.csv` vs. `<jobId>-results.csv`) is plan-level; the spec only requires that `partial` appears in the filename when applicable and that the filename is recognizably tied to the source job.
- Re-running a job or copy-creating a new job from an export is out of scope for v1 (consistent with the parent's "no first-class retry" decision).
- Audit-logging of who downloaded what and when is out of scope — there is no "who" (single-user), and download events are not tracked in v1.
