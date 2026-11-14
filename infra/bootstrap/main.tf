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
