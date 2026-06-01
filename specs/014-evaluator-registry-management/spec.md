# Feature Specification: Evaluator Registry & Management (Module 14)

**Feature Branch**: `014-evaluator-registry-management`

**Created**: 2026-05-29

**Status**: Draft

**Input**: User description: "Wizard / CRUD module where evaluation agent endpoints are registered and maintained. Each evaluation strategy is hosted as its own HTTP service built and run outside the harness; this module is the tester-facing UI for registering / editing / archiving / deleting / inspecting those endpoints. The wizard's Step 4 (`specs/003-job-creation-wizard`) populates its evaluator dropdown exclusively from registrations created here; if an evaluator is not registered, it cannot be added to a job. Same pattern as the connector CRUD module (`013`), but for evaluators."

> **Parent context**: This module sits alongside `specs/008-evaluation-agent-framework` — `008` defines the **wire protocol** by which the harness talks to an evaluator service over HTTP (and the generic HTTP client + bundled mock evaluator + at-rest credential encryption, inherited from `007`). `014` defines the **CRUD UI and persistence** for registered evaluator endpoints. Together they make the remote-service evaluator model operational. The job-creation wizard (`specs/003-job-creation-wizard`) consumes `014`'s "list active registrations" affordance to populate its Step 4 dropdown; the wizard does not render a per-evaluator configuration form anymore — all evaluator configuration (endpoint URL, auth, timeout, declared scoring dimensions) lives on the registration, not on the job. Parent-spec premises apply: single-user, no auth on the harness UI. The persistence layer (`specs/009-data-model-persistence`) defines the `EvaluationAgentRegistration` entity that this module's CRUD operations write to. The Job entity snapshots the full registration at job-creation time (per parent `FR-023`), so post-creation edits to a registration do not retroactively affect historical jobs. Soft-delete (archival) is the default deletion semantic per the 2026-05-29 design call; hard-delete is available as a separate, explicit operation that is gated when historical jobs reference the registration. This module's structure is intentionally symmetric with `specs/013-connector-registry-management`; differences are limited to evaluator-specific fields (declared scoring dimensions instead of expects-per-row-password) and the wire-protocol shape used by the "Test connection" affordance.

## Clarifications

### Session 2026-05-29

- Q: Deletion semantics — soft (archived, hidden from wizard but historical jobs still display the name) or hard (registry row removed entirely; historical jobs render from snapshot)? → A: **Soft delete is the default.** Symmetric with `013`. Archived registrations are hidden from the wizard's Step 4 dropdown and from the registry's default list view, but remain in the underlying persistence and remain navigable via a "Show archived" filter in the registry-management UI. The tester MAY restore an archived registration at any time. Hard delete is available as a separate, more deliberate operation that is gated when historical jobs reference the registration (see `FR-014`).
- Q: Should the CRUD form validate that the endpoint is reachable when the tester saves? → A: **Optional, non-blocking "Test connection" button.** Symmetric with `013`. A button on the form fires a sample request to the endpoint and surfaces the response. It does NOT block save.
- Q: What is the shape of the `auth descriptor` persisted on an evaluator registration? → A: Identical to `013`'s `authDescriptor` shape — `{ mode: "none"|"bearer"|"api-key-header"|"basic", headerName?: string, credential?: <encrypted> }`. The harness uses the same machine-local symmetric key (`007 FR-014`) and the same encryption utility (`007 FR-013`) for evaluator credentials. There is no separate evaluator-side crypto.
- Q: What identifies an `EvaluationAgentRegistration` — does the tester pick the `evaluationAgentId` or does the harness assign it? → A: **The harness assigns the `evaluationAgentId` automatically** (symmetric with `013`'s `connectorId` rule). The tester does NOT type an id; they pick the human-readable display name. Two registrations MAY share the same display name (the harness disambiguates them in the dropdown by appending the short tail of the id, per `003`'s display rules); attempting that emits a warning but does not block save. The auto-assigned id is immutable for the life of the registration.
- Q: How are declared scoring dimensions captured? → A: **As an ordered list of strings entered by the tester on the registration form.** A dynamic list input lets the tester add, remove, and reorder dimension names (e.g., `["relevance", "groundedness", "coherence"]`). The order MUST be preserved — it drives column ordering in the detail view (`004`) and export (`005`). Names MUST be non-empty and SHOULD be unique within a single registration (duplicates trigger a non-blocking warning; downstream consumers de-duplicate when rendering). Empty list `[]` is valid (for purely-verdict-based evaluators like a binary safety classifier).
- Q: Where does the evaluator service's own internal API key (e.g., its OpenAI / Anthropic key) live? → A: **Not on the registration.** The evaluator service holds its own internal credentials wherever it chooses (env vars on the host, its own secrets manager, etc.). The harness's auth credential on `EvaluationAgentRegistration` is for the harness-to-evaluator-service hop only (e.g., to gate access to the evaluator service itself). The evaluator's downstream-LLM credential is the evaluator service's concern.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Register a new evaluator endpoint (Priority: P1)

