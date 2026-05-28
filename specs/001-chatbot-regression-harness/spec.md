# Feature Specification: AI Chatbot Regression Test Harness

**Feature Branch**: `001-chatbot-regression-harness`

**Created**: 2026-05-28

**Status**: Draft

**Input**: User description: "A locally-installed, single-user web application that enables QA testers to systematically regression-test AI-powered chatbots. The tester uploads a CSV of test utterances (each row carrying a `testId` + `password` for an external identity), the harness fires each utterance at the target chatbot via a pluggable connector under the supplied identity, normalizes the response to a Standard Evaluation Contract, hands it to a pluggable AI-powered evaluation agent, and persists the full input → output → evaluation trace with optional thumbs-up/down feedback. Multiple jobs can run concurrently. Distributed as a pipx-installable Python package using embedded SQLite and a Flask UI on localhost. Multi-turn conversation support is out of scope for v1."

## Clarifications

### Session 2026-05-28

- Q: Should the tester be able to cancel a running job, and if so, what happens to in-flight rows? → A: Soft cancel. In-flight rows run to natural completion or failure; queued rows transition to "cancelled"; the job ends in a terminal "cancelled" state. Partial results are preserved.
- Q: What is the upper-bound CSV size the harness must handle without UI or persistence degradation? → A: Up to 1,000 rows per job. Larger CSVs may work but are not a design target.
- Q: How does a tester re-run only the failed rows of a completed job? → A: No first-class retry in v1. The tester filters the original CSV down to the failed rows and creates a new job. Original jobs remain immutable for traceability.
- Q: What format(s) must the results export support? → A: A single downloadable zip containing both a CSV (flat, spreadsheet-friendly, with nested fields JSON-stringified per cell) and a JSON file (lossless, nested). Both cover the same rows.
- Q: How should the harness handle transient connector failures (HTTP 429, 5xx, timeouts)? → A: No retries at the harness layer. Every connector or evaluator error is recorded as `failed` immediately with the captured cause. Individual connectors may implement internal retries at their own discretion; the harness does not.
- Q: Does a job have a "draft" state for jobs that have been created/configured but not yet started? → A: Yes. The job lifecycle is `draft` → `queued` → `running` → terminal (`completed` | `failed` | `cancelled`), with `cancelling` as the transient state on the path to `cancelled`. A `draft` job has not yet been started; testers may delete drafts but not cancel them (cancel applies only to `queued` and `running`). UI labels like "Completed with errors" are presentation only — they map to `completed` rows whose `failed`-row count is non-zero, not to a distinct state.
- Q: Beyond `draft`, are any other job statuses deletable? → A: Yes — `failed` and `cancelled` jobs MAY be deleted by the tester (`FR-001a`), to support dashboard cleanup as terminal-error jobs accumulate. `completed` jobs remain non-deletable in v1 (preserved as historical record of successful runs). Non-terminal statuses (`queued`, `running`, `cancelling`) cannot be deleted directly — the tester must cancel first.
- Q: What structure must evaluators produce for the per-row scores payload that the harness will render in the UI? → A: Each Evaluation Result MUST include a `scores` payload whose value is an ordered collection of zero or more entries, where each entry has the fields `parameter_name` (string), `score` (number or short string — the evaluator's own scale; not normalized across evaluators), and `reasoning` (string explaining that parameter's score). The count of entries, the parameter names, and the score scales MAY differ between evaluators and between evaluator versions — the harness MUST NOT assume uniformity across evaluators. The harness owns the rendering of this payload; consumers (e.g., the Module 13 detail view) MUST treat each entry as structured data, MUST NOT inject any HTML/script the evaluator may have placed in those string fields directly into the DOM, and MUST NOT provide a sort affordance over the scores payload (no canonical cross-row ordering exists).
- Q: Originally the export was specified as "always a zip with both CSV and JSON" (`FR-015`). Module 14 wants the tester to pick the format. Which wins? → A: Module 14's selectable model wins. `FR-015` was loosened to allow the tester to pick CSV, JSON, or zip-with-both at click time. The export is also expanded to be available for any job with persisted rows (including `failed`, `cancelled`, and snapshots from `running`), not just `completed`. Partial-snapshot annotation applies when the job is non-terminal, mirroring the source-CSV download's behavior on the detail view.
- Q: Module 4 (Connector Framework) introduces an "encryption utility for the password field." Does this apply to the CSV row password (changing parent FR-010), to connector config-level secrets, or both? → A: **Config-level secrets only** — API keys, auth tokens, and service-account passwords inside the connector's own configuration form. The per-row CSV `password` rule from `FR-010` is unchanged (still in-memory only, never persisted at rest). New `FR-023a` formalizes the at-rest encryption requirement: secret-declared fields within the persisted connector and evaluator config snapshots are encrypted with a symmetric machine-local key; decrypted only when needed; never in exports, UI, or logs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - End-to-end regression batch under multiple identities (Priority: P1)

