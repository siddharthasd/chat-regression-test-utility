# Quickstart: Job Execution Engine (Module 10)

**Date**: 2026-06-04
Validates the end-to-end pipeline against the bundled 007 connector mock + 008 evaluator mock.

## Prerequisites
```powershell
python -m pip install -e ".[dev]"
```

## 1. Run the orchestrator unit + integration tests
```powershell
python -m pytest tests/unit/test_password_store.py tests/unit/orchestrator/ tests/integration/test_orchestrator_e2e.py -v
```
Expect: password-store lifecycle, `process_row` mapping (success / connector-fail / evaluator-fail), full `run_job` over a multi-row job, cancellation at a row boundary, orphan reconciliation, and the empty-store pre-row failure all pass.

## 2. End-to-end against mock services (manual)
```python
from harness.connector import mock as conn_mock
from harness.evaluator import mock as ev_mock
from harness.persistence import engine, get_session
from harness.persistence.repositories import JobRepository, UtteranceRepository, EvaluationResultRepository
from harness import password_store
from harness.orchestrator import run_job

engine.init_db("e2e.db")
conn = conn_mock.make_server(mode="ok"); conn.start()       # http://127.0.0.1:<port>
ev = ev_mock.make_server(); ev.start()

with get_session() as s:
    jobs, utts = JobRepository(s), UtteranceRepository(s)
    job = jobs.create_draft("e2e", connector_endpoint=conn.url, evaluator_endpoint=ev.url)  # + snapshots
    utts.bulk_create(job.job_id, [("t1", "hello"), ("t2", "bye")])
    job_id = job.job_id

run_job(job_id)   # synchronous

with get_session() as s:
    results = EvaluationResultRepository(s).get_by_job(job_id)
    job = JobRepository(s).get(job_id)
    print(job.status, job.processed_count, job.failed_count)   # completed 2 0
    for r in results:
        print(r.test_id, r.evaluation_verdict, r.error_stage)
```
Expect: `completed`, `processed_count == 2`, two `EvaluationResult` rows with verdicts and `error_stage is None`.

## 3. Failure path
Start the connector mock with `mode="status500"` → rows persist with `error_status="failed"`, `error_stage="connector_http_error"`, and the job still reaches `completed` (row failures don't abort — FR-012); `failed_count == 2`.

## 4. Cancellation
Set the job to `cancelling` (`JobRepository.transition_to_cancelling`) from another thread mid-run → `run_job` stops at the next row boundary, job ends `cancelled`, remaining utterances get `cancelled` stub rows, password store cleared for the job.

## 5. Orphan recovery
Leave a job in `running`, restart the process, call `reconcile_orphans()` (or just `bootstrap.initialize_harness`) → the job is `failed` with an explanatory `error_details`.

## 6. Lint
```powershell
python -m ruff check src tests
```