The tester opens the Evaluator Registry management UI, clicks "Register new evaluator", and fills in a form: human-readable display name, description, endpoint URL, auth descriptor (mode + credentials), `timeoutSeconds`, and an ordered list of declared scoring dimensions. They optionally click "Test connection" to verify the endpoint responds correctly. They click Save. The new registration appears in the registry's active list and immediately becomes selectable in the job-creation wizard's Step 4 dropdown.

**Why this priority**: Without this story, no evaluator can ever be registered, and therefore no job can ever be created. This is the MVP of the module.

**Independent Test**: Open the registry-management UI on a fresh install, click "Register new evaluator", fill in the form pointing at the bundled mock evaluator's local URL with auth mode `none` and declared dimensions `["mock_dimension_a", "mock_dimension_b"]`, save, and verify (a) the new registration appears in the registry's active list, (b) it appears in the wizard's Step 4 dropdown on the next wizard launch, (c) a job created against it runs end-to-end per `008 US1`.

**Acceptance Scenarios**:

1. **Given** the registry-management UI is open, **When** the tester clicks "Register new evaluator", **Then** the UI renders a creation form with fields for display name (required, non-empty string), description (required, non-empty string — evaluator descriptions are operationally important so testers can recall what each evaluator scores), endpoint URL (required, validated as a syntactically well-formed URL), auth mode (required, dropdown of `none`/`bearer`/`api-key-header`/`basic`), the auth-mode-specific credential fields (rendered conditionally per the chosen mode, identical to `013 FR-005`), `timeoutSeconds` (required integer in plan-defined range, default 60 — evaluators typically take longer than connectors because of LLM latency), and declared scoring dimensions (a dynamic ordered list of strings, see US3).
2. **Given** the form is filled in correctly, **When** the tester clicks Save, **Then** the harness (a) assigns a fresh immutable `evaluationAgentId`, (b) encrypts any secret credential fields per `007 FR-013`, (c) persists an `EvaluationAgentRegistration` row with `archived = false` and current timestamps, (d) navigates back to the registry list with the new registration visible.
3. **Given** the form has any required field empty or invalid (malformed URL, negative timeout, declared dimension entry that is empty string), **When** the tester clicks Save, **Then** save is blocked, the offending field is highlighted, and an inline error message names the problem.
4. **Given** the tester clicks "Test connection" before saving, **When** the form has at minimum a syntactically valid endpoint URL and an auth descriptor, **Then** the harness issues a sample `POST` request to the endpoint with a test contract body (a small, syntactically valid Standard Evaluation Contract instance — see `FR-025`) and surfaces the result inline: HTTP status, response body preview (truncated), or transport / timeout / auth error / EvaluationResult validation error. The result is informational; Save remains enabled regardless.
5. **Given** the tester has not yet clicked Save, **When** they navigate away from the form, **Then** the harness prompts them to confirm discarding unsaved changes (symmetric with `013`).

---

### User Story 2 - Edit an existing evaluator registration (Priority: P1)

The tester opens the registry list, clicks an existing registration, edits its fields (e.g., rotates the bearer token, bumps `timeoutSeconds`, refines the declared scoring dimensions, fixes a typo in the display name), and saves. The edit takes effect immediately for any **future** job created against this registration. Historical jobs that already snapshotted this registration are NOT affected.

