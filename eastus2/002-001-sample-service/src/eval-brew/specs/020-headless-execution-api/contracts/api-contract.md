# API Contract: Headless Execution API (020)

**Base prefix**: `/api/headless`  
**Auth**: All endpoints require `Authorization: Bearer <Azure AD JWT>` header.  
**Content-Type**: `application/json` for all non-stream endpoints.

---

## Authentication

Every request must include:

```
Authorization: Bearer <token>
```

The token is a valid Azure AD JWT issued for the eval-brew application (`HARNESS_AZURE_CLIENT_ID`). The `oid` claim is used as the user identity for job ownership and in-flight tracking.

**Error responses**:
- `401 Unauthorized` — missing, malformed, or expired token
- `403 Forbidden` — token valid but resource belongs to another user

---

## Endpoints

### GET /api/headless/connectors

Returns all registered, active chatbot connectors. No per-user filtering.

**Response `200 OK`**:
```json
{
  "connectors": [
    {
      "id": "3f2a...",
      "name": "My Chatbot Dev",
      "description": "Development endpoint for the customer service bot"
    }
  ]
}
```

**Empty case**: Returns `{"connectors": []}` when no active connectors are registered.

---

### GET /api/headless/evaluators

Returns all registered, active evaluators. No per-user filtering.

**Response `200 OK`**:
```json
{
  "evaluators": [
    {
      "id": "9c1b...",
      "name": "LLM Quality Scorer",
      "description": "Scores responses on accuracy, tone, and completeness",
      "scoring_dimensions": ["accuracy", "tone", "completeness"]
    }
  ]
}
```

**Empty case**: Returns `{"evaluators": []}` when no active evaluators are registered.

---

### POST /api/headless/jobs

Submits test cases for evaluation. Creates a job, stages utterances, and enqueues execution.

**Request body**:
```json
{
  "test_cases": [
    {
      "id": "tc-001",
      "input_message": "How do I reset my password?",
      "scenario": "Password reset happy path"
    },
    {
      "id": "tc-002",
      "input_message": "Cancel my subscription immediately",
      "scenario": "Cancellation flow"
    }
  ],
  "connector_id": "3f2a...",
  "evaluator_id": "9c1b...",
  "source_system": "qual-brew",
  "product_name": "Customer Portal",
  "feature_name": "Account Management"
}
```

Fields:
- `test_cases` — 1 to 100 items; required
- `test_cases[].id` — caller-assigned string; non-empty; unique within submission; required
- `test_cases[].input_message` — the chatbot input; non-empty; required
- `test_cases[].*` — any additional fields are stored as extra metadata on the utterance
- `connector_id` — must reference an active connector; required
- `evaluator_id` — must reference an active evaluator; required
- `source_system`, `product_name`, `feature_name` — optional metadata; displayed in dashboard

**Response `201 Created`**:
```json
{
  "job_id": "d4e5f6...",
  "stream_url": "/api/headless/jobs/d4e5f6.../stream",
  "result_url": "/api/headless/jobs/d4e5f6.../result"
}
```

**Error responses**:

| Status | Condition | Example body |
|---|---|---|
| `422` | More than 100 test cases | `{"detail": "Submission exceeds the 100-case limit.", "submitted": 150, "limit": 100}` |
| `422` | Empty `input_message` | `{"detail": "Test case 'tc-003' has an empty input_message."}` |
| `422` | Duplicate `id` | `{"detail": "Duplicate test case id: 'tc-001'."}` |
| `422` | Connector requires per-row password | `{"detail": "Selected connector requires per-row passwords, which are not supported by the headless API in v1."}` |
| `404` | Unknown `connector_id` | `{"detail": "Connector 'abc...' not found or inactive."}` |
| `404` | Unknown `evaluator_id` | `{"detail": "Evaluator 'xyz...' not found or inactive."}` |
| `429` | 2 headless jobs already in flight | `{"detail": "2 headless jobs already in flight. Wait for one to complete before resubmitting.", "in_flight": 2}` |

