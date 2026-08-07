# Plan — Angular 21 SPA + Azure Function App Migration

**Created:** 2026-08-07  
**Status:** Draft v2 — detailed revision  
**Reference plans:**
- `qual-brew/docs/plans/plan-repo-split-and-azure-migration.md`
- `qual-brew-api/docs/plans/angular-21-migration-impact.md`

---

## Overview

EvalBrew is migrated from a Python/FastAPI monolith with Jinja2 server-side-rendered templates to a two-tier architecture:

| Tier | Current | Target |
|---|---|---|
| **Frontend** | Jinja2 SSR templates served by FastAPI | Angular 21 SPA on Azure Static Web Apps |
| **Backend** | FastAPI on AKS / Container Apps (port 8443) | Azure Function App (ASGI-wrapped FastAPI, Premium EP1) |
| **Database** | Azure PostgreSQL Flexible Server | Unchanged |
| **Auth** | Python `msal` library + session cookie | `@azure/msal-angular` in browser; Bearer JWT to backend |

> **This is a full frontend rewrite.** EvalBrew has no existing Angular code — the entire UI is Jinja2 templates. Every screen must be built from scratch. The qual-brew Angular 21 impact assessment applies as a "start-here" baseline for patterns to adopt from day one.

---

## Locked Architectural Decisions

### Backend

| Decision | Choice |
|---|---|
| ASGI wrapper | `AsgiFunctionApp` — wraps FastAPI with ~5 lines |
| App Service Plan | **Premium EP1** — always-on, no timeout, SSE-safe |
| Scale-out | `WEBSITE_MAX_DYNAMIC_APPLICATION_SCALE_OUT=1` — single instance for asyncio job queue + session locks |
| Worker count | `FUNCTIONS_WORKER_PROCESS_COUNT=1` — single Python worker process |
| TLS | Terminated by Azure Functions platform; `entrypoint.sh` not carried forward |
| Python version | **3.12** (3.13 not GA in Azure Functions at plan date) |
| Dependency packaging | `uv export --no-dev --format requirements-txt -o requirements.txt` in CI |
| CORS | `CORSMiddleware` with `HARNESS_FRONTEND_ORIGIN` env var |

### Frontend

| Decision | Choice |
|---|---|
| Framework | Angular 21 |
| Hosting | **Azure Static Web Apps — Standard tier** |
| Auth library | `@azure/msal-angular` v8+ |
| UI components | Angular Material v21 + CDK |
| Change detection | **Zoneless** (`provideZonelessChangeDetection()`) from day one — required for `EventSource` + `setTimeout` correctness |
| State | Angular Signals + RxJS 7.x |
| SSE client | Native `EventSource`; each listener writes to a signal |
| API contract | FastAPI OpenAPI → `openapi-typescript` → `src/types/api.generated.ts` |
| TypeScript | `~5.9.x` |
| Polling pattern | `interval(3000).pipe(switchMap(...))` for dashboard live jobs; SSE for detail page |

### Repo Structure

| Decision | Choice |
|---|---|
| Split | `eval-brew-api` (FastAPI backend) + `eval-brew-app` (Angular frontend) |
| Workspace | VS Code multi-root workspace in parent `brew-suite/` directory |
| System of record | `eval-brew-api` owns specs, docs, references |

---

## Target Architecture

```
Browser
  │
  ├── HTTPS ──▶ Azure Static Web Apps (CDN, global)
  │                  Angular 21 SPA
  │                  @azure/msal-angular v8
  │                  Bearer JWT on every /api/* request
  │                        │
  └── HTTPS ──▶ Azure Function App  (eval-brew-api)
                     ASGI-wrapped FastAPI
                     WEBSITE_MAX_DYNAMIC_APPLICATION_SCALE_OUT=1
                           │
               ┌───────────┴──────────────┐
               │                          │
        Azure PostgreSQL             Azure AD
        Flexible Server              (same tenant)
        (Managed Identity)
               │
         Azure Key Vault
         (Managed Identity)
```

---

## Complete REST API Specification

This section is the authoritative design contract for Phase 1. Every endpoint needed by the Angular SPA is listed. Endpoints marked **[020]** already exist in the headless API. All others must be added.

### URL prefix strategy

| Prefix | Purpose |
|---|---|
| `/api/headless/` | Existing machine-to-machine API (spec 020); **unchanged** |
| `/api/v1/` | New browser-facing REST API (Phase 1 work) |

The new `/api/v1/` router uses the same Bearer JWT auth (`require_api_auth`). The `current_user` dict returned is `{oid, name}`.

### Auth

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/auth/me` | Bearer | — | `{oid, email, display_name, role}` |
| POST | `/api/v1/auth/logout` | Bearer | — | `{ok: true}` (Angular handles MSAL sign-out client-side; backend clears server-side session if any) |

### Jobs — list and bulk actions

| Method | Path | Auth | Query / Body | Response |
|---|---|---|---|---|
| GET | `/api/v1/jobs` | Bearer | `status[]`, `q`, `sort`, `dir`, `page`, `page_size` | `{jobs: JobListItem[], total: int, page: int, pages: int}` |
| GET | `/api/v1/jobs/overview` | Bearer | — | `{total_jobs, total_sessions, total_utterances, total_turns, activity: ActivityItem[]}` |
| POST | `/api/v1/jobs/actions/clear-terminal` | Bearer | — | `{deleted: int}` |
| POST | `/api/v1/jobs/actions/clear-all` | Bearer | — | `{deleted: int}` |

### Jobs — wizard lifecycle

| Method | Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| POST | `/api/v1/jobs` | Bearer | `{job_name, description?}` | `{job_id}` | Creates draft |
| GET | `/api/v1/jobs/{id}/wizard-state` | Bearer | — | `WizardState` | Resume support |
| PATCH | `/api/v1/jobs/{id}/name` | Bearer | `{job_name, description?}` | `{ok}` | Step 1 save |
| POST | `/api/v1/jobs/{id}/csv` | Bearer | `multipart/form-data: csv_file` | `CsvUploadResult` | Step 2 |
| PATCH | `/api/v1/jobs/{id}/connector` | Bearer | `{connector_id}` | `{ok}` | Step 3 save |
| PATCH | `/api/v1/jobs/{id}/evaluator` | Bearer | `{evaluator_id}` | `{ok}` | Step 4 save |
| POST | `/api/v1/jobs/{id}/start` | Bearer | — | `{job_id, status}` | Step 5 submit |
| POST | `/api/v1/jobs/{id}/clone` | Bearer | — | `{job_id}` | Returns new draft job_id |

### Jobs — detail and results

| Method | Path | Auth | Query | Response |
|---|---|---|---|---|
| GET | `/api/v1/jobs/{id}` | Bearer | — | `Job` (full) |
| GET | `/api/v1/jobs/{id}/status` | Bearer | — | `{status, processed_count, total_utterance_count, failed_count}` |
| GET | `/api/v1/jobs/{id}/stream` | Bearer | — | SSE — see event table below **[020]** |
| GET | `/api/v1/jobs/{id}/results` | Bearer | `verdict[]`, `error_only`, `test_id[]`, `q`, `sort`, `dir`, `page`, `page_size` | `{results: ResultRow[], total, page, pages}` |
| GET | `/api/v1/jobs/{id}/results/{result_id}` | Bearer | — | `ResultRow` (full trace) |
| GET | `/api/v1/jobs/{id}/analytics` | Bearer | — | `RunAnalytics` |
| POST | `/api/v1/jobs/{id}/cancel` | Bearer | — | `{job_id, status}` |
| DELETE | `/api/v1/jobs/{id}` | Bearer | — | `{job_id}` **[020]** |
| GET | `/api/v1/jobs/{id}/export` | Bearer | `format=csv\|json` | File attachment |

### Connectors

| Method | Path | Auth | Query / Body | Response |
|---|---|---|---|---|
| GET | `/api/v1/connectors` | Bearer | `q`, `state=active\|archived\|all` | `{connectors: ConnectorItem[]}` |
| GET | `/api/v1/connectors/{id}` | Bearer | — | `ConnectorDetail` |
| POST | `/api/v1/connectors` | Bearer | `ConnectorPayload` | `ConnectorDetail` |
| PUT | `/api/v1/connectors/{id}` | Bearer | `ConnectorPayload` + `replace_credential: bool` | `ConnectorDetail` |
| POST | `/api/v1/connectors/{id}/archive` | Bearer | — | `{ok}` |
| POST | `/api/v1/connectors/{id}/restore` | Bearer | — | `{ok}` |
| DELETE | `/api/v1/connectors/{id}` | Bearer | — | `{ok}` or 409 if in use |
| POST | `/api/v1/connectors/test` | Bearer | `ConnectorPayload` (pre-save) | `TestResult` |
| POST | `/api/v1/connectors/{id}/test` | Bearer | — | `TestResult` |

### Evaluators

Same pattern as connectors. Replace `connector_id` with `evaluator_id`, add `dimensions: string[]` to payload.

| Method | Path |
|---|---|
| GET | `/api/v1/evaluators?q=&state=` |
| GET | `/api/v1/evaluators/{id}` |
| POST | `/api/v1/evaluators` |
| PUT | `/api/v1/evaluators/{id}` |
| POST | `/api/v1/evaluators/{id}/archive` |
| POST | `/api/v1/evaluators/{id}/restore` |
| DELETE | `/api/v1/evaluators/{id}` |
| POST | `/api/v1/evaluators/test` |
| POST | `/api/v1/evaluators/{id}/test` |

### Chat Sessions

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/chat-sessions` | Bearer | — | `{sessions: ChatSessionListItem[]}` |
| POST | `/api/v1/chat-sessions` | Bearer | `{session_name, connector_id, evaluator_id, test_id, password}` | `{chat_session_id}` |
| GET | `/api/v1/chat-sessions/{id}` | Bearer | — | `ChatSessionDetail` (with turns) |
| DELETE | `/api/v1/chat-sessions/{id}` | Bearer | — | `{ok}` |
| POST | `/api/v1/chat-sessions/{id}/turns` | Bearer | `{message: string}` | `{turn_id}` |
| GET | `/api/v1/chat-sessions/{id}/turns/{turn_id}/stream` | Bearer | — | SSE — see event table below |
| GET | `/api/v1/chat-sessions/{id}/analytics` | Bearer | `q`, `verdict[]`, `error_only`, `sort`, `dir` | `{analytics: RunAnalytics, turns: TurnRow[]}` |
| GET | `/api/v1/chat-sessions/{id}/export` | Bearer | `format=csv\|json` | File attachment |
| POST | `/api/v1/chat-sessions/actions/clear-errors` | Bearer (admin) | — | `{deleted: int}` |
| POST | `/api/v1/chat-sessions/actions/clear-all` | Bearer (admin) | — | `{deleted: int}` |

