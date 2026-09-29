locals {
  # How the role shows up once assumed, minus the per-session suffix
  aws_billing_role = "arn:aws:sts::${var.aws_account_id}:assumed-role/${var.aws_role_name}"
}

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

# A destroyed pool keeps its id for 30 days, a new suffix lets apply run right after a destroy
resource "random_id" "aws_billing_pool" {
  byte_length = 3
}

resource "google_iam_workload_identity_pool" "aws_billing" {
  workload_identity_pool_id = "aws-billing-${random_id.aws_billing_pool.hex}"
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

  attribute_condition = "attribute.aws_role == '${local.aws_billing_role}'"
}
