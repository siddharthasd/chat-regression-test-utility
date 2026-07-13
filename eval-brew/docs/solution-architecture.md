# Solution Architecture

This document describes the architecture of the EvalBrew for architects
and developers who need to understand its internals, deploy it, extend it, or integrate with
it.

---

## Overview

The harness is a **Python web application** built on FastAPI and served via Gunicorn with
Uvicorn workers, typically fronted by Nginx. Its purpose is to orchestrate regression test
runs against AI chatbots: it calls a user-supplied **connector** (which proxies the chatbot),
then calls a user-supplied **evaluator** (which scores the response), and persists the full
trace for reporting and export.

The system follows a clean **hexagonal / ports-and-adapters** design. The harness core knows
nothing about any specific chatbot or evaluation technology. Connectors and evaluators are
external HTTP services that implement a published JSON contract. They are registered by URL
in the harness at runtime; no harness code change is required to add, change, or swap them.

---

## High-level runtime topology

```
                          ┌────────────────────────────────┐
  Browser                 │          Harness Server         │
  ─────────────────────── │                                 │
  User / Admin ──HTTPS──▶ │  Nginx (reverse proxy)          │
                          │     │                           │
                          │     ▼                           │
                          │  Gunicorn (UvicornWorker)        │
                          │     │                           │
                          │     ▼                           │
                          │  FastAPI application            │
                          │   ├─ UI routers (Jinja2)        │
                          │   ├─ Auth middleware (MSAL)     │
                          │   └─ Orchestrator engine        │
                          │          │          │           │
                          │          ▼          ▼           │
                          │   SQLite/SQLAlchemy  httpx      │
                          └───────────────────────┼─────────┘
                                                  │
                    ┌─────────────────────────────┴────────────────────┐
                    │                                                   │
                    ▼                                                   ▼
        ┌───────────────────┐                             ┌────────────────────┐
        │   YOUR CONNECTOR  │                             │  YOUR EVALUATOR    │
        │  (any env, any    │                             │  (any env, any     │
        │   language)       │                             │   language)        │
        │                   │                             │                    │
        │  POST /endpoint   │──▶ chatbot ──▶ response     │  POST /endpoint    │
        └───────────────────┘                             └────────────────────┘
```

---

## Technology stack

