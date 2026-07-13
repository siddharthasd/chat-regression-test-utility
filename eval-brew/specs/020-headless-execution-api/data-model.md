# Data Model: Headless Execution API (020)

**Branch**: `020-headless-execution-api` | **Date**: 2026-07-12

---

## 1. Database Schema Changes

### 1.1 `job` Table — New Columns

New Alembic migration: `alembic/versions/<hash>_add_headless_job_fields.py`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `submission_source` | `VARCHAR(20)` | NOT NULL | `'wizard'` | `'wizard'` or `'api'`; existing rows get `'wizard'` |
| `source_system` | `VARCHAR(255)` | NULL | `NULL` | Caller identity (e.g. `'qual-brew'`) |
| `product_name` | `VARCHAR(255)` | NULL | `NULL` | Optional metadata from submission |
| `feature_name` | `VARCHAR(255)` | NULL | `NULL` | Optional metadata from submission |

**Migration**: `op.add_column` for each; `server_default=sa.text("'wizard'")` on `submission_source`. No data backfill required.

**SQLAlchemy model additions** (`src/harness/persistence/models/job.py`):

```python
submission_source: Mapped[str] = mapped_column(String(20), nullable=False, default="wizard")
source_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
feature_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### 1.2 `job` Table — No Structural Changes to Existing Columns

The existing status state machine (`draft → queued → running → cancelling → completed / failed / cancelled`) already supports the full headless job lifecycle. The `cancelled` terminal state is already present. No changes to the status column or constraints.

### 1.3 `utterance` Table — No Changes

Headless test cases map directly to existing `utterance` rows:

| JSON field | `utterance` column |
|---|---|
| `id` | `test_id` |
| `input_message` | `utterance_text` |
| submission index (0-based) | `row_index` |
| any additional keys | `extra_metadata` (JSON) |

---

## 2. New `JobRepository` Methods

**File**: `src/harness/persistence/repositories/job.py`

```python
def count_headless_non_terminal_by_user(self, owner_id: str) -> int:
    """Returns the number of API-submitted jobs in non-terminal state for the given user."""

def list_headless_non_terminal_by_user(self, owner_id: str) -> list[Job]:
    """Returns API-submitted jobs in non-terminal state for the given user (for diagnostics)."""
```

Terminal states for the query filter: `{completed, failed, cancelled}`.

---

## 3. Pydantic Schemas

**File**: `src/harness/ui/api/schemas.py`

### 3.1 Request — Job Submission

```python
class HeadlessTestCase(BaseModel):
    id: str                        # caller-assigned; non-empty; unique within submission
    input_message: str             # non-empty; maps to utterance_text
    model_config = ConfigDict(extra="allow")  # extra keys → extra_metadata

class HeadlessJobSubmission(BaseModel):
    test_cases: list[HeadlessTestCase]  # 1–100 items
    connector_id: str
    evaluator_id: str
    source_system: str | None = None
    product_name: str | None = None
    feature_name: str | None = None
```

**Validation rules (enforced in service layer, not Pydantic):**
- `len(test_cases)` ≤ 100; else HTTP 422 with `{"detail": "...", "submitted": N, "limit": 100}`
- `test_case.input_message` non-empty; else HTTP 422 identifying offending `id`
- `test_case.id` unique within submission; else HTTP 422 identifying duplicated value
- `connector_id` must reference an active connector; else HTTP 404
- `evaluator_id` must reference an active evaluator; else HTTP 404
- If selected connector has `expects_per_row_password=True`: HTTP 422 (not supported in v1)
- User's non-terminal headless job count < 2; else HTTP 429

### 3.2 Response — Job Submission

```python
class HeadlessJobSubmissionResponse(BaseModel):
    job_id: str
    stream_url: str    # relative path: /api/headless/jobs/{job_id}/stream
    result_url: str    # relative path: /api/headless/jobs/{job_id}/result
```

### 3.3 Response — Failed Case

```python
class FailedCase(BaseModel):
    id: str           # caller-assigned test_id
    input_message: str
```

### 3.4 Response — Job Summary

```python
class JobSummary(BaseModel):
    total: int
    passed: int
    failed: int
    top_failures: list[FailedCase]  # up to first 5 failures in execution order
