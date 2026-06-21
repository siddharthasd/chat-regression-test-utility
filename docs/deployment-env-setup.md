# Deployment Environment Setup

This guide explains every environment variable the harness reads, when each one is
required, and how to configure a `.env` file for a new deployment.

---

## 1. How configuration works

The harness reads all configuration from environment variables. On startup, it
automatically loads a `.env` file from the project root if one is present.
Variables already set in the process environment (shell exports, systemd
`EnvironmentFile`, Docker `--env`, etc.) always take precedence over `.env` values —
so production deployments that inject secrets directly are unaffected by the file.

**Never commit `.env` to source control.** The repository already lists it in
`.gitignore`. Keep real secrets (client secrets, session keys) out of version history.

---

## 2. Variable reference

### Authentication

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_AUTH_ENABLED` | No | `true` | Set to `false` to disable SSO (local dev only). When `false`, all auth checks are skipped and a synthetic admin identity is used. |

### Azure AD app registration

All four variables are required when `HARNESS_AUTH_ENABLED=true`.

| Variable | Required | Description |
|---|---|---|
| `HARNESS_AZURE_TENANT_ID` | Yes* | GUID of your Azure AD tenant. Found in Azure Portal → Azure Active Directory → Overview. |
| `HARNESS_AZURE_CLIENT_ID` | Yes* | Client ID of the harness app registration. Found in App registrations → your app → Overview. |
| `HARNESS_AZURE_CLIENT_SECRET` | Yes* | Client secret value. Created in App registrations → your app → Certificates & secrets → New client secret. |
| `HARNESS_REDIRECT_URI` | Yes* | Full callback URL registered in the app registration. Use `http://localhost:5000/auth/callback` for local, `https://your-server/auth/callback` for a shared server. |

\* Required when `HARNESS_AUTH_ENABLED=true`.

### Session security

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_SESSION_SECRET` | Yes* | — | Random string used to sign session cookies. Must be at least 32 characters. Keep it secret. |

\* Required when `HARNESS_AUTH_ENABLED=true`.

Generate a key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Database

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_DB_PATH` | No | `~/.harness/data.db` (Windows: `%USERPROFILE%\.harness\data.db`) | Absolute path to the SQLite database file. Set this when you want the database in a specific location (e.g. a shared drive). |

### Encryption

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_KEY_FILE` | No | `%LOCALAPPDATA%\harness\master.key` (Windows) / `~/.harness/master.key` (Linux/Mac) | Path to the master encryption key file used to protect connector and evaluator credentials at rest. The file is created automatically on first run if it does not exist. |

### File upload

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_MAX_UPLOAD_BYTES` | No | `52428800` (50 MiB) | Maximum accepted size in bytes for CSV uploads. |

### Mock services (development and testing only)

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_MOCK_MODE` | No | `ok` | Controls mock connector/evaluator response type. Options: `ok` (well-formed response), `nonconformant` (malformed response), `status500` (HTTP 500), `slow` (5-second delay). |
| `HARNESS_MOCK_DIMENSIONS` | No | _(evaluator default)_ | Comma-separated list of scoring dimensions reported by the mock evaluator, e.g. `accuracy,tone,completeness`. |

---

## 3. Sample `.env` file

Copy this template to `.env` at the project root and fill in your values.

```dotenv
# =============================================================================
# AI Regression Test Harness — environment configuration
#
# Copy this file to .env and fill in the values for your environment.
# Lines starting with # are comments and are ignored.
# Variables already set in the process environment take precedence over this
# file, so CI/container deployments that inject secrets directly are unaffected.
# =============================================================================


# -----------------------------------------------------------------------------
# Authentication mode
# Set to "false" for local development (no login page, all routes accessible).
# Set to "true" (or remove this line) for a shared server deployment with SSO.
# -----------------------------------------------------------------------------
HARNESS_AUTH_ENABLED=true


# -----------------------------------------------------------------------------
# Azure AD app registration
# Required when HARNESS_AUTH_ENABLED=true. Obtain these from the Azure portal
# (App registrations → your harness app → Overview / Certificates & secrets).
# -----------------------------------------------------------------------------
HARNESS_AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
HARNESS_AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
HARNESS_AZURE_CLIENT_SECRET=your-client-secret-value-here

# Full callback URL registered in Azure AD.
# For local dev: http://localhost:5000/auth/callback
# For a shared server: https://your-server.accenture.com/auth/callback
HARNESS_REDIRECT_URI=https://your-server.accenture.com/auth/callback


