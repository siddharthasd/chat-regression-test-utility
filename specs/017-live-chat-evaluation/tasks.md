# Tasks: Live Chat & Real-Time Evaluation

**Branch**: `017-live-chat-evaluation`
**Input**: Design documents from `specs/017-live-chat-evaluation/`

**Format**: `- [ ] [TaskID] [P?] [Story?] Description — file path`
- **[P]**: Parallelisable (different files, no incomplete-task dependencies)
- **[Story]**: User story label (US1–US8); omitted for Setup, Foundational, and Polish phases

---

## Phase 1: Setup

**Purpose**: Create all new package skeletons so imports resolve immediately across the codebase.

- [ ] T001 Create `src/harness/chat/` package with placeholder files: `__init__.py`, `session_service.py`, `turn_service.py`, `stream_orchestrator.py`, `event_bus.py`
- [ ] T002 Create `src/harness/ui/chat_session/` package with placeholder files: `__init__.py`, `routes.py`, `view.py`, `wizard_steps.py`; create `src/harness/ui/chat_session/templates/chat_session/` directory

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All ORM models, the Alembic migration, the event bus, the repository, and server startup recovery. No user story can begin until this phase is complete.

⚠️ **CRITICAL**: This phase gates everything downstream.

- [ ] T003 [P] Add `supports_sse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)` to `ConnectorRegistration` in `src/harness/persistence/models/connector_registration.py`
- [ ] T004 [P] Add `supports_sse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)` to `EvaluationAgentRegistration` in `src/harness/persistence/models/evaluator_registration.py`
- [ ] T005 [P] Create `ChatSession` model (all fields from data-model.md: session ID, owner OID, session name, encrypted test_id_enc + test_password_enc, connector snapshot columns, evaluator snapshot columns, created_at, turns relationship) in `src/harness/persistence/models/chat_session.py`
- [ ] T006 [P] Create `ChatTurn` model (turn_id, session_id FK, user_message, status, created_at, completed_at, result and evaluation_events relationships) in `src/harness/persistence/models/chat_turn.py`
- [ ] T007 [P] Create `ChatTurnResult` model (turn_result_id, turn_id FK unique, assembled_response, normalized_contract, final_evaluation_result, error_stage, error_details) in `src/harness/persistence/models/chat_turn_result.py`
- [ ] T008 [P] Create `EvaluationEvent` model (event_id, turn_id FK, event_type, payload JSON, sequence_number, created_at) in `src/harness/persistence/models/evaluation_event.py`
- [ ] T009 Create Alembic migration `0005_add_live_chat.py` (ADD COLUMN supports_sse on both registration tables; CREATE TABLE chat_session, chat_turn, chat_turn_result, evaluation_event) in `src/harness/persistence/migrations/versions/0005_add_live_chat.py` — depends on T003–T008; also update `tests/integration/test_migrations.py` line 49: change `assert current == "0004"` to `assert current == "0005"`
- [ ] T010 Create `ChatSessionRepository` with all methods from data-model.md: `create_session`, `get_session`, `list_sessions_for_owner`, `list_all_sessions`, `delete_session`, `create_turn`, `get_turn`, `get_in_progress_turn`, `complete_turn` (batch write: status + result + events), `fail_turn`, `recover_stale_turns`, `count_sessions_inactive_since`, `delete_sessions_inactive_since` in `src/harness/persistence/repositories/chat_session_repository.py`
- [ ] T011 Create `TurnEventBus` class (events list, asyncio.Condition, completed flag, `publish`, `mark_complete`, `stream_from` async generator) and global bus registry functions (`create_bus`, `get_bus`, `remove_bus`) in `src/harness/chat/event_bus.py`
- [ ] T012 Register `chat_session` router in the FastAPI app factory in `src/harness/ui/__init__.py`
- [ ] T013 Add server startup recovery in `src/harness/bootstrap.py` (alongside `reconcile_orphans()`): call `ChatSessionRepository.recover_stale_turns()` to flip all `in_progress` ChatTurns to `failed` with `error_details = "Server restarted while turn was in progress"`; the bootstrap function is already called from the FastAPI `lifespan` context in `src/harness/ui/__init__.py` so no changes to that file are needed

