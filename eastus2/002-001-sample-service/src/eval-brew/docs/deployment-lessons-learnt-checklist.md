# AKS + PostgreSQL PaaS Deployment — Lessons Learnt Checklist

Distilled from the eval-brew AKS enablement work (2026-07-26 – 2026-07-29).
Use this list when porting a similar FastAPI/Python project to AKS with Azure
PostgreSQL Flexible Server and Azure AD SSO.

---

## 1. Database — Drop SQLite, Require PostgreSQL

- [ ] Remove all SQLite-specific code paths (`resolve_db_path`, `apply_sqlite_pragmas`,
  batch-mode Alembic, file-size admin endpoints).
- [ ] `init_db()` must raise `RuntimeError` when the PostgreSQL connection string is
  absent — fail fast at startup, not at the first DB call.
- [ ] Replace `alembic.ini` SQLite URL placeholder with a PostgreSQL one.
- [ ] Remove SQLite from `alembic/env.py` (`render_as_batch=True` and the
  `check_same_thread` connect arg).
- [ ] Update all test fixtures: drop `HARNESS_DB_PATH`; skip integration tests when
  `DATABASE_URL` is not set.

---

## 2. PostgreSQL Managed Identity (AKS Workload Identity)

- [ ] Use **three separate environment variables** for the PostgreSQL connection —
  do not embed credentials in a single `DATABASE_URL`:
  ```
  HARNESS_PG_HOST=<server>.postgres.database.azure.com
  HARNESS_PG_DB=<db-name>
  HARNESS_PG_USER=<managed-identity-name>
  ```
- [ ] Add a dedicated `HARNESS_PG_USE_MANAGED_IDENTITY` flag (boolean, **default
  `false`**). Set it to `true` explicitly in the pod spec — do not auto-detect
  from the presence of `HARNESS_PG_*` vars; auto-detection silently enables MI
  in dev environments where the vars happen to be set.
- [ ] Add `azure-identity>=1.15` as a runtime dependency.
- [ ] On each new connection acquire a fresh Azure AD access token via
  `DefaultAzureCredential` and pass it as the password — the PostgreSQL Flexible
  Server AD auth plugin accepts it in place of a static password.
- [ ] Set `pool_pre_ping=True` on the SQLAlchemy engine so expired tokens trigger a
  transparent reconnect (tokens expire every ~60 min).
- [ ] Log token acquisition with `expires_on` so token refresh is observable in
  production: `db.managed_identity.token_acquired expires_on=<unix-ts>`.

---

## 3. Authentication & SSO (Azure AD / MSAL)

- [ ] **`userprincipalname` is the correct claim for RBAC email lookup**, not `name`
  or `display_name`. Accenture (and most Entra ID tenants) return the UPN as the
  routable email. Priority order in the OAuth2 callback:
  `userprincipalname` → `email` → `upn` → `preferred_username`.
- [ ] Drop `openid` and `profile` from the MSAL scope list. Azure AD v2 includes
  them implicitly; requesting them explicitly can break claim delivery or trigger
  unexpected consent prompts.
  ```python
  _SCOPES = ["email"]   # not ["openid", "profile", "email"]
  ```
- [ ] Add verbose SSO debug logging from day 1 (see §8): flow initiation, token
  exchange, OID resolution, session establishment, and logout — essential for
  diagnosing silent failures in the AKS → AD token flow.

---

## 4. Security Headers

- [ ] Extract HTTP security headers out of `ui/__init__.py` into a dedicated
  `security_headers.py` module as a proper `BaseHTTPMiddleware` subclass. Keeping
  them inline makes them easy to accidentally delete during refactors.
