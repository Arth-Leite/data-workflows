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

resource "google_bigquery_dataset" "api_billing" {
  project     = var.project_id
  dataset_id  = "api_billing"
  location    = var.region
  description = "FastAPI request logs used for billing"

  # In production it would be false, but here I will keep it
  delete_contents_on_destroy = true

  depends_on = [google_project_service.bigquery]
}
