locals {
  name = "ticketpilot-apartments"
  labels = {
    application = "ticketpilot-apartments"
    managed-by  = "terraform"
  }
  # Cloud Resource Manager is needed for project-scoped runtime IAM bindings.
  apis = toset(concat([
    "run.googleapis.com",
    "firestore.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ], var.create_budget ? ["billingbudgets.googleapis.com"] : []))
}

resource "google_project_service" "apis" {
  for_each                   = local.apis
  project                    = var.project_id
  service                    = each.key
  disable_on_destroy         = false
  disable_dependent_services = false
}

resource "google_artifact_registry_repository" "app" {
  project         = var.project_id
  location        = var.region
  repository_id   = local.name
  description     = "Portable TicketPilot application images"
  format          = "DOCKER"
  labels          = local.labels
  deletion_policy = var.protect_resources ? "PREVENT" : "DELETE"

  docker_config {
    # Deployments use digests. Mutable tags allow old tagged versions to be cleaned up.
    immutable_tags = false
  }

  vulnerability_scanning_config {
    enablement_config = "DISABLED"
  }

  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "delete-old-versions"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "604800s"
    }
  }
  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }
  cleanup_policies {
    id     = "keep-current-deployment"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["deployed"]
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "app" {
  for_each            = toset(["admin", "metrics"])
  project             = var.project_id
  secret_id           = "${local.name}-${each.key}"
  labels              = local.labels
  deletion_protection = var.protect_resources
  replication {
    auto {}
  }
  # Version values are uploaded outside Terraform and never enter this state.
  depends_on = [google_project_service.apis]
}

data "google_project" "target" {
  count      = var.create_budget ? 1 : 0
  project_id = var.project_id
  depends_on = [google_project_service.apis]
}

resource "google_billing_budget" "project_usage" {
  count           = var.create_budget ? 1 : 0
  billing_account = var.billing_account_id
  display_name    = "TicketPilot monthly usage alert before credits"
  budget_filter {
    projects               = ["projects/${data.google_project.target[0].number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
  }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_usd)
    }
  }
  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }
  # Default billing-account IAM recipients receive alerts. No notifications are sent by this configuration until thresholds are reached.
  lifecycle {
    precondition {
      condition     = var.billing_account_id != ""
      error_message = "Set billing_account_id locally before enabling the optional alerts-only budget."
    }
  }
  depends_on = [google_project_service.apis]
}

output "repository_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}
output "repository_name" {
  value = google_artifact_registry_repository.app.repository_id
}
output "admin_secret_id" {
  value = google_secret_manager_secret.app["admin"].secret_id
}
output "metrics_secret_id" {
  value = google_secret_manager_secret.app["metrics"].secret_id
}
output "budget_created" {
  value = var.create_budget
}