### Admin

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/admin/users` | Bearer (admin) | — | `{users: UserRecord[]}` |
| POST | `/api/v1/admin/users` | Bearer (admin) | `{email, role, display_name?}` | `UserRecord` |
| PATCH | `/api/v1/admin/users/{id}/role` | Bearer (admin) | `{role}` | `{ok}` |
| DELETE | `/api/v1/admin/users/{id}` | Bearer (admin) | — | `{ok}` |
| GET | `/api/v1/admin/maintenance/jobs` | Bearer (admin) | — | `{total_jobs, clearable_jobs, db_size_mb}` |
| POST | `/api/v1/admin/maintenance/jobs/clear` | Bearer (admin) | — | `{deleted: int}` |
| GET | `/api/v1/admin/maintenance/chat` | Bearer (admin) | — | `{total_sessions, total_turns, inactive_7d, inactive_30d, inactive_90d}` |
| POST | `/api/v1/admin/maintenance/chat/preview` | Bearer (admin) | `{days: 7\|30\|90}` | `{count: int}` |
| POST | `/api/v1/admin/maintenance/chat/delete` | Bearer (admin) | `{days: 7\|30\|90}` | `{deleted: int}` |
| GET | `/api/v1/admin/logs` | Bearer (admin) | — | `{errors: ErrorEntry[], audits: AuditEntry[]}` |

### Health (preserve as-is)

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/health` | None | `{"status": "ok"}` |

---

### SSE Event Schemas

**Job progress stream** (`/api/v1/jobs/{id}/stream`):

| Event name | Data fields |
|---|---|
| `job_started` | `{}` |
| `progress` | `{cases_completed: int, cases_failed: int}` |
| `job_complete` | `{results_url: str, summary: {total, passed, failed}}` |
| `job_failed` | `{error: str, summary: dict}` |
| `:` (comment) | keepalive, no data |

**Chat turn stream** (`/api/v1/chat-sessions/{id}/turns/{turn_id}/stream`):

| Event name | Data fields |
|---|---|
| `connector_token` | `{content: string}` |
| `evaluating` | `{}` |
| `evaluator_event` | `{event_type: "score_update"\|"warning"\|"insight"\|"diagnostic"\|"final", payload: object}` |
| `turn_complete` | `{turn_id, assembled_response, connectorTokens, evaluatorTokens}` |
| `turn_failed` | `{turn_id, error_stage, error_details}` |
| `:` (comment) | keepalive every 15 s |

---

### Response Type Schemas

```typescript
// ---- Auth ----
interface UserContext {
  oid: string;
  email: string;
  display_name: string;
  role: 'admin' | 'user';
}

// ---- Jobs ----
type JobStatus = 'draft' | 'queued' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled';
type SubmissionSource = 'wizard' | 'api';

interface JobListItem {
  job_id: string;
  job_name: string;
  description: string | null;
  status: JobStatus;
  created_by: string;
  created_at: string;        // ISO 8601
  started_at: string | null;
  completed_at: string | null;
  harness_version: string;
  connector_name: string | null;
  evaluation_agent_name: string | null;
  total_utterance_count: number | null;
  processed_count: number;
  failed_count: number;
  submission_source: SubmissionSource;
  source_system: string | null;
  product_name: string | null;
  feature_name: string | null;
  error_details: string | null;
}

interface Job extends JobListItem {
  source_csv_filename: string | null;
  connector_id: string | null;
  connector_endpoint_url: string | null;
  connector_auth_descriptor: AuthDescriptorMasked | null;
  connector_timeout_seconds: number | null;
  connector_expects_per_row_password: boolean | null;
  evaluation_agent_id: string | null;
  evaluator_endpoint_url: string | null;
  evaluator_auth_descriptor: AuthDescriptorMasked | null;
  evaluator_timeout_seconds: number | null;
  evaluator_declared_scoring_dimensions: string[] | null;
}

interface WizardState {
  job_id: string;
  step: 1 | 2 | 3 | 4 | 5;
  job_name: string | null;
  description: string | null;
  csv_uploaded: boolean;
  utterance_count: number | null;
  connector_id: string | null;
  connector_name: string | null;
  evaluator_id: string | null;
  evaluator_name: string | null;
  start_ready: boolean;
  reason: string | null;
}

interface CsvUploadResult {
  success: boolean;
  utterances_created: number;
  distinct_test_ids: number;
  warnings: string[];
  errors: CsvErrorEntry[];
}

interface CsvErrorEntry {
  category: string;
  message: string;
  row: number | null;
  column: string | null;
}

// ---- Results ----
interface EvaluationScore {
  parameter_name: string;
  score: number | string;
  reasoning: string;
  verdict: 'pass' | 'fail' | 'warn' | null;
}

interface ResultRow {
  result_id: string;
  utterance_id: string;
  row_index: number;
  test_id: string;
  utterance_text: string;
  evaluation_verdict: 'pass' | 'fail' | 'warn' | null;
  evaluation_scores: EvaluationScore[];
  utterance_intent: string | null;
  error_status: 'failed' | 'cancelled' | null;
  error_stage: string | null;
  error_details: string | null;
  evaluation_timestamp: string | null;
  connector_token_count: number | null;
  evaluator_token_count: number | null;
  total_token_count: number | null;
  // Expanded trace fields (present in /results/{result_id})
  raw_chatbot_response?: object | null;
  normalized_contract?: object | null;
  result_metadata?: object | null;
  harness_annotations?: { unexpected_score_dimensions: string[] } | null;
}

// ---- Analytics ----
interface VerdictCount { verdict: string; count: number; pct: number; }
interface HistogramBucket {
  index: number; raw_low: number; raw_high: number;
  count: number; sigma_low: number; sigma_high: number;
}
interface ParameterStats {
  parameter_name: string; parameter_id: string;
  mean: number; median: number; min: number; max: number;
  range: number; stddev: number;
  histogram_buckets: HistogramBucket[];
  verdict_distribution: VerdictCount[] | null;
  verdict_coverage: number | null;
  is_unexpected: boolean; no_data: boolean;
}
interface IntentStats {
  intent: string; mean_score: number | null; count: number;
  verdict_distribution: VerdictCount[] | null;
}
interface RunAnalytics {
  overall_mean_score: number | null;
  overall_verdict_distribution: VerdictCount[];
  parameters: ParameterStats[];
  evaluated_count: number;
  error_count: number;
  intent_breakdown: IntentStats[];
}

// ---- Connectors / Evaluators ----
type AuthMode = 'none' | 'bearer' | 'basic' | 'api-key-header' | 'client-credentials';

interface AuthDescriptorMasked {
  mode: AuthMode;
  headerName?: string; username?: string;
  tokenUrl?: string; clientId?: string; scope?: string; audience?: string;
  credential?: '••••••••'; password?: '••••••••'; clientSecret?: '••••••••';
}

interface ConnectorItem {
  connector_id: string; display_name: string; description: string | null;
  endpoint_url: string; auth_descriptor: AuthDescriptorMasked;
  timeout_seconds: number; expects_per_row_password: boolean;
  supports_sse: boolean; archived: boolean;
  created_at: string; updated_at: string; archived_at: string | null;
}
type ConnectorDetail = ConnectorItem;

interface ConnectorPayload {
  display_name: string; description?: string; endpoint_url: string;
  auth_mode: AuthMode; token?: string; header_name?: string; header_value?: string;
  username?: string; password?: string; token_url?: string;
  client_id?: string; client_secret?: string; scope?: string; audience?: string;
  timeout_seconds?: number; expects_per_row_password?: boolean; supports_sse?: boolean;
  replace_credential?: boolean;
}

interface EvaluatorItem extends Omit<ConnectorItem, 'expects_per_row_password'> {
  declared_scoring_dimensions: string[];
}
interface EvaluatorPayload extends Omit<ConnectorPayload, 'expects_per_row_password'> {
  dimensions?: string;   // newline-separated
}

interface TestResult {
  ok: boolean; category: string | null;
  status_code: number | null; detail: string; warning: string | null;
}

// ---- Chat ----
interface ChatSessionListItem {
  chat_session_id: string; session_name: string; owner_oid: string;
  created_at: string; connector_name: string | null;
  evaluator_name: string | null; turn_count: number;
}

interface ChatTurnResult {
  assembled_response: string | null; normalized_contract: object | null;
  final_evaluation_result: object | null;
  error_stage: string | null; error_details: string | null;
}

interface EvaluationEvent {
  event_id: string; event_type: string;
  payload: object; sequence_number: number; created_at: string;
}

interface ChatTurn {
  turn_id: string; session_id: string; user_message: string;
  status: 'in_progress' | 'completed' | 'failed';
  created_at: string; completed_at: string | null;
  result: ChatTurnResult | null;
  evaluation_events: EvaluationEvent[];
}

interface ChatSessionDetail {
  chat_session_id: string; session_name: string;
  owner_oid: string; created_at: string;
  connector_id: string | null; connector_name: string | null;
  connector_endpoint_url: string | null; connector_auth_descriptor: AuthDescriptorMasked | null;
  evaluator_id: string | null; evaluator_name: string | null;
  evaluator_endpoint_url: string | null; evaluator_auth_descriptor: AuthDescriptorMasked | null;
  evaluator_declared_scoring_dimensions: string[] | null;
  active_conversation_id: string | null;
  turns: ChatTurn[];
}

// ---- Admin ----
interface UserRecord {
  id: string; azure_oid: string | null; email: string;
  display_name: string | null; role: 'admin' | 'user';
  registered_at: string; last_login_at: string | null; linked: boolean;
}

interface ErrorLogEntry { timestamp: string; level: string; logger: string; message: string; }
interface AuditLogEntry { timestamp: string; actor: string; action: string; detail: string; }
```

