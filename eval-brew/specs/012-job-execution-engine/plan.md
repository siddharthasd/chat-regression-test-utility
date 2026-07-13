# Implementation Plan: Job Execution Engine (Module 10)

**Branch**: `012-job-execution-engine` | **Date**: 2026-06-04 | **Spec**: `specs/012-job-execution-engine/spec.md`

**Input**: Feature specification from `specs/012-job-execution-engine/spec.md`

## Summary

`012` is **the orchestrator** — the async loop that turns a `queued` Job into a persisted set of `EvaluationResult`s. For each Utterance (in `rowIndex` order) it: looks up the per-row password (in-memory store), `dispatch_utterance` to the connector (007), `dispatch_evaluation` to the evaluator (008), and persists one `EvaluationResult` atomically with the Job counters (009). It isolates per-row failures (Job still ends `completed`), honors soft-cancel (`cancelling → cancelled` with stubs), reconciles orphaned `running`/`cancelling` jobs to `failed` at startup, runs jobs concurrently (one worker thread per job, rows serial within a job), never retries, and fails the whole Job only for the lone pre-row case (empty password store when the connector expects per-row passwords).

**Heavy reuse — the orchestrator is thin glue:** 007's `dispatch_utterance` already validates the contract + maps `connector_*` error stages; 008's `dispatch_evaluation` already validates the EvaluationResult + maps `evaluator_*` stages + computes `harnessAnnotations`. 009's repositories already do transitions, counters, cancellation stubs, and the orphan query (`get_by_status`). So `012` mostly maps Job-snapshot → `ConnectorSnapshot`/`EvaluatorSnapshot`, sequences the two calls, builds the `EvaluationResult` row, and manages the worker/lifecycle.

**Cross-module note:** the **in-memory password store is specified by `011 FR-015`, but `011` isn't implemented yet.** `012` introduces the store module (`harness.password_store`) as shared process-scoped infra — `012` is its canonical consumer; `011` will populate it on CSV upload. **No new runtime dependencies** (threading is stdlib; httpx/sqlalchemy already present).

## Technical Context

**Language/Version**: Python 3.11+ (inherited via `foundation`).

**Primary Dependencies** (all present): `harness.connector` (`dispatch_utterance`), `harness.evaluator` (`dispatch_evaluation`), `harness.persistence` (repositories + `get_session`), stdlib `threading`/`queue`. **No new deps.**

**Storage**: 009's DB (no new entity). One engine adjustment: `init_db`'s SQLite engine must allow cross-thread use (`connect_args={"check_same_thread": False}`) for the threaded workers — safe given WAL + `busy_timeout` already configured, single-process.

**Testing**: `pytest`. Per-row pipeline unit-tested with injected `httpx.MockTransport` clients; full job lifecycle (success/per-row-fail/cancel/orphan/concurrency/empty-store) as integration tests against the bundled mock connector (007) + mock evaluator (008) over real localhost servers + the `db_session`/file DB.

**Target Platform**: Single-process harness (Flask + CLI). Workers are daemon threads.

**Performance Goals**: Async start (`enqueue` returns immediately); orphan reconciliation < 5s at startup; concurrent jobs; rows serial within a job.

**Constraints**: No retries (FR-013); per-row failure isolation (FR-012); password evicted immediately after the connector call (FR-011 step 3, SC-008); password store empty for a job at terminal (FR-016, SC-009); plaintext credentials never logged (SC-012); terminal status only in the canonical enum (FR-018, SC-011).

## Constitution Check

Unfilled template — GATE: PASS by vacuous quantification (same as prior modules).

## Project Structure

### Documentation (this feature)

```text
specs/012-job-execution-engine/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 (R1–R9)
├── data-model.md        # Phase 1 — per-row pipeline, snapshot mapping, worker/lifecycle, password store
├── quickstart.md        # Phase 1 — end-to-end run, per-row fail, cancel, orphan, concurrency
├── contracts/
│   └── engine-api.md              # run_job / enqueue_job / reconcile_orphans + password store
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (not created by this plan)
```

### Source Code

```text
src/
└── harness/
    ├── password_store.py         # in-memory (job_id, utterance_id)->password store (011 FR-015; 012 consumes)
    ├── orchestrator/
    │   ├── __init__.py           # Re-exports run_job, enqueue_job, reconcile_orphans
    │   ├── pipeline.py           # process_row(job_snapshot, utterance, *, clients) -> EvaluationResultCreateData (FR-011/012)
    │   └── engine.py             # run_job(job_id) [sync core], enqueue_job(job_id) [thread], reconcile_orphans() (FR-001/002/003/016/017/019/020)
    ├── persistence/engine.py     # (edit) check_same_thread=False for threaded workers
    └── bootstrap.py              # (edit) call reconcile_orphans() after init_db()

tests/
├── unit/
│   ├── test_password_store.py
│   └── orchestrator/
│       ├── __init__.py
│       └── test_pipeline.py      # per-row mapping: success, each errorStage, annotations, password evict (MockTransport)
└── integration/
    └── test_orchestrator_e2e.py  # US1 success, US2 per-row fail, US3 cancel, US4 orphan, US5 concurrency, US6 empty store
```

**Structure Decision**: `orchestrator/` with a pure `pipeline.process_row` (unit-testable via injected clients) and an `engine` that owns the per-job loop, threading, and lifecycle transitions. The password store is a standalone module (shared with 011). `reconcile_orphans()` is wired into `bootstrap.initialize_harness`.

