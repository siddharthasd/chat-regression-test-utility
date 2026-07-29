###### common ######
variable "airid" {
  description = "AIR ID"
  type        = string
}

variable "aks_cluster_name" {
  description = "AKS cluster name"
  type        = string
}

variable "aks_resource_group_name" {
  description = "AKS resource group name"
  type        = string
}


variable "certificate_name" {
  description = "name of app certificate"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Environment(brd, brs, brp)"
  type        = string
}

variable "acr_name" {
  description = "acr name"
  type        = string
}

variable "sub_environment" {
  description = "the sub environment name given in the AKS Config to the namespace"
  type        = string
  default     = ""
}

###### ingress ######
variable "ssl_certificate" {
  description = "SSL certificate file name"
  type        = string
}

variable "ssl_password" {
  description = "SSL certificate password"
  type        = string
}

variable "ingress_host" {
  description = "Ingress host"
  type        = string
}

variable "ingress_name" {
  description = "Ingress name"
  type        = string
}

###### service ######
variable "image_tag" {
  description = "Image tag"
  type        = string
}

variable "api_1" {
  description = "api_1 name"
  type        = string
}

variable "healthcheck_api_1" {
  description = "healthcheck_api_1"
  type        = string
}

variable "api_1_port" {
  description = "api_1 port"
  type        = string
}

variable "replicas" {
  description = "replicas"
  type        = string
}

variable "max_replicas" {
  description = "max replicas"
  type        = string
}

variable "target_cpu" {
  description = "cpu target"
  type        = string
}

variable "proxy_buffer_size" {
  description = "nginx proxy buffer size"
  type        = any
  default     = {}
}
 
variable "proxy_buffering" {
  description = "proxy buffering"
  type        = any
  default     = {}
}
 
variable "backend_protocol" {
  description = "ALB backend protocol in EKS 2.0 and AKS 2.0"
  type        = string
}

variable "HARNESS_AUTH_ENABLED" {
  description = "Authentication mode"
  type        = bool
}

variable "HARNESS_AZURE_TENANT_ID" {
  description = "Application Tenant ID"
  type        = string
}

variable "HARNESS_AZURE_CLIENT_ID" {
  description = "Application Client ID"
  type        = string
}

variable "HARNESS_AZURE_CLIENT_SECRET" {
  description = "Application Client Secret"
  type        = string
}

variable "HARNESS_REDIRECT_URI" {
  description = "Redirect url configured in app registration"
  type        = string
}

variable "HARNESS_SESSION_SECRET" {
  description = "session secret"
  type        = string
}

variable "LOG_LEVEL" {
  description = "debug logs"
  type        = string
}

variable "HARNESS_PG_HOST" {
  description = "PostgresSQL Database endpoint "
  type        = string
}

variable "HARNESS_PG_USER" {
  description = "PostgresSQL Database user "
  type        = string
}

variable "HARNESS_PG_DB" {
  description = "PostgresSQL Database "
  type        = string
}

variable "AZURE_CLIENT_ID" {
  description = "Managed Identity client id "
  type        = string
}

variable "HARNESS_DB_USE_MANAGED_IDENTITY" {
  description = "Enable Entra ID token auth for PostgreSQL"
  type        = string
  default     = "false"
}

variable "HARNESS_PG_USE_MANAGED_IDENTITY" {
  description = "Enable Entra ID token auth for PostgreSQL"
  type        = string
  default     = "false"
}

variable "harness_master_key" {
  description = "Fernet key for per-credential encryption of stored authDescriptors "
  type        = string
}