**Checkpoint**: All models, migration, event bus, and repository complete. Start app → migration 0005 runs cleanly. User story work can now begin.

---

## Phase 3: User Story 1 — Create a Live Chat Session via Dedicated Wizard (Priority: P1) 🎯 MVP

**Goal**: A tester can step through the 5-step wizard to create a named live chat session with encrypted test credentials, snapshotted SSE-capable connector and evaluator, and land on the active chat interface.

**Independent Test**: Complete all five wizard steps with valid inputs; confirm a `ChatSession` row is persisted with encrypted credentials and connector/evaluator snapshots; confirm redirect to `/chat/sessions/{id}`.

- [ ] T014 [US1] Implement `ChatSessionService` in `src/harness/chat/session_service.py`: `create_session(name, connector_id, test_id, password, evaluator_id, owner_oid) → ChatSession` — encrypts credentials via `encrypt_credential`, snapshots connector and evaluator fields from their registrations, persists via `ChatSessionRepository`
- [ ] T015 [US1] Implement per-step validation in `src/harness/ui/chat_session/wizard_steps.py`: step 1 (name non-empty), step 2 (connector selected and `supports_sse=True`), step 3 (test_id non-empty, password non-empty), step 4 (evaluator selected and `supports_sse=True`), step 5 (all previous steps valid)
- [ ] T016 [P] [US1] Create wizard step 1 template (session name input, Next button) in `src/harness/ui/chat_session/templates/chat_session/wizard_step1.html`
- [ ] T017 [P] [US1] Create wizard step 2 template (SSE-capable-only connector list with radio buttons; empty-state message if none available) in `src/harness/ui/chat_session/templates/chat_session/wizard_step2.html`
- [ ] T018 [P] [US1] Create wizard step 3 template (plain-text test_id field; masked password field with show/hide reveal toggle button; both required) in `src/harness/ui/chat_session/templates/chat_session/wizard_step3.html`
- [ ] T019 [P] [US1] Create wizard step 4 template (SSE-capable-only evaluator list with radio buttons; empty-state message if none available) in `src/harness/ui/chat_session/templates/chat_session/wizard_step4.html`
- [ ] T020 [P] [US1] Create wizard step 5 template (confirmation summary: session name, connector name, evaluator name, test_id; Confirm + Start button) in `src/harness/ui/chat_session/templates/chat_session/wizard_step5.html`
- [ ] T021 [US1] Implement all wizard routes (GET/POST `/chat/wizard/step{1–5}`) plus session-create-on-confirm in `src/harness/ui/chat_session/routes.py`; route at step 5 POST calls `ChatSessionService.create_session()` and redirects to `/chat/sessions/{session_id}` — depends on T014, T015

**Checkpoint**: Wizard is end-to-end functional. Session created, credentials encrypted, redirect lands on chat interface stub.

---

## Phase 4: User Story 2 — View Chat Sessions on the Dashboard (Priority: P1)

**Goal**: Dashboard shows a tester's 5 most recent sessions alongside jobs, with "New Chat Session" and "View All Sessions" entry points. A sortable all-sessions list page (role-scoped) is accessible.

**Independent Test**: Create 2 sessions; visit dashboard → sessions section shows both (up to 5); click "View All Sessions" → sortable table listing both; admin sees all users' sessions, tester sees only their own.

