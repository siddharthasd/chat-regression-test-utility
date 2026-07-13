# Feature Specification: Connector Registry & Management (Module 13)

**Feature Branch**: `013-connector-registry-management`

**Created**: 2026-05-29

**Status**: Draft

**Input**: User description: "Wizard / CRUD module where connector endpoints are registered and maintained. Each chatbot under test (and, optionally, each independently-testable underlying agent of a top-level chatbot) is fronted by its own connector service hosted outside the harness; this module is the tester-facing UI for registering / editing / archiving / deleting / inspecting those endpoints. The wizard's Step 3 (`specs/003-job-creation-wizard`) populates its connector dropdown exclusively from registrations created here; if a connector is not registered, it cannot be added to a job."

> **Parent context**: This module sits alongside `specs/007-connector-framework` — `007` defines the **wire protocol** by which the harness talks to a connector service over HTTP (and the generic HTTP client + bundled mock connector + at-rest credential encryption). `013` defines the **CRUD UI and persistence** for registered connector endpoints. Together they make the remote-service connector model operational. The job-creation wizard (`specs/003-job-creation-wizard`) consumes `013`'s "list active registrations" affordance to populate its Step 3 dropdown; the wizard does not render a per-connector configuration form anymore — all connector configuration (endpoint URL, auth, timeout, expects-per-row-password flag) lives on the registration, not on the job. Parent-spec premises apply: single-user, no auth on the harness UI. The persistence layer (`specs/009-data-model-persistence`) defines the `ConnectorRegistration` entity that this module's CRUD operations write to. The Job entity (`009 FR-001`) snapshots the full registration at job-creation time (per parent `FR-023`), so post-creation edits to a registration do not retroactively affect historical jobs. Soft-delete (archival) is the default deletion semantic per the 2026-05-29 design call; hard-delete is available as a separate, explicit operation that is gated when historical jobs reference the registration.

## Clarifications

### Session 2026-05-29

