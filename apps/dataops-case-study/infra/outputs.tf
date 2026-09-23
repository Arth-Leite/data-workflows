output "fast_api_hello_url" {
  description = "Public URL of the FastAPI service. Only reachable from var.my_ip."
  value       = "http://${kubernetes_service_v1.fast_api_hello.status[0].load_balancer[0].ingress[0].ip}"
}
