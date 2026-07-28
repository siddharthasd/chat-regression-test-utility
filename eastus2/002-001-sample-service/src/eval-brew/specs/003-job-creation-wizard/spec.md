# Feature Specification: Job Creation & Configuration Wizard (Module 9)

**Feature Branch**: `003-job-creation-wizard`

**Created**: 2026-05-28

**Last Amended**: 2026-05-29

**Status**: Draft

**Input**: User description: "Module 9 — Job Creation & Configuration Wizard. A guided five-step web UI (and corresponding backend API) that walks the tester through (1) creating and naming the job, (2) uploading the test CSV, (3) selecting and configuring a chatbot connector, (4) selecting and configuring an evaluation agent, and (5) reviewing and starting. Each step's data is auto-saved to a Draft job in the database so the wizard can be resumed from any point. Back/Next navigation between steps preserves all entered data. On final 'Start', the job transitions out of Draft and the Job Execution Engine takes over."

> **Parent context**: This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md` and is the navigation target of the dashboard's "Create New Job" entry point (`specs/002-dashboard-job-listing` → `FR-011`). Parent-spec premises apply unchanged: single-user, no authentication on the wizard (no login challenge). The original Module 9 description's mention of "captures createdBy from the **authenticated session**" was dropped by explicit decision (2026-05-28) — there is no authentication. **Note: Round 2 (driven by Module 3) reversed the no-`createdBy` precedent**: the wizard now auto-stamps `Job.createdBy` from the OS-derived tester identity (parent `FR-026`) on Step 1 Next. The tester does not see or edit `createdBy` from any wizard form — it remains system-derived. The job lifecycle (`draft` → `queued` → `running` → terminal `completed` | `failed` | `cancelled`, with `cancelling` as the transient state on the path to `cancelled`) is defined by the parent spec; this module only specifies what happens at the `draft` → `queued` boundary. The original Module 9 description's "transition Draft to Running" was resolved by explicit decision (2026-05-28) to mean **`draft` → `queued`**; the Job Execution Engine (Module 10) is responsible for the subsequent `queued` → `running` transition asynchronously. **Reshape note (2026-05-29):** Step 3 and Step 4 no longer render per-job configuration forms — connector and evaluator endpoint configuration (URL, auth, timeout, etc.) lives on the registration in the new CRUD modules (`013` for connectors, `014` for evaluators). The wizard's Step 3 / Step 4 reduces to a dropdown of registered, non-archived instances; selection is required to advance; the full registration is snapshotted onto the Job on Next.

## Clarifications

### Session 2026-05-28

- Q: On "Start Job", what status does the job transition to? → A: `draft` → `queued`. Matches the parent spec's lifecycle. The wizard does not synchronously trigger execution; it enqueues. The Job Execution Engine (Module 10) picks up `queued` jobs and transitions them to `running`. The UI button text remains "Start Job".
- Q: How is wizard progress persisted as a Draft job? → A: Auto-save on every step transition. Pressing Back/Next persists the current step's data to the Draft job in the database before navigating. There is no explicit "Save Draft" button; the Draft is always current up to the last step boundary the tester crossed. Closing the browser mid-step loses only data entered on the current (unsubmitted) step.

### Session 2026-05-29 (Round 2 — revision driven by Module 3)

- Q: Module 3 (`specs/010-tester-identity`) re-introduces an OS-derived `Job.createdBy` field. Does the wizard auto-populate it on Step 1 Next? → A: **Yes.** On the Step 1 Next that creates the Draft Job, the wizard MUST auto-stamp `Job.createdBy` with the harness's OS-derived tester identity (per parent `FR-026`). The field is NOT exposed in any wizard form — the tester cannot see it, cannot edit it, cannot override it. This reverses the Parent-context note at the top of this spec that said "no `createdBy` field anywhere"; only the persistence direction reversed — there is still no auth flow and no login.

### Session 2026-05-29 (Reshape)

- Q: With connectors and evaluators now remote services managed via CRUD modules (`013`, `014`), what does the wizard's Step 3 and Step 4 look like? → A: **Each step becomes a single required dropdown of registered, non-archived instances**, sourced from `013`'s read API for Step 3 (per `007 FR-009`/`FR-010`) and `014`'s read API for Step 4 (per `008 FR-008`/`FR-009`). No per-job configuration form is rendered — endpoint, auth credentials, timeout, and (for connectors) the expects-per-row-password flag all live on the registration, not the job. Selection is required; the wizard MUST NOT permit advancing past Step 3 without a registered connector selected, nor past Step 4 without a registered evaluator selected. There is no free-form name input. If the dropdown is empty (no registrations exist in the relevant CRUD module), the wizard MUST surface a clear affordance to navigate the tester to `013` / `014` to register one before continuing.
- Q: Per-job override of `connectorName` / `evaluationAgentName` (which earlier rounds allowed) — is that still in the wizard? → A: **Removed.** The display name on the Job snapshot is the registration's `displayName` at the moment of job creation. The tester does NOT edit it from the wizard. If the tester wants a different name for a different job, they edit the registration in `013` / `014` (which forward-only affects future jobs per parent `FR-023`), or they register a second instance with the desired name. This simplifies the model and removes a source of cross-spec confusion (one source of truth for the human-readable name: the registration).
- Q: The previous `FR-014` "contract-version compatibility check before Start" — does it still apply? → A: **No, deprecated for v1.** In the remote-service model neither the connector registration nor the evaluator registration declares a contract version at registration time. Runtime validation catches mismatches: a connector returning a contract with an unsupported `contractVersion` is rejected per `006 FR-015` as `errorStage = "connector_normalization"`; the row fails with an actionable detail, subsequent rows proceed (per `012 FR-011`–`FR-012`). Future work MAY add contract-version declaration on the registration if real-world experience justifies the additional registration UX; out of scope for v1.
- Q: The previous `FR-009` "Test Connection" affordance in the wizard — does it still apply? → A: **Moved to `013` / `014`.** The "Test connection" button now lives on the registration form per `013 FR-021`–`FR-025` and `014 FR-026`–`FR-030`. It does not appear in the wizard. (A registration-time test is more durable: it runs once when the endpoint is set up, not once per job creation.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a new job end-to-end through the five steps (Priority: P1)

A QA tester clicks "Create New Job" on the dashboard and lands on Step 1 of the wizard. They name the job, advance through Step 2 (CSV upload, validation, summary), Step 3 (pick a registered connector), Step 4 (pick a registered evaluation agent), and Step 5 (review). They click "Start Job"; the wizard hands the job off to the Job Execution Engine and returns the tester to the dashboard, where the new job is visible in `queued` status (and will shortly transition to `running` as the engine picks it up).

**Why this priority**: This is the entire purpose of the module. Without a working happy path, nothing else matters. It is the MVP slice.

**Independent Test**: With stubs for the dashboard, CSV Upload & Validation Service (Module 8), Connector Registry (sourced from `013`), Evaluation Agent Registry (sourced from `014`), and Job Execution Engine (Module 10), open the wizard at Step 1, complete every step with valid inputs, click "Start Job", and verify (a) the persisted Job record has the expected name, CSV reference, snapshotted connector identity + endpoint + auth + timeout + expects-per-row-password, snapshotted evaluator identity + description + endpoint + auth + timeout + declared scoring dimensions, and `queued` status; (b) the engine received a job-enqueued signal for that job.

**Acceptance Scenarios**:

1. **Given** the tester is on Step 1 with an empty form, **When** they enter a job name and click Next, **Then** a Job record is created in `draft` status with the entered name, an auto-generated `createdAt` timestamp, `createdBy` auto-stamped from the OS-derived tester identity (parent `FR-026`), and they advance to Step 2.
2. **Given** the tester is on Step 2 with a valid CSV selected, **When** they click Next, **Then** the CSV is validated via Module 8 (with the password column requirement determined by the selected connector's `expectsPerRowPassword` flag — see `011`), a summary (utterance count and distinct-testId count) is displayed, and on a successful validation result the wizard advances to Step 3. (Note: Step 2's password-column requirement depends on the Step 3 selection. The wizard either (a) defers password-column validation until after Step 3 is selected — re-running validation if needed — or (b) accepts the CSV with the password column always optional at Step 2 and re-validates on the Step-3-to-Step-4 transition. Plan-level choice.)
3. **Given** the tester is on Step 3 and the registry has at least one active (non-archived) `ConnectorRegistration`, **When** they open the connector dropdown, **Then** the dropdown lists every active registration by its `displayName` (with the short tail of `connectorId` appended for disambiguation when display names collide, per `013`'s rules). On selecting one and clicking Next, the full registration (`connectorId`, `displayName` as `connectorName`, `endpointUrl`, `authDescriptor`, `timeoutSeconds`, `expectsPerRowPassword`) is snapshotted to the Draft Job and the wizard advances to Step 4.
4. **Given** the tester is on Step 4 and the registry has at least one active (non-archived) `EvaluationAgentRegistration`, **When** they open the evaluator dropdown, **Then** the dropdown lists every active registration by its `displayName` (with disambiguation as in scenario 3). On selecting one and clicking Next, the full registration (`evaluationAgentId`, `displayName` as `evaluationAgentName`, `description`, `endpointUrl`, `authDescriptor`, `timeoutSeconds`, `declaredScoringDimensions`) is snapshotted to the Draft Job and the wizard advances to Step 5.
5. **Given** the tester is on Step 5 looking at a read-only summary, **When** they click "Start Job", **Then** the job's status transitions from `draft` to `queued`, a `startedAt` timestamp is recorded, the Job Execution Engine (Module 10) is signaled to pick the job up, and the tester is routed back to the dashboard with the new job visible.

---

### User Story 2 - Resume a Draft job exactly where it was left (Priority: P2)

A tester begins creating a job but stops partway (closes the browser, walks away, or returns to the dashboard). The Draft job persists in the database. When the tester returns and opens the Draft, the wizard re-opens at the step they last completed, with every prior step's data pre-filled and editable. They continue from there to completion.

**Why this priority**: Real-world tester workflows include interruptions and multi-session job authoring. Without resumability, every interruption is a redo. The MVP works without resume (one-sitting authoring), but resume is what makes the wizard usable in practice.

**Independent Test**: Begin a wizard, complete Step 1 and Step 2 with valid inputs (so they auto-save), close the browser tab without finishing. From the dashboard, open the Draft job and verify (a) the wizard opens at Step 3 (the next un-entered step) with Steps 1 and 2 pre-filled and editable; (b) advancing through the remaining steps and clicking Start succeeds.

**Acceptance Scenarios**:

1. **Given** a Draft job that has completed data for Steps 1 and 2 only, **When** the tester opens it from the dashboard, **Then** the wizard opens at Step 3 with all Step-1 and Step-2 fields pre-filled with the persisted values.
2. **Given** any Draft job whose data covers all five steps, **When** the tester opens it, **Then** the wizard may open directly at Step 5 (review) with full summary visible and a working "Start Job" control.
3. **Given** a Draft job whose persisted `connectorId` references a `ConnectorRegistration` that has since been archived (per `013 FR-014`) or hard-deleted (per `013 FR-018`), **When** the tester opens it and reaches Step 3, **Then** the wizard surfaces an actionable message (the connector is no longer available) and requires the tester to select a different active registration before proceeding. The persisted snapshot fields for the prior selection are discarded on the new selection.
4. **Given** a Draft job whose persisted `evaluationAgentId` references a `EvaluationAgentRegistration` that has since been archived or hard-deleted, **When** the tester opens it and reaches Step 4, **Then** the same behavior applies: actionable message, must re-select, prior snapshot discarded.

---

### User Story 3 - Navigate freely backward and forward without losing data (Priority: P2)

A tester partway through the wizard wants to revisit an earlier step (e.g., to change the connector after seeing the review screen). They click Back, edit the prior step, click Next, and arrive back at the next step with the change applied. No previously-entered data on later steps is lost, except where the change to an earlier step logically invalidates a later step's data (e.g., changing the connector resets nothing on the evaluator side, because there are no per-job configuration forms anymore — only registration snapshots — and connector vs. evaluator are independent registrations).

**Why this priority**: Coupled with auto-save (P2-resumability), free navigation makes the wizard a real authoring surface rather than a one-shot funnel. Equal priority with resume because both are usability multipliers on top of the P1 happy path.

**Independent Test**: Complete Steps 1–4 of the wizard with valid data, arrive at Step 5, click Back twice to land on Step 3, change the connector selection, click Next, arrive at Step 4 with its prior data intact (because there's no per-connector config form anymore that would have been invalidated), complete Step 4 review if needed, arrive at Step 5 with the updated summary.

**Acceptance Scenarios**:

1. **Given** the tester is on Step N with prior step data persisted, **When** they click Back, **Then** the wizard opens Step N-1 with all of its previously-entered values pre-filled.
2. **Given** the tester edits Step 1 (rename) or Step 2 (re-upload CSV), **When** they click Next, **Then** Steps 3 and 4's previously-selected registrations are preserved (the change does not invalidate connector or evaluator choice).
3. **Given** the tester changes the selected connector on Step 3, **When** they advance to Step 4, **Then** the new connector's snapshot is persisted (replacing the prior connector snapshot on the Draft); Step 4's evaluator selection is preserved. If the new connector's `expectsPerRowPassword` differs from the prior selection's, Step 2's CSV validation MAY need to be re-run (plan-level UX — either auto-rerun and surface any new errors, or warn the tester to revisit Step 2).
4. **Given** the tester changes the selected evaluation agent on Step 4, **When** they advance to Step 5, **Then** the new agent's snapshot is persisted and Step 5's summary reflects the new selection.

---

### User Story 4 - Validate the CSV before proceeding and surface what was found (Priority: P2)

At Step 2 the tester uploads a CSV. The wizard hands the file to the CSV Upload & Validation Service (Module 8). If validation fails, the wizard displays the per-row issues and refuses to advance. If validation succeeds, the wizard displays a compact summary of what's in the CSV — the parsed utterance count and the count of distinct `testId` values — so the tester can sanity-check before continuing.

**Why this priority**: CSV problems are the single most common source of broken regression runs. Surfacing them at upload time, with actionable error detail, prevents wasted job runs and saves triage time. Equal priority with resume/navigation because the wizard is unusable without an honest validation gate at Step 2.

**Independent Test**: Upload three CSVs in sequence to a wizard at Step 2: (a) a malformed CSV, (b) a CSV that's valid but has duplicate `testId`s, (c) a clean CSV. Verify (a) is rejected with actionable per-row errors and Next is disabled, (b) is accepted but the summary calls out the duplicate-testId count, (c) is accepted with a clean summary and Next enables.

**Acceptance Scenarios**:

1. **Given** the tester has selected a CSV file, **When** they invoke the upload, **Then** the wizard delegates validation to Module 8 and waits for the result. The presence-required status of the `password` column depends on the Step 3 selection's `expectsPerRowPassword` flag (per `011`); when Step 3 has not yet been completed, the validator treats `password` as optional, and any missing-password detection is deferred to the Step-3-to-Step-4 transition.
2. **Given** validation returns failure, **When** the wizard renders the result, **Then** the per-row error detail (row number, column, reason) is shown and the Next control is disabled until a valid CSV is uploaded.
3. **Given** validation returns success, **When** the wizard renders the result, **Then** the summary displays the parsed utterance count and the count of distinct `testId` values, and the Next control becomes enabled.

---

### User Story 5 - Direct the tester to register a connector or evaluator when none exist (Priority: P2)

A tester opens the wizard on a fresh install (or in a configuration where the relevant registry is empty). At Step 3, the connector dropdown is empty; the wizard surfaces a prominent affordance — link, button, or inline call-to-action — that navigates the tester to `013`'s registry-management UI to register one. After the tester registers a connector and returns to the wizard (the Draft is preserved per US2), the dropdown is populated. Same for Step 4 if no evaluator is registered.

**Why this priority**: A fresh install is the most common first-time experience. Without a clear path forward when the registry is empty, testers get stuck on a blank dropdown. P2 because experienced testers will have registrations in place; the affordance is critical for new testers / fresh installs.

**Independent Test**: On a fresh install with no connector registrations, open the wizard, reach Step 3, verify the empty-state affordance is visible and navigates to `013`. Register a connector in `013`. Return to the wizard (Draft preserved). Verify the dropdown now lists the new registration.

**Acceptance Scenarios**:

1. **Given** Step 3 is reached and `013`'s read API returns zero active registrations, **When** the wizard renders Step 3, **Then** the connector dropdown is hidden (or rendered as a disabled empty control) and a prominent affordance is shown directing the tester to register a connector at `013`'s URL / route. The Next control is disabled.
2. **Given** Step 4 is reached and `014`'s read API returns zero active registrations, **When** the wizard renders Step 4, **Then** the analogous affordance directing the tester to `014` is shown. The Next control is disabled.
3. **Given** the tester navigates away to `013` or `014` mid-wizard, **When** they return to the wizard from the dashboard, **Then** the Draft Job is preserved (per US2) and reopens at the lowest-incomplete step. The dropdown reflects the newly-registered entry.

---

### Edge Cases

- The tester opens the wizard, fills in Step 1, then closes the browser without clicking Next — no Draft is created in the database (auto-save fires only on a step transition, not on field input).
- The tester edits Step 1 of an existing Draft and changes the job name to something that already exists on another job — the wizard accepts duplicates (no unique-name constraint in v1; jobs are distinguished by id + `createdAt`).
- The CSV upload exceeds the parent spec's 1,000-row design target — the wizard surfaces the warning defined by parent `SC-011` at Step 2 but still allows the tester to proceed.
- The CSV Upload & Validation Service (Module 8) is unreachable or returns an error — the wizard shows a non-blocking error on Step 2 and does not advance; the tester can retry without losing prior step data.
- The selected connector's registration is archived (per `013 FR-014`) between Step 3 and Step 5 (e.g., the tester takes a long break and an admin / a different session archives it) — at Step 5 the review screen flags the connector as unavailable and the "Start Job" control is disabled until the tester returns to Step 3 to pick a different active registration. (Note: the snapshot already on the Draft is preserved data, but advancement requires an *active* selection.)
- The selected evaluation agent's registration is archived between Step 4 and Step 5 — same as above for the evaluator.
- The tester opens an existing Draft whose snapshotted connector's `expectsPerRowPassword` flag has been edited in `013` since the Draft was created — per parent `FR-023`, the Draft's snapshot is the source of truth; the Draft is unaffected by post-creation edits to the underlying registration. Only the "Start Job" final validation checks the live registry (for active-vs-archived, see edge cases above); the snapshot fields themselves are not refreshed.
- The tester clicks Start, but between the click and the enqueue the harness process is interrupted — on next launch, the job is found in `draft` state (the transition never persisted), and the tester can resume the wizard at Step 5 to re-attempt Start.
- The tester opens two browser tabs both pointed at the same Draft job — last-writer-wins on each step's auto-save; the spec does not promise interleaved-edit conflict detection in v1.
- The tester navigates away from the dashboard mid-wizard without finishing — the partial Draft persists; nothing is leaked or lost beyond the un-submitted current step's data.
- The tester clicks "Start Job" on a Draft whose Step 2's CSV file is no longer accessible (e.g., the upload was retained only by reference and the underlying file is gone) — the wizard surfaces an actionable message and requires re-upload before Start arms.
- The tester selects a connector whose `expectsPerRowPassword` is `true` against a CSV that lacks a populated `password` column for every row — caught by Module 8's validation either at Step 2 (if the wizard re-runs validation after Step 3) or on the Step-3-to-Step-4 transition (if validation is deferred). The wizard MUST surface the per-row missing-password errors and disable Next/Start until corrected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present a five-step wizard with the canonical step order: (1) Create Job, (2) Upload CSV, (3) Select Connector, (4) Select Evaluation Agent, (5) Review & Start.
- **FR-002**: System MUST allow the tester to navigate between adjacent steps via Back and Next controls. Back MUST be available on every step except Step 1; Next MUST be enabled only when the current step's data is valid for advancement (see step-specific gating below).
- **FR-003**: System MUST auto-save the current step's entered data to the Draft job in the database on every step transition (Back or Next or wizard exit-to-dashboard). There is no explicit "Save Draft" button. Within a single step, ephemeral field input is not persisted until the tester transitions away from the step.
- **FR-004**: Step 1 MUST require a non-empty job name. Description is optional. On the first Next from Step 1 of a brand-new wizard session, the system MUST create a Job record in `draft` status with the entered name, optional description, a `createdAt` timestamp, and `createdBy` auto-stamped from the OS-derived tester identity (parent `FR-026`). `createdBy` MUST NOT appear in any wizard form and MUST NOT be editable by the tester.
- **FR-005**: Step 2 MUST delegate uploaded-CSV validation to the CSV Upload & Validation Service (Module 8). The wizard MUST surface the service's per-row error detail when validation fails, and MUST disable Next until a CSV passes validation. The `password` column's presence-required status is conditional on the Step 3 connector selection's `expectsPerRowPassword` flag (per `011`); the wizard MUST coordinate Step-2 validation outcomes with Step-3 selection per plan-level UX.
- **FR-006**: On successful Step-2 validation, the wizard MUST display a summary including at minimum: total parsed utterance (row) count and count of distinct `testId` values appearing in the CSV.
- **FR-007**: Step 3 MUST present a single required dropdown of active (non-archived) `ConnectorRegistration` records sourced from `013`'s read API (per `007 FR-009`/`FR-010`). Each entry MUST display the registration's `displayName`, with the short tail of `connectorId` appended for disambiguation when two registrations share a display name (per `013`'s display rules). Archived registrations MUST NOT appear. No per-job configuration form is rendered; no free-form name input is rendered.
- **FR-008**: When the connector dropdown is empty (zero active registrations), Step 3 MUST display a prominent affordance directing the tester to navigate to `013`'s registry-management UI to register a connector before continuing. The Next control MUST be disabled. The Draft Job MUST be preserved across the round-trip to `013` per US5 scenario 3.
- **FR-009**: On Step-3 Next, the wizard MUST snapshot the full selected registration onto the Draft Job, including: `connectorId`, `displayName` (persisted as `Job.connectorName`), `endpointUrl`, `authDescriptor` (with encrypted credentials per `007 FR-013` — the wizard does NOT re-encrypt; it copies the encrypted ciphertext from the registration as-is into the Job snapshot), `timeoutSeconds`, `expectsPerRowPassword`. Subsequent edits to the underlying `ConnectorRegistration` MUST NOT alter the Job's snapshot (per parent `FR-023`).
- **FR-010**: Step 4 MUST present a single required dropdown of active (non-archived) `EvaluationAgentRegistration` records sourced from `014`'s read API (per `008 FR-008`/`FR-009`). Each entry MUST display the registration's `displayName`, with `evaluationAgentId` tail disambiguation. Archived registrations MUST NOT appear. No per-job configuration form is rendered; no free-form name input is rendered. The registration's `description` and `declaredScoringDimensions` SHOULD be visible alongside the dropdown or in an expandable detail panel, so the tester can verify they are selecting the right evaluator.
- **FR-011**: When the evaluator dropdown is empty (zero active registrations), Step 4 MUST display a prominent affordance directing the tester to navigate to `014`'s registry-management UI to register an evaluator. The Next control MUST be disabled. The Draft Job MUST be preserved across the round-trip.
- **FR-012**: On Step-4 Next, the wizard MUST snapshot the full selected registration onto the Draft Job, including: `evaluationAgentId`, `displayName` (persisted as `Job.evaluationAgentName`), `description`, `endpointUrl`, `authDescriptor` (ciphertext copied verbatim), `timeoutSeconds`, `declaredScoringDimensions` (ordered list). Subsequent edits to the underlying `EvaluationAgentRegistration` MUST NOT alter the Job's snapshot.
- **FR-013**: *(Reserved — formerly defined the contract-version compatibility check between connector and evaluator before Step 5. The check is deprecated for v1 per the 2026-05-29 Reshape clarification. Runtime validation catches contract-version mismatches via `006 FR-015` / `012 FR-011` step 4. The FR number is preserved for stable cross-spec references.)*
- **FR-014**: Step 5 MUST display a read-only summary including: job name, optional description, CSV summary (utterance count, distinct-`testId` count), `connectorName` and (truncated) `connectorEndpointUrl` and auth mode label (credential masked), `evaluationAgentName` and (truncated) `evaluatorEndpointUrl` and auth mode label (credential masked), declared scoring dimensions list, and `expectsPerRowPassword` flag of the snapshotted connector.
- **FR-015**: Step 5 MUST provide a "Start Job" control. The control MUST be disabled if any of the following hold: the job's persisted state is incomplete for any step; the snapshotted connector or evaluator selection references a registration that has since been archived or hard-deleted; or the CSV is no longer accessible. (The contract-version compatibility check from the earlier draft no longer applies — see `FR-013`.)
- **FR-016**: On "Start Job", the system MUST atomically: (a) transition the job's status from `draft` to `queued`, (b) record `startedAt` as the current timestamp, (c) emit an enqueue signal to the Job Execution Engine (Module 10), and (d) route the tester back to the dashboard. If any sub-step fails, the entire transition MUST roll back and the job MUST remain in `draft`; an actionable error MUST be surfaced.
- **FR-017**: A Draft job MUST be resumable at any time from the dashboard. Opening a Draft job MUST re-open the wizard at the lowest-numbered step whose data is incomplete (or Step 5 if all four input steps are complete), with every prior step's data pre-filled and editable.
- **FR-018**: Editing an earlier step MUST preserve data on later steps unless the edit logically invalidates that later data: changing the selected connector registration in Step 3 MUST replace the entire connector snapshot (a different registration is a different set of endpoint / auth / timeout / expects-per-row-password values); changing the selected evaluator registration in Step 4 MUST replace the entire evaluator snapshot. Changing the job name (Step 1) MUST NOT invalidate any later step. Changing the CSV (Step 2) MUST NOT invalidate Step 3 or Step 4 selections (the selections refer to registrations, which are independent of the CSV); a new CSV MAY re-trigger password-column validation against the snapshotted `expectsPerRowPassword` flag.
- **FR-019**: Closing the browser, navigating away, or otherwise exiting the wizard mid-flow MUST NOT delete the Draft job. The job persists in `draft` status until either (a) the tester explicitly deletes it (per parent `FR-001` draft deletion) or (b) the tester completes the wizard and Starts it.
- **FR-020**: The wizard MUST NOT expose any **authentication** flow — no login, no credentials, no password challenge. There is no UI in which the tester provides their own identity. However, per parent `FR-026`, the harness DOES resolve an OS-derived tester identity at startup; that identity is auto-stamped onto `Job.createdBy` per `FR-004` and surfaces as a subtle "Logged in as: <user>" indicator (consistent across all UI surfaces). The tester MUST NOT be able to override either of these.
- **FR-021**: The wizard's UI MUST be navigable via the dashboard's "Create New Job" entry point (`specs/002-dashboard-job-listing` → `FR-011`); no other entry point is required.
- **FR-022**: *(Reserved — formerly defined the wizard-level Test Connection affordance. Test connection is now part of `013` / `014`'s registration forms per the 2026-05-29 Reshape clarification.)*

### Key Entities *(include if feature involves data)*

- **Wizard Session State**: The currently-loaded Draft job plus the wizard's current-step pointer. Sourced from the persisted Draft job on load; mutated only on step transitions. The current-step pointer itself is derived from "lowest-numbered step whose data is incomplete" — it does not need to be stored separately.
- **Draft Job** *(extends parent `Test Job` entity)*: A Test Job whose status is `draft`. May have partial data: name and description are always present (Step 1 has been entered, since that's how the Job record gets created); CSV reference, snapshotted connector identity + endpoint + auth + timeout + expects-per-row-password, snapshotted evaluator identity + endpoint + auth + timeout + declared scoring dimensions may each be absent until their respective step is crossed. `startedAt` is null while in `draft`.
- **Step Completion Predicate**: A per-step rule used by the wizard to decide whether a step's data is complete enough to allow advancing past it. Step 1: name present. Step 2: CSV reference present and validated. Step 3: a registered connector is selected AND its registration is currently active (non-archived) AND the snapshot has been persisted. Step 4: a registered evaluator is selected AND its registration is currently active AND the snapshot has been persisted. Step 5: all of the above hold AND the CSV is still accessible AND both registrations still resolve to active state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tester starting from the dashboard's "Create New Job" can produce a running job (status `queued`, then `running` once the engine picks it up) in under 5 minutes for a typical 100-row CSV and a one-click connector/evaluator selection (registrations already in place).
- **SC-002**: After completing any step and pressing Back, the tester returns to the prior step with 100% of its previously-entered fields pre-filled exactly as last entered.
- **SC-003**: A tester who closes the browser mid-wizard and returns later sees the Draft job in the dashboard within 5 seconds of opening the dashboard (consistent with parent dashboard `SC-001`) and, upon opening it, lands on the lowest-incomplete step with all prior steps pre-filled.
- **SC-004**: A CSV that fails Module-8 validation never advances past Step 2 — verifiable by attempting to advance and observing Next remains disabled.
- **SC-005**: Step 3 cannot be advanced without a registered connector selected — verifiable by leaving the dropdown unselected and observing Next remains disabled.
- **SC-006**: Step 4 cannot be advanced without a registered evaluator selected — same verification approach.
- **SC-007**: When the connector or evaluator registry is empty, the wizard surfaces a clear affordance to navigate to `013` / `014` and disables Next on the affected step — verifiable by clearing all registrations and opening the wizard.
- **SC-008**: On successful "Start Job", the job's status is observably `queued` in the database within 1 second of the click, the `startedAt` timestamp is set, and the Job Execution Engine has received an enqueue signal for that job id.
- **SC-009**: On any rollback (a failed Start Job for any reason), the job remains in `draft` status with all step data intact; no partial transition state is left behind.
- **SC-010**: A Draft job whose snapshotted connector or evaluator registration is no longer active (archived / hard-deleted) is openable in the wizard, and the wizard correctly surfaces the unavailability at the relevant step without crashing or auto-deleting the Draft.
- **SC-011**: A Job snapshot's endpoint / auth / timeout / expects-per-row-password (connector) and endpoint / auth / timeout / declared scoring dimensions (evaluator) fields are byte-for-byte equal to the corresponding registration values **at the moment of snapshot** (verifiable by snapshotting one job, editing the registration in `013` / `014`, snapshotting another job, and asserting the first job's snapshot is unchanged).

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. The parent's "single-user, no auth, localhost" model applies — there is no login flow, no auth challenge, no tester-editable identity. `Job.createdBy` IS auto-stamped on Step 1 Next from the OS-derived tester identity (parent `FR-026`), but the tester does not see or edit this from any wizard form.
- Module 4 (Connector Framework, `007`) defines the connector wire protocol and the registry's read API; this wizard consumes the read API. Module 7 (Evaluation Agent Framework, `008`) does the same on the evaluator side.
- Module 13 (Connector Registry Management) and Module 14 (Evaluator Registry Management) host the CRUD UIs for connector and evaluator registrations. This wizard's Step 3 / Step 4 are read-only dropdowns sourced from those modules.
- Module 8 (CSV Upload & Validation, `011`) handles all CSV validation; this wizard delegates to it and surfaces its errors.
- Module 10 (Job Execution Engine, `012`) consumes the enqueue signal on Start Job and asynchronously transitions the Job through `queued → running → terminal`.
- The original Module 9 phrase "transition Draft to Running" was resolved by explicit decision to mean **`draft` → `queued`**; the engine handles `queued` → `running`.
- The job lifecycle (`draft` / `queued` / `running` / `cancelling` / `completed` / `failed` / `cancelled`) is inherited from the parent spec. The wizard handles only the `draft` → `queued` transition.
- Job names are not required to be unique in v1. Two Drafts (or two completed jobs) may share a name; they are distinguished by id + `createdAt`.
- Auto-save semantics: data is persisted on step transitions (Back/Next/exit-to-dashboard). Field-level keystrokes are not persisted. This is a deliberate trade-off between resumability and DB-write frequency.
- Per-tester wizard preferences (preferred default connector, preferred default evaluator) are out of scope for v1.
- Historical context (superseded 2026-05-29): earlier drafts of this module described per-job configuration forms in Step 3 / Step 4 that rendered fields per the connector's / evaluator's declared JSON Schema, plus a tester-editable `connectorName` / `evaluationAgentName` per-job override, plus a Step-3 "Test Connection" affordance, plus a Step-4 contract-version compatibility check. All four are removed in this revision: configuration lives on the registration in `013` / `014`; the name is the registration's `displayName` (no per-job override); test connection lives on the registration form; contract-version compatibility is deferred to runtime validation per `006 FR-015`. The corresponding requirement numbers are reserved (no content) to keep cross-spec FR references stable.