---

### GET /api/headless/jobs/{job_id}/stream

Opens a Server-Sent Events stream for the job. Requires the same Bearer token as submission.

**Response `200 OK`** (`Content-Type: text/event-stream`):

Event types emitted in order:

| Event | When | Data |
|---|---|---|
| `job_started` | Job transitions from queued to executing | `{}` |
| `progress` | Each test case completes evaluation | `{"cases_completed": N, "cases_failed": M}` |
| `job_complete` | All cases evaluated successfully | `{"results_url": "/jobs/{id}", "summary": {...}}` |
| `job_failed` | Execution error or timeout | `{"error": "...", "summary": {...}}` |

The `summary` object:
```json
{
  "total": 10,
  "passed": 8,
  "failed": 2,
  "top_failures": [
    {"id": "tc-003", "input_message": "Cancel my subscription"},
    {"id": "tc-007", "input_message": "Delete my account"}
  ]
}
```

`top_failures` contains up to the first 5 failures in execution order. The stream closes after the terminal event (`job_complete` or `job_failed`).

**Late-connect behaviour**: If the job has already completed when the stream is opened, the full event sequence (including the terminal event) is replayed from the in-memory buffer and the stream closes immediately.

**Error responses**:

| Status | Condition |
|---|---|
| `404` | `job_id` not found |
| `403` | Job belongs to a different user |

---

### GET /api/headless/jobs/{job_id}/result

Re-fetches the current state or final result of a job. Safe to call at any time.

**Response `200 OK`** for a completed job:
```json
{
  "job_id": "d4e5f6...",
  "status": "completed",
  "results_url": "/jobs/d4e5f6...",
  "summary": {
    "total": 10, "passed": 10, "failed": 0, "top_failures": []
  }
}
```

**Response `200 OK`** for an in-progress job:
```json
{
  "job_id": "d4e5f6...",
  "status": "in_progress",
  "results_url": null,
  "summary": {
    "total": 10, "passed": 3, "failed": 0, "top_failures": []
  }
}
```

**Response `200 OK`** for a cancelled job:
```json
{
  "job_id": "d4e5f6...",
  "status": "cancelled",
  "results_url": null,
  "summary": {
    "total": 10, "passed": 5, "failed": 1,
    "top_failures": [{"id": "tc-004", "input_message": "..."}]
  }
}
```

**`status` values**: `"completed"` | `"failed"` | `"cancelled"` | `"in_progress"`

`in_progress` covers all non-terminal states (submitted, queued, running, cancelling).

**Error responses**:

| Status | Condition |
|---|---|
| `404` | `job_id` not found |
| `403` | Job belongs to a different user |

---

### DELETE /api/headless/jobs/{job_id}

Cancels a headless job in any non-terminal state. Transitions it to `cancelled`, emits a terminal `job_failed` event on any open stream, and releases the in-flight slot.

**Response `200 OK`**:
```json
{
  "job_id": "d4e5f6...",
  "status": "cancelled"
}
```

**Error responses**:

| Status | Condition | Body |
|---|---|---|
| `404` | `job_id` not found | `{"detail": "Job not found."}` |
| `403` | Job belongs to a different user | `{"detail": "Forbidden."}` |
| `409` | Job already in a terminal state | `{"detail": "Job is already in terminal state: completed.", "current_status": "completed"}` |

---

## Summary Table

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/headless/connectors` | List all active connectors |
| `GET` | `/api/headless/evaluators` | List all active evaluators |
| `POST` | `/api/headless/jobs` | Submit test cases and start a job |
| `GET` | `/api/headless/jobs/{id}/stream` | SSE progress stream |
| `GET` | `/api/headless/jobs/{id}/result` | Re-fetch job result |
| `DELETE` | `/api/headless/jobs/{id}` | Cancel an in-flight job |
