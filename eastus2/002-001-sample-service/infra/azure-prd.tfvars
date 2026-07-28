###### common ######
airid                   = ""    #FIXME Input your AIR ID
aks_cluster_name        = ""    #FIXME Input the AKS Cluster name
aks_resource_group_name = ""    #FIXME Input the resource group name of the AKS Cluster
environment             = "prd" #Do Not Change
acr_name                = ""    #FIXME Input your ACR Name
sub_environment         = ""    #OPTIONAL -Input your sub_environment name from the AKS Config to deploy to the namespace, leave empty to deploy to ns-<AIRID><ENV_CODE>

###### ingress ######
ssl_certificate  = ""                                 #FIXME Input the name of the Secure File for the certificate - i.e. "mycertificate.pfx"
ssl_password     = "#{COMPUTE_SSLCERT_PASSWORD_PRD}#" #Do Not Change - This Key/Value needs to be in a variable group library
ingress_host     = ""                                 #FIXME Input your host name - i.e. "myapp.accenture.com"
ingress_name     = ""                                 #FIXME Input your ingress name - i.e. "ingress-myapp"
certificate_name = ""                                 #FIXME Input a name for the certificate

###### service ######
api_1             = ""   #FIXME Input the name of the docker image repo in the ACR
api_1_port        = 8443 #FIXME Input the port for the healthcheck, 8443 is default
healthcheck_api_1 = "/"  #FIXME Input the healthcheck path where the response is 200
replicas          = 1    #FIXME Input the number of replicas (pods)
max_replicas      = 1    #FIXME Input the maximum replicas (pods) for autoscaling
target_cpu        = 80   #FIXME Input the target CPU for autoscaling



