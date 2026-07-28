# Research: Headless Execution API (020)

**Branch**: `020-headless-execution-api` | **Date**: 2026-07-12

---

## Decision 1 — Bearer JWT Validation Library

**Decision**: Use `PyJWT` + `cryptography` for Azure AD Bearer token validation.

**Rationale**: The existing codebase uses MSAL for the Authorization Code + PKCE browser flow. MSAL does not expose a standalone token-validation path suitable for an API middleware dependency. `PyJWT` with the Azure AD JWKS endpoint is the standard, lightweight approach for server-side Bearer validation:

1. At application startup, fetch the tenant's JWKS document from `https://login.microsoftonline.com/{HARNESS_AZURE_TENANT_ID}/discovery/v2.0/keys`.
2. Cache the `PyJWKClient` instance as an application-level singleton.
3. Per request: decode the `Authorization: Bearer <token>` header value using `PyJWKClient.get_signing_key_from_jwt()` → `jwt.decode(algorithms=["RS256"], audience=HARNESS_AZURE_CLIENT_ID)`.
4. Extract `oid` (object ID) and `preferred_username` / `email` from decoded claims; construct a user identity dict matching the existing session user structure.

**Alternatives considered**:
- `azure-identity` SDK — validates credentials for acquiring tokens, not for validating incoming tokens from external callers. Incorrect tool for this use case.
- MSAL `validate_token()` — available on `PublicClientApplication` but not designed for server-side middleware and lacks async support.
- `python-jose` — functionally equivalent to `PyJWT` but less actively maintained.

**New env vars required**: None. `HARNESS_AZURE_TENANT_ID` and `HARNESS_AZURE_CLIENT_ID` are already required when `HARNESS_AUTH_ENABLED=true`. The Bearer auth dependency reuses them.

**JWKS caching**: `PyJWKClient` handles key caching and automatic refresh on key rotation. No additional caching layer required.

---

## Decision 2 — SSE Event Bus Architecture

**Decision**: Introduce a `HeadlessJobEventBus` class in `src/harness/ui/api/job_event_bus.py`, mirroring the pattern established in `src/harness/chat/event_bus.py`.

**Rationale**: The execution engine runs on synchronous daemon threads (via `threading.Thread`). The SSE stream endpoint runs in the async FastAPI/uvicorn event loop. These two execution contexts must communicate. The chat event bus already solves this problem for chat turns via an ordered in-memory event buffer plus `asyncio.Event` signaling.

**Design**:

```python
class HeadlessJobEventBus:
    def __init__(self):
        self._events: list[dict] = []    # ordered; never evicted
        self._ready = asyncio.Event()    # signals new event to async consumers
        self._closed = False             # True after terminal event

    def push(self, event_type: str, payload: dict) -> None:
        """Called from the sync engine thread via loop.call_soon_threadsafe()."""
        self._events.append({"event": event_type, "data": payload})
        self._ready.set()
        if event_type in ("job_complete", "job_failed"):
            self._closed = True

    async def stream(self, cursor: int = 0) -> AsyncIterator[dict]:
        """Yields events from cursor onward; waits for new events if bus not closed."""
        while True:
            while cursor < len(self._events):
                yield self._events[cursor]
                cursor += 1
            if self._closed:
                return
            self._ready.clear()
            await self._ready.wait()
```

A global `dict[str, HeadlessJobEventBus]` (keyed by `job_id`) lives in `job_event_bus.py`. The bus is created at job submission time and removed after the stream endpoint delivers the terminal event to all consumers.

**Late-connect replay**: Because `_events` is never evicted, a client that connects after the job completes receives the full event sequence from cursor=0, including the terminal event, and the stream closes normally.

**Thread safety for `push()`**: Called via `loop.call_soon_threadsafe(bus.push, event_type, payload)` from the engine thread. `asyncio.Event.set()` is not thread-safe in all Python versions; wrapping in `call_soon_threadsafe` is the correct pattern.

**Alternatives considered**:
- Redis pub/sub — overcomplicated for a LAN single-process deployment.
- `asyncio.Queue` — simpler for single-consumer but doesn't support the late-connect replay requirement without an additional replay buffer.
- `sse-starlette` library — adds a dependency for what amounts to a thin wrapper; the existing codebase uses raw `StreamingResponse` which is already proven.

---

## Decision 3 — Engine Progress Callback Design

**Decision**: Add an optional `progress_callback: Callable[[str, int, int], None] | None = None` parameter to `enqueue_job()`. Pass it through to `run_job()`, which calls it after each successful or failed `_process_one()` with signature `callback(job_id, processed_count, failed_count)`.

**Rationale**: The engine's `run_job()` already increments `job.processed_count` and `job.failed_count` after each row. Adding a callback at the same boundary is the minimal-invasive approach: one new `if callback:` guard after the existing count increment. No refactoring of the engine's internal logic is required.

