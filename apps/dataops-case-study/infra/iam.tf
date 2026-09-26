locals {
  k8s_namespace = "default"
  # Referencing the cluster (not "<project>.svc.id.goog") so the bindings wait for Workload Identity to be enabled
  workload_pool = google_container_cluster.gke.workload_identity_config[0].workload_pool
}

# GCP Service accounts
resource "google_service_account" "fast_api_hello" {
  account_id   = "fast-api-hello"
  display_name = "GKE workload fast-api-hello"
}

resource "google_service_account" "db_migrator" {
  account_id   = "db-migrator"
  display_name = "GKE workload db-migrator"
}

# Project-level Cloud SQL roles
# client: connect to the instance through the connector/proxy
# instanceUser: log in to Postgres as the IAM user (see google_sql_user in database.tf)
resource "google_project_iam_member" "fast_api_hello_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.fast_api_hello.member
}

resource "google_project_iam_member" "fast_api_hello_cloudsql_instance_user" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = google_service_account.fast_api_hello.member
}

resource "google_project_iam_member" "db_migrator_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = google_service_account.db_migrator.member
}

resource "google_project_iam_member" "db_migrator_cloudsql_instance_user" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = google_service_account.db_migrator.member
}

# Workload Identity: let each K8s SA impersonate its GCP SA
resource "google_service_account_iam_member" "fast_api_hello_workload_identity" {
  service_account_id = google_service_account.fast_api_hello.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.workload_pool}[${local.k8s_namespace}/${kubernetes_service_account_v1.fast_api_hello.metadata[0].name}]"
}

resource "google_service_account_iam_member" "db_migrator_workload_identity" {
  service_account_id = google_service_account.db_migrator.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.workload_pool}[${local.k8s_namespace}/${kubernetes_service_account_v1.db_migrator.metadata[0].name}]"
}

# K8s SAs, annotated with the GCP SA their pods run as
resource "kubernetes_service_account_v1" "fast_api_hello" {
  metadata {
    name      = "fast-api-hello"
    namespace = local.k8s_namespace
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.fast_api_hello.email
    }
  }
}

resource "kubernetes_service_account_v1" "db_migrator" {
  metadata {
    name      = "db-migrator"
    namespace = local.k8s_namespace
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.db_migrator.email
    }
  }
}


resource "google_bigquery_dataset_iam_member" "sink_writer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.api_billing.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.api_billing.writer_identity
}
