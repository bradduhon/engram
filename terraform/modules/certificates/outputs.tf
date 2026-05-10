# Copyright (c) 2026 Engram Contributors. All Rights Reserved.
# Licensed under the MIT License. See LICENSE for details.

output "server_cert_arn" {
  description = "ARN of the server ACM certificate -- used by Phase 4 API Gateway custom domain"
  value       = aws_acm_certificate_validation.server.certificate_arn
}

output "client_cert_arn" {
  description = "ARN of the exportable client ACM certificate -- used by Phase 3 cert rotator IAM, Phase 7 hook setup"
  value       = aws_acm_certificate_validation.client.certificate_arn
}

output "client_cert_secret_arn" {
  description = "ARN of the client cert bundle Secrets Manager secret -- used by Phase 3 Lambda IAM, Phase 5 MCP server"
  value       = aws_secretsmanager_secret.client_cert.arn
}

output "client_cert_passphrase_secret_arn" {
  description = "ARN of the client cert passphrase Secrets Manager secret -- used by Phase 3 Lambda IAM, Phase 5 MCP server"
  value       = aws_secretsmanager_secret.client_cert_passphrase.arn
}

# DNS validation records to add manually to your hosted zone.
# Both certs use DNS validation. Add these CNAMEs before running
# terraform apply again -- aws_acm_certificate_validation blocks until ISSUED.
output "server_cert_validation_records" {
  description = "CNAME records to add to your DNS zone to validate the server certificate"
  value = {
    for dvo in aws_acm_certificate.server.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }
}

output "client_cert_validation_records" {
  description = "CNAME records to add to your DNS zone to validate the client certificate"
  value = {
    for dvo in aws_acm_certificate.client.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }
}
