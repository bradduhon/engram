terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Backend config supplied via backend.hcl (gitignored):
  #   terraform init -backend-config=backend.hcl
  # See backend.hcl.example for required keys.
  backend "s3" {
    key     = "engram/terraform.tfstate"
    encrypt = true
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project   = "engram"
      ManagedBy = "terraform"
    }
  }
}