- Q: Deletion semantics — soft (archived, hidden from wizard but historical jobs still display the name) or hard (registry row removed entirely; historical jobs render from snapshot)? → A: **Soft delete is the default.** Archived registrations are hidden from the wizard's Step 3 dropdown and from the registry's default list view, but remain in the underlying persistence and remain navigable via a "Show archived" filter in the registry-management UI. The tester MAY restore an archived registration (un-archive) at any time. Hard delete is available as a separate, more deliberate operation that is gated when historical jobs reference the registration (see `FR-014`).
- Q: Should the CRUD form validate that the endpoint is reachable when the tester saves? → A: **Optional, non-blocking "Test connection" button.** A button on the form fires a sample request to the endpoint and surfaces the response (success / HTTP status / error). It does NOT block save. The tester MAY register endpoints that are not yet up (e.g., a service still being deployed) and verify them later by clicking the button or by running a job.
- Q: What is the shape of the `auth descriptor` persisted on a registration? → A: A small structured object: `{ mode: "none"|"bearer"|"api-key-header"|"basic", headerName?: string, credential?: <encrypted> }`. `headerName` is present only when mode is `api-key-header`. `credential` is absent when mode is `none`, the bearer-token / api-key value when mode is `bearer` / `api-key-header`, and a `{ username, passwordCiphertext }` object when mode is `basic` (the username is non-secret and stored as cleartext for display in the UI; the password is encrypted at rest per `007 FR-013`). All credential ciphertext uses the machine-local symmetric key from `007 FR-014`.
- Q: What identifies a `ConnectorRegistration` — does the tester pick the `connectorId` or does the harness assign it? → A: **The harness assigns the `connectorId` automatically** (e.g., a UUID, or a slug derived from the display name plus a uniquifier). The tester does NOT type a `connectorId`. The tester picks the human-readable display name; the id is an internal identifier surfaced only in exports / detail-view metadata / debugging contexts. Two registrations MAY share the same display name (the harness disambiguates them in the dropdown by appending the short tail of the id, per `003`'s display rules); attempting that emits a warning but does not block save. The harness-assigned id is immutable for the life of the registration.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Register a new connector endpoint (Priority: P1)

The tester opens the Connector Registry management UI, clicks "Register new connector", and fills in a form: human-readable display name, optional description, endpoint URL, auth descriptor (mode + credentials), `timeoutSeconds`, and the `expectsPerRowPassword` toggle. They optionally click "Test connection" to verify the endpoint responds correctly. They click Save. The new registration appears in the registry's active list and immediately becomes selectable in the job-creation wizard's Step 3 dropdown.

**Why this priority**: Without this story, no connector can ever be registered, and therefore no job can ever be created. This is the MVP of the module.

**Independent Test**: Open the registry-management UI on a fresh install (which has only the bundled mock connector pre-registered, if anything), click "Register new connector", fill in the form pointing at the bundled mock connector's local URL with auth mode `none`, save, and verify (a) the new registration appears in the registry's active list, (b) it appears in the wizard's Step 3 dropdown on the next wizard launch, (c) a job created against it runs end-to-end per `007 US1`.

**Acceptance Scenarios**:

1. **Given** the registry-management UI is open, **When** the tester clicks "Register new connector", **Then** the UI renders a creation form with fields for display name (required), description (optional), endpoint URL (required, validated as a syntactically well-formed URL), auth mode (required, dropdown of `none`/`bearer`/`api-key-header`/`basic`), the auth-mode-specific credential fields (rendered conditionally per the chosen mode — see `FR-005`), `timeoutSeconds` (required, integer, default 30, range plan-defined but at minimum 1–300), and `expectsPerRowPassword` (required boolean, default false).
2. **Given** the form is filled in correctly, **When** the tester clicks Save, **Then** the harness (a) assigns a fresh immutable `connectorId`, (b) encrypts any secret credential fields per `007 FR-013`, (c) persists a `ConnectorRegistration` row with `archived = false` and the current timestamp as `createdAt` / `updatedAt`, (d) navigates back to the registry's list view, which now shows the new registration.
3. **Given** the form has any required field empty or invalid (e.g., malformed URL, negative timeout), **When** the tester clicks Save, **Then** save is blocked, the offending field is highlighted, and an inline error message names the problem.
4. **Given** the tester clicks "Test connection" before saving, **When** the form has at minimum a syntactically valid endpoint URL and an auth descriptor, **Then** the harness issues a sample `POST` request to the endpoint with a test contract body (e.g., `{"testId": "test-connection", "utteranceText": "ping"}`, plus `"password": "test"` if `expectsPerRowPassword` is true) and surfaces the result inline: HTTP status, response body preview (truncated), or transport / timeout / auth error. The result is informational; Save remains enabled regardless of the test outcome.
5. **Given** the tester has not yet clicked Save, **When** they navigate away from the form, **Then** the harness prompts them to confirm discarding unsaved changes (per the wizard's analogous behavior in `003`).

---

### User Story 2 - Edit an existing connector registration (Priority: P1)

The tester opens the registry list, clicks an existing registration, edits its fields (e.g., rotates the bearer token, bumps `timeoutSeconds`, fixes a typo in the display name), and saves. The edit takes effect immediately for any **future** job created against this registration. Historical jobs that already snapshotted this registration are NOT affected — they continue to display and execute (if re-run) against the snapshot, not the live registration.

**Why this priority**: Credential rotation is operationally inevitable; without edit, every credential rotation would require deleting and re-creating, breaking the snapshot history.

**Independent Test**: Edit a registration to change its display name and bump its timeout. Verify (a) future wizard launches show the new display name in Step 3, (b) historical jobs in the dashboard still show the old display name (because they snapshotted it per parent `FR-023`), (c) a fresh job created against the edited registration executes with the new timeout.

**Acceptance Scenarios**:

1. **Given** an active registration in the list, **When** the tester clicks it, **Then** the registry-management UI renders the same form as in US1, pre-populated with the registration's current values. Secret credential fields display as fully-masked placeholders; the tester MAY click a "Replace credential" affordance to enter a new value, which overwrites the encrypted ciphertext on save. Existing credentials are NEVER displayed in plaintext.
2. **Given** the tester edits one or more fields, **When** they click Save, **Then** the harness re-encrypts any new credential values, updates the persisted `ConnectorRegistration`, bumps its `updatedAt` timestamp, and returns to the list view.
3. **Given** the tester edits the registration's display name, **When** an existing job in the dashboard references this registration, **Then** the dashboard continues to show the OLD display name (snapshotted on the job per parent `FR-023`); only future jobs see the new name.
4. **Given** the tester clicks "Test connection" while editing, **When** the form's current (possibly edited) values are used for the test, **Then** the test runs against those in-form values without persisting them (so the tester can validate edits before committing).
5. **Given** the registration's `connectorId` is immutable (per the 2026-05-29 clarification), **When** the tester views the edit form, **Then** the `connectorId` is displayed as a read-only field (in a debug / metadata section).

---

### User Story 3 - Archive (soft-delete) a connector that is no longer needed (Priority: P1)

The tester wants to remove a connector from the wizard's selectable list — perhaps because the underlying chatbot was retired, or the registration was a mistake. They open the registration's edit view and click "Archive" (or select multiple registrations in the list and use a bulk Archive action). The registration's `archived` flag flips to true. It disappears from the wizard's Step 3 dropdown and from the registry's default list (but remains visible under a "Show archived" filter). Historical jobs that referenced this registration continue to render and execute normally. The tester MAY click "Restore" on an archived registration to bring it back.

**Why this priority**: Without archival, the wizard's dropdown grows unboundedly over a project's life. Soft-delete is the right semantic here because hard-delete would break historical-job audit trails.

**Independent Test**: Archive one registration. Verify (a) it disappears from the registry's default list and from the wizard's Step 3 dropdown, (b) historical jobs in the dashboard still show its display name in their Connector column, (c) toggling the registry's "Show archived" filter reveals the archived registration with an "Archived" badge, (d) clicking Restore on it returns it to the active list and dropdown.

**Acceptance Scenarios**:

1. **Given** an active registration in the list, **When** the tester clicks Archive (single) or selects it and clicks bulk-Archive, **Then** the harness sets `archived = true` on the persisted record and bumps `archivedAt` (a new timestamp column) and `updatedAt`.
2. **Given** a registration that has just been archived, **When** the tester opens the wizard's Step 3, **Then** the archived registration does NOT appear in the dropdown.
3. **Given** a historical job whose snapshotted connector points to a now-archived registration, **When** the tester opens the dashboard or the job's detail view, **Then** the job's connector display reads exactly as it did before archival (from the snapshot), with no "archived" indicator on the job itself (the snapshot is what is shown).
4. **Given** an archived registration, **When** the tester clicks Restore in the "Show archived" filter view, **Then** the registration's `archived` flag flips back to false, it reappears in the wizard's Step 3 dropdown on next launch, and its `archivedAt` is cleared (or preserved with a `restoredAt` parallel field — plan-level decision).
5. **Given** a job whose snapshot points to an archived registration, **When** the orchestrator dispatches its rows at execution time, **Then** dispatch proceeds normally using the Job snapshot (per `007 FR-012`); archival is invisible to the orchestrator.

---

### User Story 4 - List, filter, and inspect registered connectors (Priority: P2)

The registry-management UI shows a list of all registrations. The tester can filter by active / archived / all, search by display name substring, and click any registration to view its details (and edit). The list shows for each registration: display name, endpoint URL (truncated if long), auth mode (with credential always masked), timeout, expects-per-row-password flag, archived state, last-updated timestamp.

**Why this priority**: Discoverability scales with project lifetime; this story is what makes a registry of 30+ connectors usable. P2 because the registry works without it (a tester with two connectors can navigate by edit/archive UI alone).

**Independent Test**: Register 5 connectors with varied display names and auth modes; archive 2 of them. Verify (a) the default list shows the 3 active registrations, (b) toggling to "All" shows all 5 with archived ones badged, (c) toggling to "Archived only" shows the 2, (d) a substring search filters across all states.

**Acceptance Scenarios**:

1. **Given** the registry-management UI is open, **When** it loads, **Then** by default it shows the list of `archived = false` registrations, ordered alphabetically by display name (case-insensitive).
2. **Given** the list view, **When** the tester switches the filter to "Archived" or "All", **Then** the list updates accordingly; archived entries display with a visible "Archived" badge.
3. **Given** the search box, **When** the tester types a substring, **Then** the list filters in real-time to registrations whose display name (case-insensitive) contains the substring; the filter respects the active/archived/all selection.
4. **Given** any row in the list, **When** the tester clicks the row, **Then** the edit form opens pre-populated (per US2). Inline row actions MAY include Archive / Restore / Delete (hard) for direct operation without opening the form.
5. **Given** a registration in the list, **When** any auth-related field is displayed, **Then** credential values are NEVER shown in plaintext — only the auth mode label and (for `api-key-header`) the header name. The credential itself is masked.

---

### User Story 5 - Hard-delete a registration that has no historical references (Priority: P3)

In rare cases (e.g., a registration created entirely by mistake, never used in any job), the tester wants to remove it from the database entirely — not just archive. The UI offers a "Delete permanently" action on individual registrations. The harness checks whether any historical Job references the registration's `connectorId` in its snapshot; if any job does, the action is blocked with an explanatory message (the tester is directed to Archive instead). If no job references the registration, the row is removed from persistence.

**Why this priority**: Soft-delete handles 99% of cleanup needs; hard-delete is for the edge case of "I never want to see this in 'Show archived' either." P3 because it can ship after the rest of the module is operational.

**Independent Test**: Register a connector, do not create any job against it, click "Delete permanently". Verify the registration is removed from persistence (visible only in pre-deletion list snapshots) and does not appear under any filter. Then register another connector, create a job against it (do not run the job), and attempt "Delete permanently". Verify the action is blocked with a message naming the referencing job.

**Acceptance Scenarios**:

1. **Given** an active or archived registration with **zero** historical Job references, **When** the tester clicks "Delete permanently" and confirms a destructive-action dialog, **Then** the harness removes the `ConnectorRegistration` row from persistence; the registration disappears from all views (active, archived, all).
2. **Given** a registration with one or more historical Job references (any job whose snapshot's `connectorId` matches this registration's id), **When** the tester clicks "Delete permanently", **Then** the action is blocked with a message naming the count of referencing jobs and directing the tester to use Archive instead. The tester MAY still Archive.
3. **Given** the destructive-action dialog, **When** the tester cancels, **Then** no change is made.

---

### Edge Cases

- The tester attempts to register a connector whose endpoint URL is malformed (not a valid `http://` or `https://` URL) — Save MUST be blocked with an inline validation error; the harness MUST NOT attempt to persist the registration.
- The tester attempts to register two connectors with the same display name — the second registration MUST be allowed (display names are not unique constraints in v1), but a non-blocking warning MUST surface explaining that the wizard's Step 3 dropdown will disambiguate by appending the short tail of the auto-assigned `connectorId`.
- The tester clicks "Test connection" against an endpoint that is unreachable (DNS failure / connection refused / TLS handshake failure) — the harness MUST surface the transport-layer error in the form's test-result area with a clear "endpoint unreachable" message. The harness MUST NOT block save.
- The tester clicks "Test connection" against an endpoint that responds within `timeoutSeconds` with a non-2xx status — the harness MUST surface the HTTP status and a truncated body in the test-result area as a warning (e.g., "Endpoint returned 401 Unauthorized — check auth credentials"). The harness MUST NOT block save.
- The tester clicks "Test connection" against an endpoint that responds with a 2xx but a non-contract-conformant body — the harness MUST surface the validation problem in the test-result area (e.g., "Response is not a valid Standard Evaluation Contract instance — connector service may be returning chatbot raw output instead of a normalized contract"). The harness MUST NOT block save.
- The tester clicks "Test connection" and the endpoint does not respond within `timeoutSeconds` — the harness MUST surface a "timeout exceeded" error in the test-result area. The harness MUST NOT block save.
- The harness's machine-local encryption key is unavailable (newly-cloned install with no key initialization) — Save of any registration with a credential MUST be blocked with the actionable "machine-local key missing or wrong" error per `007 FR-016`. The harness MUST NOT persist plaintext credentials.
- The tester archives a registration that is currently snapshotted into an actively-`running` job — the archival succeeds; the in-flight job continues to use the snapshot, not the live registration. (The harness MUST NOT abort the job because the registration was archived.)
- The tester restores an archived registration whose display name now collides with another active registration — restoration succeeds (no unique constraint on display name); the same disambiguation rule applies as in the first edge case.
- The tester attempts to edit the auto-assigned `connectorId` — the field is read-only; the UI MUST NOT permit editing.
- The tester edits an active registration's auth mode (e.g., from `bearer` to `basic`) — Save succeeds; the previously-stored credential (the bearer token's ciphertext) MUST be discarded; the form MUST require entering fresh credentials for the new mode before save. The harness MUST NOT carry over credentials across mode changes.
- A registration's `expectsPerRowPassword` flag is toggled from `false` to `true` after some jobs already exist against it — the historical jobs' execution is unaffected (they snapshotted the old value); future jobs see the new value, and the CSV upload module (per `011 FR-006` / `FR-009`) enforces the password-column requirement at the wizard's Step 2 accordingly.
- The tester opens the registry-management UI on a fresh install with zero registrations — the list view MUST show an empty state with a prominent "Register your first connector" call-to-action and a link / hint to the bundled mock connector quickstart for self-testing.

## Requirements *(mandatory)*

### Functional Requirements

#### Create

- **FR-001**: The harness MUST provide a "Register new connector" affordance in the registry-management UI that opens a creation form.
- **FR-002**: The creation form MUST collect: display name (required, non-empty string), description (optional string), endpoint URL (required, syntactically well-formed `http://` or `https://` URL), auth mode (required, one of `none`/`bearer`/`api-key-header`/`basic` per `007 FR-007`), mode-specific credential fields per `FR-005`, `timeoutSeconds` (required integer in plan-defined range, default 30), and `expectsPerRowPassword` boolean (required, default false).
- **FR-003**: On Save with all validation passing, the harness MUST (a) auto-assign a fresh immutable `connectorId` (per the 2026-05-29 clarification), (b) encrypt any secret credential fields per `007 FR-013` using the machine-local symmetric key, (c) persist a new `ConnectorRegistration` row with `archived = false` and current timestamps for `createdAt` / `updatedAt`, (d) return to the list view with the new registration visible.
- **FR-004**: Save MUST be blocked when any required field is empty, when `endpointUrl` is not syntactically a valid URL, when `timeoutSeconds` is outside the plan-defined range, or when the auth-mode-specific credential fields per `FR-005` are not satisfied for the chosen mode.

#### Auth descriptor

- **FR-005**: The auth descriptor's per-mode field requirements MUST be:
  - `none`: no credential fields shown.
  - `bearer`: a single required `token` field (treated as secret, masked input, encrypted on save).
  - `api-key-header`: a required `headerName` field (non-secret, displayed as cleartext) AND a required `headerValue` field (treated as secret, masked input, encrypted on save).
  - `basic`: a required `username` field (non-secret, displayed as cleartext) AND a required `password` field (treated as secret, masked input, encrypted on save).
- **FR-006**: When the auth mode is changed from one mode to another during editing, the previously-stored credential ciphertext MUST be discarded on Save. Re-entering credentials for the new mode is required; Save MUST be blocked until the new mode's credential fields are satisfied.

#### Read / List

- **FR-007**: The registry-management UI MUST provide a list view of `ConnectorRegistration` records. The default filter MUST show only `archived = false` registrations, ordered alphabetically by display name (case-insensitive).
- **FR-008**: The list view MUST expose a filter control with at least three options: `Active` (the default — only `archived = false`), `Archived` (only `archived = true`), `All`. The current filter MUST be visually indicated.
- **FR-009**: The list view MUST expose a search box that filters the visible registrations by case-insensitive substring match against the display name. The search filter MUST compose with (not replace) the active/archived/all filter.
- **FR-010**: Each row in the list MUST show: display name, endpoint URL (truncated with a hover or tooltip affording the full value), auth mode label (no credential value), `timeoutSeconds`, `expectsPerRowPassword` flag, archived state (visible badge when archived), `updatedAt` timestamp. Credential values MUST NOT be shown in any form on the list view.

#### Update (Edit)

- **FR-011**: Clicking a row in the list MUST open the edit form, pre-populated with the registration's current values. Secret credential fields MUST display as a fully-masked placeholder; the form MUST provide a "Replace credential" affordance that opens an input for a new value. Existing credentials MUST NEVER be returned in plaintext from persistence to the form.
- **FR-012**: On Save from the edit form, the harness MUST (a) re-encrypt any newly-entered credential values per `007 FR-013`, (b) preserve the existing ciphertext for credential fields the tester did NOT use "Replace credential" on, (c) update the persisted `ConnectorRegistration` row in place, (d) bump `updatedAt`, (e) return to the list view.
- **FR-013**: The `connectorId` MUST be immutable across edits and MUST display as a read-only field in the form (in a metadata / debug section).

#### Archive (soft-delete) / Restore

- **FR-014**: The harness MUST provide an Archive action accessible from (a) the row's inline actions in the list view, (b) the edit form, and (c) a bulk action when multiple list rows are selected. On Archive, the harness MUST set `archived = true`, set `archivedAt` to the current timestamp, and bump `updatedAt`.
- **FR-015**: Archived registrations MUST NOT appear in the wizard's Step 3 dropdown (per `003`'s read affordance). Archived registrations MUST appear in the registry's list view only under the `Archived` or `All` filter selection.
- **FR-016**: The harness MUST provide a Restore action on archived registrations (from inline row actions, the edit form, or bulk). On Restore, the harness MUST set `archived = false`, clear `archivedAt` (or set `restoredAt` parallel — plan-level), and bump `updatedAt`. The registration immediately becomes selectable in the wizard's Step 3 dropdown again.
- **FR-017**: Archival MUST NOT affect any historical Job that already snapshotted this registration. Per `012 FR-004` and parent `FR-023`, the orchestrator resolves connector configuration from the Job snapshot, not the live registry, so archived registrations remain executable for historical jobs.

