# Quickstart: CSV Upload & Validation Service (Module 8)

**Date**: 2026-06-04

## Prerequisites
```powershell
python -m pip install -e ".[dev]"
```

## 1. Run the module tests
```powershell
python -m pytest tests/unit/csv_upload/ tests/integration/test_csv_upload.py -v
```
Expect: parser unit tests (decode/BOM, RFC-4180, header/row validation) + integration (happy path, malformed rejections, non-draft gate, size gate, edge cases, replace-on-upload, password staging) all pass.

## 2. Service-call walkthrough
```python
from pathlib import Path
from harness.persistence import engine, get_session
from harness.persistence.repositories import JobRepository, UtteranceRepository
from harness import password_store
from harness.csv_upload import process_upload

engine.init_db("upload-demo.db")

# A draft job whose snapshotted connector requires per-row passwords.
with get_session() as s:
    job = JobRepository(s).create_draft("demo", None, "tester")
    job.connector_expects_per_row_password = True   # normally set via the connector snapshot
    job_id = job.job_id

Path("demo.csv").write_text(
    "utteranceText,testId,password\n"
    "hello,t1,pw1\n"
    "\"multi\nline\",t2,pw2\n",
    encoding="utf-8",
)

result = process_upload(job_id, "demo.csv")
print(result.success, result.utterances_created, result.distinct_test_ids, result.warnings)
# True 2 2 []

with get_session() as s:
    rows = UtteranceRepository(s).get_by_job_ordered(job_id)
    print([(r.row_index, r.test_id, r.utterance_text) for r in rows])
    # [(1, 't1', 'hello'), (2, 't2', 'multi\nline')]
    print(JobRepository(s).get(job_id).total_utterance_count)   # 2

# Passwords are in the in-memory store (never in the DB):
print(password_store.get(job_id, rows[0].utterance_id))         # 'pw1'
```

## 3. Validation failure (no side effects)
```python
Path("bad.csv").write_text("utteranceText,testId\nhello,\n", encoding="utf-8")  # empty testId, missing password col
result = process_upload(job_id, "bad.csv")
print(result.success)                       # False
for e in result.errors:
    print(e.category, e.row, e.column, e.message)
# missing_column None password ... ; empty_value 1 testId ...
```

## 4. Password never persisted (SC-005)
After uploading a CSV with a distinctive password (e.g. `DEADBEEF-PWD-12345`), grep the SQLite file:
```powershell
Select-String -Path upload-demo.db -Pattern "DEADBEEF-PWD-12345"   # zero matches
```

## 5. Replace-on-upload (SC-011)
Call `process_upload` twice on the same draft job with different files → the second fully replaces the first's rows and store entries (no `A.csv` traces remain).

## 6. Lint
```powershell
python -m ruff check src tests
```
