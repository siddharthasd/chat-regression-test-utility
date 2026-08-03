###### common ######
airid                   = "308826"    #FIXME Input your AIR ID
aks_cluster_name        = "aks-30882601-66c-kubclusterprd"    #FIXME Input the AKS Cluster name
aks_resource_group_name = "rg-30882601-prd"    #FIXME Input the resource group name of the AKS Cluster
environment             = "prd" #Do Not Change
acr_name                = "acr30882601kubacrprd66c"    #FIXME Input your ACR Name
sub_environment         = "prod"    #OPTIONAL -Input your sub_environment name from the AKS Config to deploy to the namespace, leave empty to deploy to ns-<AIRID><ENV_CODE>

###### ingress ######
ssl_certificate  = "evalbrew.pfx"                                 #FIXME Input the name of the Secure File for the certificate - i.e. "mycertificate.pfx"
ssl_password     = "#{COMPUTE_SSLCERT_PASSWORD_PRD}#" #Do Not Change - This Key/Value needs to be in a variable group library
ingress_host     = "evalbrew.accenture.com"                                 #FIXME Input your host name - i.e. "myapp.ciodev.accenture.com"
ingress_name     = "ingress-evalbrew"                                 #FIXME Input your ingress name - i.e. "ingress-myapp"
certificate_name = "evalbrew"                                 #FIXME Input a name for the certificate
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
HARNESS_AZURE_TENANT_ID     = "#{HARNESS_AZURE_PRD_TENANT_ID}#"
HARNESS_AZURE_CLIENT_ID     = "#{HARNESS_AZURE_PRD_CLIENT_ID}#"
HARNESS_AZURE_CLIENT_SECRET = "#{HARNESS_AZURE_PRD_CLIENT_SECRET}#"
HARNESS_REDIRECT_URI        = "#{HARNESS_PRD_REDIRECT_URI}#"
HARNESS_SESSION_SECRET      = "#{HARNESS_PRD_SESSION_SECRET}#"
LOG_LEVEL                   = "debug"
HARNESS_PG_HOST             = "#{HARNESS_PRD_PG_HOST}#"
HARNESS_PG_USER             = "#{HARNESS_PRD_PG_USER}#"
HARNESS_PG_DB               = "#{HARNESS_PRD_PG_DB}#"
AZURE_CLIENT_ID             = "#{AZURE_PRD_CLIENT_ID}#"
HARNESS_DB_USE_MANAGED_IDENTITY = "true"
HARNESS_PG_USE_MANAGED_IDENTITY = "true"
harness_master_key          = "#{harness_master_key_prd}#"