#### Hard-delete

- **FR-018**: The harness MUST provide a "Delete permanently" action on each registration (in the inline row actions and / or in the edit form). The action MUST be visually distinct from Archive (e.g., destructive-styled, requires a confirmation dialog).
- **FR-019**: Before persisting a hard delete, the harness MUST count Jobs whose snapshotted connector identity references this registration's `connectorId`. If the count is greater than zero, the harness MUST block the action with a message naming the count and directing the tester to use Archive instead. If the count is zero, the harness MUST present a confirmation dialog naming the registration; on confirm, the harness MUST remove the row from persistence.
- **FR-020**: After hard delete, the registration MUST be absent from all UI views and queries; the `connectorId` is permanently retired (the harness MUST NOT recycle the same id for a future registration).

#### Test Connection

- **FR-021**: The creation and edit forms MUST expose a "Test connection" button. On click, the harness MUST construct a sample HTTP request using the form's current (possibly unsaved) values and the connector wire protocol per `007 FR-002`, send it to the endpoint URL with the constructed auth header, await a response within `timeoutSeconds`, and display the result inline in the form.
- **FR-022**: The displayed test result MUST include: HTTP status code (when received), a truncated response body preview (when received and ≤ a plan-defined byte cap), or a categorized error label (`endpoint unreachable`, `tls failure`, `timeout exceeded`, `auth credential decryption failed`, etc.) when no response was received.
- **FR-023**: For a 2xx response, the harness MUST additionally validate the body against the Standard Evaluation Contract schema and surface either a success ("Endpoint returned a valid Standard Evaluation Contract instance") or a validation problem with a brief diagnostic (e.g., "Response is missing required field `chatbotResponse`").
- **FR-024**: The "Test connection" outcome MUST be informational only. The harness MUST NOT block Save regardless of the test outcome, and MUST NOT persist the test request, the test response, or the test result.
- **FR-025**: The test request body MUST use a fixed sample shape — e.g., `{"testId": "test-connection", "utteranceText": "ping"}`, with `"password": "test"` included if and only if the form's `expectsPerRowPassword` is currently set to `true`. The fixed sample MUST be documented in the UI alongside the button so testers understand what is being sent.

