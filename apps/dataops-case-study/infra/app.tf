locals {
  fast_api_hello_image = "${google_artifact_registry_repository.images.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/fast-api-hello:latest"
}

resource "kubernetes_deployment_v1" "fast_api_hello" {
  metadata {
    name   = "fast-api-hello"
    labels = { app = "fast-api-hello" }
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "fast-api-hello" }
    }

    template {
      metadata {
        labels = { app = "fast-api-hello" }
      }

      spec {
        container {
          name  = "fast-api-hello"
          image = local.fast_api_hello_image

          port {
            container_port = 8000
          }

          resources {
            requests = {
              cpu    = "50m"
              memory = "64Mi"
            }
            limits = {
              memory = "128Mi"
            }
          }
          
          readiness_probe {
            http_get {
              path = "/"
              port = 8000
            }
            initial_delay_seconds = 3
            period_seconds        = 5
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 15
          }
        }
      }
    }
  }

  depends_on = [google_container_node_pool.gke]
}

resource "kubernetes_service_v1" "fast_api_hello" {
  metadata {
    name = "fast-api-hello"
  }

  spec {
    type     = "LoadBalancer"
    selector = { app = "fast-api-hello" }

    port {
      port        = 80
      target_port = 8000
    }

    # Q3: expose to your IP only.
    load_balancer_source_ranges = [var.my_ip]
  }
}
