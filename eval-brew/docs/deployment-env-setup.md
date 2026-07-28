# Deployment Environment Setup

This guide explains every environment variable the harness reads, when each one is
required, and how to configure a deployment — including step-by-step instructions for
deploying to an Azure container backed by Azure Database for PostgreSQL.

---

## 1. How configuration works

The harness reads all configuration from environment variables. On startup, it
automatically loads a `.env` file from the project root if one is present.
Variables already set in the process environment (shell exports, systemd
`EnvironmentFile`, Docker `--env`, App Service Application Settings, etc.) always
take precedence over `.env` values — so production deployments that inject secrets
directly are unaffected by the file.

**Never commit `.env` to source control.** The repository already lists it in
`.gitignore`. Keep real secrets (client secrets, session keys, database passwords)
out of version history.

---

## 2. Variable reference

### Authentication

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_AUTH_ENABLED` | No | `false` | Set to `true` to enable SSO (required for multi-user and production deployments). When `false` (the default), all auth checks are skipped and a synthetic admin identity is used. |

### Azure AD app registration

All four variables are required when `HARNESS_AUTH_ENABLED=true`.

| Variable | Required | Description |
|---|---|---|
| `HARNESS_AZURE_TENANT_ID` | Yes* | GUID of your Azure AD tenant. Found in Azure Portal → Azure Active Directory → Overview. |
| `HARNESS_AZURE_CLIENT_ID` | Yes* | Client ID of the harness app registration. Found in App registrations → your app → Overview. |
| `HARNESS_AZURE_CLIENT_SECRET` | Yes* | Client secret value. Created in App registrations → your app → Certificates & secrets → New client secret. |
| `HARNESS_REDIRECT_URI` | Yes* | Full callback URL registered in the app registration. Use `http://localhost:5000/auth/callback` for local, `https://your-server/auth/callback` for a shared server. |
| `HARNESS_AZURE_API_AUDIENCE` | No | Expected `aud` claim for Bearer tokens on the headless API. Defaults to `HARNESS_AZURE_CLIENT_ID` when not set — leave unset unless your M2M clients request a different resource URI. |

\* Required when `HARNESS_AUTH_ENABLED=true`.

### Session security

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_SESSION_SECRET` | Yes* | — | Random string used to sign session cookies. Must be at least 32 characters. Keep it secret. |

\* Strictly required when `HARNESS_AUTH_ENABLED=true`. When auth is disabled, the server starts without it, but a missing value causes a fresh random key to be generated on every restart — invalidating any in-flight session state. Set a stable value in all persistent deployments regardless of auth mode.

Generate a key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Database

PostgreSQL is the only supported database backend. `DATABASE_URL` is required for all deployments.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | Full SQLAlchemy connection URL for PostgreSQL. Format: `postgresql+psycopg2://user:password@host:5432/dbname?sslmode=require` |

### Encryption

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_MASTER_KEY` | No | — | Fernet key supplied directly as an environment variable. **Recommended for container and PaaS deployments.** When set, no key file is read or written. Takes precedence over `HARNESS_KEY_FILE`. |
| `HARNESS_KEY_FILE` | No | `%LOCALAPPDATA%\harness\master.key` (Windows) / `~/.harness/master.key` (Linux/Mac) | Path to the master encryption key file. Used only when `HARNESS_MASTER_KEY` is not set. The file is created automatically on first run if it does not exist. |

> **Container deployments must set `HARNESS_MASTER_KEY`** (or mount `HARNESS_KEY_FILE`
> on persistent storage). The container filesystem is ephemeral — if the key is lost,
> all stored connector and evaluator credentials become unreadable.
>
> Generate a key once and store it as a permanent secret:
>
> ```bash
> python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
> ```

### File upload

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_MAX_UPLOAD_BYTES` | No | `52428800` (50 MiB) | Maximum accepted size in bytes for CSV uploads. |

### Server & networking

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_PUBLIC_URL` | No* | — | Base URL the server uses when constructing absolute links for external callers, e.g. `https://your-app.azurewebsites.net`. Used in headless API responses (`results_url`). If unset, `results_url` in job results will be `null`. |

