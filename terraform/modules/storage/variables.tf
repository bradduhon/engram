# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

variable "account_id" {
  description = "AWS account ID for bucket naming"
  type        = string
}

variable "vpc_endpoint_id" {
  description = "S3 Gateway Endpoint ID used in bucket policy to restrict access to VPC only"
  type        = string
}

variable "deployer_account_id" {
  description = "AWS account ID exempted from VPC-endpoint-only policy for Terraform applies and operational access"
  type        = string
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}
