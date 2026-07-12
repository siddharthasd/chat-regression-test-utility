# Tasks: Headless Execution API (020)

**Input**: Design documents from `specs/020-headless-execution-api/`

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/api-contract.md ✅ quickstart.md ✅

**Tests**: Not included (not explicitly requested). Test patterns are documented in `quickstart.md §11` and the plan's project structure. Add test tasks before implementation if a TDD approach is preferred.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Exact file paths included in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the package skeleton and install the one new dependency before any feature work begins.

- [ ] T001 Create `src/harness/ui/api/` package: add `src/harness/ui/api/__init__.py` with a stub `create_api_router()` that returns an empty `APIRouter(prefix="/api/headless")`, and add `src/harness/ui/api/routes/__init__.py` (empty)
- [ ] T002 Add `PyJWT[crypto]` runtime dependency: run `uv add "PyJWT[crypto]"` and confirm `pyproject.toml` and lockfile are updated

**Checkpoint**: Package skeleton exists; `import harness.ui.api` succeeds; `PyJWT` is importable.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can be implemented — migration, ORM model update, shared schemas, Bearer auth, and router wiring.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Write Alembic migration `alembic/versions/<hash>_add_headless_job_fields.py`: `op.add_column` for `submission_source VARCHAR(20) NOT NULL server_default='wizard'`, `source_system VARCHAR(255) NULL`, `product_name VARCHAR(255) NULL`, `feature_name VARCHAR(255) NULL` on the `job` table; include a matching `downgrade()` using `op.drop_column`
- [ ] T004 [P] Add `submission_source: Mapped[str]`, `source_system: Mapped[str | None]`, `product_name: Mapped[str | None]`, `feature_name: Mapped[str | None]` mapped columns to the `Job` ORM model in `src/harness/persistence/models/job.py` (matching types and defaults from T003)
- [ ] T005 [P] Implement all Pydantic schemas in `src/harness/ui/api/schemas.py`: `HeadlessTestCase` (id, input_message, extra="allow"), `HeadlessJobSubmission` (test_cases, connector_id, evaluator_id, source_system, product_name, feature_name), `HeadlessJobSubmissionResponse` (job_id, stream_url, result_url), `FailedCase` (id, input_message), `JobSummary` (total, passed, failed, top_failures), `HeadlessJobResult` (job_id, status, results_url, summary), `ConnectorListItem` (id, name, description), `EvaluatorListItem` (id, name, description, scoring_dimensions)
- [ ] T006 [P] Implement Bearer JWT auth dependency in `src/harness/ui/api/auth.py`: module-level `PyJWKClient` singleton pointed at `https://login.microsoftonline.com/{HARNESS_AZURE_TENANT_ID}/discovery/v2.0/keys`; `require_api_auth` FastAPI dependency that decodes the `Authorization: Bearer` header using `jwt.decode(algorithms=["RS256"], audience=HARNESS_AZURE_CLIENT_ID)`, extracts `oid` and `preferred_username`, and returns a user identity dict; when `HARNESS_AUTH_ENABLED=false` returns a synthetic `{"oid": "local-dev", "name": "Local Dev"}` without validation; raises `HTTPException(401)` on missing/malformed/expired token
- [ ] T007 Register the headless API router in `src/harness/ui/__init__.py` by calling `app.include_router(create_api_router())` inside `create_app()`

**Checkpoint**: Foundation ready. `uv run alembic upgrade head` applies cleanly. `require_api_auth` resolves in the DI container. User story implementation can now begin.

---

## Phase 3: User Story 1 — Submit Test Cases and Stream Execution Progress (P1) 🎯 MVP

**Goal**: An external caller can submit up to 100 test cases as JSON, immediately receive a stream URL and result URL, observe live per-case `progress` events and a `job_started` event as the job executes, and receive a terminal `job_complete` or `job_failed` event with a summary when the job finishes.

**Independent Test**: Submit a JSON payload with 3 test cases via `POST /api/headless/jobs`, open the returned `stream_url` with `curl.exe -N`, and observe `job_started → progress × 3 → job_complete` events. Requires the Foundational phase complete (T003–T007).