\* Required for the headless API `results_url` to be usable by M2M callers. Not needed for browser-only deployments.

### Mock services (development and testing only)

| Variable | Required | Default | Description |
|---|---|---|---|
| `HARNESS_MOCK_MODE` | No | `ok` | Controls mock connector/evaluator response type. Options: `ok` (well-formed response), `nonconformant` (malformed response), `status500` (HTTP 500), `slow` (5-second delay). |
| `HARNESS_MOCK_DIMENSIONS` | No | _(evaluator default)_ | Comma-separated list of scoring dimensions reported by the mock evaluator, e.g. `accuracy,tone,completeness`. |

---

## 3. Sample `.env` files

### Local development (no SSO)

```dotenv
HARNESS_AUTH_ENABLED=false
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/evalbrew
```

### Azure container deployment (PostgreSQL, SSO enabled)

```dotenv
# Authentication
HARNESS_AUTH_ENABLED=true
HARNESS_AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
HARNESS_AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
HARNESS_AZURE_CLIENT_SECRET=your-client-secret-value-here
HARNESS_REDIRECT_URI=https://your-app.azurewebsites.net/auth/callback

# Session signing key (generate with: python -c "import secrets; print(secrets.token_hex(32))")
HARNESS_SESSION_SECRET=replace-with-a-random-64-char-hex-string

# PostgreSQL on Azure (set in App Service Application Settings, not in a .env file)
DATABASE_URL=postgresql+psycopg2://harness_user:PASSWORD@your-server.postgres.database.azure.com:5432/evalbrew?sslmode=require

# Encryption key — set once, store as a permanent secret (generate with the command above)
HARNESS_MASTER_KEY=<your-fernet-key>

# Public base URL — required for headless API results_url to be usable by M2M callers
HARNESS_PUBLIC_URL=https://your-app.azurewebsites.net
```

> Do not commit the Azure `.env` to source control. In App Service, set these as
> Application Settings rather than deploying a `.env` file.

---

## 4. Azure Container Deployment

This section walks through deploying EvalBrew to **Azure App Service (Web App for
Containers)** backed by **Azure Database for PostgreSQL — Flexible Server**.

### Prerequisites

- Azure CLI installed and logged in (`az login`)
- Docker Desktop installed and running
- An Azure subscription with permission to create resources

Set shell variables used throughout the steps below (adjust values for your environment):

```bash
RG=rg-evalbrew-prod
LOCATION=australiaeast
ACR_NAME=acrevalbrew
APP_NAME=evalbrew
APP_PLAN=asp-evalbrew
PG_SERVER=pg-evalbrew
PG_DB=evalbrew
PG_ADMIN=harness_admin
PG_PASSWORD="<choose-a-strong-password>"
STORAGE_ACCOUNT=stevalbrew
FILE_SHARE=harness-data
```

---

### Step 1 — Create the resource group

```bash
az group create --name $RG --location $LOCATION
```

---

### Step 2 — Create Azure Container Registry

```bash
az acr create \
  --resource-group $RG \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true
```

Note the login server (it will be `<ACR_NAME>.azurecr.io`):

```bash
ACR_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)
```

---

### Step 3 — Build and push the Docker image

```bash
# Log in to ACR
az acr login --name $ACR_NAME

# Build and tag
docker build -t $ACR_SERVER/evalbrew:latest .

# Push
docker push $ACR_SERVER/evalbrew:latest
```

To rebuild and redeploy after code changes, repeat this step then restart the App
Service (Step 7).

---

### Step 4 — Create Azure Database for PostgreSQL — Flexible Server

```bash
az postgres flexible-server create \
  --resource-group $RG \
  --name $PG_SERVER \
  --location $LOCATION \
  --admin-user $PG_ADMIN \
  --admin-password $PG_PASSWORD \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --public-access 0.0.0.0
```

> `--public-access 0.0.0.0` creates a firewall rule that allows all Azure-internal IPs
> (including App Service). Restrict this further in production using VNet integration.

> **Connection pool sizing.** The harness opens up to 5 PostgreSQL connections per
> worker process (pool\_size 2 + max\_overflow 3). The B1ms tier allows 50 connections
> total, which safely supports up to 10 parallel App Service workers. If you scale out
> to more workers, move to a Standard\_D2s\_v3 or larger tier to avoid connection
> exhaustion.