- [ ] T022 [P] [US2] Add `supports_sse` boolean toggle to connector registration: (1) add `supports_sse` field to `src/harness/ui/connector_registry/forms.py`; (2) add checkbox to `src/harness/ui/connector_registry/templates/connector_registry/form.html`; (3) include `supports_sse` in `update_data` dict in `src/harness/ui/connector_registry/service.py`; (4) pass `supports_sse` form param in create/edit route handlers in `src/harness/ui/connector_registry/routes.py`; (5) add `supports_sse` to the update field list in `src/harness/persistence/repositories/connector_registration.py`
- [ ] T023 [P] [US2] Add `supports_sse` boolean toggle to evaluator registration: (1) add `supports_sse` field to `src/harness/ui/evaluator_registry/forms.py`; (2) add checkbox to `src/harness/ui/evaluator_registry/templates/evaluator_registry/form.html`; (3) include `supports_sse` in `update_data` dict in `src/harness/ui/evaluator_registry/service.py`; (4) pass `supports_sse` form param in create/edit route handlers in `src/harness/ui/evaluator_registry/routes.py`; (5) add `supports_sse` to the update field list in `src/harness/persistence/repositories/evaluator_registration.py`
- [ ] T024 [US2] Implement session projections (session row view: name, connector name, evaluator name, turn count, created_at; sort helpers) in `src/harness/ui/chat_session/view.py`
- [ ] T025 [US2] Implement session list route (`GET /chat/sessions`) with role-based scoping (testers: own sessions; admins: all sessions), sortable by name/connector/evaluator/turn count/created_at in `src/harness/ui/chat_session/routes.py`
- [ ] T026 [US2] Create session list template (sortable table, columns: name/connector/evaluator/turn count/created date/delete action; role-scoped delete visibility) in `src/harness/ui/chat_session/templates/chat_session/list.html`
- [ ] T027 [US2] Extend dashboard route to inject `chat_sessions` (5 most recent for current user) and `chat_session_count` into template context in `src/harness/ui/dashboard/routes.py`; audit ALL render paths in that file (including `delete_job()` and any other routes that call `render_template("dashboard/index.html", ...)`) and add `chat_sessions`/`chat_session_count` to each, or add `{% if chat_sessions is defined %}` guards to the template in T028
- [ ] T028 [US2] Add chat sessions section to dashboard template (5 most recent entries, "New Chat Session" button, "View All Sessions" link; empty state if no sessions) in `src/harness/ui/dashboard/templates/dashboard/index.html`; wrap the entire new section with `{% if chat_sessions is defined %}` so routes that don't yet pass the key (e.g. `delete_job()`) don't raise `UndefinedError` before T027 touches those paths
- [ ] T029 [US2] Add "Chat Sessions" navigation link and "New Chat Session" shortcut to the navbar in `src/harness/ui/templates/base.html`

**Checkpoint**: Dashboard shows sessions section. Session list page accessible. Admins see all sessions; testers see own. SSE toggles appear in both registry forms.

---

## Phase 5: User Story 3 — Send a Message and Observe Streaming Output (Priority: P1)

**Goal**: Tester submits a message; connector tokens stream into the left pane with GFM rendering; "Evaluating…" indicator appears; evaluator events stream into the right pane. Both panes are associated per turn. Left pane shows non-dismissible fidelity warning.

**Independent Test**: Using mock SSE connector and evaluator (per quickstart.md): POST a message → turn created → browser SSE stream delivers `connector_token` events then `evaluating` then `evaluator_event` events then `turn_complete`; UI renders GFM in right pane and connector response in left pane; fidelity warning is visible.