- [ ] T008 [P] [US1] Implement `HeadlessJobEventBus` in `src/harness/ui/api/job_event_bus.py`: class with `_events: list[dict]`, `_ready: asyncio.Event`, `_closed: bool`; `push(event_type, payload)` method (appends to `_events`, sets `_ready`, sets `_closed=True` for terminal events); async `stream(cursor=0)` generator that yields buffered events then awaits `_ready` if not closed; module-level `_buses: dict[str, HeadlessJobEventBus]` dict with `create_bus(job_id)`, `get_bus(job_id)`, and `remove_bus(job_id)` helpers
- [ ] T009 [P] [US1] Add `count_headless_non_terminal_by_user(owner_id: str) -> int` and `list_headless_non_terminal_by_user(owner_id: str) -> list[Job]` methods to `JobRepository` in `src/harness/persistence/repositories/job.py`; both filter on `submission_source == "api"` and `status.not_in({completed, failed, cancelled})`
- [ ] T010 [US1] Add optional keyword parameters `progress_callback: Callable[[str, int, int], None] | None = None`, `job_started_callback: Callable[[str], None] | None = None`, and `job_terminal_callback: Callable[[str, str, dict], None] | None = None` to `enqueue_job()` in `src/harness/orchestrator/engine.py`; thread them into `run_job()`; call `job_started_callback(job_id)` on transition to running, `progress_callback(job_id, processed_count, failed_count)` after each row completes, and `job_terminal_callback(job_id, final_status, partial_summary_dict)` on terminal transition; all existing call sites (`enqueue_job(job_id)`) remain unaffected
- [ ] T011 [US1] Implement headless job submission in `src/harness/ui/api/service.py`: validate `len(test_cases) ≤ 100` (422), non-empty `input_message` per case (422 with offending id), unique caller-assigned ids within submission (422 with duplicate value), active `connector_id` via `ConnectorRegistryReader` (404), active `evaluator_id` via `EvaluatorRegistryReader` (404), connector does not require per-row password (422), user's non-terminal headless job count < 2 via T009 (429); create `Job` with `submission_source='api'`, `source_system`, `product_name`, `feature_name` set; stage utterances via `UtteranceRepository.bulk_create()` mapping `id→test_id`, `input_message→utterance_text`, 0-based index→`row_index`, extra keys→`extra_metadata`; call `create_bus(job_id)` (T008); build `_progress_hook`, `_started_hook`, `_terminal_hook` closures that call `loop.call_soon_threadsafe(bus.push, ...)` for each event type; call `enqueue_job(job_id, progress_callback=_progress_hook, job_started_callback=_started_hook, job_terminal_callback=_terminal_hook)`; return `HeadlessJobSubmissionResponse`
- [ ] T012 [US1] Implement `POST /api/headless/jobs` route in `src/harness/ui/api/routes/jobs.py`: `Depends(require_api_auth)` for auth, delegate to T011 service function, return 201 with `HeadlessJobSubmissionResponse`; raise appropriate `HTTPException` for each validation error class from T011
- [ ] T013 [US1] Implement `GET /api/headless/jobs/{job_id}/stream` SSE route in `src/harness/ui/api/routes/jobs.py`: look up bus via `get_bus(job_id)` (404 if not found, or look up job in DB for 403 ownership check); return `StreamingResponse(async_generator(), media_type="text/event-stream")` where the generator yields each event from `bus.stream(cursor=0)` formatted as `f"event: {e['event']}\ndata: {json.dumps(e['data'])}\n\n"`; call `remove_bus(job_id)` after the generator exhausts for the last consumer

**Checkpoint**: US1 fully functional. Submit job → stream events → receive terminal event with report URL. All validation errors return correct HTTP status codes.

---

## Phase 4: User Story 2 — Discover Available Connectors and Evaluators (P2)

**Goal**: An authenticated caller can list all active connectors and evaluators with their id, name, description (and scoring_dimensions for evaluators) to populate a selection UI before submitting a job.

**Independent Test**: Call `GET /api/headless/connectors` and `GET /api/headless/evaluators` with a valid Bearer token. Verify 200 responses with a list of items matching the registered connectors/evaluators. Unauthenticated call → 401.

- [ ] T014 [P] [US2] Implement `GET /api/headless/connectors` route in `src/harness/ui/api/routes/connectors.py`: `Depends(require_api_auth)`, call `ConnectorRegistryReader.list_active()`, map each entry to `ConnectorListItem`, return `{"connectors": [...]}`
- [ ] T015 [P] [US2] Implement `GET /api/headless/evaluators` route in `src/harness/ui/api/routes/evaluators.py`: `Depends(require_api_auth)`, call `EvaluatorRegistryReader.list_active()`, map each entry to `EvaluatorListItem` (including `scoring_dimensions` from `declared_scoring_dimensions`), return `{"evaluators": [...]}`