Create the database:

```bash
az postgres flexible-server db create \
  --resource-group $RG \
  --server-name $PG_SERVER \
  --database-name $PG_DB
```

Note the fully qualified hostname:

```bash
PG_HOST="${PG_SERVER}.postgres.database.azure.com"
```

Compose the connection URL:

```bash
DATABASE_URL="postgresql+psycopg2://${PG_ADMIN}:${PG_PASSWORD}@${PG_HOST}:5432/${PG_DB}?sslmode=require"
```

---

### Step 5 — Generate and store the encryption key

The master encryption key must survive container restarts and redeployments.

**Recommended: `HARNESS_MASTER_KEY` App Service Application Setting**

Generate a key once and keep it — you will set it as an Application Setting in Step 7:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output. Do not regenerate it later; any new key will make previously stored
credentials unreadable.

**Alternative: Azure Files share (if you prefer file-based key storage)**

If you have a policy reason to keep the key on a mounted volume rather than in an
Application Setting, create a storage account and file share:

```bash
# Create storage account
az storage account create \
  --resource-group $RG \
  --name $STORAGE_ACCOUNT \
  --sku Standard_LRS \
  --kind StorageV2

# Create the file share
STORAGE_KEY=$(az storage account keys list \
  --resource-group $RG \
  --account-name $STORAGE_ACCOUNT \
  --query "[0].value" -o tsv)

az storage share create \
  --account-name $STORAGE_ACCOUNT \
  --account-key $STORAGE_KEY \
  --name $FILE_SHARE
```

Then in Step 6, mount it at `/mnt/harness-data` and in Step 7 set
`HARNESS_KEY_FILE=/mnt/harness-data/master.key` instead of `HARNESS_MASTER_KEY`.

---

### Step 6 — Create App Service and deploy the container

```bash
# App Service Plan (Linux)
az appservice plan create \
  --resource-group $RG \
  --name $APP_PLAN \
  --is-linux \
  --sku B2

# Web App for Containers
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)

az webapp create \
  --resource-group $RG \
  --plan $APP_PLAN \
  --name $APP_NAME \
  --deployment-container-image-name $ACR_SERVER/evalbrew:latest \
  --docker-registry-server-url https://$ACR_SERVER \
  --docker-registry-server-user $ACR_NAME \
  --docker-registry-server-password $ACR_PASSWORD
```

Mount the Azure Files share at `/mnt/harness-data` inside the container:

```bash
az webapp config storage-account add \
  --resource-group $RG \
  --name $APP_NAME \
  --custom-id harness-data \
  --storage-type AzureFiles \
  --account-name $STORAGE_ACCOUNT \
  --share-name $FILE_SHARE \
  --access-key $STORAGE_KEY \
  --mount-path /mnt/harness-data
```

> **Container user.** The container process runs as uid 1001 (`harness`). Files written
> to the Azure Files mount will be owned by uid 1001. If you pre-populate the share with
> a key file (for the `HARNESS_KEY_FILE` alternative), ensure the file is readable by
> uid 1001 (mode `0600` or `0640` is sufficient on most Azure Files mounts).

---

### Step 7 — Set Application Settings (environment variables)

These replace the `.env` file in production. App Service injects them directly into the
container's environment.

```bash
az webapp config appsettings set \
  --resource-group $RG \
  --name $APP_NAME \
  --settings \
    DATABASE_URL="$DATABASE_URL" \
    HARNESS_MASTER_KEY="<key-from-step-5>" \
    HARNESS_AUTH_ENABLED="true" \
    HARNESS_AZURE_TENANT_ID="<your-tenant-id>" \
    HARNESS_AZURE_CLIENT_ID="<your-client-id>" \
    HARNESS_AZURE_CLIENT_SECRET="<your-client-secret>" \
    HARNESS_REDIRECT_URI="https://${APP_NAME}.azurewebsites.net/auth/callback" \
    HARNESS_SESSION_SECRET="<generate-with-python-secrets-token-hex-32>" \
    HARNESS_PUBLIC_URL="https://${APP_NAME}.azurewebsites.net" \
    WEBSITES_PORT="8000"
```

