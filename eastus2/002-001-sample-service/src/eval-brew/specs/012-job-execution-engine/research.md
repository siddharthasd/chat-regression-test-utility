# Phase 0 Research: Job Execution Engine (Module 10)

**Date**: 2026-06-04
**Plan**: `specs/012-job-execution-engine/plan.md`
**Spec**: `specs/012-job-execution-engine/spec.md`

Resolves the plan-level decisions. Built on `foundation` (010+009+006+007+008+013+014).

---

## R1: Async / Concurrency Model

**Decision**: **One daemon `threading.Thread` per Job** (`enqueue_job` spawns it and returns immediately → async start, FR-001). Rows within a job are processed serially by that thread (FR-023); multiple jobs = multiple threads (FR-022). A module-level `threading.BoundedSemaphore` caps concurrent jobs (plan default 4); excess stays `queued`. The testable core, `run_job(job_id)`, is **synchronous** (tests call it directly, no thread).

**Rationale**: 007/008's HTTP clients are sync `httpx`; threads fit without rewriting them to asyncio. Single-process harness; SQLite + WAL handle concurrent writers.

**Alternatives**: asyncio (would force async httpx clients — large rewrite); a separate worker process (overkill for single-user). Rejected.

---

## R2: SQLite Across Threads

**Decision**: Set `connect_args={"check_same_thread": False}` on `init_db`'s engine so per-thread `get_session()` sessions can use pooled connections. WAL + `foreign_keys=ON` + `synchronous=NORMAL` + `busy_timeout=5000` (already configured in 009) make concurrent writers safe; each row's write is a short transaction.

**Rationale**: pysqlite forbids cross-thread connection use by default; the harness is single-process so disabling the guard is safe and is the standard SQLAlchemy approach for threaded SQLite.

---

## R3: Per-Row Pipeline — Reuse 007/008

**Decision**: `pipeline.process_row` runs: (1) password lookup (if `expects_per_row_password`); (2) `harness.connector.dispatch_utterance(ConnectorSnapshot, UtteranceRow)` — **already** validates the contract + maps `connector_*` stages; (3) evict the password immediately (FR-011 step 3); (4) if connector ok, `harness.evaluator.dispatch_evaluation(EvaluatorSnapshot, contract)` — **already** validates the EvaluationResult + maps `evaluator_*` stages + computes `harness_annotations`; (5) assemble one `EvaluationResultCreateData`. The orchestrator does **not** re-validate (007/008 own that) and **never retries** (FR-013 — the clients are single-shot).

**Rationale**: The reshape pushed validation/error-mapping into the framework modules; the orchestrator is glue. This keeps `process_row` small and the error taxonomy single-sourced.

---

## R4: Snapshot → Client-Snapshot Mapping (FR-004)

**Decision**: Build the client snapshots directly from the Job ORM row:
- `ConnectorSnapshot(connector_id, endpoint_url=job.connector_endpoint_url, auth_descriptor=job.connector_auth_descriptor, timeout_seconds=job.connector_timeout_seconds, expects_per_row_password=job.connector_expects_per_row_password)`
- `EvaluatorSnapshot(evaluation_agent_id, endpoint_url=job.evaluator_endpoint_url, auth_descriptor=job.evaluator_auth_descriptor, timeout_seconds=job.evaluator_timeout_seconds, declared_scoring_dimensions=job.evaluator_declared_scoring_dimensions)`

The registry is never consulted at runtime (parent FR-023). Credentials decrypt just-in-time inside the dispatch functions (007/008 reuse 009 encryption, FR-005).

---

## R5: EvaluationResult Assembly

**Decision** (maps `ConnectorResult`/`EvaluatorResult` → `EvaluationResultCreateData`, per 009 FR-003):
- **connector failed**: `error_status="failed"`, `error_stage=conn.error_stage`, `error_details`, `raw_chatbot_response=None`, `normalized_contract=None`, evaluation fields `None`, `evaluation_agent_id=job.evaluation_agent_id` (snapshot — never null on persisted rows), `evaluation_timestamp=now`.
- **evaluator failed**: `normalized_contract=contract`, `raw_chatbot_response=contract.chatbotResponse.rawPayload`, `error_status="failed"`, `error_stage=eval.error_stage`, `error_details`, evaluation fields `None`, `evaluation_agent_id=job.evaluation_agent_id`, `evaluation_timestamp=now`.
- **success**: `normalized_contract=contract`, `raw_chatbot_response=…rawPayload`, `evaluation_verdict/evaluation_scores/result_metadata/evaluation_agent_id` from the EvaluationResult body, `harness_annotations=eval.harness_annotations`, `evaluation_timestamp=` parsed from the body's `evaluationTimestamp` (ISO → datetime; fallback now), `error_*=None`.
- `test_id` from the Utterance; `result_id` auto-assigned by the repo.

---

## R6: Cancellation (FR-019/020)

**Decision**: The worker re-reads `Job.status` at each row boundary. When it observes `cancelling` (set externally by 004's Cancel → `JobRepository.transition_to_cancelling`), it finishes the in-flight row normally, stops the loop, and calls `JobRepository.transition_to_cancelled(job_id)` — which **already** creates `cancelled` stubs for un-processed Utterances (009 FR-003a) atomically — then clears the password store for the job. A cancel racing a completed transition is refused by `transition_to_cancelled` raising `InvalidTransitionError` (FR-021).

---

## R7: Orphan Reconciliation (FR-002)

**Decision**: `reconcile_orphans()` calls `JobRepository.get_by_status("running")` + `("cancelling")` and `transition_to_failed(job_id, "harness restarted while job was running…")` for each (sets `completed_at` + `error_details`). Wired into `bootstrap.initialize_harness` after `init_db()`, before any other work. No stub creation for orphaned `cancelling` jobs (they go to `failed`, not `cancelled`). Password store is process-scoped (empty after restart) — nothing to clear.

---

## R8: In-Memory Password Store (011 FR-015, introduced here)

**Decision**: `harness.password_store` — a process-global dict `{(job_id, utterance_id): password}` guarded by a `threading.Lock`:
```python
put(job_id, utterance_id, password) -> None
get(job_id, utterance_id) -> str | None
evict(job_id, utterance_id) -> None
clear_job(job_id) -> None
job_has_entries(job_id) -> bool
```
Process-scoped (lost on restart, per 011 FR-015). `012` consumes it; `011` will populate it on CSV upload. Keyed by `(job_id, utterance_id)` for cross-job isolation (FR-022).

---

## R9: Pre-Row Empty-Store Failure (US6 / FR-017) & Atomicity

**Decision**: Before the loop, if `job.connector_expects_per_row_password` and `not job_has_entries(job_id)` → `transition_to_failed(job_id, "credentials no longer in memory — re-upload CSV via a new job")`, no rows attempted. Otherwise loop. Each row's `EvaluationResult` create + `increment_processed_count` (+ `increment_failed_count` on failure) happen in **one** `get_session()` transaction (FR-014/020 atomicity). No new deps.

---

*All deferred decisions resolved. Implementation can proceed directly.*