# -----------------------------------------------------------------------------
# Session signing key
# Required when HARNESS_AUTH_ENABLED=true. Must be at least 32 characters.
# Generate a strong key with:
#   python -c "import secrets; print(secrets.token_hex(32))"
# Keep this secret — anyone who knows it can forge session cookies.
# -----------------------------------------------------------------------------
HARNESS_SESSION_SECRET=replace-with-output-of-the-command-above


# -----------------------------------------------------------------------------
# Database
# Path to the SQLite database file.
# Default (if unset): ~/.harness/data.db  (Windows: %USERPROFILE%\.harness\data.db)
# Uncomment and set if you want the database in a specific location.
# -----------------------------------------------------------------------------
# HARNESS_DB_PATH=C:\harness-data\data.db


# -----------------------------------------------------------------------------
# Encryption key file
# Path to the master encryption key used to protect connector/evaluator
# credentials at rest.
# Default (if unset): %LOCALAPPDATA%\harness\master.key  (Windows)
#                     ~/.harness/master.key               (Linux/Mac)
# Uncomment and set if you want the key file in a specific location.
# -----------------------------------------------------------------------------
# HARNESS_KEY_FILE=C:\harness-data\master.key


# -----------------------------------------------------------------------------
# File upload limit
# Maximum size in bytes for CSV uploads. Default: 52428800 (50 MiB).
# Uncomment to override.
# -----------------------------------------------------------------------------
# HARNESS_MAX_UPLOAD_BYTES=52428800


# -----------------------------------------------------------------------------
# Mock connector / evaluator behaviour (development and testing only)
# Leave these commented out in production.
# -----------------------------------------------------------------------------
# HARNESS_MOCK_MODE=ok
# HARNESS_MOCK_DIMENSIONS=
```

---

## 4. Deployment checklist

Work through this list when setting up a new server deployment.

**Azure AD (one-time, done by IT / Azure admin)**

- [ ] Create an app registration in your Azure AD tenant.
- [ ] Add a redirect URI: `https://your-server/auth/callback` (Web platform, not SPA).
- [ ] Generate a client secret (Certificates & secrets → New client secret). Note the **value** — it is only shown once.
- [ ] Grant the `openid`, `profile`, and `email` API permissions (Microsoft Graph → Delegated).
- [ ] Note your Tenant ID and Client ID from the app registration Overview.

**Server host**

- [ ] Copy the `.env` template above to the project root as `.env`.
- [ ] Set `HARNESS_AUTH_ENABLED=true`.
- [ ] Fill in `HARNESS_AZURE_TENANT_ID`, `HARNESS_AZURE_CLIENT_ID`, `HARNESS_AZURE_CLIENT_SECRET`.
- [ ] Set `HARNESS_REDIRECT_URI` to the exact URL registered in Azure AD.
- [ ] Generate and set `HARNESS_SESSION_SECRET` (minimum 32 characters).
- [ ] Optionally set `HARNESS_DB_PATH` and `HARNESS_KEY_FILE` to non-default locations.
- [ ] Verify `.env` is **not** committed to git (`git status` should not show it).
- [ ] Restrict file permissions: `chmod 600 .env` (Linux/Mac) or remove non-owner read access (Windows).

**First run**

- [ ] Start the server once to apply database migrations: `harness serve`.
- [ ] Pre-register the first admin via CLI: `harness users add --email you@accenture.com --role admin`.
- [ ] Navigate to the harness URL, log in with your Azure AD account, and confirm you land on the dashboard with an admin role badge.

---

## 5. Rotating secrets

**Client secret expired or compromised**

1. Create a new client secret in the Azure portal (Certificates & secrets → New client secret).
2. Update `AZURE_CLIENT_SECRET` in `.env` (or your secret manager).
3. Restart the harness process to pick up the new value.
4. Delete the old secret from the Azure portal.

**Session key rotation**

Rotating `HARNESS_SECRET_KEY` invalidates all active sessions — every logged-in user will be redirected to the login page on their next request.

1. Generate a new key: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `HARNESS_SECRET_KEY` in `.env`.
3. Restart the harness process.

---

## 6. Local development (no SSO)

Set `HARNESS_AUTH_ENABLED=false`. All other auth variables are ignored. A synthetic
admin identity is used, so all routes and admin features are accessible without a login
page.

The included `.env` ships with `HARNESS_AUTH_ENABLED=false` for this reason — it works
out of the box for local use. Change it to `true` only when deploying to a shared
server.
