# Feature Specification: Job Detail & Traceability View (Module 13)

**Feature Branch**: `004-job-detail-view`

**Created**: 2026-05-28

**Status**: Draft

**Input**: User description: "Module 13 — Job Detail & Traceability View. A web UI page for a single test job, with a Job Metadata Panel (always visible) and a Results Table (one row per utterance). The metadata panel shows job name, description, status, timestamps, connector identity + full configuration (secrets masked), evaluation agent + full configuration (secrets masked), source CSV download link, and aggregate counts. The results table has columns Row Index, Utterance Text, Chatbot Response (truncated, expand-on-click), Evaluation Verdict (color-coded), Evaluation Scores, Evaluation Reasoning (truncated, expand-on-click), User Feedback (thumbs), Error Status, and testId. The table supports sorting, filtering by verdict, filtering by error status, and free-text search across utterance and response text. Every row is expandable to reveal the complete input, raw chatbot response, normalized Standard Evaluation Contract, evaluation result, and feedback. All data is viewable regardless of job status; for running jobs the table populates incrementally."

> **Parent context**: This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md` and is the navigation target of the dashboard's row-click action (`specs/002-dashboard-job-listing` → `FR-010`). Parent-spec premises apply unchanged: single-user, no authentication, no `createdBy` field. The Module 13 description's mention of "created by" was dropped (precedent from 001/002/003); the Job Metadata Panel shows no creator/user concept. The job lifecycle states and the Standard Evaluation Contract are defined by the parent spec; this module specifies only the read-and-act surface for one persisted job.

## Clarifications

### Session 2026-05-28

- Q: Is the Job Detail View the surface for cancel and delete actions, or is it read-only? → A: Detail view is the canonical action surface. It exposes **Cancel Job** for jobs in `queued` or `running` status (triggering the parent's `FR-024` soft-cancel) and **Delete Job** for jobs in `draft`, `failed`, or `cancelled` status (triggering parent `FR-001` / `FR-001a`). `completed` jobs and in-flight `cancelling` jobs are not actionable from this view. This matches the precedent set by the dashboard spec (002 Round 2: no cancel on the dashboard; cancel lives on the detail view).
- Q: Can the tester apply / change thumbs-up / thumbs-down feedback from the Job Detail View? → A: Yes — read-write. The User Feedback column in the results table is interactive. Clicking the thumbs icon on any row sets, changes, or clears feedback for that row. Persistence semantics follow parent `FR-014` (replace prior feedback; retrievable on subsequent visits).
- Q: How are secret config fields (API keys etc.) masked in the Job Metadata Panel? → A: Fully masked. Each secret field is rendered as a fixed-length placeholder (e.g. `••••••••`) with no in-UI reveal mechanism. Secrets are not retrievable from the detail view at all; the tester can re-obtain the value from wherever they originally stored it.
- Q: What is the feedback interaction model on each row? → A: Two icons per row — thumbs-up (👍) and thumbs-down (👎). Clicking an inactive icon sets feedback in that direction; clicking the currently-active icon clears it. No separate Clear control. The two icons are mutually exclusive (setting one replaces the other).
- Q: Does the detail view have a stable URL per job? → A: Yes — `/jobs/<id>` (or equivalent stable path keyed by job id). The page is deep-linkable, bookmarkable, refresh-safe, and can be opened in multiple tabs concurrently. The exact path prefix is plan-level; the requirement is that the URL identifies the specific job and that reloading the URL re-mounts the same detail view.
- Q: What does the CSV download produce when the job is still non-terminal (queued / running / cancelling)? → A: Snapshot at click time, non-blocking. The download contains every Test Case Row persisted up to the moment of the click. The file is annotated as partial — both via filename (e.g. `…-partial.csv`) and via an inline marker (e.g. a header-row comment) that names the job's status at download time and the row count. No blocking, no refusal.

### Session 2026-05-28 (Round 2)

- Q: How is the Evaluation Scores column rendered, and is it sortable? → A: The Scores column is **not sortable** at all — the sort affordance MUST be omitted from this column's header. The cell renders the structured scores payload as inline HTML (compact list or small table of `parameter_name : score` pairs, optionally truncated if it overflows column width); the full payload — including each entry's `reasoning` — is reachable via the row's existing expand-on-click affordance (`FR-008`). The rendering MUST treat the payload as structured data the harness owns the rendering of — it MUST NOT inject arbitrary HTML emitted by the evaluator into the DOM (XSS-safe). This change requires a corresponding amendment to the parent spec's Evaluation Result entity: see parent `Clarifications` 2026-05-28.

### Session 2026-05-28 (Round 3)

- Q: Do the Metadata Panel's Total / Processed / Failed counts reflect the Results Table's active filter or stay at job-level totals? → A: The Metadata Panel counts are always **job-level (global)** and do not change when filters or search are applied to the Results Table. The Metadata Panel is metadata about the Job; the Table is a view over rows. To make any gap explicit, the Results Table MUST display a small "Visible: N of M" indicator (where M is the unfiltered total visible-as-rows count and N is the count after filters/search) whenever any filter or search is active.

### Session 2026-05-29 (Round 4 — revision driven by Module 3)

- Q: Module 3 (`specs/010-tester-identity`) re-introduces an OS-derived `Job.createdBy` field. Should the Job Metadata Panel display it? → A: **Yes.** The Metadata Panel MUST display the Created By field (the persisted `Job.createdBy` from job-creation time). This reverses the pre-spec note in this spec's Parent context that said "the Job Metadata Panel shows no creator/user concept." `FR-003` and `FR-004` are updated. The "Logged in as: <user>" application-chrome indicator (per parent `FR-026`) is also present on this page, same as on every UI surface.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See the full configuration and aggregate state of one job (Priority: P1)

A QA tester clicks a row on the dashboard and lands on that job's detail page. They immediately see the Job Metadata Panel: job name, description, status (with the same color encoding as the dashboard badge), the timestamps that apply for this status, the connector identity along with its full configuration (with any secret fields rendered as fully-masked placeholders), the evaluation agent identity and its full configuration (also masked for secrets), the source CSV filename and a download affordance, and the aggregate counts (total utterances, processed, failed). They can use this panel as the single answer to "what is this job and how was it configured?"

**Why this priority**: Without the metadata panel, the detail view has no anchor. It is the MVP slice of Module 13: a single tester who navigates here from the dashboard can answer "what is this job?" before drilling into rows.

**Independent Test**: Seed the database with one job in each of `draft`, `running`, `completed`, `failed`, `cancelled` states (each with a known connector and evaluation-agent configuration including at least one secret field). For each, navigate to its detail page and verify the panel displays the persisted configuration accurately, secrets appear masked, the aggregate counts match the job's persisted rows, and the timestamps for inapplicable states are clearly absent/blank.

**Acceptance Scenarios**:

1. **Given** a persisted job in any status, **When** the tester opens its detail page, **Then** the Job Metadata Panel renders showing the job's name, description (if any), status (with the same visual encoding the dashboard uses), all applicable timestamps, connector identity + non-secret config fields shown verbatim + secret config fields masked, evaluation agent identity + same redaction treatment, source CSV filename, and the current Total / Processed / Failed counts.
2. **Given** a job whose connector configuration contains a field the connector declared as a secret, **When** the tester views the metadata panel, **Then** that field's value is rendered as a fully-masked placeholder, and there is no in-UI mechanism to reveal the underlying value.
3. **Given** a job in `draft` status, **When** the tester views the metadata panel, **Then** `started-at` and `completed-at` are visibly empty/blank (not zero/null-as-string), and the panel makes the incomplete state apparent.

---

### User Story 2 - Inspect any single utterance's complete trace (Priority: P1)

A tester scanning the results table sees a row of interest and clicks its expand control. The row reveals the complete traceability record: the full utterance input (every field from the CSV row except `password`), the raw chatbot response JSON exactly as the connector received it, the normalized Standard Evaluation Contract instance for that row, the evaluation agent's complete result JSON, and any user feedback associated with the row. This is the spec's "full traceability" promise (parent `FR-013`) made concrete for a single utterance.

**Why this priority**: Traceability is what differentiates this product from a one-shot script. Equal-priority with the metadata panel because both are required to make the detail view useful for triage; a tester can't triage with metadata alone or with a row list alone.

**Independent Test**: With a completed job containing at least one row each of `completed`, `failed`, and (optionally) error at different stages, expand each row in turn and verify the expanded panel shows the four artifacts (input, raw response, normalized contract, evaluation result) for completed rows; for failed rows, verify it shows the stage of failure and the captured error detail in place of (or alongside) the missing artifact.

**Acceptance Scenarios**:

1. **Given** a row whose per-row status is `completed`, **When** the tester expands the row, **Then** they see the complete persisted artifacts: full input (utterance + `testId` + other metadata, no `password`), raw chatbot response, normalized Standard Evaluation Contract instance, evaluation result, and any feedback.
2. **Given** a row whose per-row status is `failed`, **When** the tester expands the row, **Then** they see the stage at which it failed (per parent `FR-017` — connector / normalization / evaluation), the captured error detail, and whichever upstream artifacts exist (e.g., a normalization failure has a raw response but no normalized contract).
3. **Given** any row, **When** the expanded view is open, **Then** large JSON artifacts (raw response, normalized contract, evaluation result) render in a readable form with the option to copy each artifact to clipboard.

---

### User Story 3 - Capture or change thumbs-up / thumbs-down feedback per row (Priority: P2)

A tester triaging a job's rows wants to mark specific rows with their own verdict — "this evaluation result agrees with my read of the response", or "the chatbot's response is wrong even though the evaluator passed it." They click the thumbs-up or thumbs-down icon in the row's User Feedback column. The feedback persists, replaces any prior feedback on that row (per parent `FR-014`), and is visible on subsequent visits.

**Why this priority**: Capturing human judgment alongside AI evaluation is the parent spec's reason for keeping feedback in the data model. The detail view is the natural place to apply it (the row is in context, the response is visible, the verdict can be inspected). Lower than P1 because the spec is still useful without feedback — the row data is there to inspect; feedback is the productivity layer on top.

**Independent Test**: On any row with no prior feedback, click thumbs-up; verify the icon updates and the feedback is persisted (visible on reload). Click thumbs-down on the same row; verify it replaces the prior feedback. Click thumbs-down again on the same row (or click an explicit clear control) and verify feedback is cleared back to "none."

**Acceptance Scenarios**:

1. **Given** a row with no feedback, **When** the tester clicks the thumbs-up icon, **Then** the icon's active state changes, the change is persisted, and reloading the detail page shows the thumbs-up still applied.
2. **Given** a row whose existing feedback is thumbs-up, **When** the tester clicks thumbs-down, **Then** the existing feedback is replaced by thumbs-down (not added alongside) and the change is persisted.
3. **Given** a row with any feedback applied, **When** the tester invokes a clear-feedback affordance, **Then** the row returns to a no-feedback state and the change is persisted.

---

### User Story 4 - Slice the results table with sort, filter, and search (Priority: P2)

A tester investigating a job with hundreds of rows wants to focus on a slice: only the rows the evaluator marked `fail`, only rows that errored out, a specific `testId`'s rows, or rows whose utterance or response contains some substring (e.g., a product name). They apply combinations of: sort by any column, filter by evaluation verdict, filter by error status (failed rows only), filter by `testId`, and free-text search across utterance text and response text. The table reflects every change live; all filters and search combine multiplicatively.

**Why this priority**: A table with no slicing is useless past a few dozen rows. Equal priority with P3 because both are usability multipliers on top of the P1 read surface.

**Independent Test**: With a job containing at least 50 rows mixing verdicts and at least one `failed` row and at least two distinct `testId`s, apply each filter type in isolation and combination, type substring search queries, and toggle column sort. Verify the table reflects the correct intersection at each step.

**Acceptance Scenarios**:

1. **Given** the results table is populated, **When** the tester applies the verdict filter to `fail`, **Then** only rows with verdict `fail` are visible.
2. **Given** the results table is populated, **When** the tester applies the error-status filter, **Then** only rows whose per-row status is `failed` are visible (regardless of evaluation verdict on rows that did complete).
3. **Given** the results table is populated, **When** the tester selects one or more `testId` values from the `testId` filter, **Then** only rows whose `testId` is in the selected set are visible.
4. **Given** a substring search query is typed, **When** the table refreshes, **Then** rows whose utterance text OR normalized chatbot response text contains the substring (case-insensitive) are visible; rows containing the substring only inside the raw response JSON, evaluation reasoning, or other fields are NOT included by this search (those are searchable only by expanding the row).
5. **Given** any combination of filters and search is active, **When** any single filter or the search query is changed, **Then** the visible row set is the intersection of all active predicates, computed live.
6. **Given** the tester activates a column header, **When** the table renders, **Then** rows sort ascending by that column; a second activation toggles to descending; the active sort indicator is shown.

---

### User Story 5 - Watch a running job populate the table incrementally (Priority: P2)

A tester who just started a job from the wizard arrives on the detail page (or navigates to it from the dashboard). The job's status is `running` and rows arrive one by one as the orchestrator processes the CSV. The Metadata Panel's Processed and Failed counts update; new rows appear in the table; the tester does not need to refresh the page. When the job reaches a terminal state, the table is complete and stops updating.

**Why this priority**: Live population is what makes the detail view useful during a run, not just after. Equal priority with sort/filter/search because both are productivity layers on the static read surface.

**Independent Test**: Start a job that takes long enough to be observable. On a separate browser, open its detail page before the job finishes. Without interacting, verify (a) the row count and Processed / Failed counters increment over time within the parent spec's update-latency ceiling (≤ 5 seconds); (b) when the job reaches a terminal state, the table stops issuing update activity for that page.

**Acceptance Scenarios**:

1. **Given** the detail page is open for a `running` job, **When** the orchestrator persists a new row's result to the database, **Then** that row appears in the table and the Processed / Failed counts in the Metadata Panel update, both within ≤ 5 seconds and without page refresh.
2. **Given** the detail page is open for a `running` job, **When** the job transitions to a terminal status (`completed` / `failed` / `cancelled`), **Then** the status badge and timestamps in the Metadata Panel update accordingly, the table reaches its final row count, and update activity ceases.
3. **Given** the detail page is open for a `running` job and the tester has an active filter or sort applied, **When** new rows arrive, **Then** they are inserted into the table respecting the active sort and filter (consistent with the dashboard's `FR-008a` live re-evaluation pattern).

---

### User Story 6 - Cancel a running (or queued) job, or delete a finished one, from the detail view (Priority: P2)

A tester reviewing a running job realizes something is wrong (wrong CSV, wrong connector config, runaway evaluation) and wants to stop it. They click Cancel; the job transitions through `cancelling` to terminal `cancelled` per the parent spec's soft-cancel semantics, and all rows already in flight finish naturally. Separately, a tester reviewing a `draft`, `failed`, or `cancelled` job that they no longer need clicks Delete; after confirmation, the job and all its rows are permanently removed.

**Why this priority**: These are the canonical job-level actions; the detail view is the only surface where they live (the dashboard's row-level delete is for `failed` / `cancelled` only and dashboard has no cancel). Equal priority with the other P2 productivity stories.

**Independent Test**: With one job in `running`, click Cancel; verify the status transitions to `cancelling` then to `cancelled` per parent `FR-024`, in-flight rows complete naturally, queued rows are marked `cancelled`, and the metadata panel reflects the terminal state. With one job in `failed`, click Delete; confirm; verify the job and all its rows are removed and the tester is routed back to the dashboard.

**Acceptance Scenarios**:

1. **Given** a job in `queued` or `running` status, **When** the tester clicks Cancel and confirms, **Then** the parent's soft-cancel sequence runs (`FR-024`): the job transitions to `cancelling`, in-flight rows are allowed to finish, queued rows are marked `cancelled`, the job reaches terminal `cancelled` once all in-flight rows have terminated. All updates are reflected on the detail page in real time.
2. **Given** a job in `cancelling` status, **When** the tester views the detail page, **Then** the Cancel control is not available (the cancel is already in progress) and the Delete control is not available either.
3. **Given** a job in `draft`, `failed`, or `cancelled` status, **When** the tester clicks Delete and confirms, **Then** the job and all its persisted rows are removed (per parent `FR-001` / `FR-001a`), and the tester is navigated back to the dashboard. The dashboard's list no longer contains the deleted job.
4. **Given** a job in `completed` or `running` status, **When** the tester views the detail page, **Then** the Delete control is not available (completed jobs are retained as historical record per `FR-001a`; running jobs must be cancelled first).
5. **Given** the tester triggers Cancel on a job that has already reached a terminal status in the background (race condition), **When** the action attempts to execute, **Then** the harness declines with an actionable message naming the current status, rather than corrupting state.

---

### Edge Cases

- The job's source CSV download is requested but no rows have been persisted yet (e.g., a `draft` job whose Step 2 was completed but Step 5 was never Started, or a `running` job where the first row hasn't completed) — the download should produce a valid CSV with header row but zero data rows, not an error.
- The source CSV download is requested for a job whose connector was never resolved (a brand-new `draft` that never crossed Step 2) — the download affordance is hidden or disabled with an explanatory tooltip.
- A row whose evaluation produced a malformed or unparseable scores object — the Scores column shows a "(unparseable)" placeholder and the expand-on-click full-trace view shows the raw structure for forensic inspection.
- A row whose evaluation reasoning is empty / null — Reasoning column shows an explicit "(none)" placeholder distinct from a missing-row state.
- The tester filters to only `fail` verdict, then a `running` job's newly-arrived row matches — that row appears live (consistent with `FR-008a`-equivalent live re-evaluation, see User Story 5 Scenario 3). Conversely, a row whose verdict changes (rare: feedback edits do not change verdict, but error-status changes during a race could move a row out of the filtered set) disappears live.
- The tester applies feedback to a row, then deletes the job — feedback is removed along with the row data; no orphan feedback persists.
- The metadata panel's connector configuration is from a connector identity that has been unregistered from the harness since the job was created — the panel still renders the snapshotted config from the job record (per parent `FR-023`); a small annotation indicates the connector is no longer available system-wide.
- Same as above for the evaluation agent.
- The detail page is open in two browser tabs and the tester applies feedback in one — the other tab reflects the new feedback within the auto-update ceiling.
- The detail page is open while another surface (the dashboard's bulk "Clear all failed and cancelled" action) deletes this very job — the detail page detects the deletion and routes the tester back to the dashboard with a non-blocking notice that the job was deleted elsewhere.
- The tester clicks Delete, confirms, and the deletion fails (e.g., DB write error) — the job remains intact, the tester sees an actionable error, and the detail page reflects the unchanged state.
- A row's Utterance Text or Response is very long (multi-paragraph) — the truncated cell preview uses a deterministic truncation length so column widths stay stable; expand-on-click reveals the full text. The same applies to Evaluation Reasoning.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST render a per-job detail page reachable from the dashboard's row-click navigation (`specs/002-dashboard-job-listing` `FR-010`). The page MUST be served at a stable, deep-linkable URL keyed by the job's id (e.g. `/jobs/<id>` or an equivalent stable path; the exact prefix is plan-level). Reloading the URL MUST re-mount the same detail view; the URL MUST be openable in multiple browser tabs concurrently; browser Back / Forward MUST navigate through detail views correctly.
- **FR-002**: The page MUST contain two regions: a Job Metadata Panel (always visible at the top or side) and a Results Table (below or alongside the panel) showing one row per persisted Test Case Row.
- **FR-003**: The Job Metadata Panel MUST display: job name, optional description, status (with the same color encoding as the dashboard), **Created By** (the persisted `Job.createdBy`, OS-derived per parent `FR-026`), `created-at`, `started-at` (blank while `draft`), `completed-at` (blank until terminal), connector identity + full snapshotted configuration with secret-declared fields fully masked, evaluation-agent identity + full snapshotted configuration with secret-declared fields fully masked, source-CSV filename, source-CSV download affordance, total utterance count, processed count, and failed count. The total / processed / failed counts MUST always reflect the **job's full persisted state** and MUST NOT change when the Results Table's filters or search are active — these are job-level metadata, not a view of the visible rows.
- **FR-004**: The Job Metadata Panel's Created By field (per `FR-003`) MUST display the persisted OS-derived `Job.createdBy` value verbatim. The harness MUST NOT expose any UI control to override or edit this value from the detail view. On a single-user laptop, the field will typically show the OS account name; on a shared laptop the value reflects whichever OS user created the job. There is still no authentication / login concept anywhere in the detail view.
- **FR-005**: Secret-declared config fields MUST be rendered as a fixed-length placeholder (e.g. `••••••••`) with no UI control to reveal them. The detail view MUST NOT expose any path by which the underlying secret value can be retrieved.
- **FR-006**: The source-CSV download MUST produce a CSV reconstructed from the job's persisted Test Case Rows at the moment of the click. The reconstructed CSV MUST contain the `utterance`, `testId`, and any preserved-metadata columns, in their original order. It MUST NOT contain the `password` column or any password value (per parent `FR-010`). The file MUST be marked clearly so the tester knows it is reconstructed rather than the verbatim file they uploaded (e.g. filename suffix `-reconstructed.csv` and/or a header-row marker).
- **FR-006a**: If the job's status at the moment of the click is non-terminal (`queued`, `running`, or `cancelling`), the download MUST be non-blocking and MUST contain only the rows persisted up to that moment. The file MUST be additionally annotated as partial — both via filename (e.g. `-partial.csv` in addition to `-reconstructed.csv`) AND via an inline marker naming the job's status at download time and the row count included. The download MUST NOT wait for further rows and MUST NOT refuse to produce a file.
- **FR-007**: The Results Table MUST display one row per persisted Test Case Row, with the following columns in canonical order: Row Index, `testId`, Utterance Text (truncated, expand-on-click for the full value), normalized Chatbot Response text (truncated, expand-on-click), Evaluation Verdict (color-coded — at minimum `pass`, `fail`, and a third "warn"/non-pass category if the evaluator emits one), Evaluation Scores (structured HTML rendering — see `FR-007a`), Evaluation Reasoning (truncated, expand-on-click), User Feedback (interactive thumbs icon — see `FR-010`), Error Status (a per-row status indicator; expandable to show error detail for `failed` rows).
- **FR-007a**: The Evaluation Scores column MUST render the row's scores payload as a compact, structured HTML representation produced by the harness (e.g., an inline list or small table of `parameter_name : score` pairs, one per scores entry). Per-entry `reasoning` MAY be truncated/omitted from the in-cell rendering and reached via the row expand. The harness MUST own the HTML rendering of this payload and MUST NOT inject arbitrary HTML or script that the evaluator may have included in its raw output into the DOM. The full structured payload (all entries with their full `reasoning`) MUST be reachable via the row's expand-on-click affordance (`FR-008`). The shape of an individual scores entry is defined by the parent spec's Evaluation Result entity (`parameter_name`, `score`, `reasoning`).
- **FR-008**: Every row MUST support an expand affordance that reveals the row's complete persisted artifacts: full utterance input (excluding `password`), the raw chatbot response in full, the normalized Standard Evaluation Contract instance in full, the complete evaluation result, and any persisted feedback. For `failed` rows, the expanded view MUST also surface the failure stage (per parent `FR-017`) and the captured error detail.
- **FR-009**: The expanded view MUST allow the tester to copy each large JSON artifact (raw response, normalized contract, evaluation result) to the clipboard with a single action.
- **FR-010**: The User Feedback column MUST be interactive and render two icons per row: thumbs-up (👍) and thumbs-down (👎). The interaction model is:
  - Clicking an inactive icon MUST set feedback in that direction (persisted per parent `FR-014`) and visually mark it active.
  - The two icons MUST be mutually exclusive: setting one when the other is active MUST replace the prior feedback (not add to it).
  - Clicking the currently-active icon MUST clear feedback for that row (return to a no-feedback state) and persist the cleared state.
  - All persistence MUST be immediate; reloading the page MUST show the same icon state.
  - There MUST NOT be a separate explicit Clear control; clearing is done by clicking the active thumb again.
- **FR-011**: The Results Table MUST support sorting by any displayed column ascending or descending, **except the Evaluation Scores column, which MUST NOT be sortable**. The Scores column's header MUST omit any sort affordance (no clickable header, no sort indicator). Reason: the scores payload's shape, parameter count, parameter names, and score scales vary between evaluators and even between evaluator versions; no deterministic cross-row ordering exists. Sort by Verdict MUST use a fixed verdict ordering (e.g., `fail` > `warn` > `pass`).
- **FR-012**: The Results Table MUST provide filters for: Evaluation Verdict (multi-select), error status (toggle: show only `failed` rows), and `testId` (multi-select; option set is the distinct `testId` values present in this job's rows).
- **FR-013**: The Results Table MUST provide a free-text search input that filters visible rows by case-insensitive substring match against (a) the Utterance Text and (b) the normalized Chatbot Response text. Other fields are NOT included in this search (they remain reachable via row expansion).
- **FR-014**: Active filters and the search query MUST combine multiplicatively (AND): only rows that match every active predicate MUST be visible.
- **FR-014a**: When any filter or search is active on the Results Table, the table MUST display a clearly-visible "Visible: N of M" indicator near the table header, where M is the total persisted row count for the job and N is the count after applying all active filters and the search query. The indicator MUST update live as filters/search change and as new rows arrive in non-terminal jobs (per `FR-015` / `FR-017`). When no filter and no search is active, the indicator MAY be hidden (or shown as "Visible: M of M") — the spec does not require it to remain visible in the unfiltered case.
- **FR-015**: For jobs in non-terminal status (`queued`, `running`, `cancelling`), the detail page MUST receive incremental updates: newly-persisted rows MUST appear in the table; the Metadata Panel's Processed and Failed counts MUST update; the status badge and timestamps MUST update on status transitions; all updates MUST land within ≤ 5 seconds of the underlying database change, without manual refresh. (Mechanism — polling vs. push — is plan-level, consistent with parent `FR-012`.)
- **FR-016**: For jobs in terminal status (`completed`, `failed`, `cancelled`), the detail page MUST NOT continue polling/subscribing for row-list updates. (Row-level feedback edits still write through to the database.)
- **FR-017**: Newly-arrived rows in a `running` job MUST respect any active sort and filter — they enter the table according to the active sort order, and they are visible only if they pass every active filter and the search query.
- **FR-018**: The page MUST expose a **Cancel Job** control if and only if the job's status is `queued` or `running`. Activating it MUST prompt for confirmation; on confirmation, the harness MUST initiate the parent's `FR-024` soft-cancel sequence. The Cancel control MUST become unavailable as soon as the job transitions to `cancelling`.
- **FR-019**: The page MUST expose a **Delete Job** control if and only if the job's status is `draft`, `failed`, or `cancelled`. Activating it MUST prompt for confirmation; on confirmation, the harness MUST permanently delete the job and all its persisted rows (per parent `FR-001` for `draft`, `FR-001a` for `failed` / `cancelled`), and MUST navigate the tester back to the dashboard. The Delete control MUST NOT appear for `completed`, `queued`, `running`, or `cancelling` jobs.
- **FR-020**: If a job being viewed is deleted by another surface (e.g., the dashboard's bulk-clear action) while the detail page is open, the page MUST detect the deletion within ≤ 5 seconds and navigate the tester back to the dashboard with a non-blocking notice that the job no longer exists.
- **FR-021**: All data on the detail page MUST be viewable regardless of job status. There MUST be no status-gated content beyond what the action controls themselves expose (Cancel vs. Delete vs. neither).

### Key Entities *(include if feature involves data)*

- **Job Detail Projection**: The composite view rendered on the page. Sourced from one Test Job (parent spec), its snapshotted connector + config and evaluation agent + config, all of its persisted Test Case Rows, every row's Connector Invocation and Evaluation Result, and any Tester Feedback applied to those rows. Aggregate counts (Total / Processed / Failed) are derived on read.
- **Row Detail Projection**: The expanded-row payload. Carries the row's full input (excluding `password`), raw response, normalized contract instance, evaluation result, error detail (if any), and feedback (if any).
- **Reconstructed CSV**: A read-time artifact built from the job's Test Case Rows for download. Header reflects the columns persisted at job-creation time minus `password`. Never includes credential values.
- **Detail View State** *(transient, client-side)*: The active sort, filters, search query, and expand state per row. Not persisted across page reloads in v1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When the tester clicks any job row on the dashboard, the detail page renders its Metadata Panel and at least the first screen of the Results Table within 1 second for jobs of any size up to the parent spec's 1,000-row design target.
- **SC-002**: For any persisted row, the tester can reach the row's full traceability record (full input + raw response + normalized contract + evaluation result + feedback) in exactly one tester action (expand) starting from the visible row.
- **SC-003**: A connector or evaluation-agent secret-declared field is verifiable as never appearing in plaintext in the rendered metadata panel, regardless of which job is viewed (test by inspecting the rendered HTML / DOM for any of the underlying secret values).
- **SC-004**: For a `running` job, a row persisted in the database appears on the detail page within ≤ 5 seconds without manual refresh; the Metadata Panel's Processed and Failed counters reach the new totals within the same window.
- **SC-005**: Applying or changing thumbs feedback on any row persists within 1 second of the click and is visible on subsequent page loads.
- **SC-006**: The Cancel control is visible exactly when status ∈ {`queued`, `running`} and never otherwise — verifiable by enumerating the seven status states.
- **SC-007**: The Delete control is visible exactly when status ∈ {`draft`, `failed`, `cancelled`} and never otherwise — verifiable by enumerating the seven status states.
- **SC-008**: A successful Delete returns the tester to the dashboard within 2 seconds; the dashboard view does not include the deleted job on the immediate next render.
- **SC-009**: The reconstructed source-CSV download for any job contains exactly the same number of data rows as the job's persisted Test Case Rows **at the moment of the click**, with the `password` column absent and all other persisted CSV columns present in their original order. For non-terminal jobs, the file's filename and inline marker both indicate that the download is partial and name the job's status and row count at download time.
- **SC-010**: Applying a verdict filter, an error-status filter, a `testId` filter, or a free-text search query updates the visible row set within 200 ms (excluding initial load) for a job at the 1,000-row design target.

## Assumptions

- This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md`. The parent's "single-user, no auth, localhost" model applies. There is no `createdBy` field on jobs.
- Module dependencies — the parent's `Connector Invocation`, `Evaluation Result`, and `Tester Feedback` entities are the source of row data; the parent's `Test Job` and its snapshotted configurations are the source of metadata-panel data. The orchestrator that produces row records is the Job Execution Engine (Module 10, TBD).
- The verbatim CSV file uploaded at Step 2 of the wizard is **not** retained on disk verbatim — only the persisted Test Case Rows are. Therefore the "download source CSV" affordance produces a CSV reconstructed from persisted rows, not a byte-for-byte copy. The reconstructed CSV is clearly marked as such (`FR-006`).
- Secret-field declaration is the responsibility of each connector and each evaluation agent (parent `FR-021` allows connectors/agents to be added without code changes elsewhere; the secret-field declaration is part of their declared config schema). The detail view simply honors those declarations.
- The third evaluation verdict category beyond `pass` / `fail` (e.g., `warn`) is a presentation feature in this spec; the actual set of verdict values an evaluator emits is governed by the parent's Standard Evaluation Contract, not by this module.
- Per-tester preferences (saved filter sets, default sort, default expand state) are out of scope for v1. Detail-view state resets each page load.
- The Evaluation Scores column is intentionally NOT sortable. The scores payload's shape, parameter count, and scales vary between evaluators (and between evaluator versions), so no deterministic cross-row ordering exists. See `FR-011`.
- "Truncated with expand-on-click" applies to Utterance Text, Chatbot Response (normalized text), and Evaluation Reasoning. The exact truncation length is a plan-level UI decision; the spec only requires that the truncation be deterministic and that the full value be reachable in one click.
- Re-running a job from the detail view is out of scope for v1, consistent with the parent spec's "no first-class retry" decision. Testers wanting to re-run filter their CSV and create a new job via Module 9.
