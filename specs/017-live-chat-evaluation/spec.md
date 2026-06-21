# Feature Specification: Live Chat & Real-Time Evaluation

**Feature Branch**: `017-live-chat-evaluation`

**Created**: 2026-06-21

**Status**: Draft

**Depends On**: 007 (Connector Framework), 008 (Evaluator Framework), 009 (Data Model), 012 (Execution Engine), 013 (Connector Registry), 014 (Evaluator Registry), 015 (Azure AD RBAC)

---

## Overview

This feature introduces a real-time, interactive chat interface that allows testers to converse with a chatbot via a registered connector while simultaneously observing streaming evaluation output from a registered evaluator agent. It extends the batch-based regression harness into a real-time observability and evaluation system.

The feature encompasses: a dedicated Chat Session Creation Wizard (separate from the Job Creation Wizard); chat session listing integrated into the existing dashboard; user-level session deletion; admin-level session maintenance via the Admin menu; and enhancements to the Connector and Evaluator registration forms to declare streaming capability.

Each chat turn follows a strict sequential model:

1. Tester submits a message via HTTP POST → server creates the turn (status: `in_progress`) and returns a turn ID
2. Browser opens a separate SSE stream endpoint for that turn to receive live output
3. Server forwards connector `token` events to the browser SSE stream as they arrive
4. Connector emits a `contract` event — server extracts and validates the Standard Evaluation Contract, then invokes the evaluator
5. Server forwards evaluator events to the same browser SSE stream
6. All assembled artifacts are persisted at turn end (turn status → `completed` or `failed`)

---

## Clarifications

### Session 2026-06-21