**Why this priority**: Credential rotation is operationally inevitable; refining the declared dimension list (e.g., adding a new dimension as the evaluator service evolves) is similarly inevitable. Without edit, every change would require deleting and re-creating, breaking the snapshot history.

**Independent Test**: Edit a registration to add a new scoring dimension and change the display name. Verify (a) future wizard launches show the new display name and any UI surfaces that pre-render dimension columns include the new dimension, (b) historical jobs in the dashboard still show the old display name and the old (snapshotted) dimension list when expanded (per parent `FR-023`), (c) a fresh job created against the edited registration executes with the new dimension expectations.

**Acceptance Scenarios**:

1. **Given** an active registration in the list, **When** the tester clicks it, **Then** the registry-management UI renders the same form as in US1, pre-populated with the registration's current values. Secret credential fields display as fully-masked placeholders; the tester MAY click a "Replace credential" affordance to enter a new value. Existing credentials are NEVER displayed in plaintext.
2. **Given** the tester edits one or more fields, **When** they click Save, **Then** the harness re-encrypts any new credential values, updates the persisted `EvaluationAgentRegistration`, bumps `updatedAt`, and returns to the list view.
3. **Given** the tester edits the registration's declared scoring dimensions (adds, removes, or reorders entries), **When** an existing job in the dashboard references this registration, **Then** the existing job's detail view and export continue to render dimensions in the OLD order (snapshotted on the job per parent `FR-023`); only future jobs see the new dimension list.
4. **Given** the tester clicks "Test connection" while editing, **When** the form's current (possibly edited) values are used, **Then** the test runs against those in-form values without persisting them.
5. **Given** the registration's `evaluationAgentId` is immutable, **When** the tester views the edit form, **Then** the id is displayed as a read-only field (in a debug / metadata section).

---

### User Story 3 - Declare and refine the evaluator's scoring dimensions (Priority: P1)

The tester knows what the evaluator service produces (e.g., a faithfulness evaluator emits scores for `relevance` and `groundedness`; a tone evaluator emits scores for `empathy`, `professionalism`, `warmth`). On the registration form, the tester captures these as an ordered list of dimension names. The order matters — it controls the column order in `004` (detail view) and `005` (export). The tester can add, remove, and reorder dimensions on edit. The harness uses the declared list to (a) populate the read affordance `008 FR-009(c)` for downstream UI / export pre-rendering, and (b) compute `harnessAnnotations.unexpected_score_dimensions` when the evaluator's actual output diverges (per `008 FR-005a`).

**Why this priority**: Without declared dimensions, the detail view and export cannot pre-render column structure for queued/running rows, and the soft-warning mechanism in `008 FR-005a` cannot function. Equal-priority with US1/US2 because the dimension list is integral to the registration model.

**Independent Test**: Register an evaluator with declared dimensions `["A", "B"]`. Run a job whose evaluator service emits scores entries with `parameter_name` values `[{name: "A"}, {name: "C"}]` (missing `B`, emitting unexpected `C`). Verify (a) the detail view renders the dimension columns in declared order `[A, B]`, with the cell for `B` showing the "no score returned" placeholder and the unexpected `C` surfaced visibly per `harnessAnnotations`, (b) editing the registration to add `C` to the declared list does NOT alter the historical row's display (per parent `FR-023`).

**Acceptance Scenarios**:

1. **Given** the registration form's "Scoring dimensions" input, **When** the tester types a dimension name and presses Enter (or clicks "Add"), **Then** the dimension is appended to the ordered list. The tester MAY click an "X" on any entry to remove it. The tester MAY drag entries (or use up/down arrows) to reorder.
2. **Given** the tester enters two dimensions with the same string, **When** they save, **Then** the form emits a non-blocking warning ("Duplicate dimension names — downstream consumers will de-duplicate when rendering"); Save proceeds normally.
3. **Given** the tester enters a dimension name with leading/trailing whitespace, **When** they add it, **Then** the form MUST trim the whitespace before adding. Empty strings (after trimming) MUST be rejected with an inline error.
4. **Given** the dimension list is saved, **When** any harness module queries `008 FR-009(c)` for this evaluator's dimensions, **Then** the response is the ordered list exactly as saved.
5. **Given** an editor reorders the dimension list and saves, **When** a future job is created against this registration, **Then** the new order is snapshotted onto the Job (per parent `FR-023`); historical jobs retain the prior order in their own snapshots.

