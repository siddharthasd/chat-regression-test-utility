# Solution Architecture

This document describes the architecture of EvalBrew for architects and developers who need
to understand its internals, deploy it, extend it, or integrate with it.

---

## Overview

The harness is a **Python web application** built on FastAPI and served via Uvicorn,
typically fronted by Nginx. Its purpose is to orchestrate regression test
runs against AI chatbots: it calls a user-supplied **connector** (which proxies the chatbot),
then calls a user-supplied **evaluator** (which scores the response), and persists the full
trace for reporting and export.

The system follows a clean **hexagonal / ports-and-adapters** design. The harness core knows
nothing about any specific chatbot or evaluation technology. Connectors and evaluators are
external HTTP services that implement a published JSON contract. They are registered by URL
in the harness at runtime; no harness code change is required to add, change, or swap them.

The harness exposes two distinct interaction surfaces:

- **Browser UI** — Jinja2 server-rendered pages for human operators (job creation wizard,
  dashboard, analytics, registry management, live chat evaluation, admin).
- **Headless API** — A REST + SSE programmatic surface (`/api/headless/*`) for external
  systems such as qual-brew, authenticated via Azure AD M2M Bearer tokens.

---

## High-level runtime topology

```
  External caller                   ┌──────────────────────────────────────┐
  (qual-brew)                       │            Harness Server             │
  ─────────────────────────         │                                       │
  qual-brew ──M2M Bearer──────────▶ │  Nginx (reverse proxy / TLS offload)  │
                                    │     │                                 │
  Browser                           │     ▼                                 │
  ─────────────────────────         │  Uvicorn                              │
  User / Admin ──HTTPS / SSO──────▶ │     │                                 │
                                    │     ▼                                 │
                                    │  FastAPI application                  │
                                    │   ├─ UI routers (Jinja2)             │
                                    │   ├─ Auth middleware (MSAL + PyJWT)  │
                                    │   ├─ Headless API (/api/headless/*)  │
                                    │   └─ Orchestrator engine             │
                                    │          │               │           │
                                    │          ▼               ▼           │
                                    │  PostgreSQL (PaaS)     httpx         │
                                    └───────────────────────────┼──────────┘
                                                                │
                              ┌─────────────────────────────────┴──────────────────────┐
                              │                                                         │
                              ▼                                                         ▼
                  ┌───────────────────┐                               ┌────────────────────┐
                  │   YOUR CONNECTOR  │                               │  YOUR EVALUATOR    │
                  │  (any env, any    │                               │  (any env, any     │
                  │   language)       │                               │   language)        │
                  │                   │                               │                    │
                  │  POST /endpoint   │──▶ chatbot ──▶ response       │  POST /endpoint    │
                  └───────────────────┘                               └────────────────────┘
```

---

## Technology stack

