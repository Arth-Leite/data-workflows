locals {
  fast_api_hello_image = "${google_artifact_registry_repository.images.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/fast-api-hello:latest"

  # auth is done with Workload Identity + Cloud SQL IAM auth
  db_env = {
    INSTANCE_CONNECTION_NAME = google_sql_database_instance.main.connection_name
    DB_NAME                  = google_sql_database.app.name
    DB_IAM_USER              = google_sql_user.app.name
  }
}

# Creates the schema and grants the API's user DML rights only. Idempotent, runs as the db-migrator identity.
resource "kubernetes_job_v1" "db_migrate" {
  metadata {
    name = "db-migrate"
  }

  spec {
    backoff_limit = 5

    template {
      metadata {
        labels = { app = "db-migrate" }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.db_migrator.metadata[0].name
        restart_policy       = "Never"

        container {
          name    = "db-migrate"
          image   = local.fast_api_hello_image
          command = ["python", "migrate_v1.py"]

          dynamic "env" {
            for_each = merge(local.db_env, { DB_MIGRATOR_USER = google_sql_user.migrator.name })
            content {
              name  = env.key
              value = env.value
            }
          }

          resources {
            requests = {
              cpu    = "25m"
              memory = "80Mi"
            }
            limits = {
              memory = "128Mi"
            }
          }
        }
      }
    }
  }

  wait_for_completion = true

  timeouts {
    create = "10m"
    update = "10m"
  }

  depends_on = [
    google_container_node_pool.gke,
    google_sql_database.app,
    google_sql_user.app,
    google_project_iam_member.fast_api_hello_cloudsql_client,
    google_project_iam_member.fast_api_hello_cloudsql_instance_user,
    google_project_iam_member.db_migrator_cloudsql_client,
    google_project_iam_member.db_migrator_cloudsql_instance_user,
    google_service_account_iam_member.fast_api_hello_workload_identity,
    google_service_account_iam_member.db_migrator_workload_identity,
  ]
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
        service_account_name = kubernetes_service_account_v1.fast_api_hello.metadata[0].name

        container {
          name  = "fast-api-hello"
          image = local.fast_api_hello_image

          port {
            container_port = 8000
          }

          dynamic "env" {
            for_each = local.db_env
            content {
              name  = env.key
              value = env.value
            }
          }

          resources {
            requests = {
              cpu    = "25m"
              memory = "80Mi"
            }
            limits = {
              memory = "128Mi"
            }
          }

          readiness_probe {
            http_get {
              path = "/healthz"
              port = 8000
            }
            initial_delay_seconds = 3
            period_seconds        = 5
          }

          liveness_probe {
            http_get {
              path = "/healthz"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 15
          }
        }
      }
    }
  }

  # The table and grants must exist before the API serves /users
  depends_on = [google_container_node_pool.gke, kubernetes_job_v1.db_migrate]
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

  lifecycle {
    # Added by GKE's load balancer controller, not managed here
    ignore_changes = [metadata[0].annotations["networking.gke.io/target-pool"]]
  }
}