**Checkpoint**: US2 fully functional independent of US1. Discovery endpoints return correct shapes; empty lists return 200 (not 404).

---

## Phase 5: User Story 3 — Re-fetch Results After Stream Closes (P3)

**Goal**: A caller that missed or closed the SSE stream can retrieve the final result via `GET /jobs/{id}/result`. A caller can also cancel an in-flight job via `DELETE /jobs/{id}`, which transitions it to `cancelled`, emits a terminal stream event, and releases the in-flight slot.

**Independent Test**: Submit a job, close the stream before the terminal event, wait for completion, then call `GET /api/headless/jobs/{id}/result` and verify the same summary and `results_url` as the stream terminal event. Separately, submit a job and call `DELETE /api/headless/jobs/{id}` while it is queued; verify 200 and that the stream (if open) receives a `job_failed` event.

- [ ] T016 [US3] Implement `GET /api/headless/jobs/{job_id}/result` route in `src/harness/ui/api/routes/jobs.py`: fetch job by id (404 if not found), enforce ownership (403 if different user), map terminal status to `"completed"`/`"failed"`/`"cancelled"` and non-terminal to `"in_progress"`, build `JobSummary` from job's processed/failed counts and top failures (up to 5 from utterance results), set `results_url` only when status is `completed`, return `HeadlessJobResult`
- [ ] T017 [US3] Implement `DELETE /api/headless/jobs/{job_id}` cancellation route in `src/harness/ui/api/routes/jobs.py`: fetch job (404), enforce ownership (403), return 409 with `{"detail": "Job is already in terminal state: {status}.", "current_status": status}` if already terminal; otherwise transition job status to `cancelled` in DB, call `loop.call_soon_threadsafe(bus.push, "job_failed", {"error": "Job cancelled by user", "summary": {...}})` on the bus if it exists, return `{"job_id": ..., "status": "cancelled"}`

**Checkpoint**: US3 fully functional. Result re-fetch and cancel endpoints work correctly for all job states. 403 on cross-user access, 409 on already-terminal cancel.

---

## Phase 6: User Story 4 — Dashboard Visibility (P4)

**Goal**: Headless-submitted jobs appear in the eval-brew job dashboard with an "API" source badge, optional product/feature metadata as sub-text, correct status labels (including "Cancelled"), and a report link only for completed jobs.

**Independent Test**: Submit a headless job with `product_name="MyProduct"` and `feature_name="MyFeature"`. Navigate to `http://localhost:8000/jobs` and verify: the job row shows an "API" badge, "MyProduct / MyFeature" sub-text, and a working report link after completion. Submit and cancel another job; verify "Cancelled" status with no report link.

- [ ] T018 [P] [US4] Update `row_view()` in `src/harness/ui/dashboard/view.py` to include six new keys in the returned dict: `submission_source` (value from ORM), `source_label` (`"API"` if `submission_source == "api"` else `None`), `source_system`, `product_name`, `feature_name`, and `has_report` (`True` only when job status is `completed`)
- [ ] T019 [P] [US4] Update `src/harness/ui/dashboard/templates/jobs.html` to: render a small `<span class="badge">API</span>` (or equivalent) next to the status badge when `source_label == "API"`; render `<div class="source-meta">{{ product_name }} / {{ feature_name }}</div>` under the job name cell when either field is non-null; suppress the report link for rows where `has_report` is `False`

**Checkpoint**: US4 fully functional. All four user stories deliver independently testable value.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Wire all routes into the router, apply the migration, and run end-to-end validation.