- [ ] T030 [US3] Implement `TurnService` in `src/harness/chat/turn_service.py`: `create_turn(session_id, user_message) → ChatTurn` (checks for existing in-progress turn via `ChatSessionRepository.get_in_progress_turn` and raises HTTP 409 if found); `get_turn`; state accessors
- [ ] T031 [US3] Implement async `StreamOrchestrator.run_turn(turn_id, session, user_message, bus)` in `src/harness/chat/stream_orchestrator.py`: (1) decrypt test credentials; (2) POST to connector with `{"auth": {"test_id": ..., "password": ...}, "message": ...}` using `httpx.AsyncClient.stream()`; (3) parse connector SSE via `aiter_lines()`; (4) publish `connector_token` browser events to `bus` as tokens arrive; (5) detect and extract `contract` event; (6) validate contract (reuse existing `harness.contract`); (7) publish `evaluating` browser event; (8) POST contract to evaluator and parse evaluator SSE; (9) publish `evaluator_event` browser events; (10) on completion publish `turn_complete`; (11) batch-write assembled response + events + final result via `ChatSessionRepository.complete_turn`
- [ ] T032 [US3] Implement turn submission route (`POST /chat/sessions/{session_id}/turns`) in `src/harness/ui/chat_session/routes.py`: validate owner, create turn via `TurnService`, create bus via `event_bus.create_bus`, launch `StreamOrchestrator.run_turn` as `BackgroundTasks` task, return `{"turn_id": "..."}` JSON immediately
- [ ] T033 [US3] Implement per-turn SSE stream route (`GET /chat/sessions/{session_id}/turns/{turn_id}/stream`) in `src/harness/ui/chat_session/routes.py`: validate owner; if turn `in_progress` stream from `event_bus.get_bus(turn_id).stream_from(cursor=0)`; if `completed`/`failed` replay persisted events from DB then send terminal event; return `StreamingResponse(..., media_type="text/event-stream")`
- [ ] T034 [US3] Implement chat interface route (`GET /chat/sessions/{session_id}`) in `src/harness/ui/chat_session/routes.py`: owner-only access; load session + last 50 turns ordered by created_at; pass to template
- [ ] T035 [US3] Create split-pane chat interface template in `src/harness/ui/chat_session/templates/chat_session/interface.html`: left pane (50 prior turns rendered as tester-message plain text + connector response GFM; sticky non-dismissible fidelity warning banner; message input + Send button, disabled during in-progress); right pane (evaluation events per turn, "Evaluating…" indicator); load marked.js v14 + DOMPurify v3 from CDN; JS: on Send POST to turn submission route, open EventSource to stream route, render `connector_token` events via `element.innerHTML = DOMPurify.sanitize(marked.parse(buffer))` on each event, handle `evaluating`/`evaluator_event`/`turn_complete`/`turn_failed` events; session metadata header showing test_id (read-only) and masked password (read-only, no reveal toggle)

**Checkpoint**: Core streaming loop works end-to-end. Left and right panes update progressively. GFM renders. Fidelity warning is always visible.

---

## Phase 6: User Story 4 — Export a Session Transcript (Priority: P2)

**Goal**: Session owner can export full turn history as JSON (lossless) or CSV (flattened). In-progress turns excluded. Always includes all turns regardless of count.

**Independent Test**: Create a session with 2 completed turns and 1 failed turn; download JSON export → verify all 3 turns present with correct fields per `contracts/export-schema.md`; download CSV export → verify one row per turn.

- [ ] T036 [US4] Implement session export builders in `src/harness/chat/export_service.py`: `build_session_export(session, turns, fmt) → (filename, mimetype, bytes)` for `json` and `csv` formats per `contracts/export-schema.md`; exclude in-progress turns; never include credentials or auth descriptor credential subfields
- [ ] T037 [US4] Add export routes (`GET /chat/sessions/{session_id}/export`) with `?format=json|csv` query param in `src/harness/ui/chat_session/routes.py`; owner-only enforcement; stream result as file download
- [ ] T038 [US4] Add "Export JSON" and "Export CSV" download buttons to chat interface template in `src/harness/ui/chat_session/templates/chat_session/interface.html`

**Checkpoint**: JSON and CSV export downloads work; credentials absent; in-progress turns excluded; failed turns included with partial content.

---

## Phase 7: User Story 5 — Delete Own Chat Sessions (Priority: P2)

**Goal**: Tester can delete any of their own sessions. If a turn is in progress, a warning is shown and explicit confirmation required. Deletion is cascade (turns + results + events).

**Independent Test**: Delete a session with no active turn → session gone from list. Delete a session mid-stream → warning appears → confirm → session deleted and stream abandoned.

- [ ] T039 [US5] Implement tester session deletion route (`POST /chat/sessions/{session_id}/delete`) in `src/harness/ui/chat_session/routes.py`: owner-only; if an in-progress turn exists and no `?confirm=true` param, re-render confirmation prompt; if confirmed (or no in-progress turn), delete via `ChatSessionRepository.delete_session` and remove bus if present
- [ ] T040 [US5] Add delete button and in-progress confirmation modal to session list template and chat interface template in `src/harness/ui/chat_session/templates/chat_session/list.html` and `interface.html`

**Checkpoint**: Testers can delete their own sessions. In-progress warning flows correctly. Non-owners blocked with 403.

---

## Phase 8: User Story 6 — Admin Manages Chat Sessions via Admin Menu (Priority: P2)

**Goal**: Admin can access Chat Session Maintenance page (aggregate stats, bulk-delete by inactivity preset). Admin can delete any individual session from the session list (silently skipping in-progress sessions).