- Q: Should the snapshotted `timeout_seconds` be applied to SSE streams as a stall/idle timeout? → A: Yes (Option A), but a stall timeout only fails the **current turn's SSE stream** — it does not fail or expire the session. The session stays `active` indefinitely. When the user returns (hours or days later) and sends a new message, the system establishes fresh SSE connections for the new turn and processing continues normally. The timeout behaves like a sleep/idle disconnect, not a terminal failure.
- Q: What should happen when the tester clicks "End Session" while a turn is streaming? → A: "End Session" is not required at all. Since SSE connections are per-turn (not per-session), there is no session-level connection to close. Sessions remain `active` until explicitly deleted by the user or admin. Export is available at any time from an `active` session. The session lifecycle simplifies to: created → `active` → deleted.
- Q: How many sessions should the dashboard section show before truncating to "View All Sessions"? → A: 5 most recent sessions (by creation date), with a "View All Sessions" link to the full list.
- Q: Must session names be unique per user, or can a tester have multiple sessions with the same name? → A: No uniqueness constraint. Session names are free-form labels; duplicate names are allowed and sessions are distinguished by creation date and ID.
- Q: What should happen if two browser tabs submit a message on the same session concurrently? → A: Server rejects concurrent submissions (Option A). The server enforces at most one in-progress turn per session at a time; a second submission arriving while a turn is active is rejected with an error. No cross-tab browser coordination required.
- Q: Should `ChatTurn` carry an explicit `status` field to track its lifecycle? → A: Yes (Option A). `ChatTurn` gains an explicit `status` field: `in_progress → completed | failed`. This aligns with the `Job` model pattern and makes server-restart recovery unambiguous — any turn with `status = in_progress` at startup is flipped to `failed`.
- Q: How does the browser subscribe to the server's token stream after submitting a message? → A: Option B — POST creates the turn and returns a turn ID; the browser then opens a separate GET SSE endpoint to receive the stream. This allows the browser to reconnect independently if the tab is refreshed mid-turn, and cleanly decouples submission from streaming.
- Q: Is the admin bulk-delete lookback window chosen per operation or a fixed platform default? → A: Admin selects from three preset options at time of operation: 7 days inactive, 30 days inactive, or more than 30 days inactive (deep clean). No free-form input; no settings page required.
- Q: What should the full sessions list page offer beyond the dashboard section? → A: All sessions displayed in a sortable table (same columns as dashboard: name, connector, evaluator, turn count, creation date), sortable by any column. No filtering or search required at this scale.
- Q: Does the `final` evaluation event carry the complete `EvaluationResult` payload, or is it a stream-termination signal only? → A: The `final` event carries the complete `EvaluationResult` in its payload. The server reads it directly into `ChatTurnResult.evaluationResult` and also persists it as an `EvaluationEvent` row for traceability. No separate extraction step needed.
- Q: What event types must a connector's SSE stream emit? → A: Two types: `token` (intermediate chatbot response chunk) and `contract` (final event carrying the complete Standard Evaluation Contract). Mirrors the evaluator's pattern for consistency.
- Q: What should happen when the `contract` event arrives but its payload fails contract validation? → A: Treat as turn failure with `error_stage = connector_normalization` (Option A) — consistent with the batch system's error taxonomy. Partial assembled response saved, session stays `active`.
- Q: What does the server send when the browser reconnects to an in-progress turn's SSE stream? → A: Server replays all buffered events from the beginning of the turn (Option A). Events are already in the in-memory buffer for the batch write, so replay is free and ensures the reconnected browser has a complete view.
- Q: How many prior turns should the chat interface load when a tester opens a session? → A: The 50 most recent turns are displayed in the chat interface (most recent at the bottom). No "Load more" or pagination. Turns beyond 50 are not shown in the UI but are fully available via export. Sessions may accumulate 100+ turns over months of use.
- Q: Should export always include all turns, or support date/range scoping? → A: Always export all turns (Option A) — complete lossless transcript regardless of session length. No scoping options. Testers who need a subset can filter the exported JSON themselves.
- Q: Should the full sessions list page show all users' sessions to admins, or only the current user's sessions? → A: Single unified sessions list route (Option A) — admins see all users' sessions; testers see only their own. Delete button available in both views; testers may only delete their own sessions, admins may delete any session.
- Q: When an admin deletes a session that has a turn currently streaming, do they get the same in-progress warning + confirmation as testers? → A: No. Admins cannot delete in-progress sessions at all — sessions with an in-progress turn are silently skipped (no warning, no error, no confirmation dialog). This applies to both individual admin deletion and bulk delete operations. Testers retain their own path: warn + explicit confirmation → may proceed with deletion of a streaming session.
- Q: For admin bulk delete inactivity calculation, what baseline date is used for sessions that have never had any turns? → A: Session creation date (Option A). A zero-turn session is considered inactive from the moment it was created; its creation date is used as the inactivity baseline. A 0-turn session created 8 days ago is eligible for the 7-day inactivity window.
- Q: Can admins navigate into the chat interface of a session they do not own, or is admin access limited to list-level visibility and deletion? → A: Option B — admins are limited to list-level visibility (session metadata only) and deletion. Admins cannot open the chat interface of another user's session and cannot export another user's transcript. The chat interface and export are always scoped to the session owner.
- Q: How should the system handle an evaluator SSE event whose type is not one of the five defined types? → A: Option A — forward to browser as-is and persist with the raw type string. Unknown event types are treated as a passthrough; no validation against the defined whitelist, no error raised. This preserves forward compatibility as evaluator implementations evolve.

---

## User Scenarios & Testing

### User Story 1 — Create a Live Chat Session via Dedicated Wizard (Priority: P1)

A tester wants to explore a chatbot's behavior interactively. They launch a dedicated Chat Session Creation Wizard (a separate workflow from the Job Creation Wizard) and step through: naming the session, selecting an SSE-capable connector, selecting an SSE-capable evaluator, and confirming. The session becomes active and the tester is taken to the split-pane chat interface.

**Why this priority**: Session creation is the entry point for all live chat functionality; nothing else works without it.

**Independent Test**: Can be tested by completing all wizard steps through to the active chat screen, verifying the session is recorded and connector/evaluator snapshots are stored.

**Acceptance Scenarios**:

1. **Given** a tester is on the dashboard or chat sessions list, **When** they click "New Chat Session", **Then** they are taken into the Chat Session Creation Wizard, which is visually and functionally distinct from the Job Creation Wizard.
2. **Given** the tester is in the wizard, **When** they complete all steps (name → connector → evaluator → confirm), **Then** a new session in `active` status is created and they are redirected to the chat interface for that session.
3. **Given** session creation is in progress, **When** the tester confirms, **Then** the system snapshots the selected connector and evaluator registrations at that moment, so future changes to those registrations do not affect the session.
4. **Given** no SSE-capable connectors exist in the registry, **When** the tester reaches the connector selection step, **Then** the list is empty and a message explains that no streaming-capable connectors are available.

---

### User Story 2 — View Chat Sessions on the Dashboard (Priority: P1)

A tester visits the main dashboard and sees their chat sessions displayed alongside their batch jobs. The sessions section shows each session's name, status, connector and evaluator used, turn count, and creation date. The tester can navigate directly from the dashboard to any session's chat interface or to the full chat sessions list.

**Why this priority**: The dashboard is the harness's primary landing page; chat sessions must be discoverable from the same place as jobs.

**Independent Test**: Can be tested independently by creating sessions and verifying they appear in the dashboard's sessions section with correct metadata, without affecting the existing job listing.

**Acceptance Scenarios**:

1. **Given** a tester has created one or more chat sessions, **When** they visit the dashboard, **Then** a chat sessions section is visible alongside the job listing, showing their sessions with name, status, turn count, and creation date.
2. **Given** a tester has no chat sessions, **When** they visit the dashboard, **Then** the sessions section shows an empty state with a prompt to create a new session.
3. **Given** the dashboard shows a chat session, **When** the tester clicks the session name, **Then** they are taken to that session's chat interface.
4. **Given** the dashboard shows a chat session, **When** the tester clicks a "View All Sessions" link, **Then** they are taken to the full chat sessions list page.

---

### User Story 3 — Send a Message and Observe Streaming Output (Priority: P1)

A tester types a message in the chat interface and submits it. The chatbot's response tokens appear progressively in the left pane as the connector streams them. Once the connector finishes, an "Evaluating…" indicator appears in the right pane. Evaluation events (scores, warnings, insights) then stream into the right pane progressively. Both streams are correlated to the same turn.

**Why this priority**: This is the core interaction loop — the primary value of the feature.

**Independent Test**: Can be tested end-to-end using a mock SSE connector and mock SSE evaluator, verifying progressive rendering in both panes and correct sequencing.

**Acceptance Scenarios**:

1. **Given** an active session, **When** the tester sends a message, **Then** the connector's streamed response tokens appear progressively in the left pane before the full response is complete.
2. **Given** the connector stream has completed, **When** the normalized contract is ready, **Then** the "Evaluating…" indicator appears in the right pane and the evaluator begins streaming.
3. **Given** the evaluator is streaming, **When** evaluation events arrive, **Then** they appear progressively in the right pane, each labeled with its event type (score update, warning, insight, etc.).
4. **Given** a turn completes, **When** the tester views the right pane, **Then** evaluation events are visually associated with the chatbot response from the same turn.
5. **Given** a turn completes, **When** the tester views the left pane, **Then** the assembled chatbot response and the full evaluation output are both displayed in full.

---

### User Story 4 — Export a Session Transcript (Priority: P2)

A tester has completed exploratory conversations in an active session and wants to share the findings or feed them into a batch regression job. At any point, they export the transcript as JSON or CSV directly from the active session, receiving a file that contains every turn's user message, assembled chatbot response, normalized evaluation contract, and structured evaluation events. There is no "End Session" step — sessions remain active until explicitly deleted.

**Why this priority**: Export is the primary mechanism for sharing findings and feeding results back into the batch regression workflow.

**Independent Test**: Can be tested independently by creating a session with known turns and verifying the exported file contains the expected fields and structure for each turn.

**Acceptance Scenarios**:

1. **Given** an active session with one or more completed turns, **When** the tester requests a JSON export, **Then** the file contains one entry per turn with: user message, assembled chatbot response, normalized contract, and all evaluation events in order.
2. **Given** an active session, **When** the tester requests a CSV export, **Then** the file contains a flattened, one-row-per-turn representation with the same fields.
3. **Given** a session with a failed turn, **When** the tester exports, **Then** the failed turn appears in the export with a partial response and error details.
4. **Given** an active session with an in-progress turn, **When** the tester requests an export, **Then** the export includes all previously completed turns; the in-progress turn is excluded until it completes.

---

### User Story 5 — Delete Own Chat Sessions (Priority: P2)

A tester wants to clean up their sessions list. Since there is no "End Session" action, deletion is the only way to remove a session. A tester can delete any of their own sessions at any time, including sessions with an in-progress turn (with a confirmation warning). Deletion removes the session and all its turns.

**Why this priority**: Session hygiene is important for testers who run many exploratory sessions; deletion keeps the list manageable.

**Independent Test**: Can be tested independently by creating a session, then deleting it and verifying it no longer appears in the list. Does not require any streaming functionality.

**Acceptance Scenarios**:

1. **Given** a tester has a session with no in-progress turn, **When** they delete it, **Then** the session and all associated turns and evaluation events are removed and no longer appear in the dashboard or session list.
2. **Given** a tester has a session with a turn currently streaming, **When** they attempt to delete it, **Then** the system shows a warning that an active stream will be abandoned, and proceeds only after explicit confirmation.
3. **Given** a non-admin tester attempts to delete a session belonging to another user, **Then** the system rejects the action.

---

### User Story 6 — Admin Manages Chat Sessions via Admin Menu (Priority: P2)

An admin wants to manage the accumulation of chat sessions across all users. Via the Admin menu, they access a Chat Session Maintenance page that shows aggregate session statistics and allows bulk deletion of all terminal sessions. They can also delete any individual session regardless of owner.

**Why this priority**: Without admin cleanup capability, completed sessions accumulate indefinitely and cannot be managed at the platform level.

**Independent Test**: Can be tested independently by creating sessions under multiple users, then using admin controls to view stats and delete terminal sessions in bulk.

**Acceptance Scenarios**:

1. **Given** an admin is on the Admin menu, **When** they click "Chat Session Maintenance", **Then** they are taken to a page showing aggregate stats: total sessions, total turns, and a breakdown of sessions by last-activity age across all users.
2. **Given** an admin is on the Chat Session Maintenance page, **When** they select a preset inactivity window (7 days / 30 days / more than 30 days) and click "Clear Inactive Sessions", **Then** a confirmation shows the count of matching sessions, and upon confirmation those sessions and all their turns are deleted.
3. **Given** an admin is on the chat sessions list, **When** they delete an individual session that has no in-progress turn, **Then** the session is deleted regardless of who created it. **When** the target session has an in-progress turn, the delete action is silently skipped — no error, no warning.
4. **Given** the lookback window would result in zero deletions, **When** the admin proceeds to the confirmation step, **Then** a message indicates no sessions match the criteria.

---

### User Story 7 — Handle a Streaming Failure Gracefully (Priority: P3)

A mid-session connector or evaluator stream fails (e.g., network interruption). The system saves whatever was buffered up to that point for that turn, marks the turn as failed with an error stage and details, and leaves the session in `active` status so the tester can continue with a new message.

**Why this priority**: Resilience is important for exploratory sessions that may run for extended periods.

**Independent Test**: Can be tested by injecting a stream failure mid-turn and verifying the session remains active, the failed turn is persisted with partial content and error details, and a new message can be sent.

**Acceptance Scenarios**:

1. **Given** a connector stream fails mid-response, **When** the failure is detected, **Then** the partially assembled response is saved to the turn result with `error_stage = connector_stream` and the session remains `active`.
2. **Given** an evaluator stream fails mid-evaluation, **When** the failure is detected, **Then** any evaluation events received so far are saved and the turn result records `error_stage = evaluator_stream`.
3. **Given** a turn has failed, **When** the tester sends a new message, **Then** the session accepts the new message and a fresh turn begins normally.

---

### Edge Cases