**Call site (in headless service)**:

```python
loop = asyncio.get_event_loop()

def _progress_hook(job_id: str, processed: int, failed: int) -> None:
    bus = get_bus(job_id)
    if bus:
        loop.call_soon_threadsafe(
            bus.push, "progress", {"cases_completed": processed, "cases_failed": failed}
        )

enqueue_job(job_id, progress_callback=_progress_hook)
```

`job_started` is emitted by the headless service just before calling `enqueue_job()` (or via a second hook when the engine transitions to `running` state). `job_complete` / `job_failed` are emitted from a job-completion hook added to the engine's terminal-state transitions.

**Existing call sites**: `enqueue_job(job_id)` — the new parameter defaults to `None`, so all existing call sites (wizard `start` route) are unaffected.

**Alternatives considered**:
- Observer/event pattern on the `Job` ORM model — too heavy; requires rewriting the engine's internal state management.
- Polling from the SSE route — defeats the purpose of a push-based event bus and would produce coarser progress updates.

---

## Decision 4 — In-flight Job Limit Enforcement

**Decision**: Enforce the 2-job-per-user non-terminal limit via a DB count query at submission time. No in-memory counter.

**Rationale**: A DB query is authoritative across multiple Gunicorn worker processes (multi-worker deployment). An in-memory dict would be per-process and could allow a user to exceed the limit by hitting different workers. The count query is cheap: indexed on `created_by` + `submission_source` + `status`.

**New `JobRepository` method**:

```python
def count_headless_non_terminal_by_user(self, owner_id: str) -> int:
    terminal = {JobStatus.completed, JobStatus.failed, JobStatus.cancelled}
    return self._session.scalar(
        select(func.count(Job.job_id)).where(
            Job.submission_source == "api",
            Job.created_by == owner_id,
            Job.status.not_in(terminal),
        )
    )
```

Called at the start of the job submission handler, before any job record is created. If count ≥ 2, return HTTP 429 with body `{"detail": "2 headless jobs already in flight. Wait for one to complete before resubmitting.", "in_flight": 2}`.

**Alternatives considered**:
- `asyncio.Semaphore` per user — in-memory, per-process; doesn't survive worker restarts or multi-process deployments.
- Redis counter — overcomplicated for the deployment scale.

---

## Decision 5 — JSON Test Case to Utterance Mapping

**Decision**: Map headless JSON test cases directly to `Utterance` rows, bypassing `csv_upload/service.py`. Call `UtteranceRepository.bulk_create()` directly from the headless service.

**Rationale**: The `process_upload()` service in `csv_upload/service.py` is tightly coupled to file-based CSV parsing (file path, size check, BOM stripping, CSV column parsing). The headless submission already has validated, structured data. The correct integration point is `UtteranceRepository.bulk_create()`, which the CSV service also calls.

**Field mapping**:

| Headless JSON field | `Utterance` column | Notes |
|---|---|---|
| `id` | `test_id` | Caller-assigned; uniqueness enforced at submission validation |
| `input_message` | `utterance_text` | Non-empty; enforced at submission validation |
| submission index | `row_index` | 0-based position in the submitted array |
| extra fields (any additional keys) | `extra_metadata` (JSON) | Passed through as-is |

No `password` field in v1. The `connector_expects_per_row_password` check is performed at submission validation; if the selected connector requires per-row passwords, the submission is rejected with HTTP 422 (not supported by headless API in v1).

---

## Decision 6 — New API Router Prefix

**Decision**: Prefix `/api/headless` (not `/api/v1/headless`).

**Rationale**: eval-brew has no existing `/api/` prefix for any routes. Adding a versioned prefix now creates a convention that doesn't exist and may be confusing. The spec uses `/api/headless/` throughout. When versioning becomes necessary, the prefix can be changed in one place (`create_api_router()`). The `source_system` field in the submission payload identifies the caller version independently.

**Alternatives considered**:
- `/api/v1/headless` — premature versioning; no other API routes exist to be consistent with.
- `/headless` — too flat; doesn't signal "API" vs "UI" routes.

---

## Decision 7 — Dashboard Source Label Display

**Decision**: Add a `submission_source` column to the `job` table (values: `'wizard'` | `'api'`). Surface it in `row_view()` as `source_label`. When `source_label == 'api'` and `product_name` or `feature_name` are present, render them as a sub-line in the dashboard job list entry.

**Dashboard template change**: Minimal — add a conditional `<span>` under the job name cell that renders `[product_name] / [feature_name]` when present, and a small "API" badge next to the status badge. No new template files; the existing `jobs.html` template is modified.

**Alternatives considered**:
- A separate `headless_job_metadata` table — unnecessary indirection; the four columns are fixed and narrow.
- Storing metadata in `extra_metadata` JSON on `Job` — `Job` has no such column today; adding one is more disruptive than four named columns.
