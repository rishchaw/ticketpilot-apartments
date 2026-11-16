locals {
  name = "ticketpilot-apartments"
  labels = {
    application = "ticketpilot-apartments"
    managed-by  = "terraform"
  }
  secret_env = {
    ADMIN_TOKEN   = var.admin_secret_id
    METRICS_TOKEN = var.metrics_secret_id
  }
  runtime_env = {
    STORAGE_MODE              = "firestore"
    GOOGLE_CLOUD_PROJECT      = var.project_id
    FIRESTORE_DATABASE        = var.firestore_database_id
    LLM_PROVIDER              = "none"
    APARTMENT_NAME            = var.apartment_name
    APARTMENT_UNITS           = var.apartment_units
    APARTMENT_REFRESH_SECONDS = tostring(var.manager_refresh_seconds)
    APARTMENT_QUEUE_LIMIT     = tostring(var.queue_limit)
    OPENBLAS_NUM_THREADS      = "1"
    OMP_NUM_THREADS           = "1"
  }
}

resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "ticketpilot-apartments-runtime"
  display_name = "TicketPilot apartment application runtime"
}

resource "google_project_iam_member" "firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each  = local.secret_env
  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_firestore_database" "tickets" {
  count                             = var.manage_database ? 1 : 0
  project                           = var.project_id
  name                              = var.firestore_database_id
  location_id                       = var.region
  type                              = "FIRESTORE_NATIVE"
  database_edition                  = "STANDARD"
  deletion_policy                   = "ABANDON"
  delete_protection_state           = "DELETE_PROTECTION_ENABLED"
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_DISABLED"
}

resource "google_cloud_run_v2_service" "app" {
  project             = var.project_id
  name                = local.name
  location            = var.region
  labels              = local.labels
  deletion_protection = var.protect_service
  ingress             = "INGRESS_TRAFFIC_ALL"

  # Service-wide maximum avoids a separate full allowance for each traffic revision.
  scaling {
    min_instance_count = 0
    max_instance_count = 1
  }

  template {
    labels                           = local.labels
    service_account                  = google_service_account.runtime.email
    timeout                          = "30s"
    max_instance_request_concurrency = 4
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image = var.image_uri
      ports {
        container_port = 8080
      }
      resources {
        limits            = { cpu = "1", memory = var.memory }
        cpu_idle          = true
        startup_cpu_boost = false
      }
      dynamic "env" {
        for_each = local.runtime_env
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 10
        timeout_seconds       = 3
        failure_threshold     = 12
        http_get {
          path = "/health"
        }
      }
    }
  }
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
  lifecycle {
    precondition {
      condition     = startswith(var.image_uri, "${var.region}-docker.pkg.dev/${var.project_id}/ticketpilot-apartments/")
      error_message = "Use an image from this project's same-region TicketPilot Artifact Registry repository."
    }
  }
  depends_on = [
    google_project_iam_member.firestore,
    google_secret_manager_secret_iam_member.runtime,
    google_firestore_database.tickets,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "service_url" {
  value = google_cloud_run_v2_service.app.uri
}
output "service_name" {
  value = google_cloud_run_v2_service.app.name
}
output "runtime_service_account" {
  value = google_service_account.runtime.email
}
output "firestore_database_id" {
  value = var.firestore_database_id
}

output "runtime_configuration" {
  value = {
    memory                  = var.memory
    min_instances           = 0
    max_instances           = 1
    manager_refresh_seconds = var.manager_refresh_seconds
    queue_limit             = var.queue_limit
    ai_enabled              = false
  }
}
