# Headless Service Integration Guide

This guide is for developers integrating an external system — such as qual-brew — with
eval-brew's programmatic API. It covers Azure AD M2M authentication, token acquisition,
all six API endpoints, SSE streaming, result delivery, and error handling.

---

## Table of Contents

1. [What the Headless API is](#1-what-the-headless-api-is)
2. [Prerequisites](#2-prerequisites)
3. [Authentication](#3-authentication)
   - 3.1 [How M2M auth works in this org](#31-how-m2m-auth-works-in-this-org)
   - 3.2 [Azure AD app registration setup](#32-azure-ad-app-registration-setup)
   - 3.3 [Acquiring a token](#33-acquiring-a-token)
   - 3.4 [Token caching and refresh](#34-token-caching-and-refresh)
   - 3.5 [Attaching the token to requests](#35-attaching-the-token-to-requests)
4. [API Endpoints](#4-api-endpoints)
   - 4.1 [Discover connectors](#41-get-apiheadlessconnectors)
   - 4.2 [Discover evaluators](#42-get-apiheadlessevaluators)
   - 4.3 [Submit a job](#43-post-apiheadlessjobs)
   - 4.4 [Stream live progress](#44-get-apiheadlessjobsjob_idstream)
   - 4.5 [Re-fetch result](#45-get-apiheadlessjobsjob_idresult)
   - 4.6 [Cancel a job](#46-delete-apiheadlessjobsjob_id)
5. [End-to-End Integration Flow](#5-end-to-end-integration-flow)
6. [Result URL and Cross-Domain Navigation](#6-result-url-and-cross-domain-navigation)
7. [Dashboard Visibility](#7-dashboard-visibility)
8. [Error Reference](#8-error-reference)
9. [Environment Variable Reference](#9-environment-variable-reference)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. What the Headless API is

The headless API is a REST surface on eval-brew that allows external systems to drive the
full evaluation lifecycle programmatically — without a browser or the wizard UI.

A calling system can:

- Discover which chatbot connectors and evaluators are registered in eval-brew
- Submit a batch of test cases as JSON and receive a job ID immediately
- Stream live per-case progress events over SSE as the job executes
- Re-fetch the final result at any time after the job completes
- Cancel an in-flight job

Jobs submitted through the API run through the same execution engine as wizard-submitted
jobs. They appear in the eval-brew job dashboard with an **API** source badge and are
accessible via the standard eval-brew reporting UI.

**Base path**: `/api/headless`

**Auth model**: OAuth2 machine-to-machine (client credentials). No human login is involved
on the API side. The calling system authenticates as itself using a client secret; the
end-user's identity is carried in the request body as metadata.

---

## 2. Prerequisites

Before calling the API, the following must be in place:

| # | What | Who |
|---|---|---|
| 1 | eval-brew is deployed and reachable at a known base URL | eval-brew operator |
| 2 | eval-brew has `HARNESS_AUTH_ENABLED=true` and all `HARNESS_AZURE_*` vars set | eval-brew operator |
| 3 | `HARNESS_PUBLIC_URL` is set to eval-brew's external base URL | eval-brew operator |
| 4 | eval-brew's Azure AD app registration is configured to accept M2M tokens | eval-brew operator |
| 5 | At least one connector and one evaluator are registered in eval-brew | eval-brew admin |
| 6 | The calling app has an Azure AD app registration with a client secret | calling-app team |
| 7 | The `HARNESS_AZURE_API_AUDIENCE` value has been shared with the calling-app team | eval-brew operator |

---

## 3. Authentication

### 3.1 How M2M auth works in this org

The headless API uses the **OAuth2 client credentials flow** (machine-to-machine). There is
no human user in the OAuth flow. The calling application authenticates as itself using its
own Azure AD client ID and client secret. The end-user's identity — if relevant for audit or
display purposes — is passed in the request body, not derived from the token.

The flow has two steps:

```
Step 1 — Calling app acquires an access token from Azure AD

  POST https://login.microsoftonline.com/{tenant_id}/oauth2/token
  grant_type=client_credentials
  client_id=<calling-app client ID>
  client_secret=<calling-app client secret>
  resource=<eval-brew API audience>          ← must match HARNESS_AZURE_API_AUDIENCE

  ← Azure AD returns: { "access_token": "eyJ...", "expires_in": 3599, ... }

Step 2 — Calling app calls the headless API with the token

  POST https://eval-brew.accenture.com/api/headless/jobs
  Authorization: Bearer eyJ...
  Content-Type: application/json

  { "test_cases": [...], "connector_id": "...", "evaluator_id": "..." }
```

eval-brew validates the incoming token by:

1. Fetching the signing keys from Azure AD's JWKS endpoint for the configured tenant
2. Verifying the token signature using RS256
3. Checking that the token's `aud` claim matches `HARNESS_AZURE_API_AUDIENCE`
4. Extracting the service principal's `oid` claim as the caller identity (used for job
   ownership and the in-flight job limit)

The token is not scoped to an individual user. All jobs submitted by the calling app share
the same service principal identity in eval-brew.

### 3.2 Azure AD app registration setup

**On the eval-brew app registration** (done once by the eval-brew operator):

1. In Azure Portal, go to **App registrations** → eval-brew app → **Expose an API**
2. Set an Application ID URI if one is not already set. The simplest value is the bare
   client ID GUID (e.g. `a1b2c3d4-...`). A custom URI such as `api://a1b2c3d4-...` is
   also valid.
3. Note the Application ID URI — this is the value the calling app must use as `resource`
   when requesting a token. It must also be set as `HARNESS_AZURE_API_AUDIENCE` on the
   eval-brew server.

> **No scope or delegated permission needs to be defined.** The client credentials flow
> issues app-only tokens. The existence of the app registration and a valid client secret
> on the calling-app side is sufficient.

**On the calling app registration** (done once by the calling-app team):

1. No special permission grant to eval-brew is required for client credentials.
2. The calling app needs its own **client secret** (Certificates & secrets → New client
   secret). Record the secret value — it is shown only once.
3. Share the calling app's **client ID** and **tenant ID** with the eval-brew operator if
   IP filtering or audit logging is required.

### 3.3 Acquiring a token

Token endpoint:

```
POST https://login.microsoftonline.com/{HARNESS_AZURE_TENANT_ID}/oauth2/token
Content-Type: application/x-www-form-urlencoded
```

Request parameters:

| Parameter | Value |
|---|---|
| `grant_type` | `client_credentials` |
| `client_id` | Calling app's client ID |
| `client_secret` | Calling app's client secret |
| `resource` | Value of `HARNESS_AZURE_API_AUDIENCE` (coordinate with eval-brew operator) |

**Python example**:

```python
import time
import requests

TOKEN_URL = (
    f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/token"
)

def acquire_token(client_id: str, client_secret: str, resource: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "grant_type":    "client_credentials",
        "client_id":     client_id,
        "client_secret": client_secret,
        "resource":      resource,
    })
    resp.raise_for_status()
    token_data = resp.json()
    # expires_at with a 60-second skew to avoid using a token right before expiry
    token_data["expires_at"] = time.time() + int(token_data["expires_in"]) - 60
    return token_data
```

**PowerShell example**:

```powershell
$tokenUrl = "https://login.microsoftonline.com/$env:HARNESS_AZURE_TENANT_ID/oauth2/token"

$body = @{
    grant_type    = "client_credentials"
    client_id     = $env:QUALBREW_CLIENT_ID
    client_secret = $env:QUALBREW_CLIENT_SECRET
    resource      = $env:HARNESS_AZURE_API_AUDIENCE
}

$tokenResp = Invoke-RestMethod -Method POST -Uri $tokenUrl -Body $body
$accessToken = $tokenResp.access_token
```

A successful response from Azure AD:

```json
{
  "token_type": "Bearer",
  "expires_in": "3599",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIs..."
}
```

### 3.4 Token caching and refresh

Access tokens are valid for approximately one hour. Acquiring a new token for every
request is wasteful and risks hitting Azure AD rate limits. Cache the token in process
memory and reuse it until it is within 60 seconds of expiry.

**Recommended Python pattern**:

```python
import threading
import time
import requests

class EvalBrewTokenCache:
    def __init__(self, client_id, client_secret, resource, tenant_id):
        self._client_id = client_id
        self._client_secret = client_secret
        self._resource = resource
        self._tenant_id = tenant_id
        self._token: str | None = None
        self._expires_at: float = 0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        # Double-checked locking — one thread refreshes, others wait
        if not self._is_expired():
            return self._token
        with self._lock:
            if not self._is_expired():  # re-check after acquiring lock
                return self._token
            self._token = self._acquire()
        return self._token

    def invalidate(self) -> None:
        """Call on 401/403 to force re-acquisition on the next request."""
        with self._lock:
            self._expires_at = 0

    def _is_expired(self) -> bool:
        return time.time() >= self._expires_at

    def _acquire(self) -> str:
        url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/token"
        resp = requests.post(url, data={
            "grant_type":    "client_credentials",
            "client_id":     self._client_id,
            "client_secret": self._client_secret,
            "resource":      self._resource,
        })
        resp.raise_for_status()
        data = resp.json()
        self._expires_at = time.time() + int(data["expires_in"]) - 60
        return data["access_token"]
```

On receiving a `401` or `403` response from the headless API, call `cache.invalidate()`
before retrying once. Do not retry automatically within the same call — surface the error.

### 3.5 Attaching the token to requests

Every request to the headless API must include:

```
Authorization: Bearer <access_token>
```

If the header is missing or the token is invalid/expired, the API returns:

```
HTTP 401 Unauthorized
WWW-Authenticate: Bearer
{"detail": "Missing Authorization header."}
```

or

```
HTTP 401 Unauthorized
{"detail": "Invalid or expired token: <reason>"}
```

---

## 4. API Endpoints

All endpoints are under the base path `/api/headless`. All non-stream endpoints use
`Content-Type: application/json`.

### 4.1 GET /api/headless/connectors

Returns all active chatbot connectors registered in eval-brew. Use this to populate a
connector selection UI or to validate a connector ID before submitting a job.

**Request**:

```
GET /api/headless/connectors
Authorization: Bearer <token>
```

**Response `200 OK`**:

```json
{
  "connectors": [
    {
      "id": "3f2a1b9c-...",
      "name": "Customer Service Bot - Production",
      "description": "Primary production endpoint for the CS bot"
    },
    {
      "id": "8d4e2f7a-...",
      "name": "Customer Service Bot - Staging",
      "description": "Staging endpoint for pre-release testing"
    }
  ]
}
```

Returns `{"connectors": []}` when no active connectors are registered. Never returns 404.

---

### 4.2 GET /api/headless/evaluators

Returns all active evaluators registered in eval-brew, including their scoring dimensions.

**Request**:

```
GET /api/headless/evaluators
Authorization: Bearer <token>
```

**Response `200 OK`**:

```json
{
  "evaluators": [
    {
      "id": "9c1b5e3d-...",
      "name": "LLM Quality Scorer v2",
      "description": "Scores chatbot responses on accuracy, tone, and completeness",
      "scoring_dimensions": ["accuracy", "tone", "completeness"]
    }
  ]
}
```

---

### 4.3 POST /api/headless/jobs

Submits test cases for evaluation. The job is created in the database, utterances are
staged, and the job is enqueued for execution immediately. The response is returned before
execution begins.

**Request**:

```
POST /api/headless/jobs
Authorization: Bearer <token>
Content-Type: application/json
```

**Request body**:

```json
{
  "connector_id": "3f2a1b9c-...",
  "evaluator_id": "9c1b5e3d-...",
  "source_system": "qual-brew",
  "product_name": "Customer Portal",
  "feature_name": "Password Reset Flow",
  "test_cases": [
    {
      "id": "tc-001",
      "input_message": "How do I reset my password?",
      "expected_criteria": "Should explain the reset steps clearly",
      "scenario": "Happy path — user knows their email"
    },
    {
      "id": "tc-002",
      "input_message": "I forgot my username and password",
      "expected_criteria": "Should offer account recovery options",
      "scenario": "Edge case — missing both credentials"
    }
  ]
}
```

**Field reference**:

| Field | Type | Required | Notes |
|---|---|---|---|
| `connector_id` | UUID string | Yes | Must match an active connector |
| `evaluator_id` | UUID string | Yes | Must match an active evaluator |
| `source_system` | string | No | Displayed in the dashboard; e.g. `"qual-brew"` |
| `product_name` | string | No | Displayed as sub-text under the job name |
| `feature_name` | string | No | Displayed alongside `product_name` |
| `test_cases` | array | Yes | 1–100 items |
| `test_cases[].id` | string | Yes | Non-empty; unique within the submission |
| `test_cases[].input_message` | string | Yes | The text sent to the chatbot |
| `test_cases[].*` | any | No | Any extra fields are stored as metadata on the utterance |

**Response `201 Created`**:

```json
{
  "job_id": "d4e5f6a7-...",
  "stream_url": "/api/headless/jobs/d4e5f6a7-.../stream",
  "result_url": "/api/headless/jobs/d4e5f6a7-.../result"
}
```

Prepend `HARNESS_PUBLIC_URL` (e.g. `https://eval-brew.accenture.com`) to `stream_url` and
`result_url` to form absolute URLs for use from the calling system.

**Validation errors**:

| HTTP | Condition | Body |
|---|---|---|
| `422` | More than 100 test cases | `{"detail": "Submission exceeds the 100-case limit.", "submitted": 150, "limit": 100}` |
| `422` | Empty `input_message` on any case | `{"detail": "Test case 'tc-003' has an empty input_message."}` |
| `422` | Duplicate `id` within submission | `{"detail": "Duplicate test case id: 'tc-001'."}` |
| `422` | Connector requires per-row password | `{"detail": "Selected connector requires per-row passwords, which are not supported by the headless API in v1."}` |
| `404` | Unknown or archived `connector_id` | `{"detail": "Connector '...' not found or inactive."}` |
| `404` | Unknown or archived `evaluator_id` | `{"detail": "Evaluator '...' not found or inactive."}` |
| `429` | 2 jobs already in flight for this caller | `{"detail": "2 headless jobs already in flight. Wait for one to complete before resubmitting.", "in_flight": 2}` |

The 429 in-flight limit is per service principal (i.e. per calling application). Submit at
most 2 concurrent jobs. Wait for at least one to reach a terminal state before submitting
again.

---

### 4.4 GET /api/headless/jobs/{job_id}/stream

Opens a Server-Sent Events (SSE) stream for the job. Events are emitted in real time as
the job executes. The stream closes automatically after the terminal event.

**Request**:

```
GET /api/headless/jobs/{job_id}/stream
Authorization: Bearer <token>
Accept: text/event-stream
```

**Event sequence**:

```
event: job_started
data: {}

event: progress
data: {"cases_completed": 1, "cases_failed": 0}

event: progress
data: {"cases_completed": 2, "cases_failed": 1}

... (one progress event per test case) ...

event: job_complete
data: {
  "results_url": "https://eval-brew.accenture.com/jobs/d4e5f6a7-.../detail",
  "summary": {
    "total": 10,
    "passed": 9,
    "failed": 1,
    "top_failures": [
      {"id": "tc-007", "input_message": "Delete my account permanently"}
    ]
  }
}
```

If the job fails at the engine level (not individual test case scoring failures):

```
event: job_failed
data: {
  "error": "Execution error",
  "summary": {"total": 10, "passed": 3, "failed": 2, "top_failures": [...]}
}
```

If cancelled via DELETE while the stream is open:

```
event: job_failed
data: {"error": "Job cancelled by user", "summary": {}}
```

**Late-connect behaviour**: If the job has already completed by the time the stream is
opened, the full event sequence — including the terminal event — is replayed from the
in-memory buffer and the stream closes immediately. This means it is safe to open the
stream slightly after submission.

**`summary` object**:

| Field | Type | Notes |
|---|---|---|
| `total` | int | Total test cases in the job |
| `passed` | int | Cases that received a passing evaluation score |
| `failed` | int | Cases that received a failing evaluation score |
| `top_failures` | array | Up to 5 earliest-failing cases; each has `id` and `input_message` |

> **Note**: Individual test case pass/fail is determined by the evaluator's scoring logic.
> A job with `status: "completed"` ran to completion even if all cases scored as failed.
> The `results_url` in the terminal event links to the full per-case analytics report.

**Python streaming example** (using `httpx`):

```python
import httpx
import json

def stream_job(base_url: str, job_id: str, token: str):
    url = f"{base_url}/api/headless/jobs/{job_id}/stream"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=None) as client:
        with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            event_type = None
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event_type = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    payload = json.loads(line.removeprefix("data:").strip())
                    yield event_type, payload
                    if event_type in ("job_complete", "job_failed"):
                        return
```

**PowerShell / curl example**:

```powershell
curl.exe -N `
  -H "Authorization: Bearer $accessToken" `
  "https://eval-brew.accenture.com/api/headless/jobs/$jobId/stream"
```

**Error responses**:

| HTTP | Condition |
|---|---|
| `401` | Missing or invalid token |
| `403` | Job belongs to a different service principal |
| `404` | Job ID not found, or stream already closed and removed |

---

### 4.5 GET /api/headless/jobs/{job_id}/result

Re-fetches the current state or final result of a job. Safe to call at any time — before,
during, or after execution. Use this as a fallback when the SSE stream is not practical
(e.g. serverless functions, fire-and-forget submission patterns).

**Request**:

```
GET /api/headless/jobs/{job_id}/result
Authorization: Bearer <token>
```

**Response `200 OK`** — completed job:

```json
{
  "job_id": "d4e5f6a7-...",
  "status": "completed",
  "results_url": "https://eval-brew.accenture.com/jobs/d4e5f6a7-.../detail",
  "summary": {
    "total": 10,
    "passed": 9,
    "failed": 1,
    "top_failures": [
      {"id": "tc-007", "input_message": "Delete my account permanently"}
    ]
  }
}
```

**Response `200 OK`** — in-progress job:

```json
{
  "job_id": "d4e5f6a7-...",
  "status": "in_progress",
  "results_url": null,
  "summary": {
    "total": 10,
    "passed": 4,
    "failed": 0,
    "top_failures": []
  }
}
```

**`status` values**:

| Value | Meaning |
|---|---|
| `in_progress` | Job is queued, running, or in any other non-terminal state |
| `completed` | All test cases have been evaluated; `results_url` is set |
| `failed` | The execution engine encountered a fatal error |
| `cancelled` | The job was cancelled via DELETE; `results_url` is null |

`results_url` is only present (non-null) when `status == "completed"`.

**Polling pattern** (for callers that cannot hold an SSE connection):

```python
import time
import requests

def poll_until_done(base_url: str, job_id: str, token: str,
                    interval_seconds: int = 10, timeout_seconds: int = 3600):
    url = f"{base_url}/api/headless/jobs/{job_id}/result"
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != "in_progress":
            return data
        time.sleep(interval_seconds)

    raise TimeoutError(f"Job {job_id} did not complete within {timeout_seconds}s")
```

---

### 4.6 DELETE /api/headless/jobs/{job_id}

Cancels an in-flight job. Transitions the job to `cancelled`, emits a terminal `job_failed`
event on any open SSE stream, and releases the in-flight slot so a new job can be submitted.

**Request**:

```
DELETE /api/headless/jobs/{job_id}
Authorization: Bearer <token>
```

**Response `200 OK`**:

```json
{
  "job_id": "d4e5f6a7-...",
  "status": "cancelled"
}
```

**Error responses**:

| HTTP | Body | Meaning |
|---|---|---|
| `404` | `{"detail": "Job not found."}` | Unknown job ID |
| `403` | `{"detail": "Forbidden."}` | Job belongs to a different service principal |
| `409` | `{"detail": "Job is already in terminal state: completed.", "current_status": "completed"}` | Job already finished; cannot cancel |

---

## 5. End-to-End Integration Flow

```
Calling system                          Azure AD              eval-brew
──────────────────────────────────────────────────────────────────────────────

1. Check token cache ──────────────────────────────────────────────────────▶
   (if expired or missing):
   POST /oauth2/token ───────────────▶
   grant_type=client_credentials         ◀── access_token (JWT, ~1h)
   resource=<HARNESS_AZURE_API_AUDIENCE>
   Store in cache with expires_at

2. GET /api/headless/connectors ────────────────────────────────────────────▶
   Authorization: Bearer <token>                         validate token
                                                         ◀── 200 {"connectors":[...]}

3. GET /api/headless/evaluators ────────────────────────────────────────────▶
   Authorization: Bearer <token>                         validate token
                                                         ◀── 200 {"evaluators":[...]}

   (present connector/evaluator selection to the user)

4. POST /api/headless/jobs ─────────────────────────────────────────────────▶
   Authorization: Bearer <token>                         validate token
   { test_cases, connector_id,                           create job, enqueue
     evaluator_id, product_name, ... }                   ◀── 201 { job_id,
                                                               stream_url,
                                                               result_url }

5a. GET /api/headless/jobs/{id}/stream  (SSE — preferred) ─────────────────▶
   Authorization: Bearer <token>                         validate token

   ◀── event: job_started  data: {}
   ◀── event: progress     data: {"cases_completed":1,"cases_failed":0}
   ◀── event: progress     data: {"cases_completed":2,"cases_failed":0}
   ...
   ◀── event: job_complete data: {"results_url":"https://...","summary":{}}

   (stream closes; present results_url link to user)

5b. OR: poll GET /api/headless/jobs/{id}/result  (polling — fallback)
   (repeat at interval until status != "in_progress")
   ◀── 200 {"status":"completed","results_url":"https://...","summary":{}}

6. User clicks results_url ─────────────────────────────────────────────────▶
   (browser navigates to eval-brew)               Azure AD SSO (same tenant)
                                                  ◀── eval-brew detail page
```

---

## 6. Result URL and Cross-Domain Navigation

The `results_url` returned in the submission response and SSE terminal event is a
fully-qualified URL when `HARNESS_PUBLIC_URL` is set on the eval-brew server:

```
https://eval-brew.accenture.com/jobs/{job_id}/detail
```

This URL points to the eval-brew analytics dashboard — a full per-case results view with
verdict breakdowns, filtering, and CSV export.

**Authentication on click**: eval-brew's UI uses Azure AD browser SSO (session cookie). When
a user clicks the link from qual-brew, their browser navigates to eval-brew. If they do not
have an active eval-brew session:

1. eval-brew redirects to Azure AD (`https://login.microsoftonline.com/...`)
2. Since both apps share the same Azure AD tenant and the user is already authenticated
   in that tenant (via qual-brew), Azure AD issues an auth code without prompting for
   credentials again (SSO)
3. eval-brew receives the auth code, establishes a session, and serves the detail page

The redirect is usually transparent — the user sees the detail page with at most a brief
redirect flash. No separate eval-brew login is required.

**If `HARNESS_PUBLIC_URL` is not set**, `results_url` is returned as a relative path
(`/jobs/{id}/detail`). In that case, the calling system must prepend eval-brew's known
base URL before presenting it as a link.

---

## 7. Dashboard Visibility

Headless-submitted jobs appear in the eval-brew job list at `/jobs` alongside wizard-
submitted jobs. They are visually distinguished by:

- An **API** badge next to the job status
- `product_name / feature_name` displayed as sub-text under the job name (when provided)
- `source_system` stored on the job record for filtering and audit

The `created_by` field on the job reflects the service principal's Azure object ID (`oid`
from the M2M token). Operators can identify which calling application submitted each job
by looking up the OID against the Azure AD app registration.

---

## 8. Error Reference

### Common errors and remediation

| HTTP | `detail` contains | Likely cause | Fix |
|---|---|---|---|
| `401` | `Missing Authorization header` | No `Authorization` header sent | Add `Authorization: Bearer <token>` |
| `401` | `Invalid or expired token` | Token expired, wrong audience, or wrong signing key | Invalidate cache, acquire a new token; verify `resource` matches `HARNESS_AZURE_API_AUDIENCE` |
| `403` | `Forbidden` | Job was submitted by a different service principal | Only the submitting service principal can read/cancel its own jobs |
| `404` | `not found or inactive` | `connector_id` or `evaluator_id` is unknown or archived | Call `/connectors` or `/evaluators` to get current active IDs |
| `404` | `Job not found` | Wrong `job_id` or job was deleted | Verify the job ID from the submission response |
| `409` | `already in terminal state` | Tried to cancel a completed/failed/cancelled job | Check `/result` first; cancel is only valid for non-terminal jobs |
| `422` | `exceeds the 100-case limit` | Submitted more than 100 test cases | Split into multiple submissions of ≤ 100 cases each |
| `422` | `empty input_message` | A test case has a blank `input_message` | All test cases must have a non-empty `input_message` |
| `422` | `Duplicate test case id` | Two test cases share the same `id` within one submission | IDs must be unique within a single submission; use UUIDs |
| `429` | `already in flight` | 2 jobs are already running for this service principal | Wait for a job to complete before submitting another |

### Checking job status on unexpected errors

If a submission returns 5xx or the stream disconnects unexpectedly, the job may or may
not have been created. Check with the result endpoint using the `job_id` from the
submission response (if one was received):

```python
result = requests.get(
    f"{EVAL_BREW_BASE}/api/headless/jobs/{job_id}/result",
    headers={"Authorization": f"Bearer {token}"}
)
```

If `404` is returned, the job was not created and the submission should be retried.

---

## 9. Environment Variable Reference

### eval-brew server (set by the eval-brew operator)

| Variable | Required | Notes |
|---|---|---|
| `HARNESS_AUTH_ENABLED` | No | Set `true` in production. `false` disables all auth checks (local dev only). |
| `HARNESS_AZURE_TENANT_ID` | Yes* | GUID of the shared Azure AD tenant. Used to build the JWKS endpoint URL. |
| `HARNESS_AZURE_CLIENT_ID` | Yes* | Client ID of the eval-brew app registration. |
| `HARNESS_AZURE_CLIENT_SECRET` | Yes* | eval-brew app registration client secret (used for SSO UI login, not for M2M). |
| `HARNESS_AZURE_API_AUDIENCE` | No | The `aud` value expected in incoming Bearer tokens. Defaults to `HARNESS_AZURE_CLIENT_ID`. Set explicitly when the app's Application ID URI differs from the bare client ID (e.g. `api://your-client-id`). **Must match the `resource` value used by calling apps.** |
| `HARNESS_PUBLIC_URL` | No | Externally-accessible base URL of eval-brew, no trailing slash (e.g. `https://eval-brew.accenture.com`). When set, `results_url` in API responses is a fully-qualified URL. |
| `HARNESS_SESSION_SECRET` | Yes* | Random 32+ character string used to sign browser session cookies. |
| `HARNESS_REDIRECT_URI` | Yes* | Azure AD callback URL for browser SSO (e.g. `https://eval-brew.accenture.com/auth/callback`). |

\* Required when `HARNESS_AUTH_ENABLED=true`.

### Calling application (set by the calling-app team)

These are the variables the calling application needs. Names are illustrative — the
calling application can choose its own naming convention.

| Suggested variable | Value |
|---|---|
| `EVAL_BREW_BASE_URL` | `https://eval-brew.accenture.com` |
| `EVAL_BREW_TENANT_ID` | Shared Azure AD tenant GUID (same as `HARNESS_AZURE_TENANT_ID`) |
| `EVAL_BREW_API_AUDIENCE` | Value of `HARNESS_AZURE_API_AUDIENCE` — coordinate with eval-brew operator |
| `<APP>_CLIENT_ID` | Calling app's own Azure AD client ID |
| `<APP>_CLIENT_SECRET` | Calling app's own client secret |

---

## 10. Troubleshooting

**`401 Invalid or expired token: Audience not found`**

The token's `aud` claim does not match `HARNESS_AZURE_API_AUDIENCE`. Check:
- What value is the calling app using as `resource` in the token request?
- What is `HARNESS_AZURE_API_AUDIENCE` set to on the eval-brew server?
- These two values must be identical. Coordinate with the eval-brew operator.

**`401` on every request despite a fresh token**

Check that `HARNESS_AZURE_TENANT_ID` on the eval-brew server matches the tenant the
calling app is acquiring tokens from. Tokens issued from a different tenant will fail
signature verification.

**`429 Too Many Requests` immediately after one submission**

A previous job may have been left in a non-terminal state (queued or running) from a prior
run. Call `GET /api/headless/jobs/{id}/result` on the previous job ID to check its state,
or contact the eval-brew operator to check the dashboard.

**SSE stream returns `404` immediately after submission**

The job completed very quickly (common when the connector returns errors immediately).
The stream buffer is cleared after the first consumer reads the terminal event. Use
`GET /api/headless/jobs/{id}/result` to retrieve the summary.

**`results_url` is a relative path, not an absolute URL**

`HARNESS_PUBLIC_URL` is not set on the eval-brew server. Either ask the eval-brew operator
to set it, or prepend eval-brew's known base URL to the relative path in your integration
code.

**User gets an eval-brew login page instead of the detail view**

This can happen on first visit if the Azure AD SSO session has expired. The user will be
redirected to Azure AD and back automatically — no separate password is needed because
both apps share the same tenant. If the redirect loop continues, check that eval-brew's
`HARNESS_REDIRECT_URI` is registered as a valid redirect URI in the eval-brew Azure AD
app registration.