**Independent Test**: Create sessions across two users; as admin, visit Chat Session Maintenance → stats correct; run 7-day bulk delete → count shown in confirmation → sessions deleted. Admin deletes a session with in-progress turn → silently skipped, no error.

- [ ] T041 [US6] Add "Chat Session Maintenance" link to the Admin dropdown menu in `src/harness/ui/admin/routes.py` and `src/harness/ui/templates/base.html` (or admin nav partial)
- [ ] T042 [US6] Implement admin Chat Session Maintenance routes (`GET /admin/chat-maintenance` — stats page; `POST /admin/chat-maintenance/preview` — count sessions matching preset; `POST /admin/chat-maintenance/delete` — execute bulk delete) in `src/harness/ui/admin/routes.py`; use `ChatSessionRepository.count_sessions_inactive_since` and `delete_sessions_inactive_since`; sessions with in-progress turns silently skipped
- [ ] T043 [US6] Create chat maintenance template (aggregate stats: total sessions, total turns, sessions-by-age breakdown; three-preset inactivity selector: 7 days / 30 days / >30 days; preview count step; confirmation step; post-delete stats refresh) in `src/harness/ui/admin/templates/admin/chat_maintenance.html`
- [ ] T044 [US6] Implement admin individual session deletion from session list (`POST /chat/sessions/{session_id}/admin-delete`) in `src/harness/ui/chat_session/routes.py`; admin role required; silently skip if session has in-progress turn; no confirmation dialog

**Checkpoint**: Admin maintenance page shows correct stats and bulk-delete works. Admin individual delete skips in-progress sessions silently.

---

## Phase 9: User Story 7 — Handle Streaming Failures Gracefully (Priority: P3)

**Goal**: Any failure during connector or evaluator streaming (stall, connection error, contract validation failure) fails only the current turn; the session remains active and the tester can continue with a new message.

**Independent Test**: Inject a stall into the mock connector stream → turn fails with `error_stage = connector_stream`; session list shows session still active; new message accepted. Inject contract validation failure → `error_stage = connector_normalization`; evaluator not invoked. Inject evaluator stall → `error_stage = evaluator_stream`; partial events persisted.

- [ ] T045 [US7] Implement connector stall timeout detection in `src/harness/chat/stream_orchestrator.py`: wrap each `aiter_lines()` iteration with `asyncio.wait_for(..., timeout=session.connector_timeout_seconds)`; on `asyncio.TimeoutError` raise `ConnectorStreamError("Stall timeout")`; catch `ConnectorStreamError` and call `ChatSessionRepository.fail_turn(turn_id, error_stage="connector_stream", partial_response=assembled_buffer)`; publish `turn_failed` browser event
- [ ] T046 [US7] Implement evaluator stall timeout and connection failure handling in `src/harness/chat/stream_orchestrator.py`: same `asyncio.wait_for` pattern for evaluator `aiter_lines()`; on failure call `ChatSessionRepository.fail_turn(turn_id, error_stage="evaluator_stream", events_so_far=buffered_events)`; publish `turn_failed` browser event
- [ ] T047 [US7] Implement contract validation failure path in `src/harness/chat/stream_orchestrator.py`: if contract validation raises, call `ChatSessionRepository.fail_turn(turn_id, error_stage="connector_normalization", partial_response=assembled_buffer)`; evaluator MUST NOT be invoked; publish `turn_failed` browser event
- [ ] T048 [US7] Add failed turn display to chat interface template in `src/harness/ui/chat_session/templates/chat_session/interface.html`: render failed turns with error stage label and any partial assembled response; ensure input re-enables after a failed turn so tester can continue

**Checkpoint**: All three failure modes (connector stall, evaluator stall, contract validation) correctly fail the turn, persist partial data, leave session active, and re-enable the message input.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Integration validation, tests, and hardening across all stories.