- [ ] Minimum header set for AKS-hosted apps:
  | Header | Value |
  |--------|-------|
  | `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
  | `X-Content-Type-Options` | `nosniff` |
  | `X-Frame-Options` | `SAMEORIGIN` |
  | `Cache-Control` | `no-store` |
  | `Content-Security-Policy` | Restrict to own origin + approved CDNs |
  | `Referrer-Policy` | `strict-origin-when-cross-origin` |
- [ ] **Never change header names or values** once they are in production — the
  security team reviews these as part of the compliance baseline.

---

## 5. Terraform & Infrastructure as Code

- [ ] Create a **`terraform.tfvars` template** (not `local.settings.json`) for all
  infrastructure configuration values. `local.settings.json` is an Azure Functions
  convention and does not translate to AKS/Terraform workflows.
- [ ] Declare every variable in `variables.tf` with a type, description, and
  `default = null` where appropriate — fail-fast validation at `terraform plan`
  time catches missing values before apply.
- [ ] Add `*.tf` and `*.tfvars` to `.gitignore` — these files contain environment-
  specific values (subscription IDs, resource names, secrets) and must not be
  committed. Provide a `*.tfvars.example` template in the repo instead.
- [ ] **Externalize all deployment values into an Azure DevOps variable library**
  (variable group linked to the pipeline). The pipeline injects them into the
  Terraform run; no secrets in source control.
- [ ] Reference the variable group in `azure-pipelines-common-vars.yml` and ensure
  every new variable added to `variables.tf` has a corresponding entry in the
  library.

---

## 6. Configuration & Environment Variables

- [ ] Create a comprehensive `.env.example` with **every** environment variable the
  app reads, grouped by concern, with a description and example value. Comment
  out variables that are not needed for a given deployment profile.
  Minimum groups:
  - Database (`DATABASE_URL` or `HARNESS_PG_*`)
  - Managed Identity (`HARNESS_PG_USE_MANAGED_IDENTITY`)
  - Encryption (`HARNESS_SECRET_KEY`, `HARNESS_FERNET_KEY`)
  - Auth / SSO (`HARNESS_AZURE_TENANT_ID`, `HARNESS_AZURE_CLIENT_ID`, `HARNESS_AZURE_CLIENT_SECRET`)
  - Session (`SESSION_SECRET`)
  - Logging (`LOG_LEVEL`)
  - Public URL (`HARNESS_PUBLIC_URL`)
  - File upload limits
- [ ] Add `python-dotenv` as a dependency and call `load_dotenv(override=False)` at
  CLI startup so a local `.env` file is picked up automatically in dev. Set
  `override=False` so production environment variables (injected by K8s) always
  win over `.env` values.
- [ ] Add `*.csv` to `.gitignore` — test/sample data files must never be committed.

---

## 7. Container & AKS Deployment

### HTTPS on port 8443 (K8s liveness probe policy)

- [ ] K8s policy at many organisations prohibits plain-HTTP liveness probes.
  Uvicorn on plain HTTP causes the pod to emit
  `WARNING: Invalid HTTP request received.` on every probe cycle.
- [ ] Set K8s liveness/readiness probes to `scheme: HTTPS` — the kubelet does not
  validate the certificate, so self-signed is sufficient.
- [ ] Start uvicorn with `--ssl-keyfile /app/ssl/tls.key` and
  `--ssl-certfile /app/ssl/tls.crt` on port `8443`.

### Aqua scan — never embed a private key in an image layer

- [ ] **Do not generate TLS certificates in a Dockerfile `RUN` step.** Aqua's
  secret scanner finds `-----BEGIN RSA PRIVATE KEY-----` (or any private key
  header) in image layers and fails the build with
  _"1 occurrence of sensitive data was found in the image"_, regardless of the
  key's purpose or certificate validity period.
- [ ] **Move cert generation to an entrypoint script** that runs at container
  startup. The key is written into the running container's filesystem and never
  touches a layer:
  ```sh
  #!/bin/sh
  set -e
  # Use a mounted cert (K8s TLS secret at /app/ssl/) if available;
  # otherwise generate a self-signed cert as a fallback.
  if [ ! -f /app/ssl/tls.key ]; then
      mkdir -p /app/ssl
      openssl req -x509 -newkey rsa:2048 \
          -keyout /app/ssl/tls.key -out /app/ssl/tls.crt \
          -days 365 -nodes -subj "/CN=<app-name>" 2>/dev/null
      chmod 600 /app/ssl/tls.key && chmod 644 /app/ssl/tls.crt
  fi
  exec uvicorn harness.ui:create_app --factory \
      --host 0.0.0.0 --port 8443 \
      --ssl-keyfile /app/ssl/tls.key --ssl-certfile /app/ssl/tls.crt
  ```
- [ ] In the Dockerfile, `COPY` the script and `RUN chmod +x` it — no key material
  ever appears in a layer:
  ```dockerfile
  COPY entrypoint.sh /app/entrypoint.sh
  RUN chmod +x /app/entrypoint.sh
  EXPOSE 8443
  CMD ["/app/entrypoint.sh"]
  ```
- [ ] The `/app/ssl/` path doubles as the mount point for a real K8s TLS secret.
  When a proper cert is mounted there (cert-manager, Azure Key Vault CSI), the
  entrypoint picks it up with no image rebuild required.
- [ ] Certificate validity must be **≤ 397 days** (CA/Browser Forum limit). Aqua
  may also flag longer periods as a separate policy violation.

### Log output stream

- [ ] Route all application logs to **`sys.stdout`**, not `sys.stderr`. Most
  container log collectors (Azure Monitor, fluentd) tag everything on stderr as
  `error` regardless of the structured log level inside the message.
  ```python
  handler = logging.StreamHandler(sys.stdout)   # not StreamHandler()
  ```
  This applies to every place a `StreamHandler` is instantiated — both the CLI
  entry point and the ASGI lifespan handler.

### structlog renderer

- [ ] In non-TTY environments (containers, CI) use `JSONRenderer`; in interactive
  sessions use `ConsoleRenderer`. Detect via `sys.stderr.isatty()` at startup.
  ANSI escape codes from `ConsoleRenderer` appear as raw character sequences in
  log aggregators and make structured fields unparseable.

### Pod spec essentials

- [ ] Set `HARNESS_PG_USE_MANAGED_IDENTITY=true` explicitly in the pod environment —
  do not rely on auto-detection.
- [ ] Set `LOG_LEVEL=debug` initially; tighten to `info` once the deployment is
  stable.
- [ ] Mount `HARNESS_PUBLIC_URL` so SSE stream and result URLs returned by the
  headless API are absolute and routable from outside the cluster.

---

## 8. Logging — Verbose from Day 1

Insufficient logging was the single biggest time sink during the initial AKS
deployment. Add these log points **before** the first container deployment, not
after:

- [ ] **Managed identity**: credential chain construction, token acquisition
  (`host`, `user`, `expires_on`).
- [ ] **Database URL assembly**: log which source was used (`HARNESS_PG_*` vs
  `DATABASE_URL`) and the assembled URL (mask the password).
- [ ] **SSO / MSAL**: flow initiation, token exchange, OID extraction, session
  write, logout.
- [ ] **Auth middleware**: every session lookup, role check, and redirect decision.
- [ ] **Bearer JWT auth** (headless API): token validation success/failure with
  caller OID.
- [ ] **OAuth2 client-credentials**: token fetch, cache hit/miss, invalidation.
- [ ] **Connector + evaluator dispatch**: auth resolve, HTTP call, response
  validation — one log per stage.
- [ ] Externalise log level to a `LOG_LEVEL` env var (default `debug`). Never
  hard-code `INFO` in a container that is about to be deployed for the first time.
- [ ] structlog: switch to JSON in non-TTY (see §7); keep `ConsoleRenderer` for
  local dev.

---

## 9. Vector / Embedding Store — Replace ChromaDB

- [ ] **ChromaDB is not AKS-friendly** without a persistent volume claim and a
  separate server deployment. Replace it before the first AKS deployment with
  one of:
  - **pgvector** — PostgreSQL extension; same connection pool, no extra service,
    data persists with the DB PaaS tier.
  - **Azure AI Search** — managed PaaS; scales independently; integrates with
    Azure AD.
- [ ] If using pgvector: `CREATE EXTENSION IF NOT EXISTS vector;` in the migration,
  add `pgvector` Python package, adjust embedding store class to use
  `sqlalchemy` with the `Vector` column type.

---

## 10. API Bug Classes to Audit Before Go-Live

These were found during code review of the headless execution API and apply to
any API that creates resources and enforces per-user limits:

- [ ] **TOCTOU on per-user limits** — merge the "count existing resources" check and
  the "create new resource" INSERT into a **single database session/transaction**.
  Two concurrent requests can both pass the count check before either INSERT
  commits, violating the stated limit.
- [ ] **SSE / streaming bus cleanup** — do not call `remove_bus(id)` in a
  `finally` block that fires on client disconnect. Move cleanup to the terminal
  event handler so mid-job disconnects do not prevent reconnection or silence
  cancellation notifications.
- [ ] **Empty collection inputs** — validate `len(collection) == 0` explicitly;
  `len > MAX` checks do not catch the empty case.

---

## Quick Reference — Key Environment Variables

| Variable | Purpose | AKS value |
|----------|---------|-----------|
| `HARNESS_PG_HOST` | PostgreSQL server hostname | `<server>.postgres.database.azure.com` |
| `HARNESS_PG_DB` | Database name | `<db-name>` |
| `HARNESS_PG_USER` | Managed identity / login name | `<mi-name>` |
| `HARNESS_PG_USE_MANAGED_IDENTITY` | Enable MI auth | `true` |
| `HARNESS_AZURE_TENANT_ID` | Azure AD tenant | `<tenant-guid>` |
| `HARNESS_AZURE_CLIENT_ID` | App registration client ID | `<client-guid>` |
| `HARNESS_AZURE_CLIENT_SECRET` | App registration secret | `<secret>` |
| `HARNESS_AUTH_ENABLED` | Enable SSO auth | `true` |
| `LOG_LEVEL` | Logging verbosity | `debug` (initial), `info` (stable) |
| `HARNESS_PUBLIC_URL` | External base URL | `https://<ingress-host>` |
| `SESSION_SECRET` | Cookie signing key | `<random-32-bytes-hex>` |
| `HARNESS_SECRET_KEY` | App encryption key | `<random-32-bytes-hex>` |
| `HARNESS_FERNET_KEY` | Credential encryption key | `<fernet-key>` |
