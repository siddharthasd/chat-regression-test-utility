# ============================================================
# eval-brew — Terraform variable declarations
# Matches terraform.tfvars; sensitive variables are marked
# sensitive = true so Terraform redacts them in plan output.
# ============================================================

# ------------------------------------
# Azure Resource Configuration
# ------------------------------------
variable "resource_group_name" {
  description = "Name of the Azure resource group that contains all eval-brew resources."
  type        = string
}

variable "location" {
  description = "Azure region for all resources (e.g. eastus2)."
  type        = string
  default     = "eastus2"
}

variable "aks_cluster_name" {
  description = "Name of the AKS cluster."
  type        = string
}

variable "acr_name" {
  description = "Name of the Azure Container Registry (without .azurecr.io suffix)."
  type        = string
}

# ------------------------------------
# Container Image
# ------------------------------------
variable "image_repository" {
  description = "Full container image repository path (e.g. acncio.azurecr.io/evalbrew)."
  type        = string
}

variable "image_tag" {
  description = "Container image tag to deploy."
  type        = string
  default     = "latest"
}

variable "container_port" {
  description = "Port the eval-brew container listens on."
  type        = number
  default     = 8443
}

variable "replicas" {
  description = "Number of AKS pod replicas."
  type        = number
  default     = 2
}

# ------------------------------------
# PostgreSQL Flexible Server (PaaS)
# ------------------------------------
variable "pg_server_name" {
  description = "Name of the Azure PostgreSQL Flexible Server (without .postgres.database.azure.com suffix)."
  type        = string
}

variable "pg_database_name" {
  description = "Name of the PostgreSQL database."
  type        = string
  default     = "evalbrew"
}

variable "pg_admin_username" {
  description = "PostgreSQL administrator username."
  type        = string
}

variable "pg_admin_password" {
  description = "PostgreSQL administrator password used by Terraform to provision the server. Not used by the app at runtime when managed identity is enabled. Inject via Azure Key Vault — never commit a real value."
  type        = string
  sensitive   = true
}

variable "pg_sku_name" {
  description = "SKU for the PostgreSQL Flexible Server (e.g. B_Standard_B1ms)."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "pg_storage_mb" {
  description = "Storage allocated to the PostgreSQL server in MB."
  type        = number
  default     = 32768
}

variable "pg_version" {
  description = "PostgreSQL major version."
  type        = string
  default     = "16"
}

variable "harness_pg_use_managed_identity" {
  description = "When 'true', the app authenticates to PostgreSQL using an Azure AD token via DefaultAzureCredential (AKS workload identity) instead of a static password. DATABASE_URL must omit the password. Required for AKS deployments."
  type        = string
  default     = "false"
}

# ------------------------------------
# App Environment — Authentication
# ------------------------------------
variable "harness_auth_enabled" {
  description = "Set to 'true' to enable Azure AD authentication. Set 'false' only for offline dev/test."
  type        = string
  default     = "true"
}

variable "harness_azure_tenant_id" {
  description = "Azure AD tenant ID used for OAuth2 and JWKS validation."
  type        = string
}

variable "harness_azure_client_id" {
  description = "Azure AD application (client) ID registered for eval-brew."
  type        = string
}

variable "harness_azure_client_secret" {
  description = "Azure AD client secret for eval-brew. Inject via Azure Key Vault."
  type        = string
  sensitive   = true
}

variable "harness_azure_api_audience" {
  description = "Expected 'aud' claim for headless API Bearer tokens (020). Defaults to harness_azure_client_id when blank."
  type        = string
  default     = ""
}

variable "harness_redirect_uri" {
  description = "Azure AD OAuth2 redirect URI (must match the app registration)."
  type        = string
}

variable "harness_session_secret" {
  description = "Secret key for Starlette session cookie signing (32+ random characters). Inject via Azure Key Vault."
  type        = string
  sensitive   = true
}

# ------------------------------------
# App Environment — Encryption
# ------------------------------------
variable "harness_master_key" {
  description = "Fernet key for per-credential encryption of stored authDescriptors. Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\". Inject via Azure Key Vault."
  type        = string
  sensitive   = true
}

# ------------------------------------
# App Environment — Runtime
# ------------------------------------
variable "harness_session_https_only" {
  description = "Enforce HTTPS-only session cookies. Set 'false' only in non-TLS test environments."
  type        = string
  default     = "true"
}

variable "harness_allowed_hosts" {
  description = "Comma-separated list of trusted hostnames for TrustedHostMiddleware (prevents Host-header injection)."
  type        = string
}

variable "log_level" {
  description = "Application log verbosity (debug, info, warning, error)."
  type        = string
  default     = "info"
}