- [ ] T049 [P] Write integration tests for wizard flow and session management (create, list, delete, export) in `tests/integration/test_chat_session_wizard.py` and `tests/integration/test_chat_session_mgmt.py`; use `httpx.MockTransport` for mock SSE streams per quickstart.md fixture patterns
- [ ] T050 [P] Write integration tests for turn lifecycle, streaming pipeline (happy path + all 3 failure modes), and admin maintenance in `tests/integration/test_chat_turn_lifecycle.py`, `tests/integration/test_chat_stream_pipeline.py`, `tests/integration/test_chat_admin_maintenance.py`
- [ ] T051 [P] Write unit tests for `TurnEventBus` (publish, replay, concurrent readers, mark_complete), `ChatSessionService` (credential encryption round-trip, snapshot fields), `TurnService` (concurrent turn rejection), and `StreamOrchestrator` (happy path, each failure mode) in `tests/unit/chat/test_event_bus.py`, `test_session_service.py`, `test_turn_service.py`, `test_stream_orchestrator.py`
- [ ] T052 Run full pytest suite and confirm all previously-passing tests (444+) still pass; investigate and resolve any regressions before marking this phase complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — blocks all user stories
- **Phases 3–9 (User Stories)**: All depend on Phase 2 completion; US3 depends on US1 (session must exist before turns can be sent)
- **Phase 10 (Polish)**: Depends on all desired user stories complete

### User Story Dependencies

| Story | Depends On | Can Run In Parallel With |
|-------|-----------|--------------------------|
| US1 (Wizard) | Phase 2 | US2 |
| US2 (Dashboard) | Phase 2 | US1 |
| US3 (Streaming) | US1 (session must exist) | — |
| US4 (Export) | US3 (turns must exist) | US5, US6 |
| US5 (Delete) | US1 | US4, US6 |
| US6 (Admin) | US2 | US4, US5 |
| US7 (Failures) | US3 | — |

### Parallel Opportunities Per Story

```
Phase 2 (Foundational):
  Parallel group A: T003, T004, T005, T006, T007, T008  ← all model files
  Then: T009 (migration), T010 (repository), T011 (event bus), T012 (app factory), T013 (recovery)

Phase 3 (US1):
  T014 (session_service), T015 (wizard_steps), T016–T020 (5 templates)  ← T014+T015+templates in parallel
  Then: T021 (routes — depends on T014+T015)

Phase 4 (US2):
  T022, T023 (registry form toggles — parallel)
  T024 (view.py — parallel with T022/T023)
  T025, T026, T027, T028, T029 — sequential route → template → dashboard → nav

Phase 5 (US3):
  T030 (turn_service), T031 (stream_orchestrator)  ← parallel
  Then: T032, T033, T034 (routes — depend on T030+T031)
  Then: T035 (interface template — depends on routes)

Phase 10 (Polish):
  T049, T050, T051  ← all parallel
  Then: T052 (full test run)
```

---

## Implementation Strategy

### MVP First (US1 + US3 only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 (wizard — session creation)
4. Complete Phase 5: US3 (streaming — the core value loop)
5. **STOP and VALIDATE**: End-to-end chat session with mock connector and evaluator per quickstart.md
6. If stable → ship MVP

### Incremental Delivery

1. Setup + Foundational → Foundation committed
2. US1 (Wizard) → Sessions creatable ✓
3. US2 (Dashboard) → Sessions visible on dashboard ✓
4. US3 (Streaming) → Core chat loop working ✓  ← **MVP delivery point**
5. US4 (Export) → Transcripts downloadable ✓
6. US5 (Delete) → Session hygiene ✓
7. US6 (Admin) → Maintenance tools ✓
8. US7 (Failures) → Resilience hardened ✓
9. Polish → Tests + regression baseline ✓

---

## Notes

- `[P]` tasks touch different files and have no dependency on incomplete earlier tasks in the same phase — safe to run in parallel
- `[US#]` labels map to user stories in `spec.md` for traceability
- Each phase checkpoint is independently verifiable before moving to the next story
- The chat session wizard (US1) uses session-scoped in-memory state for wizard step progress; follow the same pattern as the existing job creation wizard in `src/harness/ui/wizard/`
- All SSE routes must be `async def`; all existing routes remain `def` (FastAPI handles the mix via thread pool / event loop)
- Test fixtures for mock SSE streams: inject via `httpx.MockTransport` — see `quickstart.md` fixture skeleton