- Tester submits a new message before the current turn's evaluation has completed.
- Connector `contract` event payload fails Standard Evaluation Contract validation (`error_stage = connector_normalization`; evaluator not invoked).
- Evaluator stream returns an unrecognised event type → forwarded to browser and persisted with the raw type string; no error raised.
- Session creation is attempted when all registered connectors or evaluators have `supports_sse = false`.
- Tester requests an export while a turn is in progress (in-progress turn excluded from export, prior turns included).
- Same session opened in two browser tabs simultaneously; second tab submits a message while the first tab's turn is active (server rejects the second submission with an error).
- Very long chatbot responses (e.g., multi-paragraph) render without UI overflow or truncation.
- Tester attempts to delete a session while a turn is in progress → system shows a warning that the in-progress turn will be abandoned and requires explicit confirmation before proceeding (consistent with FR-LC-015).
- Admin clicks bulk delete when no sessions match the lookback window (no-op, zero-count shown in confirmation).
- Admin bulk delete lookback window is set to a value that would delete sessions still actively used by testers — sessions with an in-progress turn at execution time are silently skipped; the rest are deleted.
- A connector or evaluator registration has `supports_sse` toggled off while an active session using it is in progress (in-flight turn completes normally; future turns on that session use the snapshotted value).
- A tester returns to an active session hours or days later: the previous turn may have a stall-timed-out result; the chat interface displays prior turn history and the input is re-enabled for a new message.
- A turn's SSE stream stalls exactly at the boundary of `timeout_seconds` (race condition between last event and timeout firing).
- Session with more than 50 turns: UI shows only the 50 most recent; tester is unaware older turns exist unless they export.

---

## Requirements

### Functional Requirements

**Session Creation Wizard**

- **FR-LC-001**: System MUST provide a dedicated Chat Session Creation Wizard that is a separate workflow from the Job Creation Wizard.
- **FR-LC-002**: The wizard MUST guide the tester through: (1) naming the session, (2) selecting an SSE-capable connector, (3) selecting an SSE-capable evaluator, (4) confirming and starting.
- **FR-LC-003**: Each wizard step MUST be independently validated before advancing to the next.

**Session Management**

- **FR-LC-004**: System MUST allow authenticated testers to create Live Chat Sessions with a name, a selected SSE-capable connector, and a selected SSE-capable evaluator. Session names are free-form labels with no uniqueness constraint.
- **FR-LC-005**: Session lifecycle is `active` from creation until deletion. There is no `completed` or `failed` state at the session level. Sessions have no expiry and remain resumable indefinitely.
- **FR-LC-006**: System MUST snapshot the selected connector and evaluator registrations at session creation time (endpoint URL, auth descriptor, timeout, declared dimensions).
- **FR-LC-007**: Sessions do not have an "End Session" action. A tester closes a session by deleting it (FR-LC-013). Export is available at any time from an active session (FR-LC-041).
- **FR-LC-008**: System MUST scope session visibility to the creating user (aligned with existing job ownership model). Admins have list-level visibility across all users' sessions (FR-LC-012) and deletion rights (FR-LC-016), but MUST NOT be permitted to navigate into the chat interface or export a session they do not own. The chat interface and export endpoints MUST enforce owner-only access regardless of role.

**Dashboard Integration**

- **FR-LC-009**: The existing dashboard MUST display a chat sessions section alongside the job listing, showing the tester's 5 most recent sessions (by creation date).
- **FR-LC-010**: Each session entry in the dashboard MUST show: session name, connector name, evaluator name, turn count, and creation date.
- **FR-LC-011**: Dashboard MUST provide a "New Chat Session" entry point that launches the Chat Session Creation Wizard.
- **FR-LC-012**: Dashboard MUST provide a "View All Sessions" link navigating to the full chat sessions list page. The page is a single unified route with role-based content: testers see only their own sessions; admins see all sessions across all users. Sessions are presented in a sortable table (columns: name, connector, evaluator, turn count, creation date). Each row includes a Delete action; testers may only delete their own sessions, admins may delete any session. No filtering or search is required.

**Session Deletion**