A QA tester wants to validate that a new chatbot release behaves correctly across a representative set of utterances and across multiple test-user identities. They install the harness, launch it, create a new test job, upload a CSV (each row: utterance + `testId` + `password` + optional metadata), pick a chatbot connector, pick an evaluation agent, supply each one's configuration, and start the job. The harness processes every row by passing the utterance to the connector authenticated as that row's identity, normalizes the chatbot's response to the Standard Evaluation Contract, runs the evaluation agent against it, and persists the full trace. When the job finishes, the tester downloads a complete results export.

**Why this priority**: This is the entire purpose of the product. Without it, no other story delivers value. It is the MVP slice.

**Independent Test**: Install the harness on a clean laptop, point it at a stub chatbot connector and a stub evaluation agent, upload a 5-row CSV with two distinct `testId`s, and verify that all 5 rows complete with persisted traces and a downloadable export containing every row.

**Acceptance Scenarios**:

1. **Given** a valid CSV with N rows and a tester who has selected a connector and an evaluation agent, **When** the tester starts the job, **Then** every row is dispatched to the connector under its row-specific `testId`/`password`, normalized to the Standard Evaluation Contract, evaluated, and the input + chatbot output + evaluation result are persisted and linked to the job.
2. **Given** a row's `testId`/`password` fails to authenticate against the chatbot's identity system, **When** the connector reports the failure, **Then** the row is recorded with the failure cause and the remaining rows continue to process.
3. **Given** a completed job, **When** the tester requests an export, **Then** the export contains one record per CSV row with input, normalized output, evaluation result, and any per-row error.
4. **Given** the tester closes the browser tab while a job is running, **When** the localhost server keeps running, **Then** the job continues to completion and remains reviewable on the next visit.

---

### User Story 2 - Per-row traceability review with optional human feedback (Priority: P2)

A tester investigating a regression opens a completed (or in-progress) job and drills into individual rows to see exactly what was sent to the chatbot, what came back, how it was normalized into the Standard Evaluation Contract, what the evaluation agent decided, and (if anything went wrong) where it failed. For any row they can apply a thumbs-up or thumbs-down feedback and optionally attach a short note.

**Why this priority**: Traceability is what differentiates a regression harness from a one-shot script. It is required to triage failures and to capture the tester's own judgment alongside the evaluator's verdict — but the system can deliver value from P1 even before this is built.

**Independent Test**: With at least one completed job in the system, open the job's row list, open any single row, confirm the full trace (input, raw response, normalized contract, evaluation result, error if any) is visible, apply a thumbs-down with a note, reload the page, and confirm the feedback persists.

**Acceptance Scenarios**:

1. **Given** a row whose status is "completed", **When** the tester opens the row's detail view, **Then** they see the original CSV input, the chatbot's raw response, the normalized Standard Evaluation Contract instance, and the evaluation agent's structured result.
2. **Given** any row regardless of status, **When** the tester applies thumbs-up or thumbs-down, **Then** the feedback is persisted, replaces any prior feedback on that row, and remains visible on subsequent visits.
3. **Given** a row whose status is "failed", **When** the tester opens it, **Then** they see which stage failed (connector vs. normalization vs. evaluation) and the captured error detail.

---

### User Story 3 - Multiple concurrent jobs for comparative testing (Priority: P3)

