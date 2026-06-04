# Phase 1 Data Model: Job Execution Engine (Module 10)

**Date**: 2026-06-04
**Plan**: `specs/012-job-execution-engine/plan.md`

The orchestrator owns **no persistent entities** — it reads/writes existing 009 entities (`Job`, `Utterance`, `EvaluationResult`) and introduces one **in-memory** structure (the password store). This document defines the runtime data flows and mappings.

---

## 1. Persistent entities (owned by 009, consumed here)

| Entity | Role in the engine | Repo methods used |
|---|---|---|
| `Job` | lifecycle anchor; carries the immutable connector/evaluator **snapshots** (FR-004) + counters | `get`, `transition_to_running/completed/failed/cancelled`, `increment_processed_count`, `increment_failed_count`, `get_by_status` |
| `Utterance` | per-row input (test_id, utterance_text, expected_*) | `get_by_job_ordered` |
| `EvaluationResult` | one persisted row per processed utterance (success or failure) | `create` |

The engine **never** touches the registries (007/008 readers, 013/014 services) at runtime — only the Job snapshot (parent FR-023).

---

## 2. In-memory: Password Store (`harness.password_store`)

| Aspect | Value |
|---|---|
| Structure | `dict[(job_id: str, utterance_id: str), str]` guarded by `threading.Lock` |
| Scope | process-global; **lost on restart** (011 FR-015) |
| Producer | 011 (CSV upload) — *not yet built* |
| Consumer | 012 — `get` before connector call, `evict` immediately after |
| API | `put`, `get`, `evict`, `clear_job`, `job_has_entries` (see contract) |

No persistence, no encryption (plaintext, in-memory only, evicted per-row).

---

## 3. Snapshot → client-snapshot mapping (FR-004/005)

```
Job row                              ConnectorSnapshot (007)
  connector_id                  →      connector_id
  connector_endpoint_url        →      endpoint_url
  connector_auth_descriptor     →      auth_descriptor   (decrypted JIT in client)
  connector_timeout_seconds     →      timeout_seconds
  connector_expects_per_row_password → expects_per_row_password

Job row                              EvaluatorSnapshot (008)
  evaluation_agent_id           →      evaluation_agent_id
  evaluator_endpoint_url        →      endpoint_url
  evaluator_auth_descriptor     →      auth_descriptor
  evaluator_timeout_seconds     →      timeout_seconds
  evaluator_declared_scoring_dimensions → declared_scoring_dimensions
```

---

## 4. Per-row pipeline (`pipeline.process_row`)

```
for utterance in get_by_job_ordered(job_id):
    pw = password_store.get(job_id, utterance.utterance_id) if expects_per_row_password else None
    conn = dispatch_utterance(ConnectorSnapshot, UtteranceRow(... , password=pw))   # 007 validates + maps connector_* stages
    password_store.evict(job_id, utterance.utterance_id)                            # FR-011 step 3 (immediate)
    if conn.ok:
        ev = dispatch_evaluation(EvaluatorSnapshot, conn.contract)                  # 008 validates + maps evaluator_* + annotates
    → EvaluationResultCreateData (see §5)
    with get_session() as s:                                                        # one txn / row (FR-014)
        EvaluationResultRepository(s).create(data)
        JobRepository(s).increment_processed_count(job_id)
        if failed: JobRepository(s).increment_failed_count(job_id)
    if JobRepository.get(job_id).status == "cancelling": break                      # FR-019 row-boundary cancel
```

---

## 5. `ConnectorResult`/`EvaluatorResult` → `EvaluationResultCreateData`

| Field | connector failed | evaluator failed | success |
|---|---|---|---|
| `test_id` | utterance.test_id | utterance.test_id | utterance.test_id |
| `raw_chatbot_response` | `None` | `contract…rawPayload` | `contract…rawPayload` |
| `normalized_contract` | `None` | `contract` | `contract` |
| `evaluation_agent_id` | `job.evaluation_agent_id` | `job.evaluation_agent_id` | body `evaluationAgentId` |
| `evaluation_verdict` | `None` | `None` | body `evaluationVerdict` |
| `evaluation_scores` | `None` | `None` | body `evaluationScores` |
| `result_metadata` | `None` | `None` | body `metadata` |
| `harness_annotations` | `None` | `None` | `ev.harness_annotations` |
| `evaluation_timestamp` | now(UTC) | now(UTC) | parsed body `evaluationTimestamp` (fallback now) |
| `error_status` | `"failed"` | `"failed"` | `None` |
| `error_stage` | `conn.error_stage` | `ev.error_stage` | `None` |
| `error_details` | `conn.error_details` | `ev.error_details` | `None` |

`error_stage` values come from 009's `ERROR_STAGES` (connector_* / evaluator_* / contract_*), already assigned by 007/008.

---

## 6. Worker lifecycle (Job.status transitions driven here)

```
queued ──run_job──▶ running ──all rows ok/failed──▶ completed
   │                   │
   │                   ├── observes "cancelling" at row boundary ──▶ cancelled (009 stubs remaining rows)
   │                   └── unhandled engine error ──────────────────▶ failed
   └── pre-row: expects_per_row_password & empty store ─────────────▶ failed (US6 / FR-017, 0 rows)

reconcile_orphans() at bootstrap: running|cancelling (from prior process) ──▶ failed (FR-002)
```

`transition_to_*` are the 009 repo methods (state-machine-guarded; illegal transitions raise `InvalidTransitionError` → FR-021 race safety).

---

## 7. Validation rules

- Engine performs **no** schema validation — 007 owns contract validation, 008 owns EvaluationResult validation (FR-013, parent FR-006).
- Engine performs **no** retries (FR-013) — single-shot dispatch.
- A row failure never aborts the job (FR-012) — it persists a failed `EvaluationResult` and continues.
- An engine-level (non-row) exception → job `failed` (FR-016), surfaced via `error_details`.