- **FR-LC-013**: Testers MUST be able to delete any of their own sessions at any time.
- **FR-LC-014**: Deleting a session MUST remove the session, all its turns, turn results, and evaluation events.
- **FR-LC-015**: If the session has a turn currently streaming at deletion time, the system MUST warn the tester that the in-progress turn will be abandoned and require explicit confirmation before proceeding.
- **FR-LC-016**: Admins MUST be able to delete any session regardless of owner, EXCEPT sessions that currently have a turn in progress. Sessions with an in-progress turn MUST be silently skipped — no warning, no error — during both individual and bulk admin deletion operations. Admins do not receive a confirmation dialog for in-progress turns.

**Admin: Chat Session Maintenance**

- **FR-LC-017**: The Admin menu MUST include a "Chat Session Maintenance" entry (alongside the existing Job Maintenance entry).
- **FR-LC-018**: The Chat Session Maintenance page MUST display aggregate statistics: total session count, total turn count, and sessions-by-age breakdown (e.g., sessions with no activity in the last 7 days, 30 days) across all users.
- **FR-LC-019**: Admins MUST be able to bulk-delete sessions by selecting one of three preset inactivity windows: sessions with no turn activity in the last 7 days, 30 days, or more than 30 days. The admin selects the window at the time of the operation from a fixed preset list; no free-form input is required. Inactivity is measured from the most recent turn's creation date; for sessions with no turns, session creation date is used as the inactivity baseline. Sessions with an in-progress turn at the moment of execution MUST be silently skipped.
- **FR-LC-020**: The bulk delete operation MUST display the count of eligible sessions matching the selected window (excluding in-progress sessions) before the confirmation step.
- **FR-LC-021**: The bulk delete operation MUST require confirmation before executing.

**Connector Streaming**

- **FR-LC-022**: System MUST send the tester's message to the connector via HTTP POST and consume the connector's SSE response stream. The connector stream MUST emit two event types: `token` (intermediate chatbot response chunk) and `contract` (final event carrying the complete Standard Evaluation Contract).
- **FR-LC-023**: System MUST forward `token` events from the connector stream to the browser SSE endpoint as they arrive, enabling progressive rendering in the chat pane.
- **FR-LC-024**: System MUST detect the `contract` event in the connector stream and extract the Standard Evaluation Contract from its payload. The assembled contract MUST pass validation before the evaluator is invoked.
- **FR-LC-025**: Connector streams that fail (error or stall) before a `contract` event is received MUST be captured with `error_stage = connector_stream`, the partial buffer saved, and the session left `active`. A stall is detected when no SSE events are received within the snapshotted `timeout_seconds` window.
- **FR-LC-055**: If the `contract` event is received but its payload fails Standard Evaluation Contract validation, the turn MUST be failed with `error_stage = connector_normalization`, the partial assembled response saved, and the session left `active`. The evaluator MUST NOT be invoked. This aligns with the batch system's existing `connector_normalization` error stage.

**Evaluator Streaming**

- **FR-LC-026**: System MUST NOT begin evaluator invocation until a valid final Standard Evaluation Contract is assembled from the connector stream.
- **FR-LC-027**: System MUST POST the complete Standard Evaluation Contract to the evaluator and consume the evaluator's SSE response stream.
- **FR-LC-028**: System MUST forward evaluator events to the browser as they arrive, enabling progressive rendering in the evaluation pane. Events with an unrecognised type MUST be forwarded and persisted as-is with their raw type string — no whitelist validation is applied and no error is raised.
- **FR-LC-029**: Evaluator streams that fail (error or stall) MUST be captured with `error_stage = evaluator_stream`, any received events saved, and the session left `active`. A stall is detected when no SSE events are received within the snapshotted `timeout_seconds` window.

**Session Resumability**

- **FR-LC-048**: SSE connections MUST be scoped to a single turn. When a turn ends (normally, via stream failure, or via stall timeout), all SSE connections for that turn are torn down. No persistent connection is held at the session level between turns.
- **FR-LC-049**: A tester MUST be able to return to an `active` session at any time after any duration and send a new message. The system MUST establish fresh SSE connections for each new turn regardless of how long the session has been idle.

