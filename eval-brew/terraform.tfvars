# ============================================================
# eval-brew — AKS deployment variable values
# Replaces local.settings.json for container deployments.
#
# Secrets (marked CHANGEME) must be injected via Azure Key
# Vault or a CI/CD pipeline secret store.
# NEVER commit real secret values to source control.
# ============================================================

# ------------------------------------
# Azure Resource Configuration
# ------------------------------------
resource_group_name = "rg-evalbrew-prod"
location            = "eastus2"
aks_cluster_name    = "aks-evalbrew-prod"
acr_name            = "acncio"

# ------------------------------------
# Container Image
# ------------------------------------
image_repository = "acncio.azurecr.io/evalbrew"
image_tag        = "latest"
container_port   = 8443
replicas         = 2

# ------------------------------------
# PostgreSQL Flexible Server (PaaS)
# ------------------------------------
# The Terraform module assembles DATABASE_URL from these values:
#   postgresql+psycopg2://<pg_admin_username>:<pg_admin_password>@<pg_server_name>.postgres.database.azure.com:5432/<pg_database_name>?sslmode=require
pg_server_name    = "evalbrew-pg"
pg_database_name  = "evalbrew"
pg_admin_username = "evalbrew_admin"
pg_admin_password = "CHANGEME"   # inject via Azure Key Vault
pg_sku_name       = "B_Standard_B1ms"
pg_storage_mb     = 32768
pg_version        = "16"

# ------------------------------------
# App Environment — Authentication
# ------------------------------------
harness_auth_enabled        = "true"
harness_azure_tenant_id     = "CHANGEME"
harness_azure_client_id     = "CHANGEME"
harness_azure_client_secret = "CHANGEME"   # inject via Azure Key Vault
# API audience for headless Bearer tokens (020).
# Leave blank to default to harness_azure_client_id at runtime.
harness_azure_api_audience  = ""
harness_redirect_uri        = "https://evalbrew.example.com/auth/callback"
# 32+ character random string — inject via Azure Key Vault
harness_session_secret      = "CHANGEME"

# ------------------------------------
# App Environment — Encryption
# ------------------------------------
# Fernet key for per-credential encryption of stored authDescriptors.
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Preferred over HARNESS_KEY_FILE in container deployments — inject via Azure Key Vault.
harness_master_key = "8vvkLLKkfbnhhEamDHBzNYkMa3_2utHLaEBN8o6g2jM="

# ------------------------------------
# App Environment — Runtime
# ------------------------------------
harness_session_https_only = "true"
# Comma-separated list of valid hostnames; prevents Host-header injection.
harness_allowed_hosts = "evalbrew.example.com"
log_level             = "info"
