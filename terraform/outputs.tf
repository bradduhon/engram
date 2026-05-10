# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

output "custom_domain_target" {
  description = "DNS target for your server domain -- create an A or CNAME record pointing server_domain_name here"
  value       = module.api.custom_domain_target
}

output "custom_domain_url" {
  description = "Full HTTPS URL for the memory API"
  value       = module.api.custom_domain_url
}

output "server_cert_validation_records" {
  description = "CNAME records to add to DNS for ACM server certificate validation"
  value       = module.certificates.server_cert_validation_records
}

output "client_cert_validation_records" {
  description = "CNAME records to add to DNS for ACM client certificate validation"
  value       = module.certificates.client_cert_validation_records
}

output "client_cert_arn" {
  description = "ACM ARN of the exportable mTLS client certificate"
  value       = module.certificates.client_cert_arn
}