---

### User Story 4 - Archive (soft-delete) an evaluator that is no longer needed (Priority: P1)

The tester wants to remove an evaluator from the wizard's selectable list — perhaps because the evaluator service was retired, or the registration was a mistake. Symmetric with `013 US3`. Archive flips a flag; the registration disappears from the wizard's Step 4 dropdown and from the registry's default list (still visible under "Show archived"). Historical jobs continue to render and execute normally. Restore is available.

**Why this priority**: Without archival, the wizard's dropdown grows unboundedly. Soft-delete is the right semantic; hard-delete would break historical-job audit trails.

**Independent Test**: Symmetric with `013 US3`: archive one registration, verify it disappears from the registry's default list and the wizard's Step 4 dropdown, verify historical jobs still show its display name (from snapshot), verify the "Show archived" filter reveals it with an "Archived" badge, verify Restore returns it to active.

**Acceptance Scenarios**:

1. **Given** an active registration, **When** the tester clicks Archive (inline / form / bulk), **Then** the harness sets `archived = true`, sets `archivedAt`, bumps `updatedAt`.
2. **Given** a just-archived registration, **When** the tester opens the wizard's Step 4, **Then** the archived registration does NOT appear in the dropdown.
3. **Given** a historical job referencing the archived registration, **When** the tester opens the dashboard or detail view, **Then** the job's evaluator display reads exactly as it did before archival (from the Job snapshot).
4. **Given** an archived registration, **When** the tester clicks Restore in the "Show archived" filter, **Then** `archived` flips back to false, the registration reappears in the wizard's Step 4 dropdown on next launch.
5. **Given** a job whose snapshot points to an archived registration, **When** the orchestrator dispatches its rows at execution time, **Then** dispatch proceeds normally using the Job snapshot (per `008 FR-012`–`FR-013`).

---

### User Story 5 - List, filter, and inspect registered evaluators (Priority: P2)

Symmetric with `013 US4`. The registry-management UI shows a list with active/archived/all filter, substring search, and per-row display of: display name, endpoint URL (truncated), auth mode (masked credential), timeout, declared scoring dimensions (preview — e.g., first 3 with "+ 2 more"), archived state, last-updated timestamp.

**Why this priority**: Discoverability scales with project lifetime. P2 because the registry works without it.

**Independent Test**: Register 5 evaluators with varied display names and dimension lists; archive 2 of them. Verify (a) default list shows the 3 active ones, (b) "All" filter shows all 5 with archived ones badged, (c) "Archived only" shows the 2, (d) substring search filters across all states, (e) the dimension preview is visible per row.

**Acceptance Scenarios**:

1. **Given** the registry-management UI is open, **When** it loads, **Then** by default it shows the list of `archived = false` registrations, ordered alphabetically by display name (case-insensitive).
2. **Given** the list view, **When** the tester switches the filter to "Archived" or "All", **Then** the list updates; archived entries show an "Archived" badge.
3. **Given** the search box, **When** the tester types a substring, **Then** the list filters in real-time on display name (case-insensitive); the filter composes with the active/archived/all filter.
4. **Given** any row in the list, **When** the tester clicks it, **Then** the edit form opens pre-populated. Inline row actions MAY include Archive / Restore / Delete (hard).
5. **Given** a registration in the list, **When** auth-related fields are displayed, **Then** credential values are NEVER shown in plaintext — only the auth mode label and (for `api-key-header`) the header name.
6. **Given** a registration with many declared dimensions, **When** the row is rendered, **Then** the dimension preview shows the first 3 (in declared order) with a count of the remaining (e.g., `"relevance, groundedness, coherence, + 2 more"`); the full list is visible on click-through.

---

### User Story 6 - Hard-delete an evaluator registration with no historical references (Priority: P3)

Symmetric with `013 US5`. Hard-delete is available for cleanup of registrations that were created by mistake and never referenced by any job. The harness blocks the action if any historical Job references the registration's `evaluationAgentId`; otherwise it removes the row from persistence.

