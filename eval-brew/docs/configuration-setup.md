# Configuration Setup

This document describes every environment variable recognised by the eval-brew harness, its accepted values, defaults, and when to set it.

---

## Authentication

### `HARNESS_AUTH_ENABLED`

| | |
|---|---|
| **Default** | `true` |
| **Accepted values** | `1`, `true`, `yes` (enabled) — any other value disables auth |
| **Sample** | `HARNESS_AUTH_ENABLED=true` |

Master on/off switch for Azure AD SSO authentication. When enabled, the Azure AD variables below become required and all routes enforce the OAuth / JWT flow. When disabled, every request is granted a synthetic admin identity — **only use `false` for local offline development**.

> **Security note:** Defaults to `true` (secure by default). Never set to `false` in any internet-facing or shared environment.

---

### `HARNESS_AZURE_TENANT_ID`

| | |
|---|---|
| **Default** | *(none — required when auth is enabled)* |
| **Accepted values** | Azure AD tenant GUID or domain (e.g. `accenture.com`) |
| **Sample** | `HARNESS_AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |

Your Azure AD tenant identifier. Used in the OAuth authorisation-code flow and to construct the JWKS endpoint URI (`https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys`) for validating M2M Bearer tokens. The app raises `RuntimeError` at startup if this is missing and auth is enabled.

---

### `HARNESS_AZURE_CLIENT_ID`

| | |
|---|---|
| **Default** | *(none — required when auth is enabled)* |
| **Accepted values** | Azure AD application (client) GUID |
| **Sample** | `HARNESS_AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |

The App Registration client ID. Used in the OAuth flow and as the fallback expected `aud` claim when validating Bearer tokens. The app raises `RuntimeError` at startup if this is missing and auth is enabled.

---

### `HARNESS_AZURE_CLIENT_SECRET`

| | |
|---|---|
| **Default** | *(none — required when auth is enabled)* |
| **Accepted values** | Azure AD client secret string |
| **Sample** | `HARNESS_AZURE_CLIENT_SECRET=your-secret-here` |

The client secret for the OAuth authorisation-code flow. Used only for session-based browser login — the headless API uses JWKS public-key validation and does not need this value. Store in a secret manager; never commit to source control.

---

### `HARNESS_SESSION_SECRET`

| | |
|---|---|
| **Default** | *(none — required when auth is enabled; falls back to a random ephemeral key)* |
| **Accepted values** | Any strong random string (minimum 32 characters recommended) |
| **Sample** | `HARNESS_SESSION_SECRET=a-long-random-string-at-least-32-chars` |

The signing key for Starlette's session cookie middleware. Must be stable across restarts in production — if it changes, all existing sessions are invalidated. If not set and auth is disabled, a random key is generated per process (sessions do not survive restarts).

---

### `HARNESS_REDIRECT_URI`

| | |
|---|---|
| **Default** | `""` (empty) |
| **Accepted values** | Fully qualified URL registered in your Azure AD App Registration |
| **Sample** | `HARNESS_REDIRECT_URI=https://evalbrew.ciostage.accenture.com/auth/callback` |

The OAuth callback URL the browser is redirected to after Azure AD authentication. Must exactly match one of the Redirect URIs registered in the App Registration. Leave empty only when MSAL can resolve it automatically from the request context.

---

### `HARNESS_AZURE_API_AUDIENCE`

