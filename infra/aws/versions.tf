terraform {
  required_version = ">= 1.6, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = "ticketpilot-aws", ManagedBy = "Terraform" } }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