#### Read API (consumed by other modules)

- **FR-026**: This module MUST expose (programmatically, to other harness modules) the same read affordances `007 FR-009`–`FR-011` describe: list active registrations, get registration by id, list active+archived for the management UI. This module is the implementation; `007` defines the contract. (`007 FR-012` separately states the zero-core-change extensibility property; it is not part of the read-API surface.)

### Key Entities *(include if feature involves data)*

- **ConnectorRegistration**: The persisted record describing a connector service known to the harness. Detailed in `009 FR-001a` (new). Fields: `connectorId` (immutable string, harness-assigned), `displayName` (string), `description` (string, optional), `endpointUrl` (string), `authDescriptor` (structured object with `mode` + mode-specific fields per `FR-005`), `timeoutSeconds` (integer), `expectsPerRowPassword` (boolean), `archived` (boolean), `createdAt`, `updatedAt`, `archivedAt` (nullable). Credential fields within `authDescriptor` are encrypted at rest per `007 FR-013`.
- **Test Connection Result**: A transient, in-memory representation of a single test-request/response pair fired by the "Test connection" button. NOT persisted. Contains: HTTP status (when received), truncated body preview (when received), error category and detail (when no response or non-2xx). Lifetime: until the tester clicks Save / closes the form / clicks Test connection again.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A registered connector becomes selectable in the wizard's Step 3 dropdown on the next wizard launch — verifiable by registering a connector and immediately opening the wizard.
- **SC-002**: A registration's stored credential never appears in plaintext anywhere in the application's surface (UI, exports, logs) — verifiable by registering a connector with a known-distinctive credential (e.g., `"DEADBEEF-12345"`) and grepping the database file, the rendered list/edit pages, and any export file (must produce zero matches).
- **SC-003**: Editing a registration's display name does NOT change the display name shown on any historical Job that snapshotted the earlier name — verifiable by registering a connector with name `"v1"`, creating a job against it, editing the registration's name to `"v2"`, and checking the dashboard still shows `"v1"` for the historical job.
- **SC-004**: An archived registration is absent from the wizard's Step 3 dropdown — verifiable by archiving a registration and re-launching the wizard.
- **SC-005**: An archived registration that is referenced by a historical Job is fully executable when the job is re-run — verifiable by archiving a registration that an unfinished job references and confirming the job runs to completion.
- **SC-006**: Hard-delete is blocked when a registration is referenced by any historical Job — verifiable by creating a job against a registration and attempting to hard-delete; the action must be rejected with a clear message.
- **SC-007**: Hard-delete succeeds when a registration has zero historical Job references — verifiable by registering a connector, hard-deleting it before creating any job, and confirming it is absent from all views.
- **SC-008**: The "Test connection" button never blocks Save and never persists side effects — verifiable by clicking Test connection (with success and with failure), confirming Save remains enabled, and verifying no test-related rows appear in any persistence table.
- **SC-009**: The "Test connection" button reports the categorized outcomes named in `FR-022` accurately — verifiable by pointing the button at endpoints in each documented failure mode and asserting the displayed category matches.
- **SC-010**: Registry-management UI loads in a reasonable time even with 100+ registrations (active + archived) — plan-level performance target; spec requires only that pagination / lazy loading MAY be introduced if needed without breaking the URLs / state contract of US4's filters.

