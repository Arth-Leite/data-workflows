resource "google_project_service" "iam" {
  project            = var.project_id
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "sts" {
  project            = var.project_id
  service            = "sts.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iamcredentials" {
  project            = var.project_id
  service            = "iamcredentials.googleapis.com"
  disable_on_destroy = false
}

resource "google_iam_workload_identity_pool" "aws_billing" {
  workload_identity_pool_id = "aws-billing"
  display_name              = "AWS billing orchestrator"
  description               = "Lets the AWS billing service query BigQuery without a service account key"

  depends_on = [google_project_service.iam, google_project_service.sts]
}

# Trusts only requests signed by this AWS account
resource "google_iam_workload_identity_pool_provider" "aws" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.aws_billing.workload_identity_pool_id
  workload_identity_pool_provider_id = "aws-billing-account"
  display_name                       = "AWS billing account"

  aws {
    account_id = var.aws_account_id
  }
}
