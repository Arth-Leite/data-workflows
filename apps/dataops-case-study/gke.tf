locals {
  # Being explicit rather than read from data.google_compute_zones
  node_zones = ["europe-west1-b", "europe-west1-c", "europe-west1-d"]
}

resource "google_container_cluster" "gke" {
  name = "dataops-cluster"

  # cheaper to run on a zone instead of region
  location = local.node_zones[0]

  network    = google_compute_network.gke_vpc.id
  subnetwork = google_compute_subnetwork.gke_nodes.id

  remove_default_node_pool = true
  initial_node_count       = 1

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  deletion_protection = false

  depends_on = [google_project_service.container, google_compute_subnetwork.gke_nodes]
}

resource "google_container_node_pool" "gke" {
  name    = "cheap-as-possible-pool"
  cluster = google_container_cluster.gke.id

  node_locations = local.node_zones
  # node_count is per zone, so this provisions len(local.node_zones) nodes total
  node_count = 1

  # minimum on everything
  node_config {
    # e2-micro is the cheapest, but it is probably too small, e2-small is
    # likely necessary
    machine_type = "e2-micro"
    disk_size_gb = 12
    disk_type    = "pd-standard"
    spot         = true

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
  }
}
