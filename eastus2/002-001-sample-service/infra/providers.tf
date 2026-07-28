provider "azurerm" {
  skip_provider_registration = true
  features {}
}
provider "kubernetes" {
  experiments {
    manifest_resource = true
  }
  host                   = data.azurerm_kubernetes_cluster.this.kube_admin_config.0.host
  client_certificate     = base64decode(data.azurerm_kubernetes_cluster.this.kube_admin_config.0.client_certificate)
  client_key             = base64decode(data.azurerm_kubernetes_cluster.this.kube_admin_config.0.client_key)
  cluster_ca_certificate = base64decode(data.azurerm_kubernetes_cluster.this.kube_admin_config.0.cluster_ca_certificate)
}