**Why this priority**: Soft-delete handles 99% of cleanup needs; hard-delete is rare. P3 because it can ship after the rest of the module is operational.

**Independent Test**: Register an evaluator, create no job against it, click "Delete permanently". Verify the row is removed and not visible under any filter. Then register another, create a job against it (without running), attempt "Delete permanently". Verify the action is blocked.

**Acceptance Scenarios**:

1. **Given** a registration with zero historical Job references, **When** the tester clicks "Delete permanently" and confirms the destructive-action dialog, **Then** the harness removes the `EvaluationAgentRegistration` row from persistence.
2. **Given** a registration with one or more historical Job references (any job whose snapshot's `evaluationAgentId` matches this registration's id), **When** the tester clicks "Delete permanently", **Then** the action is blocked with a message naming the count of referencing jobs and directing the tester to use Archive instead.
3. **Given** the destructive-action dialog, **When** the tester cancels, **Then** no change is made.

---

### Edge Cases

- The tester attempts to register an evaluator with a malformed endpoint URL — Save MUST be blocked with an inline error.
- The tester attempts to register two evaluators with the same display name — allowed; a non-blocking warning surfaces explaining the wizard's dropdown will disambiguate by `evaluationAgentId` tail.
- The tester clicks "Test connection" against an unreachable endpoint — error surfaced inline; Save not blocked.
- The tester clicks "Test connection" and the endpoint returns a 2xx with a body that is NOT a valid EvaluationResult (missing required field, bad verdict, etc.) — the test result MUST surface the specific validation problem (e.g., "Response has `evaluationVerdict: 'maybe'` which is not in the closed enum"). Save is not blocked.
- The tester clicks "Test connection" and the endpoint emits scores entries with `parameter_name` values NOT in the form's currently-declared dimension list — the test result MUST surface this as a SOFT warning (e.g., "Endpoint emitted dimensions not in your declared list: ['Z']") symmetric with the runtime `harnessAnnotations.unexpected_score_dimensions` behavior. Save is not blocked.
- The harness's machine-local encryption key is unavailable — Save of any registration with a credential MUST be blocked with the actionable "machine-local key missing or wrong" error per `007 FR-016`. Save of a registration with auth mode `none` MAY succeed (nothing to encrypt).
- The tester archives a registration that is currently snapshotted into an actively-`running` job — archival succeeds; the in-flight job continues to use the snapshot.
- The tester restores an archived registration whose display name now collides with another active registration — restoration succeeds (no unique constraint); standard disambiguation applies.
- The tester attempts to edit the auto-assigned `evaluationAgentId` — the field is read-only.
- The tester edits an active registration's auth mode (e.g., from `bearer` to `none`) — Save succeeds; the previously-stored credential MUST be discarded; if switching to a mode that requires credentials, Save MUST be blocked until the new mode's credential fields are satisfied.
- The tester edits the declared scoring dimensions to remove a dimension that was previously declared — historical jobs that snapshotted the prior list continue to render that dimension; future jobs see the new list. The harness MUST NOT migrate historical snapshots.
- The tester reorders the dimension list — the new order is snapshotted onto future jobs only; historical jobs retain the prior order in their own snapshots (per parent `FR-023`).
- The tester opens the registry-management UI on a fresh install with zero registrations — the list view MUST show an empty state with a prominent "Register your first evaluator" call-to-action and a link / hint to the bundled mock evaluator quickstart for self-testing.
- The tester saves a registration with an empty declared dimension list — accepted (purely-verdict-based evaluators are a valid v1 use case per `008` edge case).

## Requirements *(mandatory)*

### Functional Requirements

#### Create