## Assumptions

- This module is part of the harness defined in `specs/001-chatbot-regression-harness/spec.md`. Single-user, no auth on the harness UI. `ConnectorRegistration` records carry no `createdBy` field of their own; per the architectural decision, in a single-user model the registry is owned by the lone tester.
- The wire protocol that registered endpoints implement is defined in `specs/007-connector-framework`. This module's "Test connection" button uses that protocol's request shape; this module does NOT redefine the protocol.
- The encryption story for stored credentials is inherited from parent `FR-023a` and `007 FR-013`–`FR-017`. This module reuses that utility; it does NOT introduce a separate encryption mechanism.
- The persistence layer (`009`) defines the `ConnectorRegistration` schema; this module's spec describes the user-facing CRUD behavior and the field rules but defers the table / column shape to `009`.
- The wizard (`003`) is the primary consumer of the registry's read API. This module's UI and the wizard are separate navigation surfaces; the tester typically opens the registry-management UI before / outside the wizard flow to set up endpoints, then opens the wizard to use them.
- Soft-delete (archival) is the default deletion semantic. Hard-delete exists for cleanup of registry rows that were never used in any job; it is rare in normal operation.
- The "Test connection" feature is a productivity affordance, not a gating mechanism. The harness MUST NOT make Save conditional on a successful test result (per the 2026-05-29 design call).
- Display names are NOT unique — two registrations MAY share the same display name. The wizard's Step 3 dropdown disambiguates by appending the short tail of the auto-assigned `connectorId` per `003`'s display rules.
- The `connectorId` is harness-assigned and immutable; the tester does not type it. This avoids the class of problems where two testers in unrelated installs choose the same id and then can't merge configurations.
- Bulk operations (bulk-Archive, bulk-Restore, bulk-Delete) are available where the analogous single-row operation is available, with the same gating rules (e.g., bulk-Delete blocks if any selected registration has historical Job references; blocked ones are listed in the error).
- Bundled mock connector pre-registration: in a stock harness install, the bundled mock connector service (per `007 FR-018`) MAY be pre-registered with auth mode `none` and a localhost endpoint URL pointing at the bundled service. This is a plan-level convenience; the spec does NOT require it.
