resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

# Our private network. Subnets are defined by hand instead of one per region
resource "google_compute_network" "gke_vpc" {
  name                    = "app-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.compute]
}

# IP ranges per GKE recommendation: https://cloud.google.com/kubernetes-engine/docs/how-to/alias-ips#defaults_for_automatically_created_subnets
resource "google_compute_subnetwork" "gke_nodes" {
  name = "gke-nodes-europe-west1"

  ip_cidr_range = "10.0.0.0/20"
  region        = var.region
  network       = google_compute_network.gke_vpc.id

  # GKE reserves /24 per node. So this will give us max 1024 nodes
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.4.0.0/14"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.8.0.0/20"
  }

  # Nodes have no public IP, so they need this to reach Google APIs (Artifact Registry, Cloud SQL Admin, Logging)
  private_ip_google_access = true
}

resource "google_project_service" "servicenetworking" {
  project            = var.project_id
  service            = "servicenetworking.googleapis.com"
  disable_on_destroy = false
}

# Reserve an IP range in the VPC to use with CloudSQL later
resource "google_compute_global_address" "cloudsql_psa" {
  name         = "cloudsql-psa"
  purpose      = "VPC_PEERING"
  address_type = "INTERNAL"
  network      = google_compute_network.gke_vpc.id
  # Ensure we don't overlap with the others
  address       = "10.16.0.0"
  prefix_length = 20
}

# Google wil build its side with the reserved range and peers it with my VPC.
resource "google_service_networking_connection" "cloudsql" {
  network                 = google_compute_network.gke_vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.cloudsql_psa.name]

  # ensure we can delete correctly
  deletion_policy = "REMOVE_PEERING"

  depends_on = [google_project_service.servicenetworking]
}
