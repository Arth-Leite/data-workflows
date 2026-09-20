terraform {
  required_version = ">= 1.16.3"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }
}

provider "google" {
  region  = var.region
  project = var.project_id
}

resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_compute_network" "gke_vpc" {
  name                    = "dataops-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.compute]
}

# IP ranges per GKE recommendation: https://cloud.google.com/kubernetes-engine/docs/how-to/alias-ips#defaults_for_automatically_created_subnets
resource "google_compute_subnetwork" "gke_nodes" {
  name = "gke-nodes-europe-west1"

  ip_cidr_range = "10.0.0.0/20"
  region        = var.region
  network       = google_compute_network.gke_vpc.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.4.0.0/14"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.8.0.0/20"
  }

}