---

## Angular Application Architecture

### Project scaffold

```bash
ng new eval-brew-app \
  --standalone \
  --routing \
  --style=scss \
  --ssr=false
```

### Core packages

```bash
# Angular Material + CDK
ng add @angular/material

# Auth
npm install @azure/msal-browser @azure/msal-angular

# Markdown (docs viewer + response rendering)
npm install ngx-markdown marked

# API type generation
npm install -D openapi-typescript
```

### Environment files

```typescript
// src/environments/environment.ts
export const environment = {
  production: false,
  apiBaseUrl: '',                     // proxied in dev
  msalTenantId: import.meta.env['NG_APP_MSAL_TENANT_ID'],
  msalClientId: import.meta.env['NG_APP_MSAL_CLIENT_ID'],
  msalApiScope: import.meta.env['NG_APP_MSAL_API_SCOPE'],
};
```

---

### Routing Tree

```
/                          → redirect → /dashboard
/login                     → LoginPageComponent        (no auth guard)
/unauthorised              → UnauthorisedPageComponent  (no auth guard)
/dashboard                 → DashboardPageComponent     (auth guard)
/jobs/new                  → JobWizardComponent         (auth guard)
/jobs/:jobId               → redirect → /jobs/:jobId/step1
/jobs/:jobId/step1         → JobWizardComponent (step 1)
/jobs/:jobId/step2         → JobWizardComponent (step 2)
/jobs/:jobId/step3         → JobWizardComponent (step 3)
/jobs/:jobId/step4         → JobWizardComponent (step 4)
/jobs/:jobId/step5         → JobWizardComponent (step 5)
/jobs/:jobId/detail        → JobDetailPageComponent    (auth guard)
/connectors                → ConnectorListPageComponent (auth guard)
/connectors/new            → ConnectorFormPageComponent (auth guard)
/connectors/:id/edit       → ConnectorFormPageComponent (auth guard)
/evaluators                → EvaluatorListPageComponent (auth guard)
/evaluators/new            → EvaluatorFormPageComponent (auth guard)
/evaluators/:id/edit       → EvaluatorFormPageComponent (auth guard)
/chat/sessions             → ChatSessionListPageComponent (auth guard)
/chat/sessions/new         → ChatWizardComponent          (auth guard)
/chat/sessions/:id         → ChatInterfacePageComponent   (auth guard)
/chat/sessions/:id/analytics → ChatAnalyticsPageComponent (auth guard)
/admin                     → redirect → /admin/users
/admin/users               → UserManagementPageComponent  (admin guard)
/admin/users/new           → UserNewPageComponent          (admin guard)
/admin/maintenance         → AdminMaintenancePageComponent (admin guard)
/admin/chat-maintenance    → AdminChatMaintenancePageComponent (admin guard)
/admin/logs                → AdminLogsPageComponent        (admin guard)
/docs/:slug                → DocsViewerPageComponent       (auth guard)
/release-notes             → ReleaseNotesPageComponent     (auth guard)
```

All routes under auth guard use `MsalGuard`. Admin routes additionally use a custom `adminGuard` (functional `CanActivateFn` that reads role from `AuthService.user()`).

---

### Services

#### `AuthService` — `src/app/core/auth/auth.service.ts`

```typescript
readonly user = signal<UserContext | null>(null);
readonly isAdmin = computed(() => this.user()?.role === 'admin');
readonly isLoggedIn = computed(() => this.user() !== null);

loadUser(): Observable<UserContext>     // GET /api/v1/auth/me; sets user signal
logout(): void                          // MSAL logout + signal clear
acquireToken(): Promise<string>         // acquireTokenSilent; returns access token string
```

#### `ApiService` — `src/app/core/api/api.service.ts`

Base wrapper over `HttpClient`. All methods return typed Observables. Token attached by `AuthInterceptor`.

```typescript
get<T>(path: string, params?: HttpParams): Observable<T>
post<T>(path: string, body: unknown): Observable<T>
put<T>(path: string, body: unknown): Observable<T>
patch<T>(path: string, body: unknown): Observable<T>
delete<T>(path: string): Observable<T>
postForm<T>(path: string, form: FormData): Observable<T>
downloadBlob(path: string, params?: HttpParams): Observable<Blob>
```

Error shape: FastAPI returns `{detail: string}` on 4xx/5xx. `ApiService` normalises to `{message: string, status: number}`.

#### `JobService` — `src/app/features/jobs/job.service.ts`

```typescript
list(params: JobListParams): Observable<{jobs: JobListItem[], total: number, pages: number}>
getOverview(): Observable<OverviewResponse>
get(jobId: string): Observable<Job>
getStatus(jobId: string): Observable<JobStatusResponse>
getWizardState(jobId: string): Observable<WizardState>
create(payload: {job_name: string, description?: string}): Observable<{job_id: string}>
updateName(jobId: string, payload: {job_name: string, description?: string}): Observable<void>
uploadCsv(jobId: string, file: File): Observable<CsvUploadResult>
setConnector(jobId: string, connectorId: string): Observable<void>
setEvaluator(jobId: string, evaluatorId: string): Observable<void>
start(jobId: string): Observable<{job_id: string, status: string}>
clone(jobId: string): Observable<{job_id: string}>
cancel(jobId: string): Observable<void>
delete(jobId: string): Observable<void>
getResults(jobId: string, params: ResultFilterParams): Observable<{results: ResultRow[], total: number, pages: number}>
getResult(jobId: string, resultId: string): Observable<ResultRow>
getAnalytics(jobId: string): Observable<RunAnalytics>
export(jobId: string, format: 'csv' | 'json'): Observable<Blob>
clearTerminal(): Observable<{deleted: number}>
clearAll(): Observable<{deleted: number}>
```

#### `JobStreamService` — `src/app/features/jobs/job-stream.service.ts`

Encapsulates `EventSource` for the job progress SSE. Zoneless-safe: all events write to signals.

```typescript
// Per-job stream — callers inject this and call open/close
readonly status = signal<JobStatus | null>(null);
readonly progress = signal<{completed: number, failed: number} | null>(null);
readonly terminal = signal<JobSseTerminalEvent | null>(null);
readonly error = signal<string | null>(null);

open(jobId: string): void     // creates EventSource; wires all event listeners to signals
close(): void                  // closes EventSource; called on component destroy via DestroyRef
```

#### `ConnectorService` — `src/app/features/connectors/connector.service.ts`

```typescript
list(params: {q?: string, state?: 'active'|'archived'|'all'}): Observable<{connectors: ConnectorItem[]}>
get(id: string): Observable<ConnectorDetail>
create(payload: ConnectorPayload): Observable<ConnectorDetail>
update(id: string, payload: ConnectorPayload): Observable<ConnectorDetail>
archive(id: string): Observable<void>
restore(id: string): Observable<void>
delete(id: string): Observable<void>
testNew(payload: ConnectorPayload): Observable<TestResult>
testExisting(id: string): Observable<TestResult>
```

#### `EvaluatorService` — `src/app/features/evaluators/evaluator.service.ts`

Symmetric to `ConnectorService`. Additional field: `dimensions: string` (newline-separated).

#### `ChatSessionService` — `src/app/features/chat/chat-session.service.ts`

```typescript
list(): Observable<{sessions: ChatSessionListItem[]}>
get(id: string): Observable<ChatSessionDetail>
create(payload: CreateChatSessionPayload): Observable<{chat_session_id: string}>
delete(id: string): Observable<void>
submitTurn(sessionId: string, message: string): Observable<{turn_id: string}>
getAnalytics(sessionId: string, params: TurnFilterParams): Observable<ChatAnalyticsResponse>
export(sessionId: string, format: 'csv'|'json'): Observable<Blob>
clearErrors(): Observable<{deleted: number}>
clearAll(): Observable<{deleted: number}>
```

#### `ChatStreamService` — `src/app/features/chat/chat-stream.service.ts`

```typescript
readonly connectorTokenBuffer = signal<string>('');   // accumulates token chunks
readonly evaluating = signal<boolean>(false);
readonly evaluatorEvents = signal<EvaluationEvent[]>([]);
readonly turnComplete = signal<TurnCompletePayload | null>(null);
readonly turnFailed = signal<TurnFailedPayload | null>(null);
readonly streamError = signal<string | null>(null);

open(sessionId: string, turnId: string): void
close(): void
reset(): void    // clears all signals; call before each new turn
```

`connector_token` listener: `this.connectorTokenBuffer.update(buf => buf + event.content)`.  
`evaluator_event` listener: `this.evaluatorEvents.update(list => [...list, parsed])`.  
`turn_complete` / `turn_failed` listeners: set terminal signal → `close()` automatically.

#### `AdminService` — `src/app/features/admin/admin.service.ts`

```typescript
listUsers(): Observable<{users: UserRecord[]}>
createUser(payload: {email: string, role: string, display_name?: string}): Observable<UserRecord>
changeRole(id: string, role: string): Observable<void>
removeUser(id: string): Observable<void>
getJobMaintenanceStats(): Observable<JobMaintenanceStats>
clearJobs(): Observable<{deleted: number}>
getChatMaintenanceStats(): Observable<ChatMaintenanceStats>
previewChatDelete(days: 7|30|90): Observable<{count: number}>
deleteChatSessions(days: 7|30|90): Observable<{deleted: number}>
getLogs(): Observable<{errors: ErrorLogEntry[], audits: AuditLogEntry[]}>
```

#### `NotificationService` — `src/app/core/notification/notification.service.ts`

Replaces the Jinja2 flash message system. Uses Angular Material `MatSnackBar`.

```typescript
success(message: string): void
error(message: string): void
info(message: string): void
```

#### `ExportService` — `src/app/core/export/export.service.ts`

```typescript
downloadBlob(blob: Blob, filename: string): void
    // Creates <a> with object URL, triggers click, revokes URL
```

---

### Auth Wiring — `app.config.ts`