```

### 3.5 Response — Job Result (re-fetch endpoint)

```python
class HeadlessJobResult(BaseModel):
    job_id: str
    status: str                          # "completed" | "failed" | "cancelled" | "in_progress"
    results_url: str | None = None       # present only when status == "completed"
    summary: JobSummary | None = None    # present when status in {completed, failed, cancelled}
```

### 3.6 Response — Connector Discovery

```python
class ConnectorListItem(BaseModel):
    id: str
    name: str
    description: str
```

### 3.7 Response — Evaluator Discovery

```python
class EvaluatorListItem(BaseModel):
    id: str
    name: str
    description: str
    scoring_dimensions: list[str]   # from declared_scoring_dimensions
```

---

## 4. SSE Event Contract

**Media type**: `text/event-stream`  
**Format per event**: `event: {type}\ndata: {json}\n\n`  
**Auth**: `Authorization: Bearer <token>` header on the stream request (same as all other headless endpoints)

### Event Sequence for a Successful Job

```
event: job_started
data: {}

event: progress
data: {"cases_completed": 1, "cases_failed": 0}

event: progress
data: {"cases_completed": 2, "cases_failed": 0}

... (one progress event per test case evaluated)

event: job_complete
data: {
  "results_url": "/jobs/{job_id}",
  "summary": {
    "total": 10, "passed": 9, "failed": 1,
    "top_failures": [{"id": "tc-003", "input_message": "..."}]
  }
}
```

### Event Sequence for a Failed Job

```
event: job_started
data: {}

event: progress
data: {"cases_completed": 3, "cases_failed": 1}

event: job_failed
data: {
  "error": "Connector timed out after 30 seconds",
  "summary": {
    "total": 10, "passed": 2, "failed": 1,
    "top_failures": [{"id": "tc-002", "input_message": "..."}]
  }
}
```

### Event Sequence for a Cancelled Job

```
event: job_started
data: {}

event: progress
data: {"cases_completed": 5, "cases_failed": 0}

event: job_failed
data: {
  "error": "Job cancelled by user",
  "summary": {"total": 10, "passed": 5, "failed": 0, "top_failures": []}
}
```

### Late-Connect Replay

When the SSE stream endpoint is called for a job that has already reached a terminal state, the full event sequence (including the terminal event) is replayed from the in-memory buffer and the stream closes. The caller receives the complete history regardless of when it connects.

---

## 5. HeadlessJobEventBus

**File**: `src/harness/ui/api/job_event_bus.py`

**Lifecycle**:
1. Created by the headless service immediately after job submission succeeds.
2. Registered in the module-level `_buses: dict[str, HeadlessJobEventBus]` dict.
3. The engine pushes events via `loop.call_soon_threadsafe(bus.push, event_type, payload)` from the sync engine thread.
4. The stream endpoint calls `bus.stream(cursor=0)` and yields events to the client.
5. After the terminal event is pushed, `bus._closed = True`. The stream generator exits when closed and cursor has passed all events.
6. The bus is removed from `_buses` once the last stream consumer has received the terminal event (or after a configurable cleanup delay, e.g. 1 hour).

**Module-level interface**:
- `create_bus(job_id: str) -> HeadlessJobEventBus`
- `get_bus(job_id: str) -> HeadlessJobEventBus | None`
- `remove_bus(job_id: str) -> None`

---

## 6. Engine Modification

**File**: `src/harness/orchestrator/engine.py`

**Change**: Add `progress_callback: Callable[[str, int, int], None] | None = None` to `enqueue_job()` signature. Thread the parameter through to `run_job()`. Inside `run_job()`, call `progress_callback(job_id, processed_count, failed_count)` after each row completes (pass or fail). Add a `job_started_callback` and `job_terminal_callback` at the corresponding state transitions.

**Compatibility**: All existing call sites use `enqueue_job(job_id)` with no keyword arguments. The new parameters are keyword-only with default `None`. No existing call sites require modification.

---

## 7. Dashboard View Changes

**File**: `src/harness/ui/dashboard/view.py`

Additional fields added to `row_view()` output dict:

| Key | Value |
|---|---|
| `submission_source` | `"wizard"` or `"api"` |
| `source_label` | `"API"` when source is `"api"`, else `None` |
| `source_system` | value or `None` |
| `product_name` | value or `None` |
| `feature_name` | value or `None` |
| `has_report` | `True` only when status is `"completed"` (existing `terminal` flag already handles this but report link visibility now also depends on status) |
