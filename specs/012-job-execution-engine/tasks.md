---
description: "Task list for Job Execution Engine (Module 10 — the orchestrator)"
---

# Tasks: Job Execution Engine (Module 10)

**Input**: Design documents from `specs/012-job-execution-engine/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R9) ✅, data-model.md ✅, contracts/engine-api.md ✅, quickstart.md ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `012-job-execution-engine` on `foundation` (010+009+006+007+008+013+014). **Heavy reuse, thin glue.** The orchestrator builds `ConnectorSnapshot`/`EvaluatorSnapshot` from the Job row and delegates to `harness.connector.dispatch_utterance` + `harness.evaluator.dispatch_evaluation` (both already validate, map the 9-value `ERROR_STAGES`, and compute `harness_annotations`); persists via 009's `EvaluationResultRepository.create` + `JobRepository` counters/transitions (incl. `transition_to_cancelled`'s `009 FR-003a` stub creation). **New code**: `harness.password_store` (011 FR-015, introduced here), `harness.orchestrator` (pipeline + engine), one `persistence/engine.py` tweak, one `bootstrap.py` hook. **No new deps.** Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US6 on story phases; Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [ ] T001 Create scaffold: `src/harness/orchestrator/__init__.py`, `src/harness/orchestrator/pipeline.py` (empty), `src/harness/orchestrator/engine.py` (empty), `tests/unit/orchestrator/__init__.py`. (No package-data: the orchestrator ships no templates.)

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T002 [P] Implement `src/harness/password_store.py`: process-global `dict[(job_id, utterance_id), str]` guarded by a module `threading.Lock`, with `put`/`get`/`evict`/`clear_job`/`job_has_entries` (011 FR-015; contract engine-api.md). In-memory only — no persistence, no encryption.
- [ ] T003 [P] Edit `src/harness/persistence/engine.py`: pass `connect_args={"check_same_thread": False}` to `create_engine` so threaded workers can share the pooled SQLite connection (R2). Preserve WAL/foreign_keys/busy_timeout pragmas + transactional-DDL.
- [ ] T004 [P] `tests/unit/test_password_store.py`: put/get/evict round-trip, `job_has_entries` true/false, `clear_job` removes only that job's entries (cross-job isolation, FR-022), evict-absent is a no-op.

**Checkpoint**: password store + threaded-safe engine ready; orchestrator package importable.

---

## Phase 3: User Story 1 — Execute a queued job end-to-end (Priority: P1) 🎯 MVP

- [ ] T005 [US1] Implement `src/harness/orchestrator/pipeline.py::process_row(job, utterance, *, conn_client=None, eval_client=None) -> EvaluationResultCreateData`: build `ConnectorSnapshot`/`EvaluatorSnapshot` from the Job snapshot fields (FR-004); password lookup via `password_store.get` iff `connector_expects_per_row_password`; `dispatch_utterance` → **evict** password immediately (FR-011 step 3); if connector ok, `dispatch_evaluation`; assemble the create-data per data-model.md §5 (success / connector-fail / evaluator-fail branches; `raw_chatbot_response=contract["chatbotResponse"]["rawPayload"]`, `evaluation_agent_id` always from the Job snapshot, `evaluation_timestamp` parsed from body `evaluationTimestamp` else now-UTC). No re-validation, no retries (FR-013).
- [ ] T006 [US1] Implement `src/harness/orchestrator/engine.py::run_job(job_id)`: `transition_to_running`; pre-row gate (US6 hook); iterate `UtteranceRepository.get_by_job_ordered`; per row, one `get_session()` txn → `EvaluationResultRepository.create` + `increment_processed_count` (+ `increment_failed_count` if `error_status`); cancel-check at row boundary (US3 hook); after loop `transition_to_completed`; wrap body so any unhandled exception → `transition_to_failed` (FR-016). Re-export `run_job` from `__init__.py`.
- [ ] T007 [P] [US1] `tests/unit/orchestrator/test_pipeline.py`: success mapping — verdict/scores/metadata/agent_id/timestamp/normalized_contract/raw_chatbot_response populated, `error_*` None; password looked up + evicted exactly once (probe the store, SC-008); body omits/includes password per `expects_per_row_password`. Uses `httpx.MockTransport` + injected clients.
- [ ] T008 [US1] `tests/integration/test_orchestrator_e2e.py`: queued job, N rows, matching store entries, bundled mock connector+evaluator (`mode="ok"`) → `status==completed`, `processed_count==N`, `failed_count==0`, `completed_at` set, N results with `error_status is None` + verdict populated, store empty for the job (SC-001, FR-016).

**Checkpoint**: MVP — a queued job runs end-to-end and persists results.

---

## Phase 4: User Story 2 — Isolate per-row failures (Priority: P1)

- [ ] T009 [P] [US2] `tests/unit/orchestrator/test_pipeline.py` (same file): failure mappings — connector `connector_transport`/`connector_response`/`connector_normalization`/`connector_auth` and evaluator `evaluator_transport`/`evaluator_response`/`evaluator_result`/`evaluator_auth` each → `error_status="failed"`, matching `error_stage`, `error_details` set; correct nulling of downstream fields (data-model.md §5); `evaluation_agent_id` still from snapshot (never null) (FR-012, SC-002/010).
- [ ] T010 [US2] `tests/integration/test_orchestrator_e2e.py` (same file): mixed-outcome job (mock connector `status500` / nonconformant + a clean run) → all rows persist one result each, job still `completed`, `failed_count==K`, per-row stages correct; every-row-fails case → `completed` with `failed_count==total` (NOT `failed`) (SC-002/003, FR-012/018).

**Checkpoint**: One flaky row never aborts the job; stages are faithful.

---

## Phase 5: User Story 3 — Honor soft-cancel mid-run (Priority: P2)

- [ ] T011 [US3] In `engine.py::run_job` (same file): at each row boundary re-read `JobRepository.get(job_id).status`; on `cancelling`, stop the loop, call `transition_to_cancelled(job_id)` (009 stubs the remainder per FR-003a) + `password_store.clear_job(job_id)` (FR-019/020).
- [ ] T012 [US3] `tests/integration/test_orchestrator_e2e.py` (same file): set the job to `cancelling` after the first row (slow mock or a hook) → in-flight row gets a normal result, remaining utterances get `cancelled` stubs, `running→cancelling→cancelled`, store empty for the job (SC-004).

**Checkpoint**: Cancel finishes the in-flight row, stubs the rest, ends `cancelled`.

---

## Phase 6: User Story 4 — Reconcile orphaned jobs at startup (Priority: P2)

- [ ] T013 [US4] Implement `engine.py::reconcile_orphans()`: for every Job in `get_by_status("running")` + `get_by_status("cancelling")`, `transition_to_failed(job_id, "harness restarted while job was <status>")`; re-export from `__init__.py`. Wire it into `src/harness/bootstrap.py::initialize_harness` immediately after `init_db()` (FR-002).
- [ ] T014 [US4] `tests/integration/test_orchestrator_e2e.py` (same file): seed a `running` and a `cancelling` job, call `reconcile_orphans()` → both `failed` with explanatory `error_details` + `completed_at` set; pre-existing results preserved; no job left `running`/`cancelling` (SC-005, FR-002).

**Checkpoint**: No job is stuck `running` after a restart.

---

## Phase 7: User Story 5 — Concurrent jobs (Priority: P2)

- [ ] T015 [US5] Implement `engine.py::enqueue_job(job_id)`: acquire a module `BoundedSemaphore` slot (cap = plan default 4), spawn `threading.Thread(target=run_job, daemon=True)`, release the slot in `finally`; return immediately (FR-001/022). Re-export from `__init__.py`.
- [ ] T016 [US5] `tests/integration/test_orchestrator_e2e.py` (same file): enqueue two jobs against the same bundled mocks → both reach `completed` with independent counters/results; cancelling one leaves the other unaffected; store entries isolated by `(job_id, …)` (SC-007, FR-024). Join threads with a timeout.

**Checkpoint**: Two jobs run concurrently with fully isolated state.

---

## Phase 8: User Story 6 — Fail cleanly on empty password store (Priority: P3)

- [ ] T017 [US6] In `engine.py::run_job` (same file): finalize the pre-row gate — if `connector_expects_per_row_password` and `not password_store.job_has_entries(job_id)` → `transition_to_failed(job_id, "credentials no longer in memory — re-upload CSV via a new job")` and return before any row; if the flag is false, proceed normally (FR-017).
- [ ] T018 [US6] `tests/integration/test_orchestrator_e2e.py` (same file): job whose snapshot has `expects_per_row_password=true` + empty store → `failed`, `error_details` names the cause, `completed_at` set, zero results, zero HTTP calls; control case with flag false → proceeds (SC-006).

**Checkpoint**: The lone true pre-row failure mode is clean.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T019 [P] SC-012/SC-008 guards: confirm no orchestrator log line emits the decrypted credential or the `Authorization` header (request logging excludes headers); assert per-row eviction happens before the evaluator dispatch via a store probe.
- [ ] T020 [P] `python -m ruff check src tests --fix`; resolve findings (line-length 100, datetime UTC/UP017).
- [ ] T021 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 265 tests still pass + adequate `orchestrator/` + `password_store` coverage.
- [ ] T022 [P] Execute `specs/012-job-execution-engine/quickstart.md`; file discrepancies.
- [ ] T023 [P] Verify FR→File and SC matrices; confirm `CLAUDE.md` marker → `012` plan.

---

## Dependencies & Execution Order

- **Setup** (T001) → no deps. **Foundational** (T002–T004) → block all stories (password store, threaded engine).
- **US1 (P3–4)** → `pipeline.process_row` (T005) then `run_job` (T006); the MVP.
- **US2 (P4)** → tests only over T005's failure branches (built once in T005).
- **US3 (P5)**, **US6 (P8)** → small additions to the single `engine.py::run_job` (cancel-check, pre-row gate) → **sequential** with T006.
- **US4 (P6)** → `reconcile_orphans` + bootstrap hook (new function + 1-line wire).
- **US5 (P7)** → `enqueue_job` (new function).
- **Polish** → after the targeted stories.

### Critical path
Setup → Foundational → US1 (T005→T006) → US2 → US3 → US4 → US5 → US6 → Polish. `engine.py` is one file grown across US1/US3/US4/US5/US6 → those edit tasks are **sequential**; `pipeline.py` is built once (T005) and only *tested* per story. `test_orchestrator_e2e.py` is one file extended per story → sequential within.

### Parallel opportunities
- Foundational: T002 ‖ T003 ‖ T004.
- `test_pipeline.py` (T007 ‖ T009 — distinct from the integration file) is [P]; the integration file is sequential across stories.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 → **STOP & VALIDATE**: a queued job runs end-to-end against the bundled mocks and persists N results (SC-001).

### Incremental delivery
US1 → US2 → US3 → US4 → US5 → US6 → Polish.

---

## Notes

- The orchestrator is glue: it never re-validates contracts/results (007/008 own that), never assigns verdicts or maps error stages itself (it copies them from `ConnectorResult`/`EvaluatorResult`), and never retries (FR-013). The 9-value `ERROR_STAGES` (009) is the single taxonomy and already matches the spec's finer taxonomy.
- `evaluation_agent_id` on every persisted row comes from the **Job snapshot**, so the column is never null even on connector-stage failures (009 FR-003).
- Integration tests reuse the bundled `harness.connector.mock` / `harness.evaluator.mock` servers and the per-test `engine.init_db(tmp)` isolation recipe (from 013/014). Commit after each task/group.