```typescript
export const appConfig: ApplicationConfig = {
  providers: [
    provideZonelessChangeDetection(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
    provideAnimationsAsync(),
    provideMarkdown(),
    // MSAL
    {
      provide: MSAL_INSTANCE,
      useFactory: msalInstanceFactory,
    },
    {
      provide: MSAL_GUARD_CONFIG,
      useFactory: msalGuardConfigFactory,
    },
    MsalService,
    MsalGuard,
    MsalBroadcastService,
  ],
};
```

**`authInterceptor`** (functional `HttpInterceptorFn`):
- Skip if URL does not start with `/api/`
- `acquireTokenSilent({account, scopes: [environment.msalApiScope]})` → attach `Authorization: Bearer <token>`
- On `InteractionRequiredAuthError`: redirect to login via `MsalService.acquireTokenRedirect`

**`errorInterceptor`** (functional `HttpInterceptorFn`):
- HTTP 401 → trigger MSAL login
- HTTP 403 → navigate to `/unauthorised`
- HTTP 4xx/5xx → extract `detail` from JSON body → `NotificationService.error(...)`

---

### App Shell — `AppComponent` (`src/app/app.component.ts`)

```typescript
readonly user = inject(AuthService).user;
readonly isAdmin = inject(AuthService).isAdmin;

// On init:
// 1. msal.instance.initialize()
// 2. msal.instance.handleRedirectPromise() → if result, call AuthService.loadUser()
// 3. broadcastService.inProgress$ filter NONE → if account, call AuthService.loadUser()
```

Template: `<app-nav />` + `<router-outlet />`.

---

## Component Catalog — Per Screen

### 1. Auth Screens

#### `LoginPageComponent` (`/login`)

No API calls. Template: full-page card with "Sign in with Microsoft" button → `MsalService.loginRedirect()`. Shown when `MsalGuard` redirects.

#### `UnauthorisedPageComponent` (`/unauthorised`)

Static message. Link: "Try a different account" → triggers `MsalService.logout()`.

---

### 2. Navigation — `NavComponent`

Signals: `user = inject(AuthService).user`, `isAdmin = inject(AuthService).isAdmin`

**Left nav groups (mirrors base.html exactly):**

| Group | Items |
|---|---|
| Dashboard | → `/dashboard` |
| Job Sessions | All Job Sessions → `/dashboard` · New Job → `/jobs/new` |
| Chat Sessions | All Chat Sessions → `/chat/sessions` · New Chat Session → `/chat/sessions/new` |
| Connectors | View All → `/connectors` · Register New → `/connectors/new` |
| Evaluators | View All → `/evaluators` · Register New → `/evaluators/new` |
| Documentation | About · CSV Upload Guide · Connector Dev Guide · Evaluator Dev Guide · Solution Architecture · Configuration Setup · Release Notes |
| Admin *(admin only)* | Job Maintenance · Chat Maintenance · Users · Logs |

**Right side:** role badge chip, `user().display_name`, Sign Out button → `AuthService.logout()`.

Implemented using `MatSidenavContainer` + `MatNavList` with `MatExpansionPanel` for dropdowns.

---

### 3. Dashboard — `DashboardPageComponent` (`/dashboard`)

**Signals:**
```typescript
readonly jobs = signal<JobListItem[]>([]);
readonly total = signal<number>(0);
readonly loading = signal<boolean>(false);
readonly filterParams = signal<JobListParams>({sort: 'created_at', dir: 'desc'});
readonly overview = resource({ loader: () => firstValueFrom(jobService.getOverview()) });
```

**Live polling:** `interval(3000).pipe(switchMap(() => jobService.list(this.filterParams())))` active while any job has status `queued | running | cancelling`. Subscription managed via `takeUntilDestroyed(destroyRef)`.

**Child components:**

#### `OverviewSectionComponent`

Input: `overview: OverviewResponse`. Displays KPI tiles: Total Jobs, Total Sessions, Total Utterances, Total Turns. Activity table with type badge (Job/Chat), name link, status badge, connector, last activity, count, actions (View Report / Open Chat / Download CSV / Delete).

#### `JobListFilterComponent`

Output: `filtersChange: EventEmitter<JobListParams>`.
Form fields:
- `q` — text search input (debounce 400 ms)
- Status checkboxes: draft / queued / running / cancelling / completed / failed / cancelled (multi-select `MatCheckbox` group)

#### `JobListTableComponent`

Input: `jobs: JobListItem[]`, `total: number`.
Signals: `sortField`, `sortDir`, `page`.

**Table columns** (all sortable via `MatSortHeader`):

| Column | Binding |
|---|---|
| Job Name | link → `/jobs/{id}/detail` |
| Status | `JobStatusBadgeComponent` |
| Created By | `job.created_by` |
| Created | `job.created_at` (formatted) |
| Started | `job.started_at` |
| Duration | computed from start/complete |
| Connector | `job.connector_name` |
| Version | `job.harness_version` |
| Utterances | `job.processed_count / job.total_utterance_count` |
| Failed | `job.failed_count` |
| Actions | `JobRowActionsComponent` |

**Page banner actions:** "Clear Errors (N)" → `jobService.clearTerminal()`, "Clear All (N)" → `jobService.clearAll()`, "+ New Job" → `router.navigate(['/jobs/new'])`.

#### `JobStatusBadgeComponent`

Input: `status: JobStatus`. Maps to `MatChip` with colour class (`draft`→grey, `queued`→blue, `running`→amber+spinner, `cancelling`→orange, `completed`→green, `failed`→red, `cancelled`→grey).

#### `JobRowActionsComponent`

Input: `job: JobListItem`. Renders conditionally:
- `draft`: "Resume" link → `/jobs/{id}/step1`
- `failed | cancelled | completed`: "Clone & Rerun" button → `jobService.clone(id)` → navigate to new `/jobs/{newId}/step1`
- `failed | cancelled | completed`: "Delete" button → confirm dialog (`MatDialog`) → `jobService.delete(id)`

---

### 4. Job Creation Wizard — `JobWizardComponent` (`/jobs/new`, `/jobs/:jobId/step1..5`)

Uses `MatStepper` (linear, vertical on mobile / horizontal on desktop).

**On init with existing `jobId`:** fetch `jobService.getWizardState(jobId)` → set stepper to `WizardState.step - 1`.

**On init without `jobId`:** call `jobService.create({job_name: 'Untitled'})` → navigate to `/jobs/{id}/step1`.

Each step is a separate `@Component` used as a `MatStep` content via `ng-template`.

#### `WizardStep1NameComponent`

Form fields:
- `job_name` (required, text, max 255)
- `description` (optional, textarea, 3 rows)

On "Next": `jobService.updateName(jobId, {job_name, description})` → stepper.next() → navigate `/jobs/{id}/step2`.

Progress: 20% `MatProgressBar`.

#### `WizardStep2CsvComponent`

Form:
- File input (`accept=".csv"`) — `required`

On file select: immediate preview (filename, estimated row count). On "Upload & Validate": `jobService.uploadCsv(jobId, file)` → show `CsvUploadResult`.

Success: show utterance count + distinct test IDs → "Next" enabled → navigate `/jobs/{id}/step3`.  
Error: render `errors[]` as `MatList` (row number, column, message). File input re-enabled.

Warning messages shown as `MatChip` list above the table.

Progress: 40%.

#### `WizardStep3ConnectorComponent`

On init: `connectorService.list({state: 'active'})`. Shows all active connectors (includes non-SSE ones — job wizard supports all auth modes).

Form: `connector_id` as `MatRadioGroup`. Each option card shows: connector name, endpoint URL, auth mode badge, timeout, expects-per-row-password indicator.

"Test Connection" button: `connectorService.testExisting(id)` → inline `ConnectionTestResultComponent`.

On "Next": `jobService.setConnector(jobId, connectorId)` → navigate `/jobs/{id}/step4`.

Progress: 60%.

#### `WizardStep4EvaluatorComponent`

Same pattern as Step 3. `evaluatorService.list({state: 'active'})`. Each card shows: evaluator name, endpoint URL, auth mode badge, timeout, scoring dimensions list.

"Test" button: `evaluatorService.testExisting(id)` → inline result.

On "Next": `jobService.setEvaluator(jobId, evaluatorId)` → navigate `/jobs/{id}/step5`.

Progress: 80%.

#### `WizardStep5ReviewComponent`

On init: `jobService.getWizardState(jobId)`.

Read-only definition list (mirrors existing `wizard/step5.html`):
- Job Name, Description
- CSV: filename, utterance count, distinct test IDs
- Connector: name, endpoint, auth mode, per-row-password indicator
- Evaluator: name, endpoint, auth mode, scoring dimensions

"Start Job" button: disabled when `WizardState.start_ready === false` (shows `reason`). On click: `jobService.start(jobId)` → navigate `/jobs/{id}/detail`.

Progress: 100%.

---

### 5. Job Detail — `JobDetailPageComponent` (`/jobs/:jobId/detail`)

On init: `jobService.get(jobId)` → populates all signals.

Signals:
```typescript
readonly job = signal<Job | null>(null);
readonly activeTab = signal<'analytics'|'results'>('analytics');
```

**Page actions** (top right):
- Print → `window.print()`
- Download CSV → `jobService.export(id, 'csv')` → `ExportService.downloadBlob(...)`
- Download JSON → `jobService.export(id, 'json')` → `ExportService.downloadBlob(...)`
- Cancel → `MatDialog` confirm → `jobService.cancel(id)`
- Delete → `MatDialog` confirm → `jobService.delete(id)` → navigate `/dashboard`

**Progress banner:** shown when `job().status` is `queued | running | cancelling`. Houses `JobProgressComponent`.

#### `JobProgressComponent`

Uses `JobStreamService`. On init: `jobStreamService.open(jobId)`.

Template: `MatProgressBar` with `value = (progress().completed / job().total_utterance_count) * 100`. Live text: "N / M processed · K failed". Listens on `terminal` signal → on `job_complete`/`job_failed`: reload job → hide banner.

Cleanup: `jobStreamService.close()` on `DestroyRef`.

#### `JobAnalyticsTabComponent`

**Session Details card** (definition list, 2-column grid):

Left column:
- Job ID, Job Name, Description, Status (badge), Created By, Created At, Started At, Completed At, Version, Error Details, Source CSV