| Layer | Technology |
|---|---|
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) 0.115+ |
| ASGI server | [Uvicorn](https://www.uvicorn.org/) 0.30+ (standalone; `--factory` mode) |
| Reverse proxy | Nginx (recommended; optional for development) |
| Templating | Jinja2 (via FastAPI's `Jinja2Templates`) |
| Frontend | Bootstrap 5.3.3 (CDN); plain HTML/JS — no build step |
| ORM / migrations | [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 + [Alembic](https://alembic.sqlalchemy.org/) |
| Database | PostgreSQL (production / PaaS) via [psycopg2](https://www.psycopg.org/) 2.9+; SQLite (local development and tests only) |
| HTTP client | [httpx](https://www.python-httpx.org/) (sync) |
| Browser auth | [MSAL](https://github.com/AzureAD/microsoft-authentication-library-for-python) (Azure AD OAuth2 Authorization Code flow) |
| API auth | [PyJWT](https://pyjwt.readthedocs.io/) `[crypto]` ≥ 2.8 (Azure AD M2M Bearer token validation) |
| Credential encryption | [cryptography](https://cryptography.io/) (Fernet symmetric encryption) |
| Session middleware | Starlette `SessionMiddleware` (signed cookie) |
| Contract validation | [jsonschema](https://python-jsonschema.readthedocs.io/) (JSON Schema draft 2020-12) |
| Structured logging | [structlog](https://www.structlog.org/) |
| CLI | [Click](https://click.palletsprojects.com/) |
| Python | 3.11+ (Docker runtime: 3.13) |

---

## Source layout

```
src/harness/
├── __init__.py
├── bootstrap.py               # One-time initialization (DB migrations, identity resolution)
├── password_store.py          # In-memory per-job password store (ephemeral)
│
├── auth/                      # Azure AD auth (MSAL, session, middleware, role guards)
├── chat/                      # Live chat evaluation domain (spec 017)
│   ├── event_bus.py           # Per-session SSE event bus
│   ├── export_service.py      # Chat session export
│   ├── session_service.py     # Session lifecycle management
│   ├── stream_orchestrator.py # Streaming evaluation orchestration
│   └── turn_service.py        # Single-turn execution
├── cli/                       # Click CLI entry points (serve, users, mock-connector, etc.)
├── connector/                 # Connector HTTP client + mock server
├── connector_registry/        # Connector CRUD service + test-connection
├── contract/                  # Standard Evaluation Contract schema + validation
├── csv_upload/                # CSV parser + validation service
├── evaluator/                 # Evaluator HTTP client + mock server
├── evaluator_registry/        # Evaluator CRUD service + test-connection
├── export/                    # Results export builder (CSV + JSON)
├── identity/                  # Identity context (tester attribution)
├── orchestrator/              # Job execution engine + per-row pipeline
│   ├── engine.py              # Job enqueue, run, and callback hook wiring
│   └── pipeline.py            # Per-row connector → contract → evaluator pipeline
├── persistence/               # SQLAlchemy models, repositories, migrations, encryption
│   ├── models/                # One file per ORM model
│   ├── repositories/          # Repository classes (query/mutation per entity)
│   └── migrations/            # Alembic env + numbered revision scripts (0001–0007)
├── remote/                    # Remote OAuth2 token acquisition for connector/evaluator auth
└── ui/                        # FastAPI app factory + all UI domain routers
    ├── __init__.py            # create_app() — app factory
    ├── _context.py            # Per-request Jinja2 context builder
    ├── _templates.py          # Shared Jinja2Templates instance (multi-directory)
    ├── context_processors.py  # Global Jinja2 context helpers
    ├── templates/base.html    # Shared nav/layout shell
    ├── static/                # CSS and static assets
    ├── admin/                 # Admin routes (user management, job maintenance)
    ├── api/                   # Headless API (spec 020) — REST + SSE, Bearer auth
    │   ├── auth.py            # PyJWT M2M token validation dependency
    │   ├── job_event_bus.py   # Per-job SSE event bus (async)
    │   ├── schemas.py         # Pydantic request/response models
    │   ├── service.py         # Job submission, result fetch, cancel logic
    │   └── routes/            # FastAPI routers (connectors, evaluators, jobs)
    ├── auth/                  # Auth routes (MSAL login/callback/logout)
    ├── chat_session/          # Live chat evaluation UI (spec 017)
    ├── connector_registry/    # Connector Registry UI
    ├── dashboard/             # Dashboard + job listing
    ├── detail/                # Job detail, traceability, and analytics view
    ├── docs_ui/               # Documentation viewer
    ├── evaluator_registry/    # Evaluator Registry UI
    ├── export_ui/             # Results export download routes
    └── wizard/                # New Job creation wizard (multi-step)
```

---

## Core data flow — one test row

```
1. Orchestrator reads the next utterance row from the database.
2. Connector client POSTs {testId, utteranceText, password?} to the connector URL.
3. Connector validates the HTTP response and parses the Standard Evaluation Contract.
4. Contract validation (jsonschema) checks the envelope shape and contractVersion.
5. Evaluator client POSTs the full contract to the evaluator URL.
6. Evaluator validates the HTTP response and parses the EvaluationResult.
7. Result validation checks verdict enum, echoed utteranceId, score entry types.
8. Row result (verdict, scores, full trace) is persisted to the database.
9. Progress callbacks fire (if registered) → SSE event bus pushed for headless jobs.
10. Dashboard / detail view updates live via JS polling (UI) or SSE (headless API).
```

Any failure at steps 2–7 is **isolated to the row**: it is recorded with a stage label
(`connector_transport`, `connector_response`, `connector_normalization`, `connector_auth`,
`evaluator_transport`, `evaluator_response`, `evaluator_result`, `evaluator_auth`) and
processing continues at step 1 for the next row.

---

## Headless Execution API (spec 020)

The headless API is a separate REST + SSE surface that allows external systems to drive the
full evaluation lifecycle programmatically — without a browser or the wizard UI.

**Base path**: `/api/headless`  
**Auth**: Azure AD M2M Bearer token (client credentials flow) — see [Authentication](#authentication-and-authorization) below.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/headless/connectors` | List active connectors |
| `GET` | `/api/headless/evaluators` | List active evaluators |
| `POST` | `/api/headless/jobs` | Submit test cases; returns `{job_id, stream_url, result_url}` |
| `GET` | `/api/headless/jobs/{id}/stream` | SSE live progress stream (per-case events + terminal event) |
| `GET` | `/api/headless/jobs/{id}/result` | Re-fetch current state or final result (polling fallback) |
| `DELETE` | `/api/headless/jobs/{id}` | Cancel a non-terminal job |

### SSE event types

| Event | Payload |
|---|---|
| `job_started` | `{}` |
| `progress` | `{"cases_completed": N, "cases_failed": N}` |
| `job_complete` | `{"results_url": "...", "summary": {total, passed, failed, top_failures[]}}` |
| `job_failed` | `{"error": "...", "summary": {...}}` |

The SSE bus replays the full event history for late-connecting consumers and closes
automatically after the terminal event is consumed.

### Thread → async bridging

The orchestrator engine runs jobs in synchronous daemon threads. The SSE event bus is async.
Bridging is done via `loop.call_soon_threadsafe(bus.push, ...)` — the event loop is captured
in the async route handler (`asyncio.get_running_loop()`) and passed into the job submission
service, which closes over it in progress/terminal callbacks registered on `enqueue_job()`.

### Constraints

- Maximum 100 test cases per submission.
- Maximum 2 concurrent in-flight headless jobs per service principal (per `oid` claim).
- Single-turn test cases only (v1); multi-turn is explicitly deferred.
- Headless API is additive — the existing wizard job creation flow is unchanged.

For the full integration reference see `docs/headless-service-integration-guide.md`.

---

## Standard Evaluation Contract

The contract is the **single shared data format** between the harness, connectors, and
evaluators. It is defined as a JSON Schema (draft 2020-12) bundled with the package at
`harness/contract/schemas/`.

**Flow:** connector produces it → harness validates it → evaluator consumes it.

The contract is **additive-only**: new optional fields may be added without bumping
`contractVersion`. The current version is `"1"`. A connector returning a higher version
is rejected (future-harness protection).

Key fields:

```json
{
  "contractVersion": "1",
  "utteranceId": "<uuid>",          // correlation key echoed by evaluator
  "utteranceText": "...",
  "testId": "...",
  "conversationContext": null,       // reserved; must be null in v1
  "connectorId": "...",
  "timestamp": "2026-06-05T14:32:00Z",
  "chatbotResponse": {
    "rawPayload": {},                // raw chatbot response (any shape)
    "normalizedText": "...",         // plain-text rendering
    "agentChain": [],                // ordered agent identifiers
    "metadata": {}                   // connector-specific metadata
  }
}
```

---

## Persistence layer

### Database

PostgreSQL is the production and PaaS target. SQLite is retained for local development
and the test suite only. The engine is selected by 12-factor config at startup:

| Config | Engine | Use case |
|---|---|---|
| `DATABASE_URL` set | PostgreSQL (via `psycopg2`) | Production / Azure PaaS deployments |
| `DATABASE_URL` unset | SQLite at `HARNESS_DB_PATH` | Local development and automated tests |

Schema is managed by Alembic migrations, applied automatically at startup via
`initialize_harness()`. The current migration head is **`0007`**.

SQLite-specific tuning (WAL mode, `NullPool`, transactional DDL) is applied only when
running SQLite; PostgreSQL uses the standard connection pool.

### Migration history

| Revision | Description |
|---|---|
| `0001` | Initial schema (job, utterance, evaluation_result) |
| `0002` | Optional columns (error details, aggregate counters) |
| `0003` | Job owner fields (`created_by`, `harness_version`) |
| `0004` | User registration table |
| `0005` | Live chat models (chat_session, chat_turn, chat_turn_result, evaluation_event) |
| `0006` | Utterance intent field |
| `0007` | Headless job metadata (`submission_source`, `source_system`, `product_name`, `feature_name`) |

### Key models

| Model | Purpose |
|---|---|
| `Job` | A test run: status, timestamps, snapshotted connector/evaluator config, submission metadata |
| `Utterance` | One input row belonging to a job: text, test ID, row index, extra metadata |
| `EvaluationResult` | Outcome for one row: stage, verdict, scores, full contract/result JSON |
| `ConnectorRegistration` | Registered connector: URL, auth config (credential encrypted at rest) |
| `EvaluationAgentRegistration` | Registered evaluator: URL, auth config, declared scoring dimensions |
| `UserRegistration` | Authorized Azure AD user: email, role (admin/user), OID, last login |
| `ChatSession` | A live chat evaluation session (spec 017) |
| `ChatTurn` | One user message + chatbot response within a chat session |
| `ChatTurnResult` | Evaluator verdict and scores for one chat turn |
| `EvaluationEvent` | One SSE streaming event emitted by the evaluator during a chat turn |

### Job submission source tracking

`Job.submission_source` distinguishes how a job was created:

| Value | Origin |
|---|---|
| `"wizard"` | Browser wizard UI (default for all pre-020 jobs) |
| `"api"` | Headless API submission |

API-sourced jobs additionally carry `source_system`, `product_name`, and `feature_name`
as optional display metadata. The dashboard renders an **API** badge for these jobs.

### Credential encryption

Connector and evaluator service credentials (bearer tokens, API keys, OAuth2 client secrets,
Basic passwords) are encrypted at rest using **Fernet symmetric encryption**
(`cryptography` library). The key is resolved in priority order:

1. **`HARNESS_MASTER_KEY`** env var — key bytes supplied inline (preferred for PaaS / container deployments; no file required).
2. File at **`HARNESS_KEY_FILE`** (default: `~/.harness/master.key`) — auto-created on first use with mode `0600`.

Credentials are decrypted in memory only when building a request; they are never logged,
exported, or surfaced in the UI. The same key must be present across redeployments — if the
key changes, all stored credentials become unreadable.

---

## Orchestrator

`harness/orchestrator/engine.py` — job execution is synchronous and runs in the same Uvicorn
worker process that accepted the "Start Job" request. The engine processes rows sequentially
(one at a time, in row-index order). This is a deliberate design choice: it simplifies
deployment (no worker queue infrastructure) and is sufficient for typical regression batch
sizes.

`harness/orchestrator/pipeline.py` — the per-row pipeline: connector call → contract
validation → evaluator call → result validation → persistence. Each stage is wrapped in
isolated error handling so a failure at any stage records the row and moves on.

**Callback hooks** (added in spec 020): `enqueue_job()` accepts three optional callbacks —
`job_started_callback`, `progress_callback`, and `job_terminal_callback`. These are used by
the headless API to push events onto the SSE bus from the engine thread. All existing
call sites (wizard job start, live chat) pass no callbacks and are unaffected.

---

## Authentication and authorization

Auth is implemented in `harness/auth/` and `harness/ui/api/auth.py`. It is **optional**
(controlled by `HARNESS_AUTH_ENABLED`). When disabled (local dev), synthetic identities are
injected and all routes are accessible.

When enabled, two auth models operate in parallel:

### Browser SSO (UI routes)

- **Protocol:** OAuth2 Authorization Code flow via Azure AD / Microsoft Entra ID, using MSAL.
- **Session:** Signed server-side cookie (`SessionMiddleware`). The session stores the user's
  token claims; there is no server-side session store.
- **User registry:** Azure AD authenticates identity but does not control harness access.
  Authorized users must be pre-registered in the `UserRegistration` table (email + role).
  First login links the Azure AD OID to the registration record.
- **Roles:** `admin` (full access including user management and job maintenance) and `user`
  (standard access: create jobs, view results, export). Role enforced at the route level
  via `Depends(require_role(...))` FastAPI dependencies.
- **CLI user management:** `harness users add/list/remove/set-role` — for bootstrapping the
  first admin before the UI is accessible.

### M2M Bearer tokens (headless API)

- **Protocol:** OAuth2 Client Credentials flow — the calling system (e.g. qual-brew) acquires
  a Bearer token from Azure AD using its own `client_id` and `client_secret`, then passes it
  in every request as `Authorization: Bearer <token>`.
- **Token acquisition** (by the caller):
  ```
  POST https://login.microsoftonline.com/{HARNESS_AZURE_TENANT_ID}/oauth2/token
  grant_type=client_credentials
  client_id=<caller client ID>
  client_secret=<caller client secret>
  resource=<HARNESS_AZURE_API_AUDIENCE>    ← must match eval-brew's config
  ```
- **Token validation** (by eval-brew): RS256 signature verified against Azure AD JWKS;
  `aud` claim checked against `HARNESS_AZURE_API_AUDIENCE`; identity extracted from `oid`
  (service principal object ID) and `app_displayname` / `appid`.
- **Audience coordination:** `HARNESS_AZURE_API_AUDIENCE` defaults to `HARNESS_AZURE_CLIENT_ID`
  when not set (bare client ID GUID). Set explicitly when the app's Application ID URI
  uses a custom scheme (e.g. `api://your-client-id`). The caller's `resource` value must
  match this exactly.
- **Ownership:** `oid` from the token is the calling service principal's Azure Object ID.
  Job ownership and the in-flight concurrency limit are enforced at the service-principal
  level (all calls from the same app share one 2-job limit).

---

## UI architecture

All browser UI is server-rendered HTML via Jinja2 templates. There is no SPA or API-first
split; forms POST to the same URL and redirect on success (PRG pattern throughout).

The `create_app()` factory in `harness/ui/__init__.py` assembles the application: registers
all domain routers, mounts static files, and attaches session middleware. Each domain
(dashboard, wizard, connector registry, etc.) is a self-contained sub-package with its own
`routes.py`, `templates/`, and (where needed) `forms.py` and `service.py`.

The shared `Jinja2Templates` instance (`_templates.py`) is initialised with a multi-directory
search list so each domain's templates are resolvable by name without subdirectory prefixes.

**Live progress:**

- *Wizard-submitted jobs* — JS polling (`setInterval`) against the detail endpoint.
- *Headless API jobs* — SSE stream on `GET /api/headless/jobs/{id}/stream`.
- *Live chat sessions* — SSE stream via the chat session UI.

---

## Extension points

### Adding a new connector

No harness code changes required. A connector is any HTTP service that:

1. Accepts `POST {testId, utteranceText, password?}` as JSON.
2. Returns HTTP 200 with a Standard Evaluation Contract JSON body.

Register it via the Connector Registry UI. See the **Connector Developer Guide** for the
full contract specification and authentication options.

### Adding a new evaluator

No harness code changes required. An evaluator is any HTTP service that:

1. Accepts `POST <Standard Evaluation Contract>` as JSON.
2. Returns HTTP 200 with an EvaluationResult JSON body.

Register it via the Evaluator Registry UI. See the **Evaluator Developer Guide** for the
full result specification, scoring dimensions, and authentication options.

### Adding a new UI module

Follow the established pattern:

1. Create `src/harness/ui/<domain>/` with `__init__.py`, `routes.py`, `templates/<domain>/`.
2. Export a `router = APIRouter()` from `__init__.py`.
3. Register it in `create_app()` (`harness/ui/__init__.py`).
4. Add the template directory to `_templates.py`.
5. Add package-data entry in `pyproject.toml`.

---

## Deployment

### Recommended production configuration

```
Nginx  ──proxy_pass──▶  Uvicorn  ──▶  FastAPI app
```

Start command:

```bash
uvicorn harness.ui:create_app \
  --factory \
  --host 0.0.0.0 \
  --port 8000
```

Or via Docker (as defined in `Dockerfile`):

```bash
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://user:pass@host/db \
  -e HARNESS_MASTER_KEY=<fernet-key> \
  eval-brew
```

Nginx proxies HTTPS externally and forwards to Uvicorn on localhost. Static files can be
served directly by Nginx for efficiency.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Full SQLAlchemy URL for PostgreSQL (e.g. `postgresql://user:pass@host/db`). Required for production / PaaS. When set, `HARNESS_DB_PATH` is ignored. | — (falls back to SQLite) |
| `HARNESS_DB_PATH` | SQLite database file path. Local development and tests only; ignored when `DATABASE_URL` is set. | `~/.harness/data.db` |
| `HARNESS_MASTER_KEY` | Fernet encryption key bytes supplied inline (URL-safe base64). **Preferred for PaaS / container deployments** — no key file needed. Takes priority over `HARNESS_KEY_FILE`. | — |
| `HARNESS_KEY_FILE` | Path to the Fernet master encryption key file. Auto-created on first use with mode `0600`. Used when `HARNESS_MASTER_KEY` is not set. | `~/.harness/master.key` |
| `HARNESS_SESSION_SECRET` | Session signing key (≥ 32 chars) | — (required when auth enabled) |
| `HARNESS_AUTH_ENABLED` | Enable Azure AD auth (`true`/`false`) | `false` |
| `HARNESS_AZURE_TENANT_ID` | Azure AD tenant GUID | — |
| `HARNESS_AZURE_CLIENT_ID` | eval-brew app registration client ID | — |
| `HARNESS_AZURE_CLIENT_SECRET` | eval-brew app registration client secret | — |
| `HARNESS_REDIRECT_URI` | OAuth2 browser callback URL (e.g. `https://host/auth/callback`) | — |
| `HARNESS_AZURE_API_AUDIENCE` | Expected `aud` in M2M Bearer tokens. Defaults to `HARNESS_AZURE_CLIENT_ID`. Set when the app's Application ID URI differs from the bare client ID. | `HARNESS_AZURE_CLIENT_ID` |
| `HARNESS_PUBLIC_URL` | External base URL of eval-brew (no trailing slash). When set, `results_url` in headless API responses is fully-qualified. | — (relative paths) |
| `HARNESS_MAX_UPLOAD_BYTES` | Maximum CSV upload size in bytes | `52428800` (50 MiB) |
| `HARNESS_MOCK_MODE` | Mock connector/evaluator response mode (`ok`, `nonconformant`, `status500`, `slow`) | `ok` |

### CLI

```bash
harness serve               # Start the web server
harness users add           # Register the first admin user
harness users list
harness users remove
harness users set-role
harness mock-connector      # Start a reference connector for development/testing
harness mock-evaluator      # Start a reference evaluator for development/testing
```

---

## Development methodology

This solution was built using **Spec-Driven Development** — each feature was fully specified
(requirements, data model, API surface, acceptance criteria) before implementation began.
Specifications live under `specs/` in the repository, one directory per feature (001–020),
each containing `spec.md`, `plan.md`, `tasks.md`, and a `checklists/` directory.

The tooling that enforces this workflow is **[GitHub Speckit](https://github.com/acm-will/speckit)**,
a Claude Code skill pack that automates spec generation, implementation planning, task
breakdown, and cross-artifact consistency checks.

**Author:** Siddhartha Dhamankar  
**AI development environment:** [Claude Code](https://claude.ai/code) by Anthropic