- **FR-001**: The harness MUST provide a "Register new evaluator" affordance in the registry-management UI that opens a creation form.
- **FR-002**: The creation form MUST collect: display name (required, non-empty string), description (required, non-empty string), endpoint URL (required, syntactically well-formed `http://` or `https://` URL), auth mode (required, one of `none`/`bearer`/`api-key-header`/`basic` per `007 FR-007`), mode-specific credential fields per `FR-005`, `timeoutSeconds` (required integer in plan-defined range, default 60), and declared scoring dimensions (ordered list of non-empty strings, MAY be empty list).
- **FR-003**: On Save with all validation passing, the harness MUST (a) auto-assign a fresh immutable `evaluationAgentId`, (b) encrypt any secret credential fields per `007 FR-013`, (c) persist a new `EvaluationAgentRegistration` row with `archived = false` and current timestamps, (d) return to the list view with the new registration visible.
- **FR-004**: Save MUST be blocked when any required field is empty, when `endpointUrl` is not syntactically a valid URL, when `timeoutSeconds` is outside the plan-defined range, when the auth-mode-specific credential fields per `FR-005` are not satisfied, or when any declared-dimension entry is empty-after-trim.

#### Auth descriptor

- **FR-005**: The auth descriptor's per-mode field requirements are identical to `013 FR-005`:
  - `none`: no credential fields shown.
  - `bearer`: a single required `token` field (secret, masked, encrypted on save).
  - `api-key-header`: required `headerName` (non-secret cleartext) AND `headerValue` (secret, masked, encrypted on save).
  - `basic`: required `username` (non-secret cleartext) AND `password` (secret, masked, encrypted on save).
- **FR-006**: When the auth mode is changed during editing, the previously-stored credential ciphertext MUST be discarded on Save; re-entering credentials for the new mode is required. Symmetric with `013 FR-006`.

#### Declared scoring dimensions

- **FR-007**: The form's "Scoring dimensions" input MUST be a dynamic ordered list of strings. The tester MUST be able to (a) add a new dimension by typing a name and confirming, (b) remove an existing dimension, (c) reorder dimensions (drag-and-drop, or up/down arrows — plan-level UI choice).
- **FR-008**: Each dimension name MUST be trimmed of leading/trailing whitespace on add. Empty-after-trim names MUST be rejected with an inline error.
- **FR-009**: Duplicate dimension names within a single registration MUST emit a non-blocking warning on save but MUST NOT block save. Downstream consumers de-duplicate when rendering.
- **FR-010**: An empty dimension list `[]` is valid (for purely-verdict-based evaluators per `008` edge case).
- **FR-011**: On save, the dimension list MUST be persisted in the exact order the tester arranged it. Read affordances (`008 FR-009(c)`) MUST return the list in the same order.

#### Read / List

- **FR-012**: The registry-management UI MUST provide a list view of `EvaluationAgentRegistration` records. The default filter MUST show only `archived = false` registrations, ordered alphabetically by display name (case-insensitive).
- **FR-013**: The list view MUST expose a filter control with at least three options: `Active` (default), `Archived`, `All`. The current filter MUST be visually indicated.
- **FR-014**: The list view MUST expose a search box that filters by case-insensitive substring match against display name. Search composes with the active/archived/all filter.
- **FR-015**: Each row MUST show: display name, endpoint URL (truncated), auth mode label (no credential), `timeoutSeconds`, declared scoring dimensions preview (first 3 in declared order with `+ N more` when applicable), archived state badge, `updatedAt` timestamp. Credential values MUST NOT be shown.

#### Update (Edit)

- **FR-016**: Clicking a row MUST open the edit form pre-populated with current values. Secret credential fields MUST display as a fully-masked placeholder with a "Replace credential" affordance; existing credentials MUST NEVER be returned in plaintext from persistence.
- **FR-017**: On Save from edit, the harness MUST (a) re-encrypt newly-entered credentials, (b) preserve existing ciphertext for fields the tester did NOT replace, (c) update the row in place, (d) bump `updatedAt`, (e) return to the list view.
- **FR-018**: The `evaluationAgentId` MUST be immutable across edits and MUST display as read-only.

#### Archive (soft-delete) / Restore