Right column (connector + evaluator snapshots):
- Connector Name, Connector ID, Connector Endpoint, Connector Auth (masked), Connector Timeout, Per-row Password
- Evaluator Name, Evaluator ID, Evaluator Endpoint, Evaluator Auth (masked), Evaluator Timeout
- Scoring Dimensions (chip list)

**Token tiles:** 3 `MatCard` tiles — Connector Tokens, Evaluator Tokens, Total Tokens. `MatTooltip` on each with definition.

**Analytics data:** on init, `jobService.getAnalytics(jobId)` → `RunAnalytics`.

**`ParameterBreakdownComponent`** (one instance per `analytics.parameters[]`):

Input: `stats: ParameterStats`.

Contains:
- `ParameterStatTilesComponent`: 6 stat tiles (Mean, Median, Min, Max, Range, σ) each with `MatTooltip`
- `HistogramComponent`: bar chart using `HistogramBucket[]`; renders sigma band overlay. Implementation: `<canvas>` with manual drawing or minimal chart lib (Chart.js via `ng2-charts`, or D3, or raw SVG). Each bucket is a `<rect>`; sigma band is an overlay `<rect>` with low opacity.
- `VerdictDistributionPillsComponent`: 3 pills (PASS / WARN / FAIL) with count and percentage

**`IntentBreakdownTableComponent`**:

Input: `intents: IntentStats[]`.

Columns: Intent | Mean Score (with `MatProgressBar`) | Count | Verdict Distribution (3 mini pills).

#### `JobResultsTabComponent`

**`ResultsFilterFormComponent`**:

Fields:
- `q` text search (debounce 400 ms)
- `verdict` checkboxes: pass / warn / fail
- `error_only` checkbox
- `test_id` checkboxes (distinct test IDs from results, loaded once)

Output: `filterChange: EventEmitter<ResultFilterParams>`.

**`ResultsTableComponent`**:

Signals: `results = signal<ResultRow[]>([])`, `total = signal(0)`, `page = signal(1)`.

Table columns (sortable):

| Column | Sort key | Notes |
|---|---|---|
| # | `row_index` | |
| testId | `test_id` | |
| Utterance | `utterance_text` | truncated |
| Response | `chatbot_response` | truncated |
| Verdict | `verdict` | `VerdictBadgeComponent` |
| Scores | — | `EvaluationScorePillsComponent` |
| Error | `error_status` | shown if errored |

**`ResultTraceExpansionComponent`** (expandable row):

Shows: full utterance text, chatbot response (markdown via `ngx-markdown`), verdict, intent, error stage + details, per-dimension scores with reasoning, raw chatbot response (`<pre>`), normalized contract (`<pre>`), evaluation scores JSON (`<pre>`), result metadata (`<pre>`), harness annotations (`<pre>`). Copy-to-clipboard button on each `<pre>` block.

---

### 6. Connector Registry

#### `ConnectorListPageComponent` (`/connectors`)

Signals: `connectors = signal<ConnectorItem[]>([])`, `filter = signal<{q: string, state: string}>({q: '', state: 'active'})`.

Filter bar: state tabs (Active / Archived / All), search input (debounce 400 ms).

**Table columns:**

| Column | Notes |
|---|---|
| Display Name | |
| Endpoint | truncated URL |
| Auth | auth mode badge |
| Timeout | `N s` |
| Per-row pwd | boolean chip |
| SSE | boolean chip |
| State | Active / Archived badge |
| Updated | formatted date |
| Actions | |

**Row actions (conditional):**
- Edit → `/connectors/{id}/edit`
- Archive → `connectorService.archive(id)` (shown if `!archived`)
- Restore → `connectorService.restore(id)` (shown if `archived`)
- Delete → confirm dialog → `connectorService.delete(id)` (409 if in use → `NotificationService.error(...)`)

Page header action: "+ Register New Connector" → `/connectors/new`.

#### `ConnectorFormPageComponent` (`/connectors/new`, `/connectors/:id/edit`)

On edit: fetch `connectorService.get(id)` → populate `FormGroup`. On new: empty form.

**Form fields** (all as `ReactiveFormsModule`):

| Field | Control | Validators | Notes |
|---|---|---|---|
| `display_name` | `FormControl<string>` | required, maxLength(255) | |
| `description` | `FormControl<string\|null>` | — | |
| `endpoint_url` | `FormControl<string>` | required, URL pattern | |
| `auth_mode` | `FormControl<AuthMode>` | required | `MatSelect` |
| `token` | `FormControl<string\|null>` | required if bearer | `type=password` |
| `header_name` | `FormControl<string\|null>` | required if api-key-header | |
| `header_value` | `FormControl<string\|null>` | required if api-key-header | `type=password` |
| `username` | `FormControl<string\|null>` | required if basic | |
| `password` | `FormControl<string\|null>` | required if basic | `type=password` |
| `token_url` | `FormControl<string\|null>` | required if client-credentials, URL | |
| `client_id` | `FormControl<string\|null>` | required if client-credentials | |
| `client_secret` | `FormControl<string\|null>` | required if client-credentials | `type=password` |
| `scope` | `FormControl<string\|null>` | — | client-credentials optional |
| `audience` | `FormControl<string\|null>` | — | client-credentials optional |
| `timeout_seconds` | `FormControl<number>` | min(1), max(300) | default 30 |
| `expects_per_row_password` | `FormControl<boolean>` | — | `MatSlideToggle` |
| `supports_sse` | `FormControl<boolean>` | — | `MatSlideToggle` |
| `replace_credential` | `FormControl<boolean>` | — | edit only; shown when `auth_mode !== 'none'` |

**`AuthCredentialFieldsComponent`** (shared between connector and evaluator forms):

Input: `authMode: AuthMode`, `isEdit: boolean`, `replaceCredential: boolean`.
Shows/hides credential sections via `@if` on `authMode`. Password fields have show/hide toggle buttons.

**`ConnectionTestPanelComponent`**:

Signal: `testResult = signal<TestResult | null>(null)`, `testing = signal(false)`.

"Test Connection" button → collects current form values → `connectorService.testNew(payload)` → displays result (ok/fail badge, HTTP status, detail text, optional warning).

On save: `connectorService.create(payload)` or `connectorService.update(id, payload)` → navigate to `/connectors` with `next` param or referrer.

#### `EvaluatorListPageComponent` / `EvaluatorFormPageComponent`

Mirrors connector list and form. Differences:
- No `expects_per_row_password` field.
- `DimensionsFieldComponent`: `<textarea>` for `dimensions` (one per line). On parse: splits on newlines, trims, filters empty. Displayed as `MatChip` list preview.
- `testExisting` calls `evaluatorService.testExisting(id)`.

---

### 7. Chat Sessions

#### `ChatSessionListPageComponent` (`/chat/sessions`)

Signals: `sessions = signal<ChatSessionListItem[]>([])`.

On init: `chatSessionService.list()`.

**Page banner actions (admin only):**
- Clear Errors → `chatSessionService.clearErrors()`
- Clear All → confirm → `chatSessionService.clearAll()`
- "+ New Chat Session" → `/chat/sessions/new`

**Table columns:**

| Column | Notes |
|---|---|
| Session Name | link → `/chat/sessions/{id}` |
| Connector | `connector_name` |
| Evaluator | `evaluator_name` |
| Turns | `turn_count` |
| Created | formatted date |
| Actions | |

**Row actions:**
- Delete → confirm dialog → `chatSessionService.delete(id)`
- (Admin only) Admin Delete → no confirm

#### `ChatWizardComponent` (`/chat/sessions/new`) — 5-step wizard

Uses `MatStepper`. Stores partial state in component signals (no server round-trips between steps; single `POST /api/v1/chat-sessions` on final step).

**Step 1 — `ChatWizardStep1NameComponent`**

Form: `session_name` (required, text). Signal: `name = signal<string>('')`.

**Step 2 — `ChatWizardStep2ConnectorComponent`**

On init: `connectorService.list({state: 'active'})` **filtered to `supports_sse === true`**.

> Note: The wizard must show only SSE-capable connectors. Non-SSE connectors are excluded. This is critical — a non-SSE connector cannot stream tokens to the chat interface.

Form: radio group. Card per connector: name, endpoint, auth mode badge, timeout.

"Test Connection" → `connectorService.testExisting(id)` → inline `ConnectionTestResultComponent`.

Signal: `selectedConnectorId = signal<string | null>(null)`.

**Step 3 — `ChatWizardStep3CredentialsComponent`**

Form fields:

| Field | Control | Validators | Notes |
|---|---|---|---|
| `test_id` | `FormControl<string>` | required | Tester identifier |
| `password` | `FormControl<string>` | required | `type=password` with show/hide toggle |

Signals: `testId = signal<string>('')`, `password = signal<string>('')`.

**Step 4 — `ChatWizardStep4EvaluatorComponent`**

On init: `evaluatorService.list({state: 'active'})` **filtered to `supports_sse === true`**.

Same card pattern as Step 2. Each card shows: name, endpoint, auth mode badge, timeout, scoring dimensions chip list.

Signal: `selectedEvaluatorId = signal<string | null>(null)`.

**Step 5 — `ChatWizardStep5ReviewComponent`**

Read-only review:
- Session Name
- Connector: name
- Test ID: masked (`test_id.substring(0, 3) + '***'`)
- Evaluator: name

"Confirm & Start Chat" → `chatSessionService.create({session_name, connector_id, evaluator_id, test_id, password})` → navigate `/chat/sessions/{id}`.

#### `ChatInterfacePageComponent` (`/chat/sessions/:id`)

On init: `chatSessionService.get(id)` → load session with all existing turns.

Layout: two-column (60% / 40% split using CSS `display:grid`).

**Header actions:**
- Analytics → `/chat/sessions/{id}/analytics`
- Export JSON → `chatSessionService.export(id, 'json')` → download
- Export CSV → `chatSessionService.export(id, 'csv')` → download
- All Sessions → `/chat/sessions`

**Token pills** (top right):
```typescript
readonly totalTokens = computed(() =>
  session().turns.reduce((s, t) =>
    s + (t.evaluation_events.find(e => e.event_type === 'final')?.payload?.tokens?.total ?? 0), 0));
```
Three pills: Connector Tokens, Evaluator Tokens, Total Tokens — updated reactively via signals.

