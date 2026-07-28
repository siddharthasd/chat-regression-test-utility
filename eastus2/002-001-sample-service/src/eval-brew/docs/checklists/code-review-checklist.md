# EvalBrew — Full Code Review Checklist

Use this checklist to track a complete review of all production modules.
Tick each item once the layer has been reviewed to the satisfaction described.
Estimated total: **2–2.5 working days** for a thorough pass.

---

## Layer 1 — Persistence (est. 3–4 h)

Modules: `src/harness/persistence/` (models, repositories, migrations, engine)

- [ ] **Models** — ORM column types, nullability, cascade rules, immutable-field guards
  - [ ] `models/job.py`
  - [ ] `models/utterance.py`
  - [ ] `models/evaluation_result.py`
  - [ ] `models/chat_session.py`
  - [ ] `models/__init__.py`
- [ ] **Repositories** — query correctness, transaction boundaries, counter atomicity
  - [ ] `repositories/job.py`
  - [ ] `repositories/utterance.py`
  - [ ] `repositories/evaluation_result.py`
  - [ ] `repositories/chat_session_repository.py`
  - [ ] `repositories/types.py`
  - [ ] `repositories/__init__.py`
- [ ] **Migrations** — each version is additive-only, reversible, safe under concurrent reads
  - [ ] `migrations/versions/0001_initial_schema.py`
  - [ ] `migrations/versions/0002_add_optional_column.py`
  - [ ] `migrations/versions/0006_add_utterance_intent.py`
  - [ ] *(any additional versions)*
- [ ] **Engine** — session factory, pool config
  - [ ] `persistence/engine.py`
- [ ] **Encryption** — credential encrypt/decrypt, key-missing behaviour
  - [ ] `persistence/encryption.py`

---

## Layer 2 — Orchestrator & Pipeline (est. 45 min)

Modules: `src/harness/orchestrator/`

- [ ] **Engine** — job lifecycle transitions, cancellation at row boundaries, orphan reconciliation, semaphore slot handling (`engine.py`)
- [ ] **Pipeline** — connector→evaluator flow, password eviction timing, token aggregation, utteranceIntent extraction (`pipeline.py`)
- [ ] Verify HTTP calls run **outside** DB transactions (no long-held write lock)
- [ ] Verify per-row failure isolation — one failing row does not abort the job

---

## Layer 3 — Connector & Evaluator Clients (est. 1–1.5 h)

Modules: `src/harness/connector/`, `src/harness/evaluator/`, `src/harness/remote/`, `src/harness/auth/`

- [ ] **Connector client** — dispatch, timeout enforcement, error stage mapping
  - [ ] `connector/client.py`
  - [ ] `connector/result.py`
  - [ ] `connector/__init__.py`
  - [ ] `connector/mock.py`
- [ ] **Evaluator client** — dispatch, validation, harness annotations
  - [ ] `evaluator/client.py`
  - [ ] `evaluator/result.py`
  - [ ] `evaluator/validation.py`
  - [ ] `evaluator/mock.py`
- [ ] **Remote auth** — bearer, api-key-header, basic, client-credentials token fetch, token cache/refresh
  - [ ] `remote/auth.py`
  - [ ] `remote/oauth.py`
- [ ] **Auth module** — M2M JWT validation, RBAC middleware
  - [ ] `auth/` (all files)
- [ ] Confirm credentials are never logged, exported, or included in error details

---

## Layer 4 — Contract, CSV Upload & Export (est. 45 min)

Modules: `src/harness/contract/`, `src/harness/csv_upload/`, `src/harness/export/`

- [ ] **Contract** — JSON Schema validation, version comparison, additive-only enforcement
  - [ ] `contract/` (all files)
  - [ ] `contract/schemas/standard_evaluation_contract.schema.json`
- [ ] **CSV upload** — column validation, password column handling, row-count limits, MIME checks
  - [ ] `csv_upload/parser.py`
  - [ ] `csv_upload/service.py`
  - [ ] `csv_upload/result.py`
- [ ] **Export** — CSV/JSON/ZIP builder correctness, no credential leakage in exports
  - [ ] `export/builder.py`
  - [ ] `export/__init__.py`

---

## Layer 5 — Registry Test-Connection (est. 45 min)

Modules: `src/harness/connector_registry/`, `src/harness/evaluator_registry/`

- [ ] Connector test-connection — sends conformant sample request, validates contract response shape
  - [ ] `connector_registry/test_connection.py`