- **FR-019**: The harness MUST provide an Archive action accessible from (a) the row's inline actions, (b) the edit form, (c) bulk action on multiple selected rows. On Archive: set `archived = true`, set `archivedAt`, bump `updatedAt`.
- **FR-020**: Archived registrations MUST NOT appear in the wizard's Step 4 dropdown. Archived registrations MUST appear in the registry's list view only under `Archived` or `All` filter.
- **FR-021**: The harness MUST provide a Restore action on archived registrations (inline / form / bulk). On Restore: set `archived = false`, clear `archivedAt` (or set `restoredAt` parallel — plan-level), bump `updatedAt`. Re-selectable in the wizard's Step 4 immediately.
- **FR-022**: Archival MUST NOT affect any historical Job that already snapshotted this registration. Per `008 FR-012`–`FR-013` and parent `FR-023`, the orchestrator resolves evaluator configuration from the Job snapshot, not the live registry.

#### Hard-delete

- **FR-023**: The harness MUST provide a "Delete permanently" action (inline / form). Visually destructive-styled. Requires a confirmation dialog.
- **FR-024**: Before hard delete, the harness MUST count Jobs whose snapshotted evaluator identity references this registration's `evaluationAgentId`. If > 0, the harness MUST block the action with a message naming the count and directing the tester to use Archive instead. If 0, the harness MUST present a confirmation dialog naming the registration; on confirm, MUST remove the row from persistence.
- **FR-025**: After hard delete, the registration MUST be absent from all UI views and queries. The `evaluationAgentId` MUST NOT be recycled for a future registration.

#### Test Connection

- **FR-026**: The creation and edit forms MUST expose a "Test connection" button. On click, the harness MUST construct a sample HTTP request using the form's current values and the evaluator wire protocol per `008 FR-002`, send it to the endpoint URL with the constructed auth header, await a response within `timeoutSeconds`, and display the result inline.
- **FR-027**: The test request body MUST be a small but syntactically valid Standard Evaluation Contract instance — e.g., a minimal contract with `testId: "test-connection"`, `utteranceId: "test-utt"`, `utteranceText: "ping"`, `chatbotResponse: "pong"`, `connectorId: "test-connection-connector"`, and any other fields the contract schema requires populated with placeholder values. The fixed sample MUST be documented in the UI alongside the button.
- **FR-028**: The displayed test result MUST include: HTTP status code (when received), a truncated EvaluationResult body preview (when received and ≤ a plan-defined byte cap), or a categorized error label (`endpoint unreachable`, `tls failure`, `timeout exceeded`, `auth credential decryption failed`, etc.) when no response was received.
- **FR-029**: For a 2xx response, the harness MUST additionally validate the body against the EvaluationResult shape per `008 FR-005b` and surface either success ("Endpoint returned a valid EvaluationResult"), a validation problem with diagnostic (e.g., "Response has `evaluationVerdict: 'maybe'` which is not in the closed enum"), or the soft-warning case where dimension names diverge from the form's currently-declared list (per `008 FR-005`/`FR-005a`).
- **FR-030**: The "Test connection" outcome MUST be informational only. The harness MUST NOT block Save regardless of outcome, and MUST NOT persist the test request / response / result.

#### Read API (consumed by other modules)

- **FR-031**: This module MUST expose (programmatically, to other harness modules) the same read affordances `008 FR-008`–`FR-013` describe: list active registrations, get registration by id, get declared scoring dimensions for an id, list active+archived for the management UI. This module is the implementation; `008` defines the contract.

### Key Entities *(include if feature involves data)*

