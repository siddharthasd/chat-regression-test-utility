# Feature Specification: Dashboard & Job Listing (Module 12)

**Feature Branch**: `002-dashboard-job-listing`

**Created**: 2026-05-28

**Last Amended**: 2026-06-01

**Status**: Draft

**Input**: User description: "Module 12 — Dashboard & Job Listing. The default landing page of the regression test harness. Displays a table of all test jobs with columns Job Name, Status (color-coded badges), Created At, Started At, Completed At, Connector Type, Utterance Count (processed/total), Failed Count. Supports filtering by status (multi-select) and connector type, sorting by any column, and free-text search by Job Name. Each row is clickable, navigating to the Job Detail View (Module 13). A prominent 'Create New Job' button launches the Job Creation Wizard (Module 9). Running jobs' status, counters, and badges update in near-real-time without a full-page refresh."

> **Parent context**: This module belongs to the harness defined in `specs/001-chatbot-regression-harness/spec.md`. That spec's "single-user, no auth, localhost" premises apply here unchanged — no authentication on the landing page. The user-supplied phrasing "default authenticated landing page" was dropped (no auth). **Note: Round 4 of this spec partially reversed an earlier "drop Created By" decision** — the dashboard now re-adds a Created By column + filter, with the filter enumerating distinct `Job.createdBy` values (OS-derived per parent `FR-026`) from persisted Jobs rather than consulting a separate users registry. **Round 5 renamed "Connector Type" to "Connector"** sourced from `Job.connectorName`. **Reshape note (2026-05-29):** post-reshape, `Job.connectorName` is a **verbatim snapshot of the selected registration's `displayName`** (per `001 FR-023` / `009 FR-001`) — NOT a tester-editable per-job override. The earlier Round-5 framing of "tester-supplied, defaulted, but editable" no longer applies; the tester picks a registration from the wizard's Step 3 dropdown (per `003 FR-007`), and the registration's `displayName` (set up in `013`) is what gets snapshotted onto the Job. There is no separate `connectorType` field. The job status enum, lifecycle, and `cancelled` semantics are defined in the parent spec; this spec only specifies how those states are rendered and acted upon in the dashboard. **Module-numbering note:** this spec's title and body use the user-input "Module 12 / 9 / 13" labels (matching the original user prompt); these map to spec-ids `002` (dashboard) / `003` (wizard) / `004` (detail view) per `001`'s Assumptions block module map. Both naming conventions refer to the same underlying specs.

## Clarifications

### Session 2026-05-28

