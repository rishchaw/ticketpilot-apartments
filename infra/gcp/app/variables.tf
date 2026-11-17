variable "project_id" {
  type        = string
  description = "Existing Google Cloud project used by the GCP bootstrap root."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a Google Cloud project ID."
  }
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

variable "image_uri" {
  type        = string
  description = "Built Dockerfile.gcp image in the regional Artifact Registry repository, pinned by digest."
  validation {
    condition     = can(regex("^[a-z0-9-]+-docker\\.pkg\\.dev/[a-z0-9-]+/ticketpilot-apartments/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$", var.image_uri))
    error_message = "Use an immutable TicketPilot Artifact Registry image digest."
  }
}

variable "admin_secret_id" {
  type    = string
  default = "ticketpilot-apartments-admin"
}

variable "metrics_secret_id" {
  type    = string
  default = "ticketpilot-apartments-metrics"
}

variable "manage_database" {
  type        = bool
  default     = false
  description = "Set true only after confirming that the selected Firestore database does not already exist. Existing databases must be left unmodified or deliberately imported."
}

variable "firestore_database_id" {
  type        = string
  default     = "(default)"
  description = "Use the first/free-tier-eligible database; do not create an additional named database merely for this application."
}

variable "memory" {
  type    = string
  default = "512Mi"
  validation {
    condition     = contains(["512Mi", "1Gi"], var.memory)
    error_message = "Use 512Mi after constrained runtime validation, or 1Gi if required."
  }
}

variable "protect_service" {
  type    = bool
  default = true
}

variable "apartment_name" {
  type    = string
  default = "Our Apartment"
}

variable "apartment_units" {
  type    = string
  default = "1,2,3,4,5,6,7,8"
}

variable "manager_refresh_seconds" {
  type        = number
  default     = 0
  description = "Zero makes manager refresh manual; this avoids background Cloud Run requests and repeated Firestore reads during a portfolio demo."
  validation {
    condition     = var.manager_refresh_seconds == 0 || (var.manager_refresh_seconds >= 30 && var.manager_refresh_seconds <= 3600 && floor(var.manager_refresh_seconds) == var.manager_refresh_seconds)
    error_message = "Use 0 or a whole number of seconds from 30 through 3600."
  }
}

variable "queue_limit" {
  type    = number
  default = 20
  validation {
    condition     = var.queue_limit >= 1 && var.queue_limit <= 200 && floor(var.queue_limit) == var.queue_limit
    error_message = "Use a whole queue limit from 1 through 200."
  }
}

variable "paused" {
  type        = bool
  default     = false
  description = "Temporarily disable request serving using manual scaling at zero; retain data, secrets and image."
}
