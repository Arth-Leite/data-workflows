# Already enabled by the container API, declared to make the dependency explicit
resource "google_project_service" "logging" {
  project            = var.project_id
  service            = "logging.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "bigquery" {
  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudquotas" {
  project            = var.project_id
  service            = "cloudquotas.googleapis.com"
  disable_on_destroy = false
}

# Approximative cap on BQ spending
resource "google_cloud_quotas_quota_preference" "bigquery_query_per_day" {
  parent   = "projects/${var.project_id}"
  name     = "bigquery-query-usage-per-day"
  service  = "bigquery.googleapis.com"
  quota_id = "QueryUsagePerDay"

  quota_config {
    # It will fit on the BQ free tier of 1 TiB/month
    preferred_value = 10 * 1024 # 10GiB
  }

  # Default is 200 TiB/day, the API refuses decreases this large without it
  ignore_safety_checks = "QUOTA_DECREASE_PERCENTAGE_TOO_HIGH"
  justification        = "Cost cap for the case study"

  depends_on = [google_project_service.cloudquotas, google_project_service.bigquery]
}

resource "google_bigquery_dataset" "api_billing" {
  project     = var.project_id
  dataset_id  = "api_billing"
  location    = var.region
  description = "FastAPI request logs used for billing"

  # In production it would be false, but here I will keep it
  delete_contents_on_destroy = true

  depends_on = [google_project_service.bigquery]
}

resource "google_logging_project_sink" "api_billing" {
  project     = var.project_id
  name        = "api-billing-to-bigquery"
  destination = "bigquery.googleapis.com/${google_bigquery_dataset.api_billing.id}"

  filter = <<-EOT
    resource.type="k8s_container"
    resource.labels.cluster_name="${google_container_cluster.gke.name}"
    resource.labels.namespace_name="default"
    resource.labels.container_name="fast-api-hello"
    jsonPayload.method:*
  EOT

  bigquery_options {
    use_partitioned_tables = true
  }

  depends_on = [google_project_service.logging]
}

# Hours are Europe/Paris, start inclusive, end exclusive
resource "google_bigquery_table" "prices" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.api_billing.dataset_id
  table_id   = "prices"

  view {
    use_legacy_sql = false
    query          = <<-EOT
      SELECT * FROM UNNEST([
        STRUCT(0 AS start_hour, 8 AS end_hour, 1 AS price_cents),
        (8, 20, 5),
        (20, 24, 2)
      ])
    EOT
  }

  deletion_protection = false
}
