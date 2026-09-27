resource "google_project_service" "sqladmin" {
  project            = var.project_id
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_sql_database_instance" "main" {
  name             = "dataops-db"
  region           = var.region
  database_version = "POSTGRES_18"

  # In production we would have it, but for this case-study I will remove it
  deletion_protection = false

  settings {
    # Cheapest setup : shared-core, single zone, small HDD.
    edition           = "ENTERPRISE"
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_type         = "PD_HDD"
    disk_size         = 10
    disk_autoresize   = false

    # same as google_container_cluster.gke
    location_preference {
      zone = local.node_zones[0]
    }

    ip_configuration {
      ipv4_enabled       = false # private IP only
      private_network    = google_compute_network.gke_vpc.id
      allocated_ip_range = google_compute_global_address.cloudsql_psa.name
      ssl_mode           = "TRUSTED_CLIENT_CERTIFICATE_REQUIRED" # reject clients without a valid cert from the connector
    }

    connector_enforcement = "REQUIRED" # reject certs not freshly issued via IAM on this connection

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on" # required for the CLOUD_IAM_SERVICE_ACCOUNT users below to authenticate
    }

    database_flags {
      name  = "log_connections"
      value = "on" # log every connection attempt
    }

    database_flags {
      name  = "log_disconnections"
      value = "on" # log every session end, with duration
    }
  }

  depends_on = [google_project_service.sqladmin, google_service_networking_connection.cloudsql]
}

resource "google_sql_database" "app" {
  name     = "users_db"
  instance = google_sql_database_instance.main.name

  # Skip Terraform's own DROP DATABASE (fails if tables/connections still exist) since the whole instance is deleted anyway
  deletion_policy = "ABANDON"
}

# DB Users

resource "google_sql_user" "app" {
  name     = trimsuffix(google_service_account.fast_api_hello.email, ".gserviceaccount.com")
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
  # no roles, basic DML

  deletion_policy = "ABANDON"
}

# Schema owner, used only by the db-migrate job
resource "google_sql_user" "migrator" {
  name           = trimsuffix(google_service_account.db_migrator.email, ".gserviceaccount.com")
  instance       = google_sql_database_instance.main.name
  type           = "CLOUD_IAM_SERVICE_ACCOUNT"
  database_roles = ["cloudsqlsuperuser"]

  deletion_policy = "ABANDON"
}
