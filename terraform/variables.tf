variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
}

variable "server_domain_name" {
  description = "FQDN for the API Gateway server certificate (e.g. memory.example.com)"
  type        = string
}

variable "client_domain_name" {
  description = "FQDN for the exportable mTLS client certificate (e.g. mcp-client.example.com)"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for creating the server domain A alias record"
  type        = string
}

