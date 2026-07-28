# Quickstart: Headless Execution API (020)

**Branch**: `020-headless-execution-api` | **Date**: 2026-07-12

This guide covers how to build, configure, and test the headless execution API locally.

---

## Prerequisites

- Python 3.11 with `uv` (existing project toolchain)
- eval-brew running locally (`uv run uvicorn harness.ui:create_app --factory --reload`)
- An Azure AD app registration with `HARNESS_AZURE_TENANT_ID` and `HARNESS_AZURE_CLIENT_ID` configured (or auth disabled for local testing)

---

## 1. Apply the Database Migration

```powershell
uv run alembic upgrade head
```

This applies the new migration that adds `submission_source`, `source_system`, `product_name`, and `feature_name` to the `job` table. Existing rows get `submission_source = 'wizard'`; all other new columns are `NULL`.

---

## 2. Install New Dependencies

`PyJWT` and `cryptography` are new runtime dependencies:

```powershell
uv add "PyJWT[crypto]"
```

Verify:

```powershell
uv run python -c "import jwt; print(jwt.__version__)"
```

---

## 3. Configure Auth for Local Testing

**Option A — Disable auth entirely** (simplest for development):

```
HARNESS_AUTH_ENABLED=false
```

With auth disabled, `require_api_auth` returns a synthetic admin user (oid = `"local-dev"`, name = `"Local Dev"`). All headless endpoints work without a Bearer token.

**Option B — Use a real Azure AD token**:

Acquire a token for the eval-brew client using the Azure CLI or an API client (e.g. Postman with OAuth 2.0 auth code flow), then include it as:

```
Authorization: Bearer <token>
```

---

## 4. Register a Connector and Evaluator

Use the existing eval-brew UI to register at least one connector and one evaluator before submitting headless jobs.

- Navigate to `http://localhost:8000/connectors` → Register a connector
- Navigate to `http://localhost:8000/evaluators` → Register an evaluator

Note the connector ID and evaluator ID from the registry listing pages.

---

## 5. Discover Available Connectors and Evaluators

```powershell
# Connectors
Invoke-RestMethod -Uri "http://localhost:8000/api/headless/connectors" `
  -Headers @{ Authorization = "Bearer $token" }

# Evaluators
Invoke-RestMethod -Uri "http://localhost:8000/api/headless/evaluators" `
  -Headers @{ Authorization = "Bearer $token" }
```

Expected response shape:

```json
{
  "connectors": [
    { "id": "...", "name": "My Bot", "description": "..." }
  ]
}
```

---

## 6. Submit a Headless Job

```powershell
$body = @{
  test_cases = @(
    @{ id = "tc-001"; input_message = "How do I reset my password?" }
    @{ id = "tc-002"; input_message = "What are your opening hours?" }
  )
  connector_id = "<connector-id-from-step-5>"
  evaluator_id = "<evaluator-id-from-step-5>"
  source_system = "qual-brew"
  product_name  = "Customer Portal"
  feature_name  = "Account Management"
} | ConvertTo-Json -Depth 5

$response = Invoke-RestMethod `
  -Method POST `
  -Uri "http://localhost:8000/api/headless/jobs" `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $token" } `
  -Body $body

$response | ConvertTo-Json
```

Expected response:

```json
{
  "job_id": "d4e5f6...",
  "stream_url": "/api/headless/jobs/d4e5f6.../stream",
  "result_url": "/api/headless/jobs/d4e5f6.../result"
}
```

---

## 7. Stream Job Progress

SSE streams require a streaming HTTP client. Use `curl` or Python `httpx`:

**PowerShell (curl)**:

```powershell
curl.exe -N `
  -H "Authorization: Bearer $token" `
  "http://localhost:8000/api/headless/jobs/$($response.job_id)/stream"
```

Expected output:

```
event: job_started
data: {}

event: progress
data: {"cases_completed": 1, "cases_failed": 0}

event: progress
data: {"cases_completed": 2, "cases_failed": 0}

event: job_complete
data: {"results_url": "/jobs/d4e5f6...", "summary": {"total": 2, "passed": 2, "failed": 0, "top_failures": []}}
```

---

## 8. Re-fetch the Result

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/headless/jobs/$($response.job_id)/result" `
  -Headers @{ Authorization = "Bearer $token" }
```

---

## 9. Cancel an In-flight Job

```powershell
Invoke-RestMethod `
  -Method DELETE `
  -Uri "http://localhost:8000/api/headless/jobs/$($response.job_id)" `
  -Headers @{ Authorization = "Bearer $token" }
```

---

## 10. Verify Dashboard Visibility

After submitting a headless job, navigate to `http://localhost:8000/jobs`. The job should appear in the list with:

- An **API** source badge
- The `product_name` and `feature_name` displayed as sub-text under the job name
- A **Cancelled** status label if cancelled (no report link)
- A working report link when completed

---

## 11. Running the Tests

```powershell
# All headless API tests
uv run pytest tests/unit/ui/api/ tests/integration/test_headless_*.py -v

# Specific test file
uv run pytest tests/integration/test_headless_jobs.py -v
```

**Key test patterns**:

- Route tests use `TestClient(create_app())` with `app.dependency_overrides[require_api_auth] = lambda: fake_user`
- DB tests use the existing `db_session` savepoint fixture from `conftest.py`
- Engine progress callback tests use synchronous mocks — no async infrastructure needed for unit tests
- SSE stream tests use `TestClient` with `stream=True` and parse the `text/event-stream` body line by line

---

## 12. Environment Variable Reference

| Variable | Required | Notes |
|---|---|---|
| `HARNESS_AUTH_ENABLED` | No | Set `true` to require real Azure AD tokens |
| `HARNESS_AZURE_TENANT_ID` | If auth enabled | Used to construct JWKS URI |
| `HARNESS_AZURE_CLIENT_ID` | If auth enabled | Expected JWT audience |
| `HARNESS_DB_PATH` | No | SQLite path for local dev (omit for PostgreSQL) |
| `DATABASE_URL` | No | PostgreSQL URL for production |

No new environment variables are required for the headless API beyond what the existing auth system already uses.
