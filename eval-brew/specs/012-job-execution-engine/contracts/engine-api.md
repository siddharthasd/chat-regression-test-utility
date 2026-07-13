# Contract: Job Execution Engine Public API (Module 10)

**Date**: 2026-06-04
Consumers: 004 (job control UI — enqueue/cancel), 011 (CSV upload populates the password store then enqueues), `bootstrap` (orphan reconciliation).

---

## `harness.orchestrator`

### `run_job(job_id: str) -> None`
Synchronous, single-threaded execution of one job. **The testable core.**
- Pre: Job exists in `queued` (or `running` when re-entered by a worker thread).
- Transitions Job `queued → running` (`transition_to_running`), processes every Utterance in order via `pipeline.process_row`, then `running → completed`.
- Pre-row gate: if `connector_expects_per_row_password` and `not password_store.job_has_entries(job_id)` → `transition_to_failed(...)`, return (0 rows) — FR-017.
- Cancellation: when it observes `cancelling` at a row boundary → `transition_to_cancelled(job_id)` (009 stubs the remainder) + `password_store.clear_job(job_id)`, return — FR-019/020.
- On any unhandled exception → `transition_to_failed(job_id, repr(exc))`, re-raise suppressed (logged) — FR-016.
- Idempotent counters: `increment_processed_count` / `increment_failed_count` per row inside the row transaction.

### `enqueue_job(job_id: str) -> None`
Asynchronous start (FR-001).
- Acquires a slot on the module `BoundedSemaphore` (default 4 concurrent jobs); if none free the job stays `queued` until a slot frees.
- Spawns a `threading.Thread(target=run_job, args=(job_id,), daemon=True)` and returns immediately (does not block the caller / UI request).
- Releases the slot in a `finally` around `run_job`.

### `reconcile_orphans() -> None`
Startup recovery (FR-002).
- For every Job in `running` or `cancelling` (left by a prior crashed/stopped process), `transition_to_failed(job_id, "harness restarted while job was in progress")`.
- Idempotent; completes in <5s for realistic backlogs. Called by `bootstrap.initialize_harness` immediately after `init_db()`.

---

## `harness.password_store`

Process-global, thread-safe, in-memory. No persistence (011 FR-015).

| Function | Signature | Behavior |
|---|---|---|
| `put` | `(job_id, utterance_id, password) -> None` | store/overwrite the plaintext password for a row |
| `get` | `(job_id, utterance_id) -> str \| None` | return password or `None` if absent |
| `evict` | `(job_id, utterance_id) -> None` | delete one entry (no-op if absent) — called immediately after the connector call |
| `clear_job` | `(job_id) -> None` | delete all entries for a job (cancellation / completion cleanup) |
| `job_has_entries` | `(job_id) -> bool` | True iff any entry exists for the job (pre-row gate) |

All mutations hold a module `threading.Lock`.

---

## Engine edits to existing modules

| File | Edit | Why |
|---|---|---|
| `persistence/engine.py` | `connect_args={"check_same_thread": False}` on `create_engine` | threaded workers share the pooled SQLite connection (R2) |
| `bootstrap.py` | call `reconcile_orphans()` after `init_db()` | FR-002 |

---

## Error & verdict semantics (delegated)

The engine assigns **no** verdicts and maps **no** error stages itself — it copies `error_stage`/`error_details` from `ConnectorResult`/`EvaluatorResult` (007/008) and `evaluation_verdict`/`evaluation_scores`/`harness_annotations` from the validated EvaluationResult body. The `ERROR_STAGES` enum (009) is the single taxonomy. No retries (FR-013).