- **EvaluationAgentRegistration**: The persisted record describing an evaluator service known to the harness. Detailed in `009 FR-001b` (new). Fields: `evaluationAgentId` (immutable string, harness-assigned), `displayName`, `description`, `endpointUrl`, `authDescriptor` (structured object per `FR-005`), `timeoutSeconds`, `declaredScoringDimensions` (ordered list of strings), `archived` (boolean), `createdAt`, `updatedAt`, `archivedAt` (nullable). Credential fields within `authDescriptor` are encrypted at rest per `007 FR-013`.
- **Test Connection Result**: A transient, in-memory representation of a single test-request/response pair fired by the "Test connection" button. Symmetric with `013`'s analogous entity. NOT persisted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A registered evaluator becomes selectable in the wizard's Step 4 dropdown on the next wizard launch — verifiable by registering an evaluator and immediately opening the wizard.
- **SC-002**: A registration's stored credential never appears in plaintext anywhere — verifiable by registering an evaluator with a known-distinctive credential and grepping the database file, the rendered UI pages, and any export file (zero matches expected).
- **SC-003**: Editing a registration's display name does NOT change the display name shown on any historical Job that snapshotted the earlier name — verifiable analogously to `013 SC-003`.
- **SC-004**: Editing a registration's declared scoring dimensions does NOT change the dimension order or contents on any historical Job's snapshot — verifiable by registering an evaluator with `[A, B]`, creating a job, editing to `[B, A, C]`, and confirming the historical job's detail view still renders `[A, B]`.
- **SC-005**: An archived registration is absent from the wizard's Step 4 dropdown — verifiable by archiving and re-launching the wizard.
- **SC-006**: An archived registration referenced by a historical Job is fully executable when the job is re-run — verifiable by archiving a registration with an unfinished job and confirming the job completes.
- **SC-007**: Hard-delete is blocked when a registration is referenced by any historical Job — verifiable by creating a job against a registration and attempting to hard-delete.
- **SC-008**: Hard-delete succeeds when a registration has zero historical Job references — verifiable by registering, never creating a job, and hard-deleting.
- **SC-009**: The "Test connection" button never blocks Save and never persists side effects — verifiable analogously to `013 SC-008`.
- **SC-010**: The "Test connection" button reports categorized outcomes accurately — verifiable by pointing the button at endpoints in each documented failure mode.
- **SC-011**: Declared scoring dimensions persist and are read back in the exact saved order — verifiable by registering with `["C", "A", "B"]`, querying the read affordance, and asserting the returned list is `["C", "A", "B"]`.
- **SC-012**: An empty declared-dimension list `[]` is acceptable on Save and produces a wizard / detail-view / export experience that gracefully renders a verdict-only result — verifiable by registering an evaluator with empty dimensions and running a job through.
- **SC-013**: Registry-management UI loads in a reasonable time with 100+ registrations (active + archived) — plan-level performance target.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, no auth on the harness UI. `EvaluationAgentRegistration` records carry no `createdBy` field of their own.
- The wire protocol that registered endpoints implement is defined in `specs/008-evaluation-agent-framework`. This module's "Test connection" button uses that protocol's request shape; this module does NOT redefine the protocol.
- The encryption story for stored credentials is inherited from parent `FR-023a` and `007 FR-013`–`FR-017`. This module reuses that utility; it does NOT introduce a separate mechanism. (And does not have a parallel encryption story for the evaluator service's own internal LLM credentials — those live on the evaluator service host, not on the registration; see the 2026-05-29 clarification.)
- The persistence layer (`009`) defines the `EvaluationAgentRegistration` schema; this module's spec describes the user-facing CRUD behavior and the field rules but defers the table / column shape to `009`.
- The wizard (`003`) is the primary consumer of the registry's read API. This module's UI and the wizard are separate navigation surfaces.
- Soft-delete is the default deletion semantic. Hard-delete is rare.
- "Test connection" is a productivity affordance, not a gating mechanism. Save MUST NOT be conditional on a successful test result.
- Display names are NOT unique. Wizard disambiguates by `evaluationAgentId` tail.
- The `evaluationAgentId` is harness-assigned and immutable.
- Declared scoring dimensions live on the registration, not the evaluator service. The evaluator service emits whatever it emits; the registration declares what the tester *expects* it to emit. Divergence is recorded in `harnessAnnotations` per `008 FR-005`/`FR-005a`, not as a hard failure.
- The "test contract" body sent by the "Test connection" feature is a fixed sample that satisfies the Standard Evaluation Contract schema. The evaluator service is expected to handle it gracefully (return a well-formed EvaluationResult); evaluators that depend on real chatbot output to function MAY return a low-confidence or default-verdict response for the test sample, which is acceptable — the goal of the test is to verify reachability / auth / protocol conformance, not evaluation quality.
- Bulk operations symmetric with `013`. Bundled mock evaluator pre-registration is a plan-level convenience, not spec-mandated.
- Structurally symmetric with `specs/013-connector-registry-management`. Where this spec is silent on an aspect that `013` addresses (e.g., empty-state UI, unique-constraint warnings), `013`'s rule applies by analogy.