**Chat Interface UI**

- **FR-LC-030**: System MUST render a split-pane chat interface: left pane for chatbot interaction, right pane for evaluation output.
- **FR-LC-031**: Left pane MUST display the 50 most recent completed turns' assembled responses plus the current in-progress turn's tokens as they stream. Turns beyond the 50 most recent are not shown in the UI; they remain accessible via export.
- **FR-LC-032**: Right pane MUST display the evaluation events for the same 50 most recent turns shown in the left pane, plus the current in-progress turn's evaluator stream as it arrives.
- **FR-LC-033**: System MUST display an "Evaluating…" indicator in the right pane after the connector stream completes and before the evaluator stream begins.
- **FR-LC-034**: System MUST visually associate evaluation output with its corresponding chat turn.
- **FR-LC-035**: System MUST NOT execute any HTML or script content received from connector or evaluator streams.
- **FR-LC-036**: System MUST disable the message input while a turn is in progress (within the current browser tab).
- **FR-LC-050**: Server MUST enforce at most one in-progress turn per session at a time. A message submission received while a turn is already active MUST be rejected with an error, regardless of which browser tab or client submitted it.
- **FR-LC-051**: `ChatTurn` lifecycle MUST follow: `in_progress → completed | failed`. At server startup, any turn with `status = in_progress` MUST be transitioned to `failed` with appropriate error details persisted.

**Browser Streaming**

- **FR-LC-052**: Submitting a message MUST be a two-step interaction: (1) an HTTP POST that creates the turn and returns a turn ID; (2) the browser opening a separate SSE endpoint scoped to that turn ID to receive the live stream.
- **FR-LC-053**: The server MUST provide a per-turn SSE endpoint that the browser can subscribe to in order to receive connector tokens and evaluator events for that turn.
- **FR-LC-054**: If the browser disconnects from the turn SSE endpoint and reconnects (e.g., tab refresh mid-turn), the server MUST allow reconnection to the same turn stream while the turn is still `in_progress`. On reconnect, the server MUST replay all buffered events from the beginning of the turn so the reconnected browser receives a complete view of the current turn's output.

**Persistence**

- **FR-LC-037**: System MUST persist per turn: the user message, assembled chatbot response, normalized contract, all structured evaluator events (in sequence order), final evaluation result, and error details if applicable.
- **FR-LC-038**: Persistence MUST occur as a batch write at turn completion, not per streaming event.
- **FR-LC-039**: On streaming failure, System MUST persist whatever was buffered at the point of failure along with error stage and details.
- **FR-LC-040**: Sensitive data MUST NOT be persisted in plain text (aligned with existing encryption constraints).

**Export**

- **FR-LC-041**: System MUST allow the session owner to export their session transcript in JSON (lossless) and CSV (flattened) formats at any time. Export is scoped to the session owner; admins cannot export sessions they do not own. Export MUST always include all turns in the session regardless of session length — no date-range or turn-range scoping is supported.
- **FR-LC-042**: Export MUST include per turn: user message, assembled chatbot response, normalized contract, evaluation events in sequence order, final evaluation result, error stage and details if applicable.

**Registration Changes**

- **FR-LC-043**: ConnectorRegistration MUST gain a `supports_sse` boolean field (default `false` for existing registrations).
- **FR-LC-044**: EvaluationAgentRegistration MUST gain a `supports_sse` boolean field (default `false` for existing registrations).
- **FR-LC-045**: The Connector Registration create and edit forms MUST include a "Supports Streaming (SSE)" toggle so operators can declare streaming capability when registering or updating a connector.
- **FR-LC-046**: The Evaluator Registration create and edit forms MUST include a "Supports Streaming (SSE)" toggle so operators can declare streaming capability when registering or updating an evaluator.
- **FR-LC-047**: Session creation wizard MUST only offer connectors and evaluators where `supports_sse = true`.

---

### Key Entities