A tester wants to compare two chatbot configurations (e.g., two different model temperatures, two different system prompts, or two release builds) by running them side-by-side against the same CSV. They create job A, start it, immediately create job B with a different connector configuration, and start it while A is still running. Both jobs progress independently and both results sets are independently reviewable and exportable.

**Why this priority**: Comparative testing is the headline use case for a regression harness, but it builds on top of the P1 single-job flow. Until P1 is solid, parallelism adds no value.

**Independent Test**: With P1 working, start two jobs whose CSVs and configurations differ, observe both progressing in the job list without one blocking or corrupting the other, and verify the two exports are correct and isolated.

**Acceptance Scenarios**:

1. **Given** Job A is running, **When** the tester creates and starts Job B, **Then** Job B begins processing without waiting for Job A and does not alter Job A's state.
2. **Given** two concurrent jobs, **When** both complete, **Then** each job's results contain only its own rows and its own connector/evaluator configuration snapshot.

---

### User Story 4 - Pluggable connector & evaluation agent selection at job creation (Priority: P4)

The tester picks the chatbot platform and the evaluation strategy independently when creating a job, choosing from whatever connectors and evaluation agents are currently registered with the harness. Each connector and each evaluation agent exposes its own configuration form (e.g., endpoint URL, model name, evaluation criteria) which the tester fills in. The harness records a snapshot of both configurations with the job so results remain interpretable later.

**Why this priority**: Extensibility is core to the product's purpose, but the first release ships with at least one connector and at least one evaluation agent, so the pluggability mechanism is exercised even if only one of each exists. P1 still works with a single hard-coded pair; this story unlocks the architecture for additional pairs.

**Independent Test**: Register an additional connector and an additional evaluation agent, create a new job, confirm both appear in their respective pickers, select them, fill in their config forms, start the job, and confirm the chosen pair is recorded on the job and used for execution.

**Acceptance Scenarios**:

1. **Given** at least two registered connectors and at least two registered evaluation agents, **When** the tester opens the job creation form, **Then** the pickers list all registered connectors and all registered evaluation agents.
2. **Given** the tester has selected a specific connector, **When** the form renders, **Then** it shows the configuration fields declared by that connector and validates the input before allowing job start.
3. **Given** an evaluation agent declares it accepts only Standard Evaluation Contract version X, **When** the tester pairs it with a connector that emits a different version, **Then** the harness prevents the job from starting with an actionable message.

---

### Edge Cases