- Q: What is the default sort order when the dashboard first loads? → A: Sort by Created At, descending — newest jobs at the top. Tester sort actions override this for the session.
- Q: How are jobs rendered at the 1,000-job design target — paginated, virtualized, or all-at-once? → A: Render all rows in a single scrollable table. No pagination, no infinite scroll, no virtualization in v1. Preserves the "scan everything at a glance" UX.
- Q: How are Created At / Started At / Completed At rendered? → A: Hybrid format — relative ("just now", "5 minutes ago", "3 hours ago") for timestamps within the last ~24 hours, absolute (`YYYY-MM-DD HH:MM` in tester's local timezone) thereafter. The alternate representation is available on hover.
- Q: When a near-real-time update changes whether a row matches the active filter or search, what happens? → A: Strict live re-evaluation. The row immediately disappears from the filtered view the moment it stops matching, and immediately appears when it starts matching. Filters and search are treated as live predicates over current state, not as one-time snapshots.

### Session 2026-05-28 (Round 2)

- Q: Are row-level job actions (cancel, delete) available inline on the dashboard, or only via the Job Detail View? → A: No row-level actions on the dashboard in v1. Cancel (queued/running) and Delete (draft) are reachable only through the Job Detail View (Module 13). The dashboard stays a read-only triage and navigation surface.

### Session 2026-05-28 (Round 3 — revision)

- Q: Should the previous "no row-level actions" rule be revised to permit dashboard cleanup of accumulated terminal-error jobs? → A: Yes — revision. The dashboard MUST expose a row-level delete affordance, but **only for jobs in `failed` or `cancelled` status**. Rationale: failed and cancelled jobs accumulate as clutter over time and the tester needs a fast way to clean the dashboard. This revision overrides Round-2 Q1 in part. Jobs in `completed` status remain non-deletable from the dashboard (preserved as historical record of successful runs); jobs in `draft`, `queued`, `running`, and `cancelling` status remain non-deletable from the dashboard (cancel-then-delete must flow through Module 13).
- Q: Per-row delete only, or also a bulk "clear all failed and cancelled" action? → A: Both. The dashboard exposes per-row delete (for surgical cleanup) AND a top-of-dashboard "Clear all failed and cancelled" action that, on confirmation showing the count, deletes every `failed` and `cancelled` job in a single operation. Multi-select checkboxes are out of scope.

### Session 2026-05-29 (Round 4 — revision driven by Module 3)

- Q: Module 3 (`specs/010-tester-identity`) introduces OS-derived tester attribution. Should the dashboard re-add the Created By column + filter that the original Module 12 input proposed (and earlier rounds dropped)? → A: **Yes, partial revision.** Re-add a Created By column to the row layout. Re-add a Created By filter, but with a different shape than the original "dropdown of known users" — it is now a multi-select over the **distinct `createdBy` values actually present in persisted Job rows**, NOT a separate users registry. This reverses the pre-spec "single-user / no creator" decision from `Parent context` at the top of this spec, in lock-step with new parent `FR-026`. Per parent `FR-026`, `createdBy` is OS-derived; the tester cannot override it; on a single-user laptop the column will typically show one repeated name. Per-job rendering remains identical except for the new column.

### Session 2026-05-29 (Round 5 — Connector Type renamed)

- Q: The earlier rounds named the column "Connector Type" and the field `connectorType`. The cross-spec audit found this conflicts with the Module 4 framework's `connectorId` + `displayName` model. What's the canonical name? → A: **Drop `connectorType` entirely. Replace with `connectorName` — a tester-supplied human-readable name per Job.** Wizard's Step 3 captures `connectorName` from the tester, defaulted from the connector's framework-declared display name but editable. Job snapshots both `connectorId` (technical, for registry lookup) and `connectorName` (human-readable, what the tester reads everywhere). The dashboard's column changes from "Connector Type" → "Connector". The filter source changes from "union of currently-registered connector types + historical" to "distinct `connectorName` values present in persisted Jobs". `FR-003`, `FR-006`, `FR-016`, `Job List Row` entity, and Assumptions all updated. **Superseded in part by the 2026-05-29 Reshape clarification below**: the rename Connector Type → Connector stands; the dashboard column source remains `Job.connectorName`; but the underlying "tester-supplied per-job, defaulted from framework display name, editable" mechanism is replaced by "verbatim snapshot of the selected registration's `displayName` at job-creation time" — there is no per-job tester-editable name input post-reshape.

### Session 2026-05-29 (Reshape)

- Q: The 2026-05-29 architecture reshape moved connectors and evaluators to remote HTTP services managed by CRUD modules (`013`/`014`), and removed the per-job tester-editable name override that Round 5 had assumed. What changes for the dashboard? → A: **Three semantic adjustments, no UI-layout changes:** (1) `Job.connectorName` becomes a verbatim snapshot of the selected `ConnectorRegistration.displayName` (per `001 FR-023`, `009 FR-001`) — the dashboard's Connector column renders this snapshot, identical at all post-creation moments regardless of whether the underlying registration was later edited or archived in `013`. (2) The Connector filter enumerates the distinct set of `connectorName` snapshot values across persisted Jobs (per `FR-006`); since `connectorName` is now uniquely determined by the registration that the Job pointed to at creation time, the filter's granularity is determined by how registrations are named in `013` (one display name per registration). (3) The "no longer registered" edge case (`FR-016`) is reframed as the "archived" case (per `013 FR-014`), since hard-delete of a registration referenced by historical jobs is blocked by `013 FR-019` / `014 FR-024`. The dashboard's rendering and behavior are unchanged in either case — the snapshot is what is shown. No UI re-layout, no column re-order, no filter-mechanism change.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See every job's status at a glance from the landing page (Priority: P1)

A QA tester opens the harness and immediately sees a single table listing every test job that exists in the local database, with each job's current status visually distinguishable from the others. They can scan the table to find the job they care about — a running job that's progressing, a completed job to review, a failed job to triage — without clicking through navigation. This is the dashboard's reason to exist.

**Why this priority**: Without this baseline, no other dashboard story works. It is the MVP slice of Module 12 and the primary entry point for every workflow in the harness.

**Independent Test**: Seed the local database with 5 jobs across at least 4 different statuses (e.g., one each of `draft`, `running`, `completed`, `failed`), open the harness at its root URL, and verify all 5 jobs appear in a single table with their status badges visually distinguishable at a glance.

**Acceptance Scenarios**:

1. **Given** at least one persisted test job, **When** the tester opens the harness's root URL, **Then** they are taken to the dashboard and see every persisted job as one row in a single table, with no further navigation required.
2. **Given** a job whose status is `completed` and whose Failed Count is greater than zero, **When** the tester views its row, **Then** the row visually distinguishes it from a `completed` job with zero failed rows (e.g., a "Completed with errors" label, a sub-badge, or a distinct badge color), without introducing a separate underlying status value.
3. **Given** no persisted jobs in the database, **When** the tester opens the dashboard, **Then** they see an explicit empty-state message and the "Create New Job" call-to-action.

---

### User Story 2 - Start a new test job from the dashboard (Priority: P2)

A tester landing on the dashboard wants to start a brand-new regression run. They click a prominent, clearly-labeled "Create New Job" button and are taken into the Job Creation Wizard. This is the dashboard's entry point into the create-a-job workflow.

**Why this priority**: Creating a job is the primary "next action" for a tester whose existing jobs are all in terminal states (or who has just installed the harness). It must be reachable in one click from the dashboard, but it depends on the table being there to anchor the UX.

**Independent Test**: From any state of the dashboard (empty, populated, filtered), confirm the "Create New Job" button is visible without scrolling and that activating it routes the tester to the Job Creation Wizard.

**Acceptance Scenarios**:

1. **Given** the tester is on the dashboard, **When** they activate the "Create New Job" control, **Then** they are routed to the Job Creation Wizard (Module 9).
2. **Given** the dashboard is showing the empty state, **When** the tester views the page, **Then** the "Create New Job" call-to-action is at least as prominent as in the populated state.

---

### User Story 3 - Drill into a single job's full detail (Priority: P2)

A tester scanning the dashboard sees a job they want to investigate (e.g., one with many failed rows, or a recently-completed run). They click the row and are taken to the Job Detail View for that specific job. The dashboard hands off cleanly to the detail module.

**Why this priority**: Drill-in is the second-most-common action from the dashboard (after "see the list") and is what makes the dashboard useful as a triage surface. Equal priority with creating jobs because both are core entry points; the team can sequence them independently.

**Independent Test**: With at least one persisted job visible on the dashboard, click anywhere on its row outside of overt action buttons, and verify navigation to the Job Detail View carries the correct job identifier.

**Acceptance Scenarios**:

1. **Given** the tester sees at least one job row on the dashboard, **When** they activate (click) the row body, **Then** the application navigates to the Job Detail View (Module 13) for that exact job.
2. **Given** the row contains in-row controls (if any) other than the main row activation, **When** the tester activates one of those controls, **Then** the row-level navigation is not triggered.

---

### User Story 4 - Narrow the job list with filters, sort, and search (Priority: P3)

A tester with many jobs in the database wants to focus on a slice: only the running jobs, only jobs that used a specific connector, or a specific job by name. They apply a multi-select status filter, a Connector filter (multi-select over distinct `Job.connectorName` values), and/or a free-text search against Job Name. They sort the resulting set by any column ascending or descending. The table reflects every filter/sort/search change immediately, and all three combine.

**Why this priority**: This is a productivity feature: it makes the dashboard usable at scale (toward the parent spec's 1,000-job design target) but the dashboard remains functional without it for smaller working sets.

**Independent Test**: With at least 20 jobs across multiple statuses and at least 2 distinct `connectorName` values, apply each filter type in isolation and combination, type a search query, and click each column header to toggle sort. Verify the table reflects the correct intersection at each step.

**Acceptance Scenarios**:

1. **Given** a dashboard populated with jobs across multiple statuses, **When** the tester selects a subset of statuses in the status filter, **Then** only rows whose status is in that subset are visible.
2. **Given** filters are active and the tester types a substring of a job's name into the search box, **When** the search updates, **Then** the visible rows are the intersection of the active filters and the case-insensitive name substring match.
3. **Given** any non-empty table view, **When** the tester activates a column header, **Then** the table sorts ascending by that column; a second activation toggles to descending; the active sort column and direction are visually indicated.
4. **Given** active filters yield zero matches, **When** the tester views the dashboard, **Then** they see a "no matches" empty state distinct from the "no jobs in database" empty state, with a one-click way to clear filters.

---

### User Story 5 - Watch a running job's status update without refreshing (Priority: P3)

A tester who has just started a long-running job leaves the dashboard open in their browser. As the job progresses, the row's status badge, processed/total counter, and Failed Count update on screen automatically. When the job reaches a terminal state, the row stops changing. The tester never needs to hit reload.

**Why this priority**: Near-real-time updates make the dashboard genuinely useful as a "watchwindow" during long runs. Without it, the table is a frozen snapshot that misleads the tester. Equal priority with filters/sort/search because it's also a usability layer on top of the core P1 listing.

**Independent Test**: Start a job that takes long enough to be observable (e.g., a 20-row job with artificial delay). On a separate machine or browser, open the dashboard before the job finishes. Without interacting with the page, verify that within 5 seconds of any change to that job's status or counters in the database, the visible row reflects the change. After the job reaches a terminal state, verify the row stops changing.

**Acceptance Scenarios**:

1. **Given** the dashboard is open and shows a job in `running` state, **When** that job's processed count or failed count changes in the database, **Then** the corresponding row reflects the new values within 5 seconds without any tester interaction.
2. **Given** the dashboard is open and shows a job in `running` state, **When** that job transitions to a terminal status (`completed` / `failed` / `cancelled`), **Then** the row's badge and counters update to the terminal values within 5 seconds and the row stops requesting updates.
3. **Given** the dashboard is open and shows only jobs in terminal states, **When** the tester waits, **Then** the page issues no further status-update activity for those rows.

---

### Edge Cases

- The database is empty (no jobs yet) — show the empty-state CTA, not a blank table or an error.
- A historical job's snapshotted `ConnectorRegistration` has since been archived (soft-deleted) in `013` (per `013 FR-014`) — the row still renders the persisted `Job.connectorName` (the snapshot of the registration's `displayName` at job-creation time, which remains meaningful regardless of the registration's current archival state), and the Connector filter still includes that label as an option. Hard-deletion of a registration referenced by any historical job is blocked by `013 FR-019` (and analogously `014 FR-024` for evaluators), so the "registration entirely gone" case cannot occur in normal operation; if it somehow did, the snapshot remains the source of truth for the dashboard's rendering.
- A job is in `draft` state (created but never started) — `Started At`, `Completed At`, and counters render as empty/zero; the row is still clickable but the detail view is responsible for what it shows.
- A `draft` job is deleted while the dashboard is open — its row disappears from the visible table without page-level error.
- A very long Job Name overflows its column — the cell truncates with an affordance to view the full name (tooltip on hover or expansion-on-click), without breaking the row layout.
- A filter combination produces zero rows — show a distinct "no matches under current filters" state, separate from the "no jobs in database" state, and offer a one-click clear-filters action.
- The harness process restarts while the tester has the dashboard open — the live-update mechanism reconnects cleanly without requiring a manual refresh, or surfaces a non-blocking notice that updates have paused if reconnection fails.
- The tester has the dashboard open in two browser tabs simultaneously — both reflect updates independently and correctly.
- The job database has at or near the parent spec's 1,000-job design target — the table remains interactive (filter/sort/search latency stays under 200 ms).
- A Connector filter or status filter is applied, then the only matching job is deleted — the table transitions to the "no matches" state automatically.
- The tester triggers delete on a `failed` or `cancelled` row while the dashboard is open in a second browser tab — the second tab MUST reflect the deletion (row disappears) within the auto-update interval defined in `FR-012`.
- The tester triggers delete on a row whose status changes between confirmation and execution (e.g., a connector retry runs in the background between the click and the confirm-OK) — the harness MUST re-check status at execute time and decline the delete with an actionable message if the row is no longer `failed` or `cancelled`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST render the dashboard as the root route of the harness web UI and as the page the tester first sees when launching the harness.
- **FR-002**: Dashboard MUST display every test job that exists in the local database as one row in a single table view. No job MUST be omitted from the default (unfiltered) view. The table MUST be rendered as a single scrollable list — there is no pagination, no "load more" affordance, and no virtualization in v1. Within the parent spec's 1,000-job design target, all rows are rendered at once and the browser handles scrolling.
- **FR-003**: Each row MUST display the following columns, in this canonical order: Job Name, Status, Created By, Created At, Started At, Completed At, Connector, Utterance Count (formatted as `processed/total`), Failed Count, Harness Version. The Created By column shows the `Job.createdBy` value (OS-derived per parent `FR-026`); on a single-user installation, the column will typically show one repeated name. The Connector column shows the `Job.connectorName` value — the **verbatim snapshot** of the selected `ConnectorRegistration.displayName` at job-creation time (per `001 FR-023`, `009 FR-001`, snapshotted by the wizard per `003 FR-007`'s Step 3 Next). The display value is immutable past `draft` and is the snapshot, NOT the live registration's current display name. There is no separate "Connector Type" column; `connectorName` serves the "what kind of connector is this?" UX role. The Harness Version column shows the `Job.harnessVersion` value (per `009 FR-001`) — the harness version stamped at job creation time; on a single-install dashboard this is typically constant across rows but becomes meaningful after an upgrade or when the tester compares historical jobs across versions. The Utterance Count's `processed` numerator and the Failed Count value source directly from `Job.processedCount` and `Job.failedCount` per `009 FR-001`; cancelled-before-process rows (per `009 FR-003a`, `errorStatus = "cancelled"`) are reflected only in the gap `totalUtteranceCount - processedCount` and are not added to either counter.
- **FR-003a**: The Created At, Started At, and Completed At columns MUST render timestamps in a hybrid format: relative phrasing for timestamps within the last 24 hours (e.g., "just now", "5 minutes ago", "3 hours ago"); absolute datetime in the tester's local timezone (`YYYY-MM-DD HH:MM`) for timestamps older than 24 hours. The alternate representation MUST be available on hover/tooltip. Sorting by these columns MUST always sort by the underlying absolute timestamp value, never by the display string.
- **FR-004**: The Status column MUST render as a color-coded visual badge that distinguishes at minimum the lifecycle states defined by the parent spec: `draft`, `queued`, `running`, `cancelling`, `completed`, `failed`, `cancelled`.
- **FR-005**: A `completed` job whose Failed Count is greater than zero MUST be visually distinguished from a `completed` job with zero failed rows (for example via a "Completed with errors" sub-label, a distinct shade, or an icon affix), without introducing a distinct underlying status value. The distinction MUST be derivable purely from `status == completed` and `failedCount > 0`.
- **FR-006**: Dashboard MUST provide a filter UI that supports: (a) multi-select on job Status, (b) multi-select on Connector whose option set is the distinct set of `Job.connectorName` snapshot values actually present in the persisted Job rows, and (c) multi-select on Created By whose option set is the distinct set of `createdBy` values actually present in the persisted Job rows. Neither the Connector filter nor the Created By filter consults a separate registry — both just enumerate distinct values seen in the persisted data. Since `connectorName` is a verbatim snapshot of the registration's `displayName` (per `001 FR-023`, `009 FR-001`), the Connector filter's granularity is determined by how registrations are named in `013` — one display name per registration, possibly shared across jobs that selected that same registration.
- **FR-007**: Dashboard MUST provide a free-text search input that filters visible rows by case-insensitive substring match against Job Name.
- **FR-008**: Active filters and the current search query MUST combine multiplicatively (AND): only rows that match every active filter and the search query MUST be visible.
- **FR-008a**: Filters and search MUST be re-evaluated live against every row whose state changes via the near-real-time update mechanism (`FR-012`). A row that newly matches the active filter/search set MUST appear immediately; a row that ceases to match MUST disappear immediately. There is no snapshot semantics, no "stale match" indicator, and no manual re-apply step.
- **FR-009**: Dashboard MUST support sorting by any displayed column, both ascending and descending, with a persistent visual indicator of the active sort column and direction. Activating the sort control on a non-active column MUST sort ascending by default; activating it again MUST toggle to descending.
- **FR-009a**: The default sort on first load (and on a full filter/search reset) MUST be Created At descending — newest jobs at the top. Any tester-initiated sort MUST override this for the remainder of the browser session.
- **FR-010**: Activating (clicking) the body of any job row MUST navigate to the Job Detail View (Module 13) for that specific job.
- **FR-010a**: The dashboard MUST NOT expose row-level job actions in v1 **except** the dashboard-cleanup delete defined in `FR-010b`. Cancel (for `queued` / `running` jobs) and delete-of-draft (for `draft` jobs) remain reachable only through the Job Detail View (Module 13). The dashboard is otherwise a read-only triage and navigation surface; the only top-level tester-actionable affordance is the "Create New Job" entry point (`FR-011`).
- **FR-010b**: The dashboard MUST expose a row-level **delete** affordance, but **only** on rows whose status is `failed` or `cancelled`. Activating delete MUST prompt the tester for confirmation (destructive, irreversible action) and, on confirmation, MUST permanently remove the job and all of its persisted rows from the local database (cascade per `009 FR-010` / `FR-012`). The row MUST disappear from the dashboard immediately after confirmation. Rows in any other status (`draft`, `queued`, `running`, `cancelling`, `completed`) MUST NOT display the delete affordance at all. Per `FR-010`, activating the in-row delete control MUST NOT trigger row-level navigation to the detail view.
- **FR-010c**: The dashboard MUST also expose a top-level **"Clear all failed and cancelled"** action (positioned alongside or near the "Create New Job" control). Activating it MUST open a confirmation prompt that states the exact count of jobs that will be deleted (combined `failed` + `cancelled` count visible in the database, regardless of any active filter or search). On confirmation, the harness MUST delete every job whose status is `failed` or `cancelled` at the moment of execution, cascading to all of their persisted rows per `009 FR-010` / `FR-012`, atomically with respect to the database (either all are deleted or none are). The control MUST be disabled (or hidden) when the count is zero. Multi-select / checkbox-based selection is out of scope.
- **FR-011**: Dashboard MUST display a clearly-discoverable "Create New Job" control that, when activated, opens the Job Creation Wizard (Module 9). This control MUST be visible in both the populated and the empty-state views.
- **FR-012**: For every visible job whose status is non-terminal (`queued`, `running`, or `cancelling`), the dashboard MUST update its Status, processed-count, total-count, and Failed Count without requiring the tester to refresh the page. The maximum time between an underlying change in the database and the dashboard reflecting it MUST be ≤ 5 seconds. The implementation mechanism (e.g., polling, server-sent events, WebSocket) is a plan-level decision.
- **FR-013**: For every visible job whose status is terminal (`completed`, `failed`, or `cancelled`), the dashboard MUST NOT continue to poll/subscribe for updates on that row. (Newly-added or status-transitioning rows MUST start/stop participating in updates accordingly.)
- **FR-014**: Dashboard MUST render an explicit, distinguishable empty state when the database contains zero jobs, surfacing the "Create New Job" call-to-action.
- **FR-015**: Dashboard MUST render a separate, distinguishable empty state when active filters or search produce zero matching rows (different from FR-014's "no jobs at all" state), and MUST offer a one-action mechanism to clear all filters and the search query.
- **FR-016**: Dashboard MUST handle gracefully the case where a row's snapshotted `connectorId` refers to a `ConnectorRegistration` that has since been archived (per `013 FR-014`): render the snapshotted `Job.connectorName` value as-is (it remains meaningful regardless of the registration's current archival state, since the Job carries the full snapshot per `001 FR-023` / `009 FR-001`), and surface it in the Connector filter so the tester can still filter to those jobs. Hard-deletion of a registration referenced by historical jobs is blocked by `013 FR-019`, so the "registration entirely gone" case cannot occur in normal operation; if it somehow does, the snapshot remains the sole source of truth for the dashboard's rendering and no separate "deleted connector" indicator is required.

### Key Entities *(include if feature involves data)*

- **Job List Row**: The per-job projection rendered as one table row. Sourced from a `Job` (parent spec; `009 FR-001`) plus aggregations across its Utterances. Carries: `jobId`, `jobName`, `status`, `createdBy`, `createdAt`, `startedAt` (nullable), `completedAt` (nullable), `connectorName` (the verbatim snapshot of the selected `ConnectorRegistration.displayName` at job-creation time, per `001 FR-023` / `009 FR-001`), `processedCount`, `totalUtteranceCount`, `failedCount`, `harnessVersion`. The "Completed with errors" presentation is derived (`status == completed && failedCount > 0`), not stored.
- **Dashboard View State** *(transient, client-side)*: The currently-active filter selections, search query, and sort column/direction. Does not need to persist across browser sessions for v1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When the tester opens the harness, the dashboard renders the first visible job rows (or the empty state) within 1 second on a typical tester laptop with up to 1,000 jobs in the database.
- **SC-002**: A change to a non-terminal job's status, processed count, or failed count in the database is reflected on the visible row within 5 seconds without any tester interaction.
- **SC-003**: Applying a filter, changing sort, or typing a search query updates the visible row set within 200 ms (excluding initial data load) for a list of up to 1,000 jobs.
- **SC-004**: A tester can locate any specific job by name from a list of 1,000 jobs in under 10 seconds using the search box.
- **SC-005**: 100% of jobs in the database are reachable from the dashboard's default (unfiltered) view — no row is dropped without an explicit tester filter or search query producing the exclusion.
- **SC-006**: A `completed` job with one or more failed rows is visually distinguishable from a `completed` job with zero failed rows from at least three feet away on a typical laptop display (i.e., the distinction is communicated by color/iconography, not requiring the tester to read text).
- **SC-007**: Once every visible job is in a terminal state, the dashboard issues no further status-update network/process activity for those rows, verifiable by observation of network or process traffic for at least 30 seconds.
- **SC-008**: From the dashboard, the "Create New Job" entry point is reachable in exactly one tester action (one click or one keyboard activation), regardless of whether the table is populated, empty, or filtered to zero rows.
- **SC-009**: When the database contains any combination of `failed` and `cancelled` jobs, the tester can clear all of them — and only those — in two actions (click "Clear all failed and cancelled" + confirm), with the confirmation prompt showing the exact count before commit.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. The parent's "single-user, no auth, localhost" identity model applies. Per Round 4 (driven by Module 3), the Created By column and Created By filter ARE present, sourced from `Job.createdBy` (OS-derived per parent `FR-026`). The dropped items from the original Module 12 input are: "authenticated landing page" (there is still no auth flow / login challenge) and "dropdown of known users" (there is no separate users registry; the filter enumerates distinct `createdBy` values seen in persisted Jobs instead).
- Module 9 (Job Creation Wizard) and Module 13 (Job Detail View) exist as separate feature specs (TBD) and provide the navigation targets referenced by FR-010 and FR-011. The Dashboard module is responsible only for the navigation handoff, not for the wizard or detail-view content.
- The job status lifecycle and enum values (`draft` / `queued` / `running` / `cancelling` / `completed` / `failed` / `cancelled`) are inherited from the parent spec. This spec does not redefine them; "Completed with errors" is a UI presentation only.
- The 1,000-job scale ceiling is inherited from the parent spec's design target (`SC-010`). Dashboards may render larger sets but performance guarantees apply only up to 1,000 jobs.
- Per-tester preferences (saved filters, default sort) are out of scope for v1. Dashboard view state resets each browser session.
- Deleting **draft** jobs is per parent `FR-001` (handled by Module 13 detail view, not the dashboard). Deleting **failed / cancelled** jobs IS available from the dashboard (Round-3 revision: per-row delete + bulk "Clear all failed and cancelled" action — see `FR-010b` / `FR-010c`). **Completed** jobs remain non-deletable from the dashboard (and indeed from any surface in v1) — preserved as the historical record of successful runs per parent `FR-001a`.
- The "near-real-time" mechanism — polling vs. server-sent events vs. WebSocket — is an implementation-plan decision; the spec only constrains the observable behavior (≤ 5-second update latency, stop-polling-on-terminal).
- The Connector column shows the `Job.connectorName` value, which is a **verbatim snapshot** of the selected `ConnectorRegistration.displayName` at job-creation time (per `001 FR-023`, `009 FR-001`, captured by the wizard per `003 FR-007`'s Step 3 snapshot rule). Post-2026-05-29-reshape, there is no per-job tester-editable name override — the dashboard simply renders the snapshot. Display names of registrations themselves are managed in `013` (connector CRUD); the dashboard makes no attempt to disambiguate variants or versions of the same underlying connector beyond what the registration's display name carries.