| | |
|---|---|
| **Default** | Falls back to the value of `HARNESS_AZURE_CLIENT_ID` |
| **Accepted values** | Azure AD application URI or client ID GUID |
| **Sample** | `HARNESS_AZURE_API_AUDIENCE=api://xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |

The expected `aud` claim in Bearer JWT tokens arriving at the headless API (`/api/headless/...`). When a calling service acquires an M2M token for `resource=<client_id>`, Azure sets `aud` to the client ID — so the default fallback is the standard pattern. Set this explicitly only when a separate API App Registration is used.

---

## Session & Security

### `HARNESS_SESSION_HTTPS_ONLY`

| | |
|---|---|
| **Default** | `true` |
| **Accepted values** | `false` to disable; any other value keeps HTTPS enforcement on |
| **Sample** | `HARNESS_SESSION_HTTPS_ONLY=false` |

Controls the `Secure` flag on the session cookie. When `true`, browsers will only send the session cookie over HTTPS connections. Set to `false` only in local development environments where the test client speaks plain HTTP.

---

### `HARNESS_ALLOWED_HOSTS`

| | |
|---|---|
| **Default** | `*` (allow all — development only) |
| **Accepted values** | Comma-separated list of hostnames; `*` to allow all |
| **Sample** | `HARNESS_ALLOWED_HOSTS=evalbrew.ciostage.accenture.com,localhost` |

Trusted hostname allowlist enforced by `TrustedHostMiddleware`. Requests with a `Host` header not in this list are rejected with HTTP 400, preventing Host-header injection and open-redirect attacks. **Set this to your production hostname(s) in any internet-facing deployment.** The wildcard default is safe only for local development.

---

## Database

### `DATABASE_URL`

| | |
|---|---|
| **Default** | *(none — required; no fallback)* |
| **Accepted values** | PostgreSQL SQLAlchemy URL (with or without a password) |
| **Sample (password auth)** | `DATABASE_URL=postgresql+psycopg2://user:pass@db-host:5432/harness` |
| **Sample (managed identity)** | `DATABASE_URL=postgresql+psycopg2://evalbrew_admin@evalbrew-pg.postgres.database.azure.com:5432/evalbrew?sslmode=require` |

Full SQLAlchemy database connection URL. PostgreSQL is the only supported backend. A connection pool (`pool_size=2, max_overflow=3`) is used. Required for all deployments.

When `HARNESS_PG_USE_MANAGED_IDENTITY=true`, the password component of this URL is ignored — the app acquires an Azure AD access token at connection time and uses it as the password. In that mode, omit the password from the URL entirely.

---

### `HARNESS_PG_USE_MANAGED_IDENTITY`

| | |
|---|---|
| **Default** | `false` |
| **Accepted values** | `1`, `true`, `yes` (enabled) — any other value uses password auth |
| **Sample** | `HARNESS_PG_USE_MANAGED_IDENTITY=true` |

When enabled, the database engine acquires an Azure AD access token (via `DefaultAzureCredential`) and passes it as the PostgreSQL password on every new connection. This is the required mode for AKS deployments that authenticate to Azure PostgreSQL Flexible Server via workload identity — no static `pg_admin_password` is needed or used by the app at runtime.

`DefaultAzureCredential` tries credential sources in this order: AKS Workload Identity → node-level Managed Identity → Azure CLI (useful for local testing against a cloud database). Token caching is handled internally; the token is refreshed automatically before expiry. `pool_pre_ping=true` ensures any connection whose token has expired is detected and replaced transparently on the next pool checkout.

> **Prerequisites (AKS):** The pod's workload identity must be assigned the PostgreSQL AAD Authentication role on the Flexible Server, and the server must be configured with an AAD admin. Leave this `false` for local development where `DATABASE_URL` carries a static password.

---

## Encryption

### `HARNESS_MASTER_KEY`

| | |
|---|---|
| **Default** | *(none — falls back to reading/creating the key file at `HARNESS_KEY_FILE`)* |
| **Accepted values** | URL-safe base64-encoded Fernet key (32 bytes) |
| **Sample** | `HARNESS_MASTER_KEY=aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABCDEF=` |

Supplies the Fernet encryption key directly as an environment variable. Used to encrypt and decrypt connector and evaluator credential fields in the database. Takes priority over the key file. **Preferred for container and PaaS deployments** where mounting a key file is impractical. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

> **Security note:** Treat this value with the same care as a database password. Store in a secret manager (Azure Key Vault, Kubernetes Secret) — never in source control.

---

### `HARNESS_KEY_FILE`

| | |
|---|---|
| **Default** | Windows: `%LOCALAPPDATA%\harness\master.key` / Other: `~/.harness/master.key` |
| **Accepted values** | Any writable file path |
| **Sample** | `HARNESS_KEY_FILE=/data/master.key` |

