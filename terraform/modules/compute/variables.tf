# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

variable "vector_bucket_name" {
  description = "S3 Vectors bucket name for memory storage"
  type        = string
}

variable "vector_bucket_arn" {
  description = "S3 Vectors bucket ARN for memory storage"
  type        = string
}

variable "vector_index_name" {
  description = "S3 Vectors index name"
  type        = string
  default     = "memories"
}

variable "vpc_id" {
  description = "VPC ID -- used to create the Bedrock Interface Endpoint"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Lambda VPC config and Bedrock endpoint"
  type        = list(string)
}

variable "lambda_security_group_id" {
  description = "Lambda security group ID"
  type        = string
}

variable "bedrock_endpoint_security_group_id" {
  description = "Security group ID for the Bedrock Interface Endpoint"
  type        = string
}

variable "client_cert_arn" {
  description = "ACM exportable client certificate ARN (for cert rotator)"
  type        = string
}

variable "client_cert_secret_arn" {
  description = "Secrets Manager ARN for the cert bundle secret"
  type        = string
}

variable "client_cert_passphrase_secret_arn" {
  description = "Secrets Manager ARN for the cert passphrase secret"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "powertools_layer_version" {
  description = "AWS Lambda Powertools layer version number (extras variant, includes pydantic v2)"
  type        = number
  default     = 7
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
