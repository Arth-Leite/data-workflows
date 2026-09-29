output "fast_api_hello_url" {
  description = "Public URL of the FastAPI service. Only reachable from var.my_ip."
  value       = "http://${kubernetes_service_v1.fast_api_hello.status[0].load_balancer[0].ingress[0].ip}"
}

# For gcloud iam workload-identity-pools create-cred-config, the pool id changes on each apply after a destroy
output "aws_billing_wif_provider" {
  value = google_iam_workload_identity_pool_provider.aws.name
}

output "cluster_name" {
  value = google_container_cluster.gke.name
}

output "cluster_location" {
  value = google_container_cluster.gke.location
}
