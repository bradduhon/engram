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
  description = "Route53 hosted zone ID for creating the server domain A alias record. Optional -- omit if DNS is managed outside Route53; create the A record manually after apply."
  type        = string
  default     = null
}

variable "alert_email" {
  description = "Email address for SNS alarm notifications (requires manual confirmation after apply)"
  type        = string
}

variable "truststore_version" {
  description = "S3 object version ID of mtls/truststore.pem -- update after running export_client_cert.py to force API Gateway to reload the truststore"
  type        = string
  default     = null
}


