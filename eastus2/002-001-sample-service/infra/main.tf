locals {
  env_code_short = {
    # Azure 2.0
    "sbx" = "03"
    "npd" = "02"
    "prd" = "01"
  }
  env_code = local.env_code_short[var.environment]
}

data "azurerm_subscription" "current" {}

data "azurerm_kubernetes_cluster" "this" {
  name                = var.aks_cluster_name
  resource_group_name = var.aks_resource_group_name
}

module "kubernetes" {
  source  = "acnciotfregistry.accenture.com/accenture-cio/kubernetes/kubernetes"
  version = "2.13.0"

  platform    = "AKS2"
  environment = var.environment

  platform_config = {
    airid           = var.airid
    sub_environment = var.sub_environment
  }

  service = {
    "${var.api_1}" = {
      image              = "${var.acr_name}.azurecr.io/${var.api_1}:${var.image_tag}"
      pullPolicy         = "Always"
      healthcheck        = var.healthcheck_api_1
      healthcheck_scheme = "HTTPS"
      ssl_certificate    = var.ssl_certificate
      ssl_password       = var.ssl_password
      port               = var.api_1_port
      replicas           = var.replicas
      max_replicas       = var.max_replicas
      target_cpu         = var.target_cpu
      # Inject configuration secrets into the pod (module kubernetes v2.13.0)
      # configuration{} only CREATES the K8s Secrets; variables mounts them as env.
      variables          = ["azuread", "myapp-configuration"]

      resources = {
        memory         = "512Mi"
        cpu            = "500m"
        memory_request = "256Mi"
        cpu_request    = "250m"
      }
    }
  }

  configuration = {
  myapp-configuration = {
    HARNESS_ENVIRONMENT = var.environment
    SOME_VARIABLE       = 1
  }
  azuread = {
    HARNESS_AUTH_ENABLED        = var.HARNESS_AUTH_ENABLED
    HARNESS_AZURE_TENANT_ID     = var.HARNESS_AZURE_TENANT_ID
    HARNESS_AZURE_CLIENT_ID     = var.HARNESS_AZURE_CLIENT_ID
    HARNESS_AZURE_CLIENT_SECRET = var.HARNESS_AZURE_CLIENT_SECRET
    HARNESS_REDIRECT_URI        = var.HARNESS_REDIRECT_URI
    HARNESS_SESSION_SECRET      = var.HARNESS_SESSION_SECRET
    LOG_LEVEL                   = var.LOG_LEVEL
    HARNESS_PG_HOST             = var.HARNESS_PG_HOST
    HARNESS_PG_USER             = var.HARNESS_PG_USER
    HARNESS_PG_DB               = var.HARNESS_PG_DB
    AZURE_CLIENT_ID             = var.AZURE_CLIENT_ID
    HARNESS_DB_USE_MANAGED_IDENTITY = var.HARNESS_DB_USE_MANAGED_IDENTITY
    HARNESS_PG_USE_MANAGED_IDENTITY = var.HARNESS_PG_USE_MANAGED_IDENTITY
    harness_master_key          = var.harness_master_key
  }
}
  ingress = {
    certificate_name  = var.certificate_name
    ssl_certificate   = var.ssl_certificate
    ssl_password      = var.ssl_password
    host              = var.ingress_host
    name              = var.ingress_name
    default_service   = var.api_1
    default_port      = var.api_1_port
    proxy_buffering   = var.proxy_buffering
    proxy_buffer_size = var.proxy_buffer_size
    backend_protocol  = var.backend_protocol
  }
}