## FR → File Coverage Matrix

| FR | Implementation file | Verifying test |
|---|---|---|
| `FR-001` (async start) | `orchestrator/engine.py::enqueue_job` (daemon thread) | `integration/test_orchestrator_e2e.py::test_enqueue_returns_immediately` |
| `FR-002` (orphan reconciliation < 5s) | `engine.py::reconcile_orphans` + `bootstrap.py` | `test_orchestrator_e2e.py::test_orphan_reconciled` (US4) |
| `FR-003` (pick up queued → running) | `engine.py::run_job` | `test_orchestrator_e2e.py::test_full_run` |
| `FR-004` (read snapshot, not registry) | `engine.py` (builds snapshots from Job) | `test_pipeline.py` |
| `FR-005` (JIT credential decrypt) | reused — `dispatch_utterance`/`dispatch_evaluation` decrypt | covered by 007/008 |
| `FR-006`–`FR-010`/`FR-015` (reserved — no instantiation/teardown) | (architectural — stateless) | n/a |
| `FR-011` (per-row pipeline) | `orchestrator/pipeline.py::process_row` | `unit/orchestrator/test_pipeline.py` |
| `FR-012` (per-row failure isolation + errorStage) | `pipeline.py` (maps 007/008 results) + `engine.py` (continue loop) | `test_pipeline.py::test_*_stage`; `test_orchestrator_e2e.py::test_per_row_failures` |
| `FR-013` (no retry) | `pipeline.py` (single dispatch each) | covered by 007/008 (no retry) |
| `FR-014` (atomic counter updates) | `engine.py` (per-row `get_session` txn: create + increment) | `test_orchestrator_e2e.py::test_counts` |
| `FR-016` (terminal `completed`) | `engine.py` (transition_to_completed + clear store) | `test_orchestrator_e2e.py::test_full_run`/`test_all_fail` |
| `FR-017` (empty-store → `failed`) | `engine.py` (pre-row store check) | `test_orchestrator_e2e.py::test_empty_store_fails` (US6) |
| `FR-018` (canonical enum only) | `engine.py` (uses JobRepository transitions only) | `test_orchestrator_e2e.py::test_status_enum` |
| `FR-019`/`FR-020` (soft-cancel sequence) | `engine.py` (cancel check at row boundary → `transition_to_cancelled`) | `test_orchestrator_e2e.py::test_cancel` (US3) |
| `FR-021` (post-completed cancel refused) | reused — `JobRepository.transition_to_cancelled` raises `InvalidTransitionError` | `test_orchestrator_e2e.py` |
| `FR-022`–`FR-024` (concurrency isolation) | `engine.py` (one thread per job; store keyed by (job_id,utterance_id)) | `test_orchestrator_e2e.py::test_concurrent_jobs` (US5) |

## SC Verification Matrix

| SC | Verification path |
|---|---|
| `SC-001` | `test_orchestrator_e2e.py::test_full_run` (N connector + N evaluator POSTs, counts, store empty) |
| `SC-002`/`SC-003` | `test_orchestrator_e2e.py::test_per_row_failures` / `test_all_rows_fail` (terminal `completed`) |
| `SC-004` | `test_orchestrator_e2e.py::test_cancel` (running→cancelling→cancelled + stubs) |
| `SC-005` | `test_orchestrator_e2e.py::test_orphan_reconciled` (within 5s, none left running) |
| `SC-006` | `test_orchestrator_e2e.py::test_empty_store_fails` |
| `SC-007` | `test_orchestrator_e2e.py::test_concurrent_jobs` |
| `SC-008` | `test_pipeline.py::test_password_evicted_after_connector_call` |
| `SC-009` | `test_orchestrator_e2e.py` (probe store empty at terminal) |
| `SC-010` | `test_orchestrator_e2e.py` (one EvaluationResult per attempted Utterance) |
| `SC-011` | `test_orchestrator_e2e.py::test_status_enum` |
| `SC-012` | reused — 007/008 never log the auth header; orchestrator adds no logging of it |

## Foundation Note

`012` is built on **`foundation`** (010+009+006+007+008+013+014, 265 tests). It is the integration capstone that exercises 006/007/008/009 together at runtime. Reuses everything; adds only the orchestrator package + the password store + a `reconcile_orphans` bootstrap hook + the `check_same_thread=False` engine tweak.

**Cross-module debt flagged:** the in-memory password store belongs to `011 FR-015`; since `011` is unbuilt, `012` introduces `harness.password_store` (the data structure + eviction discipline). When `011` lands, it populates this same store on CSV upload — no second store.

## Complexity Tracking

| Element | Justification |
|---|---|
| Threading-based workers (one daemon thread per job) | FR-001/022 require async start + concurrent jobs; threads are the simplest fit for sync httpx + SQLite in a single process (no asyncio rewrite of the clients) |
| `check_same_thread=False` on the SQLite engine | Required for per-thread sessions in the threaded workers; safe given WAL + busy_timeout + single-process |
| Introducing `harness.password_store` here | 011 (its spec owner) is unbuilt; 012 is the canonical consumer and needs it now; 011 will populate the same module later |
| Pure `process_row` separate from `engine` | Makes the per-row stage→errorStage mapping unit-testable via injected MockTransport clients, without threads or a live server |
