# Quickstart: Data Model & Persistence Layer (Module 2)

**Date**: 2026-06-02
**Plan**: `specs/009-data-model-persistence/plan.md`

End-to-end verification of the `009` implementation. Organized by user story (US1–US5) with the automated test as the canonical pass signal and a manual SQL inspection path for forensic verification.

---

## Prerequisites

- `pip install -e .[dev]` (adds `sqlalchemy`, `alembic`, `cryptography` to the environment after this spec is implemented and `pyproject.toml` is updated).
- The `010` identity module is already installed (from the prior spec).
- Default DB location: `~/.harness/data.db` (created by `harness serve` or `init_db()` on first run).

---

## US1: Full job lifecycle through the persistence layer

### Automated test (canonical)

```bash
pytest tests/integration/test_lifecycle.py::test_full_lifecycle -v
```

Expected: PASS. Covers draft creation → snapshot → queued → running → EvaluationResult rows → completed; asserts exact row counts and counter values.

### Manual SQL inspection

```bash
# Ensure harness is NOT running (close any harness serve window)
python - <<'EOF'
from harness.persistence.engine import init_db
from harness.persistence.repositories import JobRepository
from sqlalchemy.orm import Session

engine = init_db()
with Session(engine) as sess:
    jobs = JobRepository(sess).get_by_status("completed")
    for j in jobs:
        print(f"job_id={j.job_id} status={j.status} processed={j.processed_count} failed={j.failed_count}")
EOF
```

Or via `sqlite3`:

```bash
sqlite3 ~/.harness/data.db "SELECT job_id, job_name, status, processed_count, failed_count, created_by FROM job ORDER BY created_at DESC LIMIT 5;"
```

*(Note: SQL column names are snake_case per SQLAlchemy's default mapping from camelCase Python attributes. Check `009`'s migration file for the exact DDL column names if the above query fails.)*

---

## US2: Snapshot immutability past draft

### Automated test (canonical)

```bash
pytest tests/unit/persistence/test_repositories/test_job_repository.py::test_immutability -v
```

### Manual verification

```bash
python - <<'EOF'
from harness.persistence.engine import init_db
from harness.persistence.repositories import JobRepository
from harness.persistence.exceptions import SnapshotImmutableError
from sqlalchemy.orm import Session

engine = init_db()
with Session(engine) as sess:
    with sess.begin():
        repo = JobRepository(sess)
        j = repo.create_draft("test job", None, "alice")
        repo.transition_to_queued(j.job_id)   # This will fail if no snapshot set yet

    # Attempting to overwrite connector_endpoint_url after queued should raise
    with sess.begin():
        try:
            repo.set_connector_snapshot(j.job_id, None)
            print("ERROR: should have raised SnapshotImmutableError")
        except SnapshotImmutableError:
            print("PASS: SnapshotImmutableError raised correctly")
EOF
```

---

## US3: Cascade delete + status-gated delete

### Automated test (canonical)

```bash
pytest tests/integration/test_cascade_delete.py -v
```

### Manual verification

```bash
sqlite3 ~/.harness/data.db "
SELECT j.job_id, COUNT(u.utterance_id) AS utterances, COUNT(e.result_id) AS results
FROM job j
LEFT JOIN utterance u ON u.job_id = j.job_id
LEFT JOIN evaluation_result e ON e.utterance_id = u.utterance_id
GROUP BY j.job_id LIMIT 10;
"
```

After deleting a job: the same query should show no rows for that `job_id`, and the utterance/result tables should have no orphaned rows.

---

## US4: Restart with consistent persisted state / migration gating

### Migration startup (automated, canonical)

```bash
pytest tests/integration/test_migrations.py -v
```

### DB-too-new error (manual)

```bash
# Manually set the alembic_version to a future revision
sqlite3 ~/.harness/data.db "UPDATE alembic_version SET version_num = '9999_future_revision';"

# Now try to start the harness — it should refuse:
harness serve
# Expected: error message "database newer than this harness version; upgrade harness"
```

Restore after verifying:

```bash
sqlite3 ~/.harness/data.db "UPDATE alembic_version SET version_num = '<current-head>';"
```

*(Retrieve the current head: `alembic heads` from the repo root.)*

---

## US5: Schema version migration across harness upgrades

### Automated (canonical)

```bash
pytest tests/integration/test_migrations.py::test_partial_migration_rollback -v
pytest tests/integration/test_migrations.py::test_startup_migration_applies_pending -v
```

### Manual fresh-install verification

```bash
# Move aside the existing DB
mv ~/.harness/data.db ~/.harness/data.db.bak

# First launch: DB should be created from scratch and fully migrated
harness info
# Then:
sqlite3 ~/.harness/data.db ".tables"
# Expected: job utterance evaluation_result connector_registration evaluation_agent_registration alembic_version
```

---

## Encryption spot-check

### Automated (canonical)

```bash
pytest tests/unit/persistence/test_encryption.py -v
```

### Manual credential-in-db check

```bash
# Insert a registration with a known-distinctive token via the application layer:
python - <<'EOF'
from harness.persistence.engine import init_db
from harness.persistence.repositories import ConnectorRegistrationRepository
from sqlalchemy.orm import Session

engine = init_db()
with Session(engine) as sess:
    with sess.begin():
        repo = ConnectorRegistrationRepository(sess)
        reg = repo.create(dict(
            display_name="Test connector",
            endpoint_url="http://localhost:9000",
            auth_descriptor={"mode": "bearer", "credential": "DEADBEEF-TOKEN-12345"},
            timeout_seconds=30,
            expects_per_row_password=False,
        ))
        print(f"connector_id={reg.connector_id}")
EOF

# Grep the DB file for the plaintext token — must produce zero matches:
python -c "
import sys
data = open(r'~/.harness/data.db', 'rb').read()
assert b'DEADBEEF-TOKEN-12345' not in data, 'TOKEN LEAKED TO DB!'
print('PASS: token not in DB plaintext')
".replace('~', __import__('os').path.expanduser('~'))
```

Cross-platform (PowerShell):

```powershell
$data = [System.IO.File]::ReadAllBytes("$env:USERPROFILE\.harness\data.db")
$token = [System.Text.Encoding]::UTF8.GetBytes("DEADBEEF-TOKEN-12345")
$found = [System.Linq.Enumerable]::Contains($data, $token[0])  # rough; pytest is canonical
if ($found) { Write-Error "TOKEN LEAKED" } else { Write-Host "PASS" }
```

---

## Pass criteria

All automated tests pass:

```bash
pytest tests/unit/persistence tests/integration/test_lifecycle.py tests/integration/test_migrations.py tests/integration/test_cascade_delete.py -v
```

All five user stories verified end-to-end. Encryption spot-check confirms zero plaintext credential bytes in the DB file. Migration gating refuses start for a DB-too-new scenario.
