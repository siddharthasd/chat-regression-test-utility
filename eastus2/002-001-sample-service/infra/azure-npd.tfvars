###### common ######
airid                   = "308826"    #FIXME Input your AIR ID
aks_cluster_name        = "aks-30882602-80a-kubclusterstg"    #FIXME Input the AKS Cluster name
aks_resource_group_name = "rg-30882602-stg"    #FIXME Input the resource group name of the AKS Cluster
environment             = "npd" #Do Not Change
acr_name                = "acr30882602use280a"    #FIXME Input your ACR Name
sub_environment         = "stage"    #OPTIONAL -Input your sub_environment name from the AKS Config to deploy to the namespace, leave empty to deploy to ns-<AIRID><ENV_CODE>

###### ingress ######
ssl_certificate  = "evalbrew.ciostage.pfx"                                 #FIXME Input the name of the Secure File for the certificate - i.e. "mycertificate.pfx"
ssl_password     = "#{COMPUTE_SSLCERT_PASSWORD_NPD}#" #Do Not Change - This Key/Value needs to be in a variable group library
ingress_host     = "evalbrew.ciostage.accenture.com"                                 #FIXME Input your host name - i.e. "myapp.ciodev.accenture.com"
ingress_name     = "ingress-evalbrew"                                 #FIXME Input your ingress name - i.e. "ingress-myapp"
certificate_name = "evalbrew.ciostage"                                 #FIXME Input a name for the certificate
proxy_buffering   = "on"
proxy_buffer_size = "30k"
backend_protocol  = "HTTPS"

###### service ######
api_1             = "evalbrewrelease"   #FIXME Input the name of the docker image repo in the ACR
api_1_port        = 8443 #FIXME Input the port for the healthcheck, 8443 is default
healthcheck_api_1 = "/health"  # Public probe path (no auth); see harness.ui /health
replicas          = 1    #FIXME Input the number of replicas (pods)
max_replicas      = 2    #FIXME Input the maximum replicas (pods) for autoscaling
target_cpu        = 80   #FIXME Input the target CPU for autoscaling

##### configuration #####
HARNESS_AUTH_ENABLED        = "true"
HARNESS_AZURE_TENANT_ID     = "f3211d0e-125b-42c3-86db-322b19a65a22"
HARNESS_AZURE_CLIENT_ID     = "#{HARNESS_AZURE_CLIENT_ID}#"
HARNESS_AZURE_CLIENT_SECRET = "#{HARNESS_AZURE_CLIENT_SECRET}#"
HARNESS_REDIRECT_URI        = "https://evalbrew.ciostage.accenture.com/auth/callback"
HARNESS_SESSION_SECRET      = "#{HARNESS_SESSION_SECRET}#"
LOG_LEVEL                   = "debug"
HARNESS_PG_HOST             = "azpgsvr-30882602-evalbrewharness.postgres.database.azure.com"
HARNESS_PG_USER             = "cio-cloud-azure-npd-308826-mi"
HARNESS_PG_DB               = "azpgdb-30882602-evalbrew"
AZURE_CLIENT_ID             = "#{AZURE_CLIENT_ID}#"
HARNESS_DB_USE_MANAGED_IDENTITY = "true"
