# Copyright (c) 2026 Brad Duhon. All Rights Reserved.
# Confidential and Proprietary.
# Unauthorized copying of this file is strictly prohibited.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "memory_handler_function_name" {
  description = "Memory handler Lambda function name -- used in CloudWatch alarm dimensions"
  type        = string
}

variable "memory_handler_arn" {
  description = "Memory handler Lambda ARN -- target for the daily summarizer scheduler"
  type        = string
}

variable "cert_rotator_arn" {
  description = "Cert rotator Lambda ARN -- target for the ACM cert expiry EventBridge rule"
  type        = string
}

variable "cert_rotator_function_name" {
  description = "Cert rotator Lambda function name -- used in Lambda resource-based policy"
  type        = string
}

variable "client_cert_arn" {
  description = "ACM client certificate ARN -- used to filter cert expiry events"
  type        = string
}

variable "alert_email" {
  description = "Email address for SNS alarm notifications (requires manual confirmation after apply)"
  type        = string
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