> `WEBSITES_PORT=8000` tells App Service which port the container listens on (uvicorn
> binds to `0.0.0.0:8000` by default).
>
> `HARNESS_PUBLIC_URL` sets the base URL embedded in headless API `results_url` responses.
> Set it to the public HTTPS address of your App Service.

---

### Step 8 — First-run: migrations and admin user

Alembic migrations run automatically when the harness starts. Verify in the App Service
log stream:

```bash
az webapp log tail --resource-group $RG --name $APP_NAME
```

Look for lines like:
```
Running migrations...
INFO  [alembic.runtime.migration] Running upgrade -> 0001, initial schema
...
INFO  [alembic.runtime.migration] Running upgrade <prev> -> <latest>, <description>
Migrations complete.
```

The exact revision identifiers will vary with the installed version. If any migration fails, the process exits with a non-zero code and the log will show an `ERROR` line before the exit.

Then register the first admin user via the App Service console or SSH:

```bash
az webapp ssh --resource-group $RG --name $APP_NAME
# inside the container:
harness users add --email you@accenture.com --role admin
```

---

### Step 9 — Verify

1. Open `https://<APP_NAME>.azurewebsites.net` in a browser.
2. You should be redirected to the Azure AD login page.
3. After login, confirm you land on the dashboard with an **Admin** role badge.
4. Navigate to **Admin → Job Maintenance** to confirm admin features are accessible.

---

### Redeploying after code changes

```bash
docker build -t $ACR_SERVER/evalbrew:latest .
docker push $ACR_SERVER/evalbrew:latest
az webapp restart --resource-group $RG --name $APP_NAME
```

The harness will automatically run any new Alembic migrations on startup. No manual
database intervention is needed.

---

## 5. Deployment checklist

### Azure AD (one-time, done by IT / Azure admin)

- [ ] Create an app registration in your Azure AD tenant.
- [ ] Add a redirect URI: `https://<APP_NAME>.azurewebsites.net/auth/callback` (Web platform, not SPA).
- [ ] Generate a client secret (Certificates & secrets → New client secret). Note the **value** — it is only shown once.
- [ ] Grant the `openid`, `profile`, and `email` API permissions (Microsoft Graph → Delegated).
- [ ] Note your Tenant ID and Client ID from the app registration Overview.

### Azure resources

- [ ] Resource group created.
- [ ] Azure Container Registry created and image pushed.
- [ ] Azure Database for PostgreSQL — Flexible Server created.
- [ ] `evalbrew` database created on the server.
- [ ] Firewall rule allows App Service egress (or VNet integration configured).
- [ ] Fernet encryption key generated (Step 5) and saved somewhere safe.

### App Service configuration

- [ ] Web App for Containers created and pointing to the ACR image.
- [ ] `DATABASE_URL` set in Application Settings (PostgreSQL connection string with `sslmode=require`).
- [ ] `HARNESS_MASTER_KEY` set in Application Settings (Fernet key from Step 5).
- [ ] `HARNESS_AUTH_ENABLED=true`.
- [ ] `HARNESS_AZURE_TENANT_ID`, `HARNESS_AZURE_CLIENT_ID`, `HARNESS_AZURE_CLIENT_SECRET` set.
- [ ] `HARNESS_REDIRECT_URI` matches the redirect URI registered in Azure AD exactly.
- [ ] `HARNESS_SESSION_SECRET` set (minimum 32 characters, random).
- [ ] `HARNESS_PUBLIC_URL` set to the public HTTPS address (required for headless API `results_url`).
- [ ] `WEBSITES_PORT=8000` set.

### First run

- [ ] App Service started; log stream shows migrations completing without errors.
- [ ] First admin user registered: `harness users add --email you@accenture.com --role admin`.
- [ ] Login verified end-to-end in a browser.

---

## 6. Rotating secrets

### Encryption key — do not rotate without a migration plan

