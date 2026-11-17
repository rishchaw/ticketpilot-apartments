variable "region" {
  type    = string
  default = "ap-southeast-1"
}

variable "image_uri" {
  type        = string
  description = "Built ECR image URI with an immutable sha256 digest."
  validation {
    condition     = can(regex("@sha256:[a-f0-9]{64}$", var.image_uri))
    error_message = "Use the immutable ECR image digest returned by the build."
  }
}

variable "enable_bedrock" {
  type    = bool
  default = false
}

variable "bedrock_model_id" {
  type    = string
  default = "amazon.nova-micro-v1:0"
  validation {
    condition     = !strcontains(var.bedrock_model_id, "/") && !strcontains(var.bedrock_model_id, "*")
    error_message = "Use a regional foundation-model ID, not an ARN, wildcard or inference profile."
  }
}

variable "bedrock_region" {
  type        = string
  default     = "ap-southeast-2"
  description = "Nova Micro supports direct in-region inference in Sydney. Singapore requires a cross-region inference profile."
}

variable "reserved_concurrency" {
  type        = number
  default     = -1
  description = "-1 uses account concurrency. New accounts may not allow a reservation; set 1 or 2 only when the regional quota permits."
  validation {
    condition     = contains([-1, 0, 1, 2, 3, 4, 5], var.reserved_concurrency)
    error_message = "Use -1, 0 to disable invocations, or 1 through 5."
  }
}

variable "protect_ticket_data" {
  type    = bool
  default = true
}


variable "paused" {
  type        = bool
  default     = false
  description = "Disable Lambda invocations with zero reserved concurrency while retaining data, secrets and images. Storage charges may remain."
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
  description = "Zero makes manager refresh manual, avoiding background Lambda invocations and repeated database reads."
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