- **ChatSession**: A named live testing session. Holds lifecycle status, creating user, timestamps, and snapshotted connector/evaluator configuration. One session contains many turns.
- **ChatTurn**: One user message within a session. Records the user message text, timestamps for when the turn started and completed, and an explicit `status` field (`in_progress → completed | failed`). The status enables server-side in-progress detection (FR-LC-050) and restart recovery.
- **ChatTurnResult**: The assembled output for a completed or failed turn. Holds the assembled chatbot response text, the normalized Standard Evaluation Contract, the final `EvaluationResult` (populated from the evaluator's `final` event payload if evaluation completed), error stage, and error details. One result per turn.
- **EvaluationEvent**: A single structured event emitted by the evaluator during a turn. Carries event type, a JSON payload, sequence number, and timestamp. Multiple events per turn; written in batch at turn end. Event types: `score_update` (partial scoring signal), `warning`, `insight`, `diagnostic`, `final` (carries the complete `EvaluationResult` payload — the server reads this directly into `ChatTurnResult.evaluationResult`).

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: A tester can complete session creation (all wizard steps) and be in the chat interface in under 60 seconds.
- **SC-002**: A tester can see the first streamed chatbot token appear within 500ms of the connector beginning its response.
- **SC-003**: Evaluation output begins appearing in the right pane within 500ms of the evaluator beginning its response.
- **SC-004**: A session with 20 turns can be exported to JSON in under 3 seconds.
- **SC-005**: A streaming failure on any single turn does not prevent the tester from sending subsequent messages in the same session.
- **SC-006**: The session creation wizard never displays connectors or evaluators that do not support SSE streaming.
- **SC-007**: Exported transcripts contain all turns, including failed turns with partial content and error details, with no data loss for completed turns.
- **SC-008**: An admin can bulk-delete sessions matching a selected inactivity preset (7 / 30 / >30 days) in a single confirmed action, with the operation completing in under 10 seconds for up to 1,000 sessions.
- **SC-009**: The dashboard chat sessions section loads without degrading the existing job listing load time.
- **SC-010**: The chat interface loads and renders the 50 most recent turns of a session in under 2 seconds, regardless of the total turn count in that session.

---

## Assumptions

- Only SSE-capable connectors and evaluators (declared via `supports_sse = true` in their registration) are eligible for live chat sessions. Existing registrations default to `supports_sse = false` and must be explicitly opted in via the enhanced registration forms.
- The Standard Evaluation Contract format used by batch jobs is reused as-is for live chat evaluation; no new contract schema is introduced.
- Session replay UI is out of scope for this release. The data model supports future replay via persisted turn results and ordered evaluation events, but no replay interface is built.
- Concurrent live chat sessions from multiple users are supported at the data model level. Performance under high concurrency is bounded by the single-file SQLite constraint and is acceptable for the deployment scale of 50–80 users.
- Token-level streaming events are ephemeral transport; only the assembled final response is persisted. Individual connector tokens are not stored.
- The tester may not submit a new message while a turn is in progress; the input is disabled until the current turn (including evaluation) completes.
- Live chat sessions are owned by the creating user and follow the same ownership/visibility model as batch jobs.
- At server restart, any `ChatTurn` with `status = in_progress` is updated to `status = failed` (partial content saved to its `ChatTurnResult`). The session remains `active` and is resumable. There is no session-level recovery action needed — sessions never enter a failed state.
- SSE connections are per-turn, not per-session. No persistent connection is held between turns. A session can remain `active` for days with no connection overhead.
- Sessions may accumulate well over 100 turns across months of use. The chat UI shows only the 50 most recent turns; the full turn history is available via export. This is by design — the UI is for active exploration, not historical review.
- The Chat Session Creation Wizard is a new, self-contained UI flow. It shares the same connector and evaluator registry data as the job creation wizard but does not share any wizard steps, routes, or templates with it.
- Admin bulk delete of terminal chat sessions follows the same pattern as existing Job Maintenance (016): terminal-only, confirmation required, with a post-operation stats refresh.
- The dashboard chat sessions section shows only the current user's sessions, consistent with how the job listing is scoped. Admins see all sessions only via the Chat Session Maintenance page.
