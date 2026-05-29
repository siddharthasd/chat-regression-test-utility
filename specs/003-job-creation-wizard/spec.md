# Feature Specification: Job Creation & Configuration Wizard (Module 9)

**Feature Branch**: `003-job-creation-wizard`

**Created**: 2026-05-28

**Status**: Draft

**Input**: User description: "Module 9 — Job Creation & Configuration Wizard. A guided five-step web UI (and corresponding backend API) that walks the tester through (1) creating and naming the job, (2) uploading the test CSV, (3) selecting and configuring a chatbot connector, (4) selecting and configuring an evaluation agent, and (5) reviewing and starting. Each step's data is auto-saved to a Draft job in the database so the wizard can be resumed from any point. Back/Next navigation between steps preserves all entered data. On final 'Start', the job transitions out of Draft and the Job Execution Engine takes over."

> **Parent context**: This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md` and is the navigation target of the dashboard's "Create New Job" entry point (`specs/002-dashboard-job-listing` → `FR-011`). Parent-spec premises apply unchanged: single-user, no authentication on the wizard, no `createdBy` field. The original Module 9 description's mention of "captures createdBy from the authenticated session" was dropped by explicit decision (2026-05-28) — there is no creator concept anywhere in the harness. The job lifecycle (`draft` → `queued` → `running` → terminal `completed` | `failed` | `cancelled`, with `cancelling` as the transient state on the path to `cancelled`) is defined by the parent spec; this module only specifies what happens at the `draft` → `queued` boundary. The original Module 9 description's "transition Draft to Running" was also resolved by explicit decision (2026-05-28) to mean **`draft` → `queued`**; the Job Execution Engine (Module 10) is responsible for the subsequent `queued` → `running` transition asynchronously.

## Clarifications

### Session 2026-05-28

- Q: On "Start Job", what status does the job transition to? → A: `draft` → `queued`. Matches the parent spec's lifecycle. The wizard does not synchronously trigger execution; it enqueues. The Job Execution Engine (Module 10) picks up `queued` jobs and transitions them to `running`. The UI button text remains "Start Job".
- Q: How is wizard progress persisted as a Draft job? → A: Auto-save on every step transition. Pressing Back/Next persists the current step's data to the Draft job in the database before navigating. There is no explicit "Save Draft" button; the Draft is always current up to the last step boundary the tester crossed. Closing the browser mid-step loses only data entered on the current (unsubmitted) step.

### Session 2026-05-29 (Round 2 — revision driven by Module 3)

- Q: Module 3 (`specs/010-tester-identity`) re-introduces an OS-derived `Job.createdBy` field. Does the wizard auto-populate it on Step 1 Next? → A: **Yes.** On the Step 1 Next that creates the Draft Job, the wizard MUST auto-stamp `Job.createdBy` with the harness's OS-derived tester identity (per parent `FR-026`). The field is NOT exposed in any wizard form — the tester cannot see it, cannot edit it, cannot override it. This reverses the Parent-context note at the top of this spec that said "no `createdBy` field anywhere"; only the persistence direction reversed — there is still no auth flow and no login.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a new job end-to-end through the five steps (Priority: P1)

A QA tester clicks "Create New Job" on the dashboard and lands on Step 1 of the wizard. They name the job, advance through Step 2 (CSV upload, validation, summary), Step 3 (pick and configure connector), Step 4 (pick and configure evaluation agent), and Step 5 (review). They click "Start Job"; the wizard hands the job off to the Job Execution Engine and returns the tester to the dashboard, where the new job is visible in `queued` status (and will shortly transition to `running` as the engine picks it up).

**Why this priority**: This is the entire purpose of the module. Without a working happy path, nothing else matters. It is the MVP slice.

**Independent Test**: With stubs for the dashboard, CSV Upload & Validation Service (Module 8), Connector Registry (Module 4), Evaluation Agent Registry (Module 7), and Job Execution Engine (Module 10), open the wizard at Step 1, complete every step with valid inputs, click "Start Job", and verify (a) the persisted Job record has the expected name, CSV reference, connector snapshot, evaluation-agent snapshot, and `queued` status; (b) the engine received a job-enqueued signal for that job.

**Acceptance Scenarios**:

1. **Given** the tester is on Step 1 with an empty form, **When** they enter a job name and click Next, **Then** a Job record is created in `draft` status with the entered name, an auto-generated `created-at` timestamp, and they advance to Step 2.
2. **Given** the tester is on Step 2 with a valid CSV selected, **When** they click Next, **Then** the CSV is validated via Module 8, a summary (utterance count and distinct-testId count) is displayed, and on a successful validation result the wizard advances to Step 3.
3. **Given** the tester is on Step 3 and selects a connector, **When** the connector's configuration form renders, **Then** the form fields match the connector's declared configuration schema. **When** the tester fills in valid configuration and clicks Next, **Then** the connector identity and a snapshot of the configuration are persisted to the Draft job and the wizard advances to Step 4.
4. **Given** the tester is on Step 4 and selects an evaluation agent, **When** they fill in its configuration and click Next, **Then** the agent identity and a configuration snapshot are persisted to the Draft job and the wizard advances to Step 5.
5. **Given** the tester is on Step 5 looking at a read-only summary, **When** they click "Start Job", **Then** the job's status transitions from `draft` to `queued`, a `started-at` timestamp is recorded, the Job Execution Engine (Module 10) is signaled to pick the job up, and the tester is routed back to the dashboard with the new job visible.

---

### User Story 2 - Resume a Draft job exactly where it was left (Priority: P2)

A tester begins creating a job but stops partway (closes the browser, walks away, or returns to the dashboard). The Draft job persists in the database. When the tester returns and opens the Draft, the wizard re-opens at the step they last completed, with every prior step's data pre-filled and editable. They continue from there to completion.

**Why this priority**: Real-world tester workflows include interruptions and multi-session job authoring. Without resumability, every interruption is a redo. The MVP works without resume (one-sitting authoring), but resume is what makes the wizard usable in practice.

**Independent Test**: Begin a wizard, complete Step 1 and Step 2 with valid inputs (so they auto-save), close the browser tab without finishing. From the dashboard, open the Draft job and verify (a) the wizard opens at Step 3 (the next un-entered step) with Steps 1 and 2 pre-filled and editable; (b) advancing through the remaining steps and clicking Start succeeds.

**Acceptance Scenarios**:

1. **Given** a Draft job that has completed data for Steps 1 and 2 only, **When** the tester opens it from the dashboard, **Then** the wizard opens at Step 3 with all Step-1 and Step-2 fields pre-filled with the persisted values.
2. **Given** any Draft job whose data covers all five steps, **When** the tester opens it, **Then** the wizard may open directly at Step 5 (review) with full summary visible and a working "Start Job" control.
3. **Given** a Draft job whose persisted Connector Type is no longer registered with the harness, **When** the tester opens it and reaches Step 3, **Then** the wizard surfaces an actionable message (the connector is no longer available) and requires the tester to select a different connector before proceeding.

---

### User Story 3 - Navigate freely backward and forward without losing data (Priority: P2)

A tester partway through the wizard wants to revisit an earlier step (e.g., to change the connector after seeing the review screen). They click Back, edit the prior step, click Next, and arrive back at the next step with the change applied. No previously-entered data on later steps is lost, except where the change to an earlier step logically invalidates a later step's data (e.g., changing the connector resets the connector configuration but not the CSV).

**Why this priority**: Coupled with auto-save (P2-resumability), free navigation makes the wizard a real authoring surface rather than a one-shot funnel. Equal priority with resume because both are usability multipliers on top of the P1 happy path.

**Independent Test**: Complete Steps 1–4 of the wizard with valid data, arrive at Step 5, click Back twice to land on Step 3, change the connector selection, click Next, arrive at Step 4 with its prior data lost (because connector changed) but Steps 1 and 2 intact, complete Step 4 again, arrive at Step 5 with the updated summary.

**Acceptance Scenarios**:

1. **Given** the tester is on Step N with prior step data persisted, **When** they click Back, **Then** the wizard opens Step N-1 with all of its previously-entered values pre-filled.
2. **Given** the tester edits Step 1 (rename) or Step 2 (re-upload CSV), **When** they click Next, **Then** Steps 3 and 4's previously-entered configuration is preserved (the change does not invalidate connector or evaluator choice).
3. **Given** the tester changes the selected connector on Step 3, **When** they advance to Step 4, **Then** Step 4's persisted evaluator config is preserved BUT the connector configuration entered against the prior connector is discarded (the new connector's config form is shown empty/with defaults).
4. **Given** the tester changes the selected evaluation agent on Step 4, **When** they advance to Step 5, **Then** the prior agent's configuration is discarded and Step 5's summary reflects the new selection.

---

### User Story 4 - Validate the CSV before proceeding and surface what was found (Priority: P2)

At Step 2 the tester uploads a CSV. The wizard hands the file to the CSV Upload & Validation Service (Module 8). If validation fails, the wizard displays the per-row issues and refuses to advance. If validation succeeds, the wizard displays a compact summary of what's in the CSV — the parsed utterance count and the count of distinct `testId` values — so the tester can sanity-check before continuing.

**Why this priority**: CSV problems are the single most common source of broken regression runs. Surfacing them at upload time, with actionable error detail, prevents wasted job runs and saves triage time. Equal priority with resume/navigation because the wizard is unusable without an honest validation gate at Step 2.

**Independent Test**: Upload three CSVs in sequence to a wizard at Step 2: (a) a malformed CSV, (b) a CSV that's valid but has duplicate `testId`s, (c) a clean CSV. Verify (a) is rejected with actionable per-row errors and Next is disabled, (b) is accepted but the summary calls out the duplicate-testId count, (c) is accepted with a clean summary and Next enables.

**Acceptance Scenarios**:

1. **Given** the tester has selected a CSV file, **When** they invoke the upload, **Then** the wizard delegates validation to Module 8 and waits for the result.
2. **Given** validation returns failure, **When** the wizard renders the result, **Then** the per-row error detail (row number, column, reason) is shown and the Next control is disabled until a valid CSV is uploaded.
3. **Given** validation returns success, **When** the wizard renders the result, **Then** the summary displays the parsed utterance count and the count of distinct `testId` values, and the Next control becomes enabled.

---

### User Story 5 - Test connector connectivity before committing to it (Priority: P3)

On Step 3 (Configure Connector), after the tester fills in the connector's configuration form, they may optionally click a "Test Connection" affordance. The wizard invokes a connectivity probe through the connector (using the just-entered config but no real test utterance), and reports success or failure. The probe is non-blocking: the tester may proceed without running it, and proceeding does not depend on its outcome.

**Why this priority**: Connectivity errors discovered at job-execution time waste a full run's worth of tester attention. A pre-flight probe catches misconfiguration cheaply. Lower than P1/P2 because it's a productivity feature, not a correctness gate.

**Independent Test**: With a stub connector that exposes a probe endpoint, on Step 3, fill in a valid config and click "Test Connection" → expect a success indicator. Wipe the config to invalid values and click "Test Connection" → expect a failure indicator with detail. In both cases, verify the tester can advance to Step 4 regardless of probe outcome.

**Acceptance Scenarios**:

1. **Given** a connector that declares it supports a connectivity probe, **When** the tester fills in valid config and activates "Test Connection", **Then** the wizard invokes the probe and renders the result (success or failure with cause) within a reasonable timeframe.
2. **Given** a connector that does NOT declare a connectivity probe, **When** the tester reaches Step 3, **Then** the "Test Connection" affordance is hidden (or disabled with a tooltip explaining the connector does not support it).
3. **Given** the tester has not run the probe at all, **When** they click Next, **Then** the wizard does not block — the probe is purely optional.

---

### Edge Cases

- The tester opens the wizard, fills in Step 1, then closes the browser without clicking Next — no Draft is created in the database (auto-save fires only on a step transition, not on field input).
- The tester edits Step 1 of an existing Draft and changes the job name to something that already exists on another job — the wizard accepts duplicates (no unique-name constraint in v1; jobs are distinguished by id + created-at).
- The CSV upload exceeds the parent spec's 1,000-row design target — the wizard surfaces the warning defined by parent `SC-011` at Step 2 but still allows the tester to proceed.
- The CSV Upload & Validation Service (Module 8) is unreachable or returns an error — the wizard shows a non-blocking error on Step 2 and does not advance; the tester can retry without losing prior step data.
- The selected connector is removed from the registry between Step 3 and Step 5 (e.g., the tester takes a long break) — at Step 5 the review screen flags the connector as unavailable and the "Start Job" control is disabled until the tester returns to Step 3 to pick a different connector.
- The selected evaluation agent is removed from the registry between Step 4 and Step 5 — same as above for the evaluator.
- The connector and evaluation agent declare incompatible Standard Evaluation Contract versions (per parent `FR-020`) — the wizard catches this before the Start button arms (either on Step 4 selection or on entering Step 5) and surfaces an actionable message naming both declared versions.
- The tester clicks Start, but between the click and the enqueue the harness process is interrupted — on next launch, the job is found in `draft` state (the transition never persisted), and the tester can resume the wizard at Step 5 to re-attempt Start.
- The tester opens two browser tabs both pointed at the same Draft job — last-writer-wins on each step's auto-save; the spec does not promise interleaved-edit conflict detection in v1.
- The tester navigates away from the dashboard mid-wizard without finishing — the partial Draft persists; nothing is leaked or lost beyond the un-submitted current step's data.
- The tester clicks "Start Job" on a Draft whose Step 2's CSV file is no longer accessible (e.g., the upload was retained only by reference and the underlying file is gone) — the wizard surfaces an actionable message and requires re-upload before Start arms.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present a five-step wizard with the canonical step order: (1) Create Job, (2) Upload CSV, (3) Select & Configure Connector, (4) Select & Configure Evaluation Agent, (5) Review & Start.
- **FR-002**: System MUST allow the tester to navigate between adjacent steps via Back and Next controls. Back MUST be available on every step except Step 1; Next MUST be enabled only when the current step's data is valid for advancement (see step-specific gating below).
- **FR-003**: System MUST auto-save the current step's entered data to the Draft job in the database on every step transition (Back or Next or wizard exit-to-dashboard). There is no explicit "Save Draft" button. Within a single step, ephemeral field input is not persisted until the tester transitions away from the step.
- **FR-004**: Step 1 MUST require a non-empty job name. Description is optional. On the first Next from Step 1 of a brand-new wizard session, the system MUST create a Job record in `draft` status with the entered name, optional description, a `created-at` timestamp, and `createdBy` auto-stamped from the OS-derived tester identity (parent `FR-026`). `createdBy` MUST NOT appear in any wizard form and MUST NOT be editable by the tester.
- **FR-005**: Step 2 MUST delegate uploaded-CSV validation to the CSV Upload & Validation Service (Module 8). The wizard MUST surface the service's per-row error detail when validation fails, and MUST disable Next until a CSV passes validation.
- **FR-006**: On successful Step-2 validation, the wizard MUST display a summary including at minimum: total parsed utterance (row) count and count of distinct `testId` values appearing in the CSV.
- **FR-007**: Step 3 MUST present the list of connectors currently registered with the Connector Registry (Module 4) and let the tester select one.
- **FR-008**: On connector selection in Step 3, the wizard MUST dynamically render a configuration form whose fields match the selected connector's declared configuration schema. Required fields MUST be marked; type-level validation MUST be enforced before Next arms.
- **FR-009**: Step 3 MAY expose a "Test Connection" affordance when, and only when, the selected connector declares support for a connectivity probe. Activating it MUST invoke the probe with the currently-entered configuration and render success/failure with cause. The probe outcome MUST NOT gate Next; Next remains enabled whenever the form passes its declared validation.
- **FR-010**: On Step-3 Next, the wizard MUST persist to the Draft job (a) the connector identity and (b) a snapshot of the entered configuration values. Subsequent changes to the connector registry MUST NOT alter the snapshot (per parent `FR-023`).
- **FR-011**: Step 4 MUST present the list of evaluation agents currently registered with the Evaluation Agent Registry (Module 7) and let the tester select one.
- **FR-012**: On evaluation-agent selection in Step 4, the wizard MUST dynamically render a configuration form whose fields match the selected agent's declared configuration schema. Required-field and type-level validation MUST be enforced before Next arms.
- **FR-013**: On Step-4 Next, the wizard MUST persist to the Draft job (a) the evaluation-agent identity and (b) a snapshot of the entered configuration values.
- **FR-014**: Before exiting Step 4 (or entering Step 5), the wizard MUST verify that the selected connector's declared emitted-contract version is in the selected evaluation agent's declared accepted-contract-versions set (per parent `FR-020`). On mismatch, the wizard MUST display an actionable message naming both declared versions and disable Next/Start until the mismatch is resolved.
- **FR-015**: Step 5 MUST display a read-only summary including: job name, optional description, CSV summary (utterance count, distinct-`testId` count), connector identity + visible (non-secret) configuration fields, evaluation-agent identity + visible (non-secret) configuration fields, and the declared Standard Evaluation Contract version expectation.
- **FR-016**: Step 5 MUST provide a "Start Job" control. The control MUST be disabled if any of the following hold: the job's persisted state is incomplete for any step; the connector/evaluator selections refer to identities no longer present in the respective registries; the contract-version compatibility check fails; or the CSV is no longer accessible.
- **FR-017**: On "Start Job", the system MUST atomically: (a) transition the job's status from `draft` to `queued`, (b) record `started-at` as the current timestamp, (c) emit an enqueue signal to the Job Execution Engine (Module 10), and (d) route the tester back to the dashboard. If any sub-step fails, the entire transition MUST roll back and the job MUST remain in `draft`; an actionable error MUST be surfaced.
- **FR-018**: A Draft job MUST be resumable at any time from the dashboard. Opening a Draft job MUST re-open the wizard at the lowest-numbered step whose data is incomplete (or Step 5 if all four input steps are complete), with every prior step's data pre-filled and editable.
- **FR-019**: Editing an earlier step MUST preserve data on later steps unless the edit logically invalidates that later data: changing the selected connector identity in Step 3 MUST discard the persisted connector-configuration snapshot (but not the evaluator); changing the selected evaluation-agent identity in Step 4 MUST discard the persisted evaluator-configuration snapshot. Changing the job name (Step 1) or the CSV (Step 2) MUST NOT invalidate Step-3 or Step-4 data.
- **FR-020**: Closing the browser, navigating away, or otherwise exiting the wizard mid-flow MUST NOT delete the Draft job. The job persists in `draft` status until either (a) the tester explicitly deletes it (per parent `FR-001` draft deletion) or (b) the tester completes the wizard and Starts it.
- **FR-021**: The wizard MUST NOT expose any **authentication** flow — no login, no credentials, no password challenge. There is no UI in which the tester provides their own identity. However, per parent `FR-026`, the harness DOES resolve an OS-derived tester identity at startup; that identity is auto-stamped onto `Job.createdBy` per `FR-004` and surfaces as a subtle "Logged in as: <user>" indicator (consistent across all UI surfaces). The tester MUST NOT be able to override either of these.
- **FR-022**: The wizard's UI MUST be navigable via the dashboard's "Create New Job" entry point (`specs/002-dashboard-job-listing` → `FR-011`); no other entry point is required.

### Key Entities *(include if feature involves data)*

- **Wizard Session State**: The currently-loaded Draft job plus the wizard's current-step pointer. Sourced from the persisted Draft job on load; mutated only on step transitions. The current-step pointer itself is derived from "lowest-numbered step whose data is incomplete" — it does not need to be stored separately.
- **Draft Job** *(extends parent `Test Job` entity)*: A Test Job whose status is `draft`. May have partial data: name and description are always present (Step 1 has been entered, since that's how the Job record gets created); CSV reference, connector identity + config snapshot, evaluation-agent identity + config snapshot may each be absent until their respective step is crossed. `started-at` is null while in `draft`.
- **Step Completion Predicate**: A per-step rule used by the wizard to decide whether a step's data is complete enough to allow advancing past it. Step 1: name present. Step 2: CSV reference present and validated. Step 3: connector identity persisted and config snapshot satisfies the connector's declared schema. Step 4: evaluation-agent identity persisted and config snapshot satisfies the agent's declared schema, AND the contract-version compatibility check passes against the selected connector. Step 5: all of the above hold AND the CSV is still accessible AND both registry entries still resolve.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tester starting from the dashboard's "Create New Job" can produce a running job (status `queued`, then `running` once the engine picks it up) in under 5 minutes for a typical 100-row CSV and a one-click connector/evaluator configuration.
- **SC-002**: After completing any step and pressing Back, the tester returns to the prior step with 100% of its previously-entered fields pre-filled exactly as last entered.
- **SC-003**: A tester who closes the browser mid-wizard and returns later sees the Draft job in the dashboard within 5 seconds of opening the dashboard (consistent with parent dashboard `SC-001`) and, upon opening it, lands on the lowest-incomplete step with all prior steps pre-filled.
- **SC-004**: A CSV that fails Module-8 validation never advances past Step 2 — verifiable by attempting to advance and observing Next remains disabled.
- **SC-005**: An invalid connector configuration (missing required fields or wrong types per the declared schema) never advances past Step 3 — verifiable by attempting to advance and observing Next remains disabled.
- **SC-006**: An invalid evaluation-agent configuration never advances past Step 4 — same verification approach.
- **SC-007**: A contract-version mismatch between the selected connector and the selected evaluation agent is detected before Step 5's "Start Job" control becomes active — the tester sees an actionable error at or before Step 5 entry, not at runtime.
- **SC-008**: On successful "Start Job", the job's status is observably `queued` in the database within 1 second of the click, the `started-at` timestamp is set, and the Job Execution Engine has received an enqueue signal for that job id.
- **SC-009**: On any rollback (a failed Start Job for any reason), the job remains in `draft` status with all step data intact; no partial transition state is left behind.
- **SC-010**: A Draft job whose connector or evaluation agent is no longer registered is openable in the wizard, and the wizard correctly surfaces the unavailability at the relevant step without crashing or auto-deleting the Draft.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. The parent's "single-user, no auth, localhost" identity model applies. There is no `createdBy` / "creator" / authentication anywhere in the wizard.
- Module 4 (Connector Registry), Module 7 (Evaluation Agent Registry), Module 8 (CSV Upload & Validation Service), and Module 10 (Job Execution Engine) exist as separate features/modules with their own specs (TBD). The wizard depends on them as integration seams (selection lists, configuration schemas, validation results, enqueue signal) but does not specify their internals.
- The original Module 9 phrase "transition Draft to Running" was resolved by explicit decision to mean **`draft` → `queued`**; the engine handles `queued` → `running`.
- The job lifecycle (`draft` / `queued` / `running` / `cancelling` / `completed` / `failed` / `cancelled`) is inherited from the parent spec. The wizard handles only the `draft` → `queued` transition.
- Job names are not required to be unique in v1. Two Drafts (or two completed jobs) may share a name; they are distinguished by id + `created-at`.
- The "Test Connection" probe in Step 3 is purely advisory. Whether a connector declares support for it is a connector-level capability, not a harness-wide one.
- Visible vs. non-visible (secret) configuration fields: each connector and evaluation agent is responsible for declaring which of its config fields are secret (e.g., API keys); the wizard MUST NOT display secret fields' values in the Step-5 read-only review. Concrete redaction strategy is plan-level.
- Auto-save semantics: data is persisted on step transitions (Back/Next/exit-to-dashboard). Field-level keystrokes are not persisted. This is a deliberate trade-off between resumability and DB-write frequency.
- Per-tester wizard preferences (preferred default connector, preferred default evaluator) are out of scope for v1.