- [ ] T020 Wire all route modules into `create_api_router()` in `src/harness/ui/api/__init__.py`: `router.include_router(connectors_router)`, `router.include_router(evaluators_router)`, `router.include_router(jobs_router)` — all with their own prefixes/tags; confirm `uv run uvicorn harness.ui:create_app --factory` starts without import errors
- [ ] T021 Apply Alembic migration to the development database and smoke-test: run `uv run alembic upgrade head`, query a sample of existing job rows to confirm `submission_source='wizard'` and the three nullable columns are `NULL`
- [ ] T022 [P] Validate all error response shapes against `contracts/api-contract.md`: confirm 422 on >100 cases, empty input_message, duplicate IDs; 404 on bad connector/evaluator; 429 on 3rd concurrent submission; 409 on cancel of terminal job; 403 on cross-user access — all match contract body format exactly
- [ ] T023 [P] Run end-to-end quickstart validation per `specs/020-headless-execution-api/quickstart.md`: register connector + evaluator → submit job → stream events → verify dashboard → re-fetch result → cancel a second job → confirm "Cancelled" in dashboard

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001, T002) — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational (T003–T007) — no dependency on US2, US3, or US4
- **US2 (Phase 4)**: Depends on Foundational (T003–T007) — **can run in parallel with US1**
- **US3 (Phase 5)**: Depends on US1 (needs job bus T008 for cancel stream event, job repo T009 for ownership checks, jobs route file T012 to extend)
- **US4 (Phase 6)**: Depends on Foundational T003/T004 (migration + Job model columns) — otherwise independent
- **Polish (Phase 7)**: Depends on all user story phases complete

### Within US1

```
T008 [P] ──┐
T009 [P] ──┤
           ├─→ T011 ──→ T012 ──→ T013
T010 ──────┘
```

### Within US2

T014 [P] and T015 [P] are fully independent of each other.

### Within US3

T016 and T017 are independent of each other but both depend on T009 (job repo) and T008 (bus for cancel).

### Within US4

T018 [P] and T019 [P] touch different files — fully parallel. T018 must complete before T019 can reference its new template variables.

---

## Parallel Opportunities

### Phase 2 (Foundational)

```bash
# All four of these can run simultaneously after T001+T002:
Task: "T003 — Write Alembic migration in alembic/versions/"
Task: "T004 — Add ORM columns to src/harness/persistence/models/job.py"
Task: "T005 — Write all Pydantic schemas in src/harness/ui/api/schemas.py"
Task: "T006 — Implement auth dependency in src/harness/ui/api/auth.py"
```

### Phase 3 (US1)

```bash
# T008 and T009 can run simultaneously:
Task: "T008 — HeadlessJobEventBus in src/harness/ui/api/job_event_bus.py"
Task: "T009 — JobRepository methods in src/harness/persistence/repositories/job.py"
# Then T010, T011, T012, T013 in sequence
```

### Phase 4 (US2)

```bash
# Fully parallel, and can overlap with Phase 3:
Task: "T014 — Connectors route in src/harness/ui/api/routes/connectors.py"
Task: "T015 — Evaluators route in src/harness/ui/api/routes/evaluators.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks everything)
3. Complete Phase 3: US1 (T008 → T009 → T010 → T011 → T012 → T013)
4. **STOP and VALIDATE**: Submit a job, open the stream, observe `job_started → progress → job_complete`
5. Demo to stakeholders — core integration with qual-brew is functional

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 (Phase 3) → job submission + SSE streaming → **MVP**: qual-brew can submit and monitor jobs
3. US2 (Phase 4) → connector/evaluator discovery → qual-brew can populate selection UI
4. US3 (Phase 5) → result re-fetch + cancel → production-grade reliability and control
5. US4 (Phase 6) → dashboard visibility → eval-brew users can audit headless jobs

### Recommended Single-Developer Order

`T001 → T002 → T003‖T004‖T005‖T006 → T007 → T008‖T009 → T010 → T011 → T012 → T013 → T014‖T015 → T016 → T017 → T018‖T019 → T020 → T021 → T022‖T023`

---

## Notes

- `[P]` tasks touch different files with no incomplete dependencies — safe to implement simultaneously
- All story-phase tasks must have `[US1]`–`[US4]` labels for traceability
- Commit after each logical group (e.g., after T003+T004 together, after T008+T009, after each story phase checkpoint)
- The `loop.call_soon_threadsafe()` pattern for thread→async bridging is the critical correctness requirement in T008/T010/T011/T017 — verify this is used everywhere the sync engine thread pushes to the async event bus
- Existing wizard job flow must remain untouched: `enqueue_job(job_id)` (no kwargs) must behave identically after T010
- `submission_source='wizard'` is the server default in the migration — no backfill Python script needed; existing rows are covered by the SQL `server_default`