| Layer | Technology |
|---|---|
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) 0.115+ |
| ASGI server | [Uvicorn](https://www.uvicorn.org/) (via Gunicorn `UvicornWorker`) |
| Process manager | [Gunicorn](https://gunicorn.org/) 22+ |
| Reverse proxy | Nginx (recommended; optional for development) |
| Templating | Jinja2 (via FastAPI's `Jinja2Templates`) |
| Frontend | Bootstrap 5.3.3 (CDN); plain HTML/JS — no build step |
| ORM / migrations | [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 + [Alembic](https://alembic.sqlalchemy.org/) |
| Database | SQLite (file-based; single-file deployment) |
| HTTP client | [httpx](https://www.python-httpx.org/) (sync) |
| Auth | [MSAL](https://github.com/AzureAD/microsoft-authentication-library-for-python) (Azure AD / Microsoft Entra ID OAuth2) |
| Credential encryption | [cryptography](https://cryptography.io/) (Fernet symmetric encryption) |
| Session middleware | Starlette `SessionMiddleware` (signed cookie) |
| Contract validation | [jsonschema](https://python-jsonschema.readthedocs.io/) (JSON Schema draft 2020-12) |
| CLI | [Click](https://click.palletsprojects.com/) |
| Python | 3.11+ |

---

## Source layout

```
src/harness/
├── __init__.py
├── bootstrap.py               # One-time initialization (DB migrations, identity resolution)
├── password_store.py          # In-memory per-job password store (ephemeral)
│
├── auth/                      # Azure AD auth (MSAL, session, middleware, role guards)
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
├── persistence/               # SQLAlchemy models, repositories, migrations, encryption
└── ui/                        # FastAPI app factory + all UI domain routers
    ├── __init__.py            # create_app() — app factory
    ├── _context.py            # Per-request Jinja2 context builder
    ├── _templates.py          # Shared Jinja2Templates instance (multi-directory)
    ├── templates/base.html    # Shared nav/layout shell
    ├── admin/                 # Admin routes (user management, job maintenance)
    ├── auth/                  # Auth routes (MSAL login/callback/logout)
    ├── connector_registry/    # Connector Registry UI
    ├── dashboard/             # Dashboard + job listing
    ├── detail/                # Job detail & traceability view
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
8. Row result (verdict, scores, full trace) is persisted to SQLite.
9. Dashboard / detail view updates live via polling.
```

Any failure at steps 2–7 is **isolated to the row**: it is recorded with a stage label
(`connector_transport`, `connector_response`, `connector_normalization`, `connector_auth`,
`evaluator_transport`, `evaluator_response`, `evaluator_result`, `evaluator_auth`) and
processing continues at step 1 for the next row.

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

SQLite, single file (path configurable via `HARNESS_DB_PATH` environment variable, default
`harness.db` in the working directory). Schema managed by Alembic migrations, applied
automatically at startup via `initialize_harness()`.

### Key models

| Model | Purpose |
|---|---|
| `Job` | A test run: status, timestamps, snapshotted connector/evaluator config |
| `Utterance` | One CSV row belonging to a job: input text, testId, extra metadata |
| `UtteranceResult` | Outcome for one row: stage, verdict, scores, full contract/result JSON |
| `ConnectorRegistration` | Registered connector: URL, auth config (credential encrypted at rest) |
| `EvaluatorRegistration` | Registered evaluator: URL, auth config, declared scoring dimensions |
| `UserRegistration` | Authorized Azure AD user: email, role (admin/user), OID, last login |

### Credential encryption

Connector and evaluator service credentials (bearer tokens, API keys, OAuth2 client secrets,
Basic passwords) are encrypted at rest using **Fernet symmetric encryption**
(`cryptography` library). The encryption key is derived from a `HARNESS_SECRET_KEY`
environment variable (or auto-generated and stored in `harness.key` if not set). Credentials
are decrypted in memory only when building a request; they are never logged, exported, or
surfaced in the UI.

---

## Orchestrator

`harness/orchestrator/engine.py` — job execution is synchronous and runs in the same Gunicorn
worker process that accepted the "Start Job" request. The engine processes rows sequentially
(one at a time, in CSV order). This is a deliberate design choice for the MVP: it simplifies
deployment (no worker queue infrastructure) and is sufficient for typical regression batch
sizes.

`harness/orchestrator/pipeline.py` — the per-row pipeline: connector call → contract
validation → evaluator call → result validation → persistence. Each stage is wrapped in
isolated error handling so a failure at any stage records the row and moves on.

---

## Authentication and authorization

Auth is implemented in `harness/auth/` and is **optional** (controlled by `HARNESS_AUTH_ENABLED`
environment variable). When disabled (local dev), a synthetic admin user is injected and all
routes are accessible.

When enabled:

- **Protocol:** OAuth2 Authorization Code flow via Azure AD / Microsoft Entra ID, using MSAL.
- **Session:** Signed server-side cookie (`SessionMiddleware`). The session stores the user's
  token claims; there is no server-side session store.
- **User registry:** Azure AD authenticates identity but does not control harness access.
  Authorized users must be pre-registered in the `UserRegistration` table (email + role).
  First login links the Azure AD OID to the registration record.
- **Roles:** `admin` (full access including user management and job maintenance) and `user`
  (standard access: create jobs, view results, export). Role is enforced at the route level
  via `Depends(require_role(...))` FastAPI dependencies.
- **CLI user management:** `harness users add/list/remove/set-role` — for bootstrapping the
  first admin before the UI is accessible.

---

## UI architecture

All UI is server-rendered HTML via Jinja2 templates. There is no SPA or API-first split;
forms POST to the same URL and redirect on success (PRG pattern throughout).

The `create_app()` factory in `harness/ui/__init__.py` assembles the application:
registers all domain routers, mounts static files, and attaches session middleware. Each
domain (dashboard, wizard, connector registry, etc.) is a self-contained sub-package with
its own `routes.py`, `templates/`, and (where needed) `forms.py` and `service.py`.

The shared `Jinja2Templates` instance (`_templates.py`) is initialised with a multi-directory
search list so each domain's templates are resolvable by name without subdirectory prefixes.

Live progress on the job detail view is implemented via JavaScript polling (`setInterval`)
against the same detail endpoint — no WebSocket or SSE infrastructure.

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
Nginx  ──proxy_pass──▶  Gunicorn (UvicornWorker)  ──▶  FastAPI app
```

Start command:
```bash
gunicorn harness.ui:create_app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 2 \
  --bind 127.0.0.1:8000
```

Nginx proxies HTTPS externally and forwards to Gunicorn on localhost. Static files can be
served directly by Nginx for efficiency.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `HARNESS_DB_PATH` | SQLite database file path | `harness.db` (working directory) |
| `HARNESS_SECRET_KEY` | Session signing + Fernet encryption key | Auto-generated; saved to `harness.key` |
| `HARNESS_AUTH_ENABLED` | Enable Azure AD auth (`true`/`false`) | `false` |
| `AZURE_CLIENT_ID` | Azure AD app registration client ID | — |
| `AZURE_CLIENT_SECRET` | Azure AD app registration client secret | — |
| `AZURE_TENANT_ID` | Azure AD tenant ID | — |
| `AZURE_REDIRECT_URI` | OAuth2 callback URL | — |

### CLI

```bash
harness serve               # Start the web server
harness users add           # Register the first admin user
harness users list
harness mock-connector      # Start a reference connector for development/testing
harness mock-evaluator      # Start a reference evaluator for development/testing
```

---

## Development methodology

This solution was built using **Spec-Driven Development** — each feature was fully specified
(requirements, data model, API surface, acceptance criteria) before implementation began.
Specifications live under `specs/` in the repository, one directory per feature, each
containing `spec.md`, `plan.md`, `tasks.md`, and a `checklists/` directory.

The tooling that enforces this workflow is **[GitHub Speckit](https://github.com/acm-will/speckit)**,
a Claude Code skill pack that automates spec generation, implementation planning, task
breakdown, and cross-artifact consistency checks.

**Author:** Siddhartha Dhamankar  
**AI development environment:** [Claude Code](https://claude.ai/code) by Anthropic