- [ ] Evaluator test-connection — sends conformant sample contract, validates EvaluationResult shape, flags unexpected dimensions
  - [ ] `evaluator_registry/test_connection.py`
- [ ] Confirm test-connection does not persist any state or credentials

---

## Layer 6 — UI Routes (est. 4–5 h)

Modules: `src/harness/ui/` (all sub-packages)

- [ ] **Wizard** — 5-step job creation flow, snapshot correctness, CSV upload wiring (`ui/wizard/routes.py`, `steps.py`)
- [ ] **Job detail** — per-row trace display, analytics, export links (`ui/detail/routes.py`, `view.py`, `analytics.py`)
- [ ] **Chat session** — turn lifecycle, SSE relay, token pill updates, delete guards (`ui/chat_session/routes.py`, `view.py`)
- [ ] **Connector registry** — register/edit/archive/restore, test-connection endpoint (`ui/connector_registry/routes.py`)
- [ ] **Evaluator registry** — register/edit/archive/restore, dimension validation, test-connection endpoint (`ui/evaluator_registry/routes.py`)
- [ ] **Dashboard** — overview KPI tiles, activity feed, filter pills (`ui/dashboard/routes.py`, `view.py`)
- [ ] **Admin** — bulk-clear operations, RBAC guard (admin role only) (`ui/admin/routes.py`)
- [ ] **Docs UI** — guide routing, release notes data (`ui/docs_ui/routes.py`)
- [ ] **Export UI** — download route auth, format selection (`ui/export_ui/routes.py`)
- [ ] **Headless API** — bearer JWT auth, all 6 endpoints, SSE streaming, results_url construction (`ui/api/service.py`, `ui/api/routes/`)
- [ ] **Auth UI** — SSO login, unauthorised redirect, multi-email fallback (`ui/auth/`)
- [ ] Check all routes enforce RBAC (role check present, not bypassable via URL)
- [ ] Check no raw SQL / template injection surfaces

---

## Layer 7 — Chat / SSE Orchestrator (est. 45 min)

Module: `src/harness/chat/`

- [ ] `stream_orchestrator.py` — connector SSE→contract→evaluator SSE pipeline, stall timeout, error stage mapping
- [ ] Token extraction from both connector contract and evaluator final event
- [ ] Turn persistence on both success and failure paths
- [ ] `event_bus.py` — bus lifecycle, `mark_complete` always fires (finally block)
- [ ] Confirm assembled_response is never None on the success path

---

## Layer 8 — Cross-cutting Concerns (review during all layers)

- [ ] **Credential handling** — no plaintext passwords in logs, DB, or HTTP responses at any layer
- [ ] **Error messages** — no stack traces or internal paths exposed to the browser
- [ ] **Input validation** — all user-supplied strings validated at system boundaries (CSV, registration forms, API body)
- [ ] **RBAC** — every route that mutates state or exposes data checks the authenticated user's role
- [ ] **Token aggregation** — connector + evaluator `totalTokens` summed correctly; fallback to `promptTokens + completionTokens` when `totalTokens` absent

---

## Layer 9 — Tests (est. 2–3 h)

Directories: `tests/unit/`, `tests/integration/`

- [ ] Unit tests cover the validation and error-stage logic for connector and evaluator clients
- [ ] Unit tests cover pipeline token aggregation and utteranceIntent extraction
- [ ] Integration tests cover the full connector→evaluator e2e flow
- [ ] Integration tests cover CSV upload edge cases (missing columns, bad MIME, oversized)
- [ ] Integration tests cover cascade delete behaviour
- [ ] Integration tests cover credential masking rules (no password in response/DB)
- [ ] Integration tests cover chat session analytics (batch-format SSE evaluators)
- [ ] Test coverage for all 9 migration versions
- [ ] No tests rely on mocked DB where a real integration test is feasible

---

## Sign-off

| Layer | Reviewer | Date | Notes |
|---|---|---|---|
| 1 — Persistence | | | |
| 2 — Orchestrator & Pipeline | | | |
| 3 — Connector & Evaluator Clients | | | |
| 4 — Contract, CSV Upload & Export | | | |
| 5 — Registry Test-Connection | | | |
| 6 — UI Routes | | | |
| 7 — Chat / SSE Orchestrator | | | |
| 8 — Cross-cutting Concerns | | | |
| 9 — Tests | | | |