**`ChatMessageThreadComponent`** (left pane):

Input: `turns: ChatTurn[]`, `streamingContent: string` (live buffer from `ChatStreamService.connectorTokenBuffer`).

Renders each completed turn as:
- User message bubble
- Connector response (assembled_response rendered with `ngx-markdown` + `DomSanitizer`)
- Error indicator (maps `error_stage` → human label):

| `error_stage` | Display label |
|---|---|
| `connector_auth` | Connector (authentication) |
| `connector_stream` | Connector |
| `connector_normalization` | Connector (response validation) |
| `evaluator_auth` | Evaluator (authentication) |
| `evaluator_stream` | Evaluator |
| `server_restart` | Server (restart) |

Live turn: streaming bubble showing `chatStreamService.connectorTokenBuffer()` with cursor blink animation.

**`ChatInputFormComponent`**:

Form: text input + Send button.

Signals: `message = signal<string>('')`, `sending = signal<boolean>(false)`.

On submit:
1. Set `sending(true)`, clear input
2. `chatSessionService.submitTurn(sessionId, message)` → `{turn_id}`
3. `chatStreamService.reset()`
4. `chatStreamService.open(sessionId, turn_id)`
5. Await `chatStreamService.turnComplete()` or `chatStreamService.turnFailed()`
6. Reload session → append completed turn to thread
7. `chatStreamService.close()`, set `sending(false)`

Input disabled while `sending()`.

**`ChatEvaluationPaneComponent`** (right pane):

Two view modes toggled by `MatButtonToggle`:
- **User View** — renders each evaluator `score_update` event as a table (Parameter Name | Score | Reason)
- **Developer View** — renders each event as raw JSON block with `event_type` badge

Signal: `viewMode = signal<'user'|'dev'>('user')`, `displayedTurnIndex = signal<number>(0)`.

Shows evaluation for the currently selected turn (arrows to navigate turns). Live turn: shows events as they arrive via `chatStreamService.evaluatorEvents()`.

"Evaluating..." spinner shown while `chatStreamService.evaluating()` is true.

---

### 8. Chat Analytics — `ChatAnalyticsPageComponent` (`/chat/sessions/:id/analytics`)

On init: `chatSessionService.getAnalytics(id)` → `{analytics: RunAnalytics, turns: TurnRow[]}`.

**Sidebar tabs:** Analytics | Results (same tab pattern as `JobDetailPageComponent`).

**Sidebar actions:**
- Print
- Download CSV → `chatSessionService.export(id, 'csv')`
- Download JSON → `chatSessionService.export(id, 'json')`
- Back to Session → `/chat/sessions/{id}`

**Analytics tab — Session Overview** (definition list):

Session Details: Session Name, Created, Connector (name + auth mode), Evaluator (name + auth mode), Total Turns, Failed Turns, Scoring Dimensions chip list.

Reuses `RunAnalytics` display: `ParameterBreakdownComponent` + `VerdictDistributionPillsComponent` + overall mean score tile. (Reuse same shared components as `JobAnalyticsTabComponent`.)

**Results tab — Turn Explorer**:

**`TurnFilterFormComponent`**: `q` text, `verdict[]` checkboxes, `error_only` checkbox.

**`TurnExplorerTableComponent`**:

Table columns (sortable):

| Column | Sort key |
|---|---|
| # | `turn_index` |
| User Message | |
| Response | |
| Verdict | `VerdictBadgeComponent` |
| Scores | `EvaluationScorePillsComponent` |
| Error | |

Expandable row "Trace": user message (full), error stage + details, assembled response (`<pre>`), normalized contract (`<pre>`), evaluation result (`<pre>`). Copy button on each block.

---

### 9. Admin

#### `UserManagementPageComponent` (`/admin/users`)

On init: `adminService.listUsers()`.

**Table columns:**

| Column | Notes |
|---|---|
| Email | |
| Display Name | |
| Role | `MatChip` colour-coded |
| Status | Linked / Pending badge |
| Registered | formatted date |
| Last Login | formatted date |
| Actions | |

**Inline row actions:**
- Role change: `MatSelect` (admin/user) + Save → `adminService.changeRole(id, role)`
- Remove: confirm dialog → `adminService.removeUser(id)` (blocked if self)

**Page action:** "+ Register User" → `/admin/users/new`.

#### `UserNewPageComponent` (`/admin/users/new`)

Form:

| Field | Control | Validators |
|---|---|---|
| `email` | `FormControl<string>` | required, email |
| `display_name` | `FormControl<string\|null>` | — |
| `role` | `FormControl<string>` | required; `MatSelect` (admin / user) |

On submit: `adminService.createUser(payload)` → navigate `/admin/users`. Cancel → `/admin/users`.

#### `AdminMaintenancePageComponent` (`/admin/maintenance`)

On init: `adminService.getJobMaintenanceStats()`.

Displays: Total Jobs tile, Clearable Jobs tile (highlighted if > 0), DB Size tile.

Action: "Clear Jobs" → confirm dialog → `adminService.clearJobs()` → reload stats → `NotificationService.success(...)`.

#### `AdminChatMaintenancePageComponent` (`/admin/chat-maintenance`)

On init: `adminService.getChatMaintenanceStats()`.

**Stats tiles:** Total Sessions, Total Turns, DB Size.

**Inactivity breakdown table:**

| Row | Inactive Period |
|---|---|
| >7 days | `inactive_7d` count |
| >30 days | `inactive_30d` count |
| >90 days | `inactive_90d` count |

**Preview + delete flow:**

Three "Preview" buttons (7 / 30 / 90 days) → each calls `adminService.previewChatDelete(days)` → shows `{count} sessions would be deleted`. "Confirm Delete" form with hidden `days` → `adminService.deleteChatSessions(days)` → reload stats.

Signal: `previewResult = signal<{days: number, count: number} | null>(null)`.

#### `AdminLogsPageComponent` (`/admin/logs`)

On init: `adminService.getLogs()`.

**Error log table:** Timestamp | Level (`MatChip` colour by level) | Logger (`code` monospace) | Message.

**Audit log table:** Timestamp | Actor | Action (`MatChip`) | Detail.

---

### 10. Documentation Viewer

#### `DocsViewerPageComponent` (`/docs/:slug`)

On init: reads `:slug` → constructs asset URL `/assets/docs/{slug}.md` → `HttpClient.get(url, {responseType: 'text'})` → pass to `ngx-markdown`.

Slug → filename mapping (matches existing `docs_ui/routes.py`):

| Slug | File |
|---|---|
| `about` | `about.md` |
| `csv-upload` | `csv-upload-guide.md` |
| `connector-developer-guide` | `connector-developer-guide.md` |
| `evaluator-developer-guide` | `evaluator-developer-guide.md` |
| `configuration-setup` | `configuration-setup.md` |
| `solution-architecture` | `solution-architecture.md` |

If slug not found: show 404 message with link back to dashboard.

#### `ReleaseNotesPageComponent` (`/release-notes`)

Static page listing release note versions: v3.3, v3.2, v3.1, v2.0, v1.1, v1.0-mvp. Each version is a collapsible `MatExpansionPanel` — content loaded from `/assets/docs/release-notes/v{version}.md` via `ngx-markdown`.

**Docs asset sync** — add to `package.json`:
```json
"prebuild": "node scripts/sync-docs.mjs"
```

`scripts/sync-docs.mjs` copies all `*.md` from `../eval-brew-api/docs/` and `../eval-brew-api/release-notes/` into `src/assets/docs/` at build time.

#### `DocsNavComponent` (shared sidebar in docs pages)

Static list of 6 doc links + Release Notes. Highlights the active route via `RouterLinkActive`.

---

## Shared Components

| Component | Purpose |
|---|---|
| `JobStatusBadgeComponent` | Coloured chip for 7 job states |
| `VerdictBadgeComponent` | pass/warn/fail chip |
| `AuthModeBadgeComponent` | none/bearer/basic/api-key-header/client-credentials chip |
| `EvaluationScorePillsComponent` | Mini score pills per parameter |
| `VerdictDistributionPillsComponent` | PASS/WARN/FAIL count + pct pills |
| `ParameterStatTilesComponent` | 6 stat tiles with tooltips |
| `HistogramComponent` | SVG/Canvas bar chart with sigma band |
| `IntentBreakdownTableComponent` | Intent × score × verdict table |
| `ConnectionTestResultComponent` | ok/fail badge + HTTP status + detail |
| `ConfirmDialogComponent` | Generic `MatDialog` confirm (title, message, confirm label) |
| `TokenPillsComponent` | 3 token count pills |
| `CopyButtonComponent` | Clipboard copy with visual feedback |
| `ParameterBreakdownComponent` | Full parameter analytics card (wraps stat tiles + histogram + verdict pills) |

---

## Implementation Phases

### Phase 1 — REST API Expansion

*Prerequisite for all Angular work. Backend-only changes. Jinja2 UI continues to work throughout.*

- [ ] Create `src/harness/ui/api/v1/` router package mounted at `/api/v1`
- [ ] Implement `auth_router` — `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`
- [ ] Implement `jobs_router` — all 15 endpoints listed above (list, overview, wizard CRUD, detail, results, analytics, cancel, delete, export, batch actions)
  - Paginated list: implement `sort`, `dir`, `page`, `page_size` query params; support all existing filter fields (`status[]`, `q`)
  - `GET /api/v1/jobs/{id}/analytics` — delegates to `analytics.compute_analytics()`
  - `GET /api/v1/jobs/{id}/results` — delegates to `EvaluationResultRepository.get_by_job()`; supports filter params
  - CSV upload: reuse `csv_upload.service.process_upload()`
  - Clone: create a new draft job copying connector/evaluator snapshots from source
