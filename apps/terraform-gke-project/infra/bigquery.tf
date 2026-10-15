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

# Quota preferences can't be deleted, destroy only forgets it, so adopt the existing one
import {
  provider = google.billed_to_project
  to       = google_cloud_quotas_quota_preference.bigquery_query_per_day
  id       = "projects/${var.project_id}/locations/global/quotaPreferences/bigquery-query-usage-per-day"
}

# Approximative cap on BQ spending
resource "google_cloud_quotas_quota_preference" "bigquery_query_per_day" {
  provider = google.billed_to_project
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
  justification        = "Cost cap on BigQuery query usage"

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

# Normally created by the sink on the first log, declared so the billing_shared views can reference it
# Minimal schema, the sink adds the other LogEntry columns itself
resource "google_bigquery_table" "stdout" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.api_billing.dataset_id
  table_id   = "stdout"

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  schema = jsonencode([
    { name = "timestamp", type = "TIMESTAMP", mode = "NULLABLE" },
    {
      name = "jsonPayload", type = "RECORD", mode = "NULLABLE",
      fields = [
        { name = "method", type = "STRING", mode = "NULLABLE" },
        { name = "path", type = "STRING", mode = "NULLABLE" },
        # JSON numbers land as FLOAT
        { name = "status", type = "FLOAT", mode = "NULLABLE" },
      ]
    },
  ])

  deletion_protection = false

  lifecycle {
    # The sink extends the schema, removing columns would recreate the table
    ignore_changes = [schema]
  }
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

  # The table must exist before the sink writes, or the sink creates its own and the apply fails
  depends_on = [google_project_service.logging, google_bigquery_table.stdout]
}

# Dates and hours are Europe/Paris, start inclusive, end exclusive
# A price change closes the current rows' valid_to and adds new ones from that date
resource "google_bigquery_table" "prices" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.api_billing.dataset_id
  table_id   = "prices"

  view {
    use_legacy_sql = false
    query          = <<-EOT
      SELECT * FROM UNNEST([
        STRUCT(DATE '2026-01-01' AS valid_from, DATE '9999-12-31' AS valid_to, 0 AS start_hour, 8 AS end_hour, 1 AS price_cents),
        (DATE '2026-01-01', DATE '9999-12-31', 8, 20, 5),
        (DATE '2026-01-01', DATE '9999-12-31', 20, 24, 2)
      ])
    EOT
  }

  deletion_protection = false
}

# Only what the billing team needs, the raw logs in api_billing stay private
resource "google_bigquery_dataset" "billing_shared" {
  project     = var.project_id
  dataset_id  = "billing_shared"
  location    = var.region
  description = "Billing views shared with the AWS billing service"

  delete_contents_on_destroy = true

  depends_on = [google_project_service.bigquery]
}

# One row per request with the price in force, no pod names, labels or paths (they hold user ids)
resource "google_bigquery_table" "shared_requests" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.billing_shared.dataset_id
  table_id   = "requests"

  view {
    use_legacy_sql = false
    query          = <<-EOT
      SELECT
        r.timestamp,
        r.jsonPayload.method AS method,
        CAST(r.jsonPayload.status AS INT64) AS status,
        p.price_cents
      FROM `${var.project_id}.${google_bigquery_table.stdout.dataset_id}.${google_bigquery_table.stdout.table_id}` r
      LEFT JOIN `${var.project_id}.${google_bigquery_table.prices.dataset_id}.${google_bigquery_table.prices.table_id}` p
        ON DATE(r.timestamp, 'Europe/Paris') >= p.valid_from
        AND DATE(r.timestamp, 'Europe/Paris') < p.valid_to
        AND EXTRACT(HOUR FROM r.timestamp AT TIME ZONE 'Europe/Paris') >= p.start_hour
        AND EXTRACT(HOUR FROM r.timestamp AT TIME ZONE 'Europe/Paris') < p.end_hour
    EOT
  }

  deletion_protection = false
}

resource "google_bigquery_table" "shared_prices" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.billing_shared.dataset_id
  table_id   = "prices"

  view {
    use_legacy_sql = false
    query          = "SELECT * FROM `${var.project_id}.${google_bigquery_table.prices.dataset_id}.${google_bigquery_table.prices.table_id}`"
  }

  deletion_protection = false
}

# Views in billing_shared can read api_billing, their readers can't
resource "google_bigquery_dataset_access" "api_billing_shared" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.api_billing.dataset_id

  dataset {
    dataset {
      project_id = var.project_id
      dataset_id = google_bigquery_dataset.billing_shared.dataset_id
    }
    target_types = ["VIEWS"]
  }

  # Both edit the api_billing ACL, run them one after the other
  depends_on = [google_bigquery_dataset_iam_member.sink_writer]
}