> **Warning: rotating `HARNESS_MASTER_KEY` permanently breaks all stored credentials.**
> Every connector and evaluator credential in the database is encrypted with the current
> key. If you replace the key with a new value, those records become permanently
> unreadable — there is no automatic re-encryption. Before rotating the key, export all
> connector and evaluator credentials from the UI, then re-enter them after the rotation.
>
> The safest strategy is to back up the key securely (Azure Key Vault, a password
> manager) and never rotate it unless it is compromised. If rotation is unavoidable:
> 1. Export all credentials from the UI.
> 2. Generate a new key and update `HARNESS_MASTER_KEY` in Application Settings.
> 3. Restart the App Service.
> 4. Re-enter every connector and evaluator credential via the UI.

### Client secret expired or compromised

1. Create a new client secret in the Azure portal (Certificates & secrets → New client secret).
2. Update `HARNESS_AZURE_CLIENT_SECRET` in App Service Application Settings.
3. Restart the App Service to pick up the new value.
4. Delete the old secret from the Azure portal.

### Session key rotation

Rotating `HARNESS_SESSION_SECRET` invalidates all active sessions — every logged-in
user will be redirected to the login page on their next request.

1. Generate a new key: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `HARNESS_SESSION_SECRET` in App Service Application Settings.
3. Restart the App Service.

### PostgreSQL password rotation

1. Update the password in Azure Portal (PostgreSQL server → Settings → Server parameters, or via CLI).
2. Update `DATABASE_URL` in App Service Application Settings with the new password.
3. Restart the App Service.

---

## 7. Headless API (M2M) configuration

The headless API (`/api/v1/jobs`) lets CI/CD pipelines and automated scripts create jobs
and poll results without the browser UI. Authentication uses Bearer JWTs issued by Azure
AD for a service-principal (client-credentials flow).

### Required variables

| Variable | Notes |
|---|---|
| `HARNESS_AUTH_ENABLED` | Must be `true`. Bearer auth is only enforced when SSO is enabled. |
| `HARNESS_AZURE_TENANT_ID` | Same tenant as the interactive SSO app registration. |
| `HARNESS_AZURE_CLIENT_ID` | The app registration the M2M client targets as the resource. |
| `HARNESS_AZURE_API_AUDIENCE` | Optional. Expected `aud` claim in incoming Bearer tokens. Defaults to `HARNESS_AZURE_CLIENT_ID` when unset — only set this if your M2M clients request a different resource URI. |
| `HARNESS_PUBLIC_URL` | Required for `results_url` in job-result responses to be absolute and usable outside the server. |

### Setting up a service principal

1. In your Azure AD tenant, create (or reuse) an app registration for the M2M caller.
2. In the **harness** app registration, add an **Application permission** (not Delegated)
   or an **App Role** to define what the caller is allowed to do.
3. Grant admin consent for the new permission.
4. In the caller app, create a client secret and configure it in your pipeline as
   `AZURE_CLIENT_SECRET` (or equivalent for your SDK).

The M2M caller acquires a token with scope `api://<HARNESS_AZURE_CLIENT_ID>/.default` and
passes it as `Authorization: Bearer <token>` on each request.

### Example headless workflow

```bash
# Acquire a token (using Azure CLI for illustration)
TOKEN=$(az account get-access-token --resource api://<client-id> --query accessToken -o tsv)

# Create a job
JOB=$(curl -s -X POST https://your-app.azurewebsites.net/api/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @payload.json)
JOB_ID=$(echo $JOB | jq -r .job_id)

# Poll until complete
while true; do
  STATUS=$(curl -s -H "Authorization: Bearer $TOKEN" \
    https://your-app.azurewebsites.net/api/v1/jobs/$JOB_ID/status | jq -r .status)
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 10
done

# Fetch results
curl -s -H "Authorization: Bearer $TOKEN" \
  https://your-app.azurewebsites.net/api/v1/jobs/$JOB_ID/results
```

---

## 8. Local development (no SSO)

Set `HARNESS_AUTH_ENABLED=false`. All other auth variables are ignored. A synthetic
admin identity is used, so all routes and admin features are accessible without a login
page.

Install PostgreSQL locally (or use a Docker container), create a database, then set:

```bash
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/evalbrew
```

Alembic migrations run automatically on first start.
