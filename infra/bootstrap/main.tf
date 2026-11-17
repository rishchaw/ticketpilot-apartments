terraform {
  required_version = ">= 1.6, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}

variable "region" {
  type    = string
  default = "ap-southeast-1"
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = "ticketpilot-aws", ManagedBy = "Terraform" } }
}

resource "aws_ecr_repository" "app" {
  name                 = "ticketpilot-aws"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = false }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({ rules = [{
    rulePriority = 1
    description  = "Expire untagged build layers after one day"
    selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 1 }
    action       = { type = "expire" }
  }] })
}

output "repository_url" { value = aws_ecr_repository.app.repository_url }


# Billing is global; retain the Singapore default provider for ECR.
provider "aws" {
  alias  = "billing"
  region = "us-east-1"
  default_tags { tags = { Project = "ticketpilot-aws", ManagedBy = "Terraform" } }
}

variable "budget_alert_email" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Explicit local recipient for optional account-wide monthly usage alerts. Empty disables the budget; no recipient is inferred."
  validation {
    condition     = trimspace(var.budget_alert_email) == "" || can(regex("^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$", trimspace(var.budget_alert_email)))
    error_message = "Provide one email address, or leave empty to disable this optional budget."
  }
}

variable "monthly_target_usd" {
  type        = number
  default     = 10
  description = "Account-wide monthly unblended cost alert target before credits/refunds; this is not a spending cap."
  validation {
    condition     = var.monthly_target_usd > 0 && var.monthly_target_usd <= 100
    error_message = "Use a positive monthly alert target no greater than USD 100."
  }
}

resource "aws_budgets_budget" "monthly" {
  provider = aws.billing
  # Declassify only the presence boolean, never the email value itself.
  count        = nonsensitive(trimspace(var.budget_alert_email) != "") ? 1 : 0
  name         = "ticketpilot-aws-monthly-account-usage"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_target_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # No service/tag filters: alert on this account's gross spend before credits
  # and refunds. Billing data/notifications are delayed and cannot cap charges.
  cost_types {
    include_credit = false
    include_refund = false
    use_blended    = false
    use_amortized  = false
  }
  dynamic "notification" {
    for_each = [50, 90, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [trimspace(var.budget_alert_email)]
    }
  }
}

output "budget_enabled" {
  value = nonsensitive(trimspace(var.budget_alert_email) != "")
}