- [ ] Implement `connectors_router` — all 9 endpoints; reuse `ConnectorRegistryService`
- [ ] Implement `evaluators_router` — all 9 endpoints; reuse `EvaluatorRegistryService`
- [ ] Implement `chat_sessions_router` — all 10 endpoints; reuse `ChatSessionService`, `TurnService`, `run_turn`, `build_session_export`
- [ ] Implement `admin_router` — all 10 endpoints; reuse `UserRegistrationRepository`, `log_store`
- [ ] Add `CORSMiddleware` to `create_app()` with `HARNESS_FRONTEND_ORIGIN` env var (fallback `http://localhost:4200`)
- [ ] All new endpoints use `require_api_auth` (Bearer JWT); role check for admin endpoints uses `user['role']` from a `UserRegistrationRepository.find_by_oid()` lookup (or embed role in JWT claim if available)
- [ ] Add OpenAPI export step to CI: export `schema/openapi.json`
- [ ] Write integration tests for all new routers in `tests/api/v1/`

**Role resolution for v1 endpoints:** The headless API `require_api_auth` only returns `{oid, name}` — no role. The v1 API serves browser users whose role is stored in `user_registration`. Add a `require_browser_auth` dependency that (1) validates Bearer JWT, (2) loads `UserRegistration` by OID, (3) returns `{oid, email, display_name, role}`. Admin endpoints use `require_browser_auth` + role check.

---

### Phase 2 — Angular 21 Project Bootstrap

*Can begin as soon as Phase 1's first endpoints are available. Run in parallel with Phase 1 completion.*

- [ ] Scaffold project: `ng new eval-brew-app --standalone --routing --style=scss --ssr=false`
- [ ] Configure zoneless CD: `provideZonelessChangeDetection()` in `app.config.ts`; remove `zone.js` from `polyfills` in `angular.json`
- [ ] Set TypeScript to `~5.9.x`
- [ ] Install `@angular/material`, `@azure/msal-browser`, `@azure/msal-angular`, `ngx-markdown`, `marked`
- [ ] Install devDependencies: `openapi-typescript`, `@testing-library/angular`, `jest-preset-angular`
- [ ] Configure MSAL: `msalInstanceFactory`, `msalGuardConfigFactory` using environment variables
- [ ] Implement `AuthInterceptor` (functional), `ErrorInterceptor` (functional)
- [ ] Implement `AuthService`, `NotificationService`, `ExportService`, `ApiService`
- [ ] Create `app.routes.ts` — full routing tree with lazy-loaded feature routes
- [ ] Create `AppComponent` — MSAL init + redirect promise handling
- [ ] Create `NavComponent` — full nav matching `base.html` structure
- [ ] Create `LoginPageComponent`, `UnauthorisedPageComponent`
- [ ] Configure `proxy.conf.json` (`/api → localhost:7071`)
- [ ] Add `generate:api` npm script (openapi-typescript)
- [ ] Set up CI: `npm ci → tsc --noEmit → ng build`
- [ ] Set up environment files for dev/prod

---

### Phase 3 — Angular Feature Implementation

*Implement in dependency order. Each feature is independently committable.*

**3.1 Shared components (Days 1–3)**
- [ ] `JobStatusBadgeComponent`, `VerdictBadgeComponent`, `AuthModeBadgeComponent`
- [ ] `VerdictDistributionPillsComponent`, `EvaluationScorePillsComponent`
- [ ] `ParameterStatTilesComponent` (with `MatTooltip` per stat)
- [ ] `HistogramComponent` (SVG bar chart with sigma band overlay)
- [ ] `ConnectionTestResultComponent`, `ConfirmDialogComponent`
- [ ] `TokenPillsComponent`, `CopyButtonComponent`
- [ ] `ParameterBreakdownComponent` (wraps stat tiles + histogram + verdict pills)
- [ ] `IntentBreakdownTableComponent`

**3.2 Connector Registry (Days 4–7)**
- [ ] `ConnectorService`
- [ ] `AuthCredentialFieldsComponent` — auth mode fields with dynamic visibility
- [ ] `ConnectionTestPanelComponent`
- [ ] `ConnectorListPageComponent` with filter bar and table
- [ ] `ConnectorFormPageComponent` (create + edit) — reactive form, all auth modes, test connection

**3.3 Evaluator Registry (Days 8–10)**
- [ ] `EvaluatorService`
- [ ] `DimensionsFieldComponent` (textarea → chip list preview)
- [ ] `EvaluatorListPageComponent`
- [ ] `EvaluatorFormPageComponent` (mirrors connector form + dimensions)

**3.4 Job Creation Wizard (Days 11–17)**
- [ ] `JobService` (wizard methods: create, updateName, uploadCsv, setConnector, setEvaluator, start, clone, getWizardState)
- [ ] `JobWizardComponent` shell with `MatStepper`
- [ ] `WizardStep1NameComponent`
- [ ] `WizardStep2CsvComponent` (file input, upload, error display)
- [ ] `WizardStep3ConnectorComponent` (connector selection, test button)
- [ ] `WizardStep4EvaluatorComponent` (evaluator selection, test button)
- [ ] `WizardStep5ReviewComponent` (review + start)

**3.5 Dashboard (Days 18–22)**
- [ ] `JobService` (list, overview, clearTerminal, clearAll, cancel, delete)
- [ ] `OverviewSectionComponent` (KPI tiles + activity table)
- [ ] `JobListFilterComponent`
- [ ] `JobStatusBadgeComponent`, `JobRowActionsComponent`
- [ ] `JobListTableComponent` (sortable, paginated)
- [ ] `DashboardPageComponent` (assembles above + live polling)

**3.6 Job Detail + Progress + Analytics (Days 23–32)**
- [ ] `JobService` (get, getStatus, getAnalytics, getResults, getResult, export)
- [ ] `JobStreamService` (SSE consumer for job progress)
- [ ] `JobProgressComponent` (progress bar + live counts)
- [ ] `JobAnalyticsTabComponent` (session details card, token tiles, parameter breakdown, intent breakdown)
- [ ] `ResultsFilterFormComponent`, `ResultsTableComponent`
- [ ] `ResultTraceExpansionComponent` (expandable row with trace)
- [ ] `JobDetailPageComponent` (assembles all above; tab layout)

**3.7 Chat Sessions (Days 33–45)**
- [ ] `ChatSessionService`, `ChatStreamService`
- [ ] `ChatSessionListPageComponent`
- [ ] `ChatWizardComponent` (5-step wizard; SSE-only connectors/evaluators)
- [ ] `ChatMessageThreadComponent` (turn history + live streaming bubble)
- [ ] `ChatInputFormComponent` (submit + SSE lifecycle)
- [ ] `ChatEvaluationPaneComponent` (user view / dev view; live evaluator events)
- [ ] `ChatInterfacePageComponent` (60/40 split layout; token pills; header actions)
- [ ] `TurnFilterFormComponent`, `TurnExplorerTableComponent`
- [ ] `ChatAnalyticsPageComponent` (reuses RunAnalytics components + turn explorer)

**3.8 Admin (Days 46–51)**
- [ ] `AdminService`
- [ ] `UserManagementPageComponent` (table with inline role change + remove)
- [ ] `UserNewPageComponent` (create user form)
- [ ] `AdminMaintenancePageComponent` (stats tiles + clear action)
- [ ] `AdminChatMaintenancePageComponent` (stats + preview/delete flow)
- [ ] `AdminLogsPageComponent` (error + audit log tables)

**3.9 Documentation Viewer (Days 52–54)**
- [ ] `scripts/sync-docs.mjs` (Node.js build script to copy markdown files)
- [ ] `DocsNavComponent`
- [ ] `DocsViewerPageComponent` (loads `.md` from assets, renders with ngx-markdown)
- [ ] `ReleaseNotesPageComponent` (collapsible panels per version)

---

### Phase 4 — Backend Jinja2 Removal

*After Phase 3 is feature-complete and tested. Slims the backend to pure API.*

- [ ] Remove all Jinja2 router registrations from `create_app()` (dashboard, wizard, detail, connector_registry, evaluator_registry, export_ui, chat_session, auth, admin, docs_ui)
- [ ] Remove `src/harness/ui/*/templates/` directories
- [ ] Remove `src/harness/ui/static/` assets (`harness.css`, `marked.min.js`, `purify.min.js`)
- [ ] Remove `jinja2>=3.1` from `pyproject.toml` dependencies
- [ ] Remove `itsdangerous>=2.2` (session cookie signing — no more server sessions)
- [ ] Remove `SessionMiddleware` from middleware stack in `create_app()`
- [ ] Remove Python `msal>=1.28` library (MSAL is now entirely in the browser; backend only validates Bearer JWT via `PyJWT`)
- [ ] Remove `auth/msal_client.py`, `auth/session.py`, `auth/config.py` (MSAL + session code)
- [ ] **Keep:** `python-multipart>=0.0.9` (CSV file upload still uses `multipart/form-data`)
- [ ] **Keep:** `CORSMiddleware`, `SecurityHeadersMiddleware`, `TrustedHostMiddleware`
- [ ] **Keep:** `ui/api/auth.py` Bearer JWT validation (used by both `/api/headless` and `/api/v1`)
- [ ] Remove `package-data` entries for templates in `pyproject.toml`
- [ ] Remove `HARNESS_SESSION_SECRET`, `HARNESS_AZURE_CLIENT_SECRET` from `.env.example` (no longer needed)
- [ ] Update `src/harness/ui/__init__.py` — simplify `create_app()` to: CORS + security headers + trusted hosts + `/health` + `/api/headless` router + `/api/v1` router
- [ ] Run full test suite; fix any import errors
- [ ] Update `docs/deployment-env-setup.md`

---

### Phase 5 — Backend → Azure Function App

*Parallel with latter half of Phase 3. Must be ready before Phase 6.*

**Compatibility gate**
- [ ] Verify Python 3.12 is the correct pin (confirm Azure Functions GA status for 3.12 and 3.13 at migration time)
- [ ] Update `pyproject.toml`: `requires-python = ">=3.12"`; update `.python-version` to `3.12`
- [ ] Add `azure-functions>=1.21` to `pyproject.toml` dependencies

**New files at repo root**

`function_app.py`:
```python
import azure.functions as func
from azure.functions import AsgiFunctionApp
from harness.ui import create_app as create_fastapi_app

_fastapi_app = create_fastapi_app()
app = AsgiFunctionApp(app=_fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)
```

`host.json`:
```json
{
  "version": "2.0",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```

