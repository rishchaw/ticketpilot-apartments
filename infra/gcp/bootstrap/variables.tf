variable "project_id" {
  type        = string
  description = "Existing dedicated Google Cloud project with trial billing already linked."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a Google Cloud project ID, not its display name or project number."
  }
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

variable "protect_resources" {
  type        = bool
  default     = true
  description = "Protect the repository and secret metadata from accidental Terraform deletion."
}

variable "create_budget" {
  type        = bool
  default     = false
  description = "Create an optional project-wide alerts-only budget if the signed-in user has billing-budget permission. This is not a spend cap."
}

variable "billing_account_id" {
  type        = string
  default     = ""
  description = "Existing billing account ID for the optional budget; pass locally, never commit an account-specific value."
  validation {
    condition     = var.billing_account_id == "" || can(regex("(?i)^[0-9a-f]{6}-[0-9a-f]{6}-[0-9a-f]{6}$", var.billing_account_id))
    error_message = "Use the billing account ID in the form XXXXXX-XXXXXX-XXXXXX."
  }
}

variable "budget_amount_usd" {
  type    = number
  default = 10
  validation {
    condition     = var.budget_amount_usd >= 1 && var.budget_amount_usd <= 100 && floor(var.budget_amount_usd) == var.budget_amount_usd
    error_message = "Use a whole USD alert target from 1 through 100."
  }
}