- The uploaded CSV is missing required columns, uses a non-UTF-8 encoding, has empty rows, or has duplicate `testId`s firing different utterances.
- The chatbot connector times out, returns a non-success status, or returns a payload the connector cannot normalize into the Standard Evaluation Contract.
- The evaluation agent crashes, exceeds its timeout, or returns output that does not conform to its declared output schema.
- The tester restarts the harness process while a job's status in the database is "running" — the harness must reconcile orphaned jobs deterministically rather than leaving them in a stuck state. Because passwords are not persisted (`FR-010`), rows that have not yet fired cannot resume without a CSV re-upload.
- Two concurrent jobs reference the same `testId` at the same time (allowed; the harness treats this as the tester's choice, not a conflict).
- The CSV references a `testId` that no longer exists in the external identity system.
- The disk fills up or SQLite write fails mid-job.
- The user resubmits the same CSV against the same job (the harness must not silently merge — it is a new job).
- The evaluation agent declares it accepts a contract version that no registered connector emits.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow a tester to create and name a test job from the UI. A newly created job is in `draft` state until the tester explicitly starts it (at which point it transitions to `queued`). The tester MAY delete a `draft` job at any time before starting it.
- **FR-001a**: System MUST allow the tester to permanently delete any test job whose status is `failed` or `cancelled`. Deletion MUST cascade to all of that job's persisted rows (input rows, connector invocations, evaluation results, feedback). Jobs in any other status (`draft` excepted per `FR-001`, plus `queued`, `running`, `cancelling`, `completed`) MUST NOT be deletable. `completed` jobs are intentionally retained as the historical record of successful runs; non-terminal jobs must be cancelled to reach `cancelled` before they become deletable. Deletion MUST require explicit tester confirmation and MUST be irreversible.
- **FR-002**: System MUST accept a CSV upload whose schema requires per row at minimum: `utterance`, `testId`, `password`. Additional columns MUST be preserved verbatim as per-row metadata.
- **FR-003**: System MUST validate the uploaded CSV against the required schema and reject malformed uploads with row-level error messages before the job starts.
- **FR-004**: System MUST present a registry of available chatbot connectors and let the tester pick one per job along with that connector's required configuration.
- **FR-005**: System MUST present a registry of available evaluation agents and let the tester pick one per job along with that agent's required configuration.
- **FR-006**: System MUST pass each CSV row's `utterance`, `testId`, and `password` through to the selected connector unmodified, so the connector can authenticate as that identity when calling the chatbot.
- **FR-007**: System MUST normalize each connector's raw chatbot response into an instance of the Standard Evaluation Contract — a versioned, canonical JSON schema — before evaluation.
- **FR-008**: System MUST pass the normalized contract instance to the selected evaluation agent and capture its structured evaluation result.
- **FR-008a**: Every Evaluation Result captured by the harness MUST include a `scores` field whose value is an ordered collection of zero or more entries. Each entry MUST be an object with the fields `parameter_name` (string), `score` (number or short string — the evaluator's own scale), and `reasoning` (string). The count of entries, the parameter names, and the score scales are evaluator-defined and MAY vary between evaluators and between evaluator versions. The harness MUST persist the payload as structured data, MUST NOT normalize scales across evaluators, and MUST treat all string fields as data (not as HTML or executable content) when rendering them in any UI.
- **FR-009**: System MUST persist for every row: the original input row **excluding the row's `password`**, the raw chatbot response, the normalized Standard Evaluation Contract instance, the evaluation result, all relevant timestamps, the per-row status (queued / running / completed / failed / cancelled), and a link to the parent job. (Note: `draft` is a job-level state only; rows do not exist for jobs in `draft` because the CSV has not yet been bound to a started job.)
- **FR-010**: System MUST treat each row's `password` as an opaque pass-through value held **in memory only** for the duration of that row's connector call. Passwords MUST NOT be written to the local database, the exported results file, application logs, or any other persistent storage at any point in the job lifecycle.
- **FR-010a**: Because passwords are in-memory only, the system MUST NOT attempt to auto-resume rows that require credentials after a process restart. Per `FR-022`, any job whose rows still need to fire MUST transition into a tester-visible state that requires explicit re-upload of the CSV to continue, rather than silently failing or stalling.
- **FR-011**: System MUST support multiple jobs running concurrently without interference: each job's status, rows, and configuration snapshot MUST remain isolated.
- **FR-012**: System MUST surface job-level status (draft / queued / running / cancelling / completed / failed / cancelled) and per-row progress in the UI while jobs are running.
- **FR-013**: System MUST allow the tester to inspect, for any persisted row, its full input → raw output → normalized contract → evaluation result chain (or the captured error and the stage where it occurred).
- **FR-014**: System MUST allow the tester to attach optional thumbs-up or thumbs-down feedback to any row, replace prior feedback on that row, and retrieve that feedback on subsequent visits.
- **FR-015**: System MUST allow the tester to download a complete results export of any job that has at least one persisted Test Case Row (so: jobs in `completed`, `failed`, `cancelled`, `running`, or `cancelling` status; the `draft` and `queued` statuses have no rows and therefore no export). The harness MUST offer the tester a choice at click time of at least these three output forms: (a) a CSV file with one row per test case row and nested structures JSON-stringified per cell, (b) a JSON file with the same rows in nested, lossless form, and (c) a zip archive bundling both (a) and (b). Whichever form is selected, the file MUST include every row's input (excluding `password`), normalized output, evaluation result, error (if any), and feedback (if any), plus the job-level metadata snapshot (with secrets masked in the same manner as the detail view, per `specs/004-job-detail-view` → `FR-005`). The export MUST be generated on-demand at click time, always reflecting the latest persisted state including any feedback or new rows added since the last download. For jobs not yet in a terminal state, the export MUST be annotated as a partial snapshot consistent with `specs/004-job-detail-view` → `FR-006a`.
- **FR-016**: System MUST continue processing remaining rows when any individual row fails at any stage (connector error, normalization error, evaluator error). Per-row failures MUST NOT abort the whole job.
- **FR-017**: System MUST record per-row failures with the stage at which they failed (connector / normalization / evaluation) and the captured error detail.
- **FR-018**: System MUST run entirely on the tester's local machine: all persistence MUST use the embedded local database, and no functionality MUST require a remote server, shared service, or external account managed by the harness.
- **FR-019**: System MUST be installable via `pipx` and launchable with a single command that serves the UI on a localhost address.
- **FR-020**: System MUST version the Standard Evaluation Contract, and each evaluation agent MUST declare which contract version(s) it accepts. The harness MUST refuse to start a job whose connector emits a contract version not accepted by the chosen evaluator.
- **FR-021**: System MUST allow new connectors and new evaluation agents to be registered without modifying any existing connector, existing evaluation agent, or the core orchestration code.
- **FR-022**: System MUST reconcile jobs whose status is "running" at process startup (i.e., orphaned jobs after a restart) by transitioning them to a deterministic terminal or paused state visible to the tester rather than leaving them stuck.
- **FR-023**: System MUST snapshot the connector configuration and evaluation agent configuration onto the job at job-creation time so historical results remain interpretable even if the underlying registry entries change later.
- **FR-023a**: Within those persisted configuration snapshots, any field that the connector or evaluation agent declared as secret (e.g., API keys, auth tokens, service-account passwords contained inside the connector's own config — NOT the per-row CSV `password` which remains in-memory only per `FR-010`) MUST be **encrypted at rest** using symmetric encryption with a machine-local key. The harness MUST decrypt these values transparently at the moment they are needed for connector authentication or evaluator invocation; decrypted values MUST NEVER appear in UI rendering (per `specs/004-job-detail-view` → `FR-005`), in exports (per `specs/005-results-export` → `FR-011`), or in application logs. Key management (key location, generation, rotation) is plan-level; the spec only requires that the key is machine-local — i.e., not in the database file, not committed to source, not portable to another machine without explicit migration.
- **FR-024**: System MUST allow the tester to cancel any job that is `queued` or `running`. On cancellation the job MUST transition to a transient `cancelling` state during which: rows already in-flight at any stage (connector call, normalization, evaluation) MUST be allowed to run to natural completion or failure; rows still in `queued` state MUST be transitioned to `cancelled`; once all in-flight rows have reached a terminal per-row status, the job MUST transition to terminal `cancelled`. All rows that reached `completed`, `failed`, or `cancelled` MUST remain reviewable and exportable.
- **FR-025**: System MUST NOT retry connector or evaluator calls at the orchestration layer. Every error returned by a connector or evaluator MUST be recorded as a `failed` row with the captured cause and the stage at which it occurred (per `FR-017`). Individual connectors MAY implement their own internal retry behavior, but the harness orchestrator MUST treat each per-row connector or evaluator invocation as a single shot.

### Key Entities *(include if feature involves data)*

- **Test Job**: A single regression run. Carries: name, status (`draft` / `queued` / `running` / `cancelling` / `completed` / `failed` / `cancelled`), created-at, started-at (null while `draft`), completed-at, snapshot of the selected connector + its config, snapshot of the selected evaluation agent + its config, reference to the source CSV (null while `draft`), and a contract version expectation.
- **Test Case Row**: One row from the uploaded CSV. Carries: utterance, `testId`, credential reference, optional metadata fields preserved verbatim, status, and link to the parent Job.
- **Connector Invocation**: Per-row record of the chatbot interaction. Carries: raw outbound request shape, raw inbound response, normalized Standard Evaluation Contract instance, timestamps, error (if any), and the stage where the error occurred.
- **Evaluation Result**: Per-row evaluation output. Carries: verdict, a `scores` payload (an ordered collection of zero or more entries, each shaped `{ parameter_name: string, score: number-or-short-string, reasoning: string }` — see `FR-008a`), evaluator-specific structured fields beyond `scores` and `verdict`, the agent's raw payload, timestamps, and error (if any). The number of `scores` entries, their `parameter_name` values, and the score scales MAY differ between evaluators and between evaluator versions; uniformity across evaluators MUST NOT be assumed.
- **Tester Feedback**: Optional per-row human verdict. Carries: thumbs-up or thumbs-down, optional note, timestamp.
- **Registered Connector**: A discovered connector. Carries: identity, version, declared contract version it emits, and schema for its job-time configuration form.
- **Registered Evaluation Agent**: A discovered evaluation agent. Carries: identity, version, declared contract version(s) it accepts, and schema for its job-time configuration form.
- **Standard Evaluation Contract Version**: The canonical JSON schema that is the only integration seam between connectors and evaluation agents. Carries: version identifier and schema definition.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tester starting from a clean machine can install the harness, launch it, and start their first job in under 10 minutes.
- **SC-002**: A 100-row regression job runs to completion without manual intervention, with every row reaching a terminal per-row status (completed or failed) and never stuck mid-stage.
- **SC-003**: For any row in any completed job, the tester can locate the original input, the chatbot's response, and the evaluation result in under 30 seconds starting from the job dashboard.
- **SC-004**: A tester can run three jobs concurrently with no observable interference — each job's results, statuses, and configuration snapshots remain correct and isolated.
- **SC-005**: A completed job's exported results contain 100% of the rows from the input CSV; no rows are silently dropped.
- **SC-006**: Adding a new chatbot platform or a new evaluation strategy requires zero changes to any existing connector, any existing evaluation agent, or the core orchestrator.
- **SC-007**: Per-row credentials from the CSV are reachable by the selected connector for the duration of that row's call only. They never appear in any persisted form — not in the local database, not in any exported results file, and not in application logs — verifiable by inspecting those artifacts after any completed or failed job.
- **SC-008**: When the harness process is restarted, no job remains in "running" state — every previously-running job appears in a deterministic, tester-visible state (paused, failed, or completed) within 5 seconds of startup.
- **SC-009**: When an evaluation agent's declared accepted contract version does not match the connector's emitted contract version, the tester sees an actionable message at job-creation time, not a runtime error mid-job.
- **SC-010**: A 1,000-row job runs to completion on a typical tester laptop with the job dashboard, row list, and row detail view remaining usable (no full-page hang) throughout the run.
- **SC-011**: When a CSV upload exceeds 1,000 rows, the tester sees a clear, actionable warning at upload time stating that the job is above the supported design target; the tester may proceed at their discretion, but the harness makes no responsiveness or completion-time guarantees beyond 1,000 rows.

## Assumptions

- The tester has Python and `pipx` available locally. Bootstrapping Python itself is out of scope.
- The tester has network reachability from their laptop to the target chatbot endpoint and to whatever identity system the connector authenticates against.
- Test accounts referenced by `testId`/`password` in the CSV are pre-existing in an external identity system; the harness does not provision, rotate, or validate them out-of-band.
- The CSV's column schema is documented and stable: required columns are `utterance`, `testId`, `password`; additional columns are preserved as per-row metadata but not interpreted.
- Evaluation is non-deterministic: re-running the same row may yield a different evaluation result, and that variability is acceptable and expected by users.
- Multi-turn / context-carrying conversations across multiple CSV rows are out of scope for v1. Each row is an independent single-turn invocation.
- First-class retry of failed rows is out of scope for v1. Completed jobs are immutable; a tester who wants to re-run failed rows does so by filtering their CSV and creating a new (independent) job. There is no parent-child job linkage in v1.
- The harness is a single-user tool. Because it runs on localhost on the tester's laptop, no authentication or authorization layer is needed inside the harness itself.
- Concurrency limits (e.g., maximum simultaneous in-flight rows per job) are an implementation tuning concern, not a specification concern.
- The design target is jobs of up to 1,000 utterances. CSVs above that may still process but are out of scope for performance and UI-responsiveness guarantees.
- The export file format and the specific Standard Evaluation Contract schema content are implementation-plan decisions; the spec only requires that they be canonical, versioned, and complete.
- The fourteen internal modules referenced in the input ("foundational layers, integration layers, orchestration, UI/experience") are architectural detail and belong in the implementation plan rather than the spec.