`local.settings.json` (gitignored):
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "HARNESS_DB_URL": "postgresql+asyncpg://...",
    "HARNESS_FRONTEND_ORIGIN": "http://localhost:4200",
    "HARNESS_AZURE_TENANT_ID": "",
    "HARNESS_AZURE_CLIENT_ID": "",
    "HARNESS_AUTH_ENABLED": "false"
  }
}
```

**Infrastructure Bicep rewrite** (`infrastructure/bicep/main.bicep`):

| Resource | Config |
|---|---|
| App Service Plan | `kind: FunctionApp`, `sku: EP1` (`ELASTIC_PREMIUM`) — **not** Consumption Y1 or Flex Consumption |
| Function App | Python 3.12, Linux |
| Storage Account | Required by Function App runtime |
| Azure PostgreSQL Flexible Server | Retain existing; no data migration |
| Key Vault | Retain existing; Managed Identity access |

App settings in Bicep:
```
WEBSITE_MAX_DYNAMIC_APPLICATION_SCALE_OUT = 1
FUNCTIONS_WORKER_PROCESS_COUNT = 1
HARNESS_FRONTEND_ORIGIN = <Static Web App URL>
HARNESS_DEV_MODE = false
```

**CI/CD updates**
- [ ] Add to CI before packaging:
  ```bash
  uv export --no-dev --format requirements-txt -o requirements.txt
  ```
- [ ] Exclude from deployment zip: `.venv/`, `__pycache__/`, `tests/`, `docs/`, `specs/`, `references/`, `*.pyc`
- [ ] Add CD step: deploy via `azure/functions-action@v1` (GitHub Actions) or `AzureFunctionApp@2` (Azure Pipelines)

**Local testing**
- [ ] Install Azure Functions Core Tools: `npm install -g azure-functions-core-tools@4`
- [ ] `func start` → FastAPI on `http://localhost:7071`
- [ ] Smoke-test all `/api/v1/` and `/api/headless/` endpoints
- [ ] Verify SSE: `curl -N --no-buffer http://localhost:7071/api/v1/jobs/{id}/stream`
- [ ] Verify SSE: `curl -N --no-buffer http://localhost:7071/api/v1/chat-sessions/{id}/turns/{t}/stream`
- [ ] Verify APScheduler / asyncio job queue starts on first HTTP request
- [ ] Verify `asyncio.Lock` and `TTLCache` survive across multiple HTTP requests (same worker process)

---

### Phase 6 — Repo Split + Angular Hosting

#### 6.1 Repo Split

Follow `git filter-repo` pattern from qual-brew.

**eval-brew-api**
```bash
git clone <current-repo> eval-brew-api-staging
cd eval-brew-api-staging
# Promote src/eval-brew/ to root (or restructure as appropriate)
```
- [ ] Overlay current working tree (exclude `.venv/`, `__pycache__/`, `.pytest_cache/`)
- [ ] Add at root: `function_app.py`, `host.json`, `docker-compose.yml`, `infrastructure/`, `docs/`, `specs/`, `references/`
- [ ] Update `.gitignore`: add `local.settings.json`, `requirements.txt`; remove frontend-specific entries
- [ ] Push to new `eval-brew-api` repository
- [ ] Recreate repo secrets: `HARNESS_MASTER_KEY`, `HARNESS_DB_URL`, `AZURE_FUNCTION_APP_PUBLISH_PROFILE`, `HARNESS_AZURE_TENANT_ID`, `HARNESS_AZURE_CLIENT_ID`, `HARNESS_AZURE_API_AUDIENCE`

**eval-brew-app**
- [ ] Push Angular project to new `eval-brew-app` repository
- [ ] Create `.env.example`:
  ```
  NG_APP_API_BASE_URL=https://<function-app>.azurewebsites.net
  NG_APP_MSAL_TENANT_ID=
  NG_APP_MSAL_CLIENT_ID=
  NG_APP_MSAL_API_SCOPE=
  ```
- [ ] Recreate repo secrets: `AZURE_STATIC_WEB_APPS_API_TOKEN`

#### 6.2 Angular Hosting — Azure Static Web Apps

- [ ] Create Azure Static Web App (Standard tier) in same subscription
- [ ] `staticwebapp.config.json` at repo root:
  ```json
  {
    "navigationFallback": {
      "rewrite": "/index.html",
      "exclude": ["/assets/*"]
    }
  }
  ```
- [ ] CI/CD workflow using `Azure/static-web-apps-deploy@v1`:
  ```yaml
  app_location: "/"
  output_location: "dist/eval-brew-app/browser"
  ```
- [ ] Set `NG_APP_API_BASE_URL` to Function App URL in CI environment
- [ ] Add Static Web App URL to Azure AD app registration allowed redirect URIs (MSAL)
- [ ] Set `HARNESS_FRONTEND_ORIGIN` in Function App app settings to Static Web App URL
- [ ] Test MSAL login → token acquisition → API call → SSE stream end-to-end

---

### Phase 7 — Cutover + Cleanup

- [ ] DNS cutover: point custom domain to Azure Static Web Apps
- [ ] Smoke test all critical paths: login, create job (wizard), run job, stream progress, view results + analytics, export, live chat, chat analytics, admin, docs
- [ ] Monitor Function App: Application Insights — error rate, response time, active instances (confirm always 1)
- [ ] Decommission old AKS / Container Apps deployment
- [ ] Archive K8s manifests to `docs/archive/k8s/`
- [ ] Archive old Container Apps Bicep templates
- [ ] Mark original `eval-brew` monorepo as archived / read-only
- [ ] Update `docs/solution-architecture.md` with new architecture diagram
- [ ] Update `docs/deployment-env-setup.md` for Function App + Static Web App

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Python 3.13 not GA in Azure Functions | Certain (at plan date) | Low | Pin to 3.12; re-evaluate when 3.13 GA ships |
| ASGI wrapper incompatibility with `CORSMiddleware` or `SecurityHeadersMiddleware` | Low | Medium | Test locally with `func start`; middleware order matters — `CORSMiddleware` must wrap the FastAPI app, which it does through the ASGI adapter |
| SSE streaming buffered on Function App | Very Low | High | Premium EP1 plan handles chunked responses; test with `curl -N` before cutover |
| `asyncio.Lock` and job queue state lost if instance count > 1 | Low | High | `WEBSITE_MAX_DYNAMIC_APPLICATION_SCALE_OUT=1` is a hard gate; add monitoring alert if instance count > 1 |
| APScheduler silent failure on Function App | Low | Low | Premium plan is always-on; re-enqueue logic retained as safety net |
| `uv.lock` not understood by Function App | Certain | Low | `uv export → requirements.txt` in CI before packaging; verified pattern from qual-brew |
| `@azure/msal-angular` v8 breaking API changes | Medium | High | Verify v8 changelog before Phase 2; known stable: `MsalService`, `MsalGuard`; check `MsalBroadcastService` subscription API |
| Zoneless CD + `EventSource` not triggering render | Medium | Medium | Every SSE listener must write to a signal; test each SSE consumer (job stream + chat stream) end-to-end before Phase 6 |
| `EventSource` reconnect on network blip mid-chat | Medium | Low | `ChatStreamService.open()` must set `onerror` handler to detect closure and expose error signal; UI shows reconnect prompt |
| Chat wizard allows non-SSE connector (bug) | Certain (if missed) | High | Step 2 and Step 4 filter list to `supports_sse === true`; write a unit test asserting this filter is applied |
| CORS preflight blocked for `/api/v1/` | Medium | High | `CORSMiddleware` must include `OPTIONS` in allowed methods; test with browser network inspector before Phase 6 |
| MSAL redirect URI mismatch on Static Web App | Medium | High | Add Static Web App URL to Azure AD app registration before Phase 6 testing |
| CSV upload size limit on Function App | Low | Medium | Default Function App request body is 100 MB; default `HARNESS_MAX_UPLOAD_BYTES` is 50 MiB — both are fine; verify Bicep does not set a lower limit |
| Histogram component rendering performance (large result sets) | Low | Low | Pre-aggregate histograms server-side (`analytics.compute_analytics` already does); Angular component receives bucketed data, not raw scores |
| `role` claim not in JWT — `require_browser_auth` fails to resolve role | Medium | High | Role is stored in `user_registration` table; `require_browser_auth` must query DB by OID; cache result per request; test with both admin and user tokens |
| Docs Markdown assets out of sync | Low | Low | `prebuild` script runs on every `ng build`; add check in CI that ensures no docs file is missing |
| `openapi.json` export missing from CI | Medium | Medium | Fail the CI build if `schema/openapi.json` is not produced; add a `check-openapi` step |
| GitHub secrets not recreated after repo split | Medium | Medium | Explicit checklist in Phase 6.1; run a dry-deploy before decommissioning old repo |

---

## Effort Estimates

| Phase | Effort | Dependency |
|---|---|---|
| Phase 1 — REST API Expansion | 5–7 days | None — start immediately |
| Phase 2 — Angular Bootstrap | 2–3 days | Phase 1 partial (first endpoints available) |
| Phase 3.1–3.3 — Shared + Registries | 7–10 days | Phase 2 complete |
| Phase 3.4 — Wizard | 5–7 days | Phase 3.2–3.3 |
| Phase 3.5 — Dashboard | 4–5 days | Phase 3.1, 3.4 |
| Phase 3.6 — Job Detail + Analytics | 8–10 days | Phase 3.5 |
| Phase 3.7 — Chat Sessions | 11–14 days | Phase 3.3, 3.6 |
| Phase 3.8 — Admin | 5–6 days | Phase 2 |
| Phase 3.9 — Docs Viewer | 2–3 days | Phase 2 |
| Phase 4 — Jinja2 Removal | 1–2 days | Phase 3 complete |
| Phase 5 — Azure Function App | 3–5 days | Phase 1; parallel with Phase 3.7+ |
| Phase 6 — Repo Split + Hosting | 2–3 days | Phase 4 + Phase 5 |
| Phase 7 — Cutover + Cleanup | 1–2 days | Phase 6 |
| **Total** | **~57–77 days** | Phase 5 runs in parallel with Phase 3.7+ |

> **Acceleration strategy:** Phase 5 (Function App) can run in parallel with Phase 3.7 (Chat Sessions — the longest phase). Starting Phase 5 at Day 33 alongside Phase 3.7 saves ~5 days of critical path.