Path to the Fernet encryption key file. Created automatically with `chmod 600` on first use if it does not exist. Ignored when `HARNESS_MASTER_KEY` is set. Use this for persistent single-instance deployments where a file volume is available (e.g. Docker with a named volume).

---

## API & Networking

### `HARNESS_PUBLIC_URL`

| | |
|---|---|
| **Default** | `""` (empty — relative paths returned as-is) |
| **Accepted values** | Fully qualified base URL with no trailing slash |
| **Sample** | `HARNESS_PUBLIC_URL=https://evalbrew.ciostage.accenture.com` |

The publicly reachable base URL of the harness server. Prepended to relative path strings in headless API responses (e.g. the `results_url` field in job status responses) so external callers receive fully qualified URLs. Leave empty only when the API is consumed internally and relative paths are acceptable.

---

### `HARNESS_MAX_UPLOAD_BYTES`

| | |
|---|---|
| **Default** | `52428800` (50 MiB) |
| **Accepted values** | Integer number of bytes |
| **Sample** | `HARNESS_MAX_UPLOAD_BYTES=10485760` |

Maximum permitted CSV file size in bytes. Uploads exceeding this limit are rejected before any parsing occurs. Increase for large test datasets; decrease to protect server resources in multi-tenant environments.

---

## Mock / Testing

### `HARNESS_MOCK_MODE`

| | |
|---|---|
| **Default** | `ok` |
| **Accepted values** | `ok`, `status500`, `nonconformant`, `slow`, `unexpected_dims` |
| **Sample** | `HARNESS_MOCK_MODE=status500` |

Controls the failure-injection behaviour of the built-in mock connector and evaluator servers. Used in integration tests and local development to simulate error conditions without a real backend.

| Value | Behaviour |
|---|---|
| `ok` | Returns a well-formed successful response |
| `status500` | Returns HTTP 500 with an error body |
| `nonconformant` | Returns HTTP 200 with a malformed payload |
| `slow` | Sleeps before responding (simulates latency) |
| `unexpected_dims` | *(Evaluator only)* Includes an undeclared dimension in the result |

---

### `HARNESS_MOCK_DIMENSIONS`

| | |
|---|---|
| **Default** | `mock_dimension_a,mock_dimension_b` |
| **Accepted values** | Comma-separated dimension name strings |
| **Sample** | `HARNESS_MOCK_DIMENSIONS=accuracy,fluency,groundedness` |

The evaluation dimension names exposed by the mock evaluator server. Only used when `make_server()` is called without an explicit `dimensions` argument. Set this to match the dimensions your real evaluator returns when running integration tests.

---

## Quick-Reference Table

| Variable | Default | Required | Category |
|---|---|---|---|
| `HARNESS_AUTH_ENABLED` | `true` | No | Auth |
| `HARNESS_AZURE_TENANT_ID` | — | When auth enabled | Auth |
| `HARNESS_AZURE_CLIENT_ID` | — | When auth enabled | Auth |
| `HARNESS_AZURE_CLIENT_SECRET` | — | When auth enabled | Auth |
| `HARNESS_SESSION_SECRET` | — | When auth enabled | Auth |
| `HARNESS_REDIRECT_URI` | `""` | No | Auth |
| `HARNESS_AZURE_API_AUDIENCE` | `HARNESS_AZURE_CLIENT_ID` | No | Auth |
| `HARNESS_SESSION_HTTPS_ONLY` | `true` | No | Security |
| `HARNESS_ALLOWED_HOSTS` | `*` | No (set in production) | Security |
| `DATABASE_URL` | — | Yes | Database |
| `HARNESS_PG_USE_MANAGED_IDENTITY` | `false` | No (required on AKS) | Database |
| `HARNESS_MASTER_KEY` | — | No (recommended for containers) | Encryption |
| `HARNESS_KEY_FILE` | platform default | No | Encryption |
| `HARNESS_PUBLIC_URL` | `""` | No | API |
| `HARNESS_MAX_UPLOAD_BYTES` | `52428800` | No | API |
| `HARNESS_MOCK_MODE` | `ok` | No | Testing |
| `HARNESS_MOCK_DIMENSIONS` | `mock_dimension_a,mock_dimension_b` | No | Testing |
