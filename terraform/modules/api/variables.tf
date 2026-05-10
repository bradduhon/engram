# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "server_cert_arn" {
  description = "ACM server certificate ARN for the custom domain TLS configuration"
  type        = string
}

variable "truststore_s3_uri" {
  description = "S3 URI of the mTLS truststore PEM (e.g. s3://engram-artifacts-.../mtls/truststore.pem)"
  type        = string
}

variable "truststore_version" {
  description = "S3 object version ID of the truststore PEM. Update after running export_client_cert.py to force API Gateway to reload."
  type        = string
  default     = null
}

variable "lambda_invoke_arn" {
  description = "Memory handler Lambda invoke ARN for API Gateway integration"
  type        = string
}

variable "lambda_function_name" {
  description = "Memory handler Lambda function name for the resource-based policy"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for the server domain A alias record. Optional -- set to null to skip record creation."
  type        = string
  default     = null
}

variable "server_domain_name" {
  description = "FQDN for the API Gateway custom domain (must match the server certificate)"
  type        = string
}

variable "api_log_retention_days" {
  description = "CloudWatch log retention for API Gateway access logs"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